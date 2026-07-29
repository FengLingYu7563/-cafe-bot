"""共用邏輯：管理員判定、統一守衛、overwrite 建構、額度、名稱、位置、embed。

集中在這裡是為了讓 5 支指令共用同一份守衛與錯誤文案，避免各 cog 各自重複判斷。
不可放在 slash/ 底下，否則會被 main.py 的自動載入器當成 extension 載入而失敗。
"""

import re

import discord

import config
import database as db


# ---------- 管理員判定 ----------

def is_admin(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(role.id == config.ADMIN_ROLE_ID for role in member.roles)


def can_manage(member: discord.Member, record) -> bool:
    return record["owner_id"] == member.id or is_admin(member)


# ---------- 統一守衛 ----------

class GuardError(Exception):
    """帶著中文訊息的守衛失敗，cog 統一 except 後直接回覆訊息內容。"""


async def guard_managed_channel(
    interaction: discord.Interaction,
    channel: discord.abc.GuildChannel | None,
    *,
    require_active: bool = True,
):
    """檢查目標頻道是否為本機器人管理的私人頻道，且呼叫者有權限操作。

    回傳 (channel, record) tuple；任何條件不符會拋出 GuardError。
    """
    guild = interaction.guild
    assert guild is not None  # 已由 @app_commands.guild_only() 保證

    if channel is None:
        raw = interaction.channel
        if raw is None:
            raise GuardError("找不到目標頻道，請指定一個頻道。")
        resolved = guild.get_channel(raw.id)
        if resolved is None:
            raise GuardError("找不到目標頻道，請指定一個頻道。")
        channel = resolved

    if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
        raise GuardError("只能對文字或語音頻道使用這個指令。")

    record = db.get_channel(channel.id)
    if record is None:
        raise GuardError("這個頻道不是由機器人建立的私人頻道，無法操作。")

    member = interaction.user
    assert isinstance(member, discord.Member)
    if not can_manage(member, record):
        raise GuardError("只有頻道建立者或管理員可以執行這個操作。")

    if require_active and record["archived"]:
        raise GuardError("這個頻道已被廢棄，無法再進行操作。")

    return channel, record


# ---------- overwrite 建構 ----------

def member_allow_overwrite(is_voice: bool) -> discord.PermissionOverwrite:
    overwrite = discord.PermissionOverwrite(view_channel=True)
    if is_voice:
        overwrite.connect = True
        overwrite.speak = True
    return overwrite


def base_overwrites(
    guild: discord.Guild,
    owner: discord.Member,
    bot_member: discord.Member,
    is_voice: bool,
) -> dict:
    return {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        bot_member: discord.PermissionOverwrite(
            view_channel=True,
            manage_channels=True,
            manage_permissions=True,
            send_messages=True,
        ),
        owner: member_allow_overwrite(is_voice),
    }


def archived_overwrites(guild: discord.Guild, bot_member: discord.Member) -> dict:
    """廢棄頻道的權限：只留 @everyone 拒看 + bot 自己的存取權，一次 PATCH 清空所有成員覆寫。"""
    return {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        bot_member: discord.PermissionOverwrite(
            view_channel=True,
            manage_channels=True,
            manage_permissions=True,
        ),
    }


# ---------- 額度 ----------

async def count_live_channels(guild: discord.Guild, owner_id: int, channel_type: str) -> int:
    """回傳實際仍存在於 Discord 的未廢棄頻道數，順手清掉已被真刪除的殘留紀錄。"""
    channel_ids = db.count_active_channels(guild.id, owner_id, channel_type)
    live_count = 0
    for channel_id in channel_ids:
        if guild.get_channel(channel_id) is None:
            db.delete_channel_record(channel_id)
        else:
            live_count += 1
    return live_count


# ---------- 名稱 ----------

def default_channel_name(member: discord.Member) -> str:
    return f"{member.display_name}的頻道"


def sanitize_channel_name(raw: str, is_voice: bool) -> str:
    name = raw.strip()
    if not is_voice:
        # 文字頻道名稱會被 Discord 強制正規化：轉小寫、空白換成 '-'、移除不合法字元
        name = name.lower()
        name = re.sub(r"\s+", "-", name)
        name = re.sub(r"[^\w一-鿿\-]", "", name)
        name = re.sub(r"-{2,}", "-", name).strip("-")
    if not name:
        name = "頻道" if is_voice else "channel"
    return name[: config.CHANNEL_NAME_LIMIT]


def resolve_name_conflict(category: discord.CategoryChannel, base: str, is_voice: bool) -> str:
    existing = {
        ch.name
        for ch in (category.voice_channels if is_voice else category.text_channels)
    }
    if base not in existing:
        return base
    suffix = 2
    while True:
        candidate = f"{base}-{suffix}"
        if not is_voice:
            candidate = sanitize_channel_name(candidate, is_voice)
        if len(candidate) > config.CHANNEL_NAME_LIMIT:
            overflow = len(candidate) - config.CHANNEL_NAME_LIMIT
            candidate = f"{base[:-overflow]}-{suffix}" if overflow < len(base) else candidate[: config.CHANNEL_NAME_LIMIT]
        if candidate not in existing:
            return candidate
        suffix += 1


def archived_name(original: str) -> str:
    prefix = config.ARCHIVE_PREFIX
    budget = config.CHANNEL_NAME_LIMIT - len(prefix)
    return f"{prefix}{original[:budget]}" if budget > 0 else prefix[: config.CHANNEL_NAME_LIMIT]


# ---------- 位置 ----------

def bottom_position(channel: discord.TextChannel | discord.VoiceChannel) -> int:
    category = channel.category
    if category is None:
        return channel.position
    siblings = (
        category.voice_channels
        if isinstance(channel, discord.VoiceChannel)
        else category.text_channels
    )
    positions = [ch.position for ch in siblings if ch.id != channel.id]
    return (max(positions) + 1) if positions else channel.position


# ---------- Embed ----------

def build_list_embeds(
    rows,
    *,
    is_admin_view: bool,
    max_text: int,
    max_voice: int,
    text_count: int,
    voice_count: int,
) -> list[discord.Embed]:
    embeds: list[discord.Embed] = []
    current = discord.Embed(
        title="私人頻道清單" if not is_admin_view else "伺服器私人頻道清單",
        color=discord.Color.blurple(),
    )
    field_count = 0

    for row in rows:
        archived_tag = "（🗑 已廢棄）" if row["archived"] else ""
        title = f"{row['name']}{archived_tag}"

        channel_mention = f"<#{row['channel_id']}>"

        member_ids = db.list_members(row["channel_id"])
        if member_ids:
            shown = member_ids[:20]
            member_text = " ".join(f"<@{uid}>" for uid in shown)
            if len(member_ids) > 20:
                member_text += f" …等 {len(member_ids)} 人"
        else:
            member_text = "（無）"

        lines = [f"頻道：{channel_mention}"]
        if is_admin_view:
            lines.append(f"建立者：<@{row['owner_id']}>")
        lines.append(f"成員（{len(member_ids)}）：{member_text}")

        if field_count >= 25:
            embeds.append(current)
            current = discord.Embed(
                title="私人頻道清單（續）",
                color=discord.Color.blurple(),
            )
            field_count = 0

        current.add_field(name=title, value="\n".join(lines), inline=False)
        field_count += 1

    if field_count > 0 or not embeds:
        embeds.append(current)

    if not is_admin_view:
        embeds[-1].set_footer(
            text=f"文字頻道 {text_count}/{max_text}　語音頻道 {voice_count}/{max_voice}"
        )
    else:
        embeds[-1].set_footer(text=f"共 {len(rows)} 個頻道")

    return embeds
