import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
import utils

logger = logging.getLogger("aocafe.create")


class CreateChannelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="create", description="建立一個屬於你的私人頻道")
    @app_commands.describe(
        type="要建立文字頻道還是語音頻道",
        name="頻道名稱（不填則自動命名）",
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name="文字頻道", value="text"),
            app_commands.Choice(name="語音頻道", value="voice"),
        ]
    )
    @app_commands.guild_only()
    async def create(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str],
        name: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        assert guild is not None
        member = interaction.user
        assert isinstance(member, discord.Member)
        is_voice = type.value == "voice"

        category = guild.get_channel(config.CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.followup.send(
                "設定錯誤：找不到指定的頻道分類，請聯絡管理員檢查 CATEGORY_ID。",
                ephemeral=True,
            )
            return

        bot_member = guild.me
        perms = category.permissions_for(bot_member)
        if not (perms.manage_channels and perms.manage_permissions):
            await interaction.followup.send(
                "機器人在該分類沒有「管理頻道／管理身分組」權限，無法建立頻道。",
                ephemeral=True,
            )
            return

        text_count = await utils.count_live_channels(guild, member.id, "text")
        voice_count = await utils.count_live_channels(guild, member.id, "voice")

        if is_voice and voice_count >= config.MAX_VOICE_CHANNELS:
            await interaction.followup.send(
                f"你已經有 {config.MAX_VOICE_CHANNELS} 個語音頻道了，請先用 /delete 廢棄後再建立。",
                ephemeral=True,
            )
            return
        if not is_voice and text_count >= config.MAX_TEXT_CHANNELS:
            await interaction.followup.send(
                f"你已經有 {config.MAX_TEXT_CHANNELS} 個文字頻道了，請先用 /delete 廢棄其中一個再建立。",
                ephemeral=True,
            )
            return

        if len(category.channels) >= config.CATEGORY_CHANNEL_LIMIT:
            await interaction.followup.send(
                "頻道分類已達 Discord 上限（50 個頻道），請聯絡管理員清理已廢棄的頻道。",
                ephemeral=True,
            )
            return

        base_name = utils.sanitize_channel_name(name or utils.default_channel_name(member), is_voice)
        final_name = utils.resolve_name_conflict(category, base_name, is_voice)
        overwrites = utils.base_overwrites(guild, member, bot_member, is_voice)

        try:
            if is_voice:
                channel = await category.create_voice_channel(
                    name=final_name,
                    overwrites=overwrites,
                    reason=f"/create by {member} ({member.id})",
                )
            else:
                channel = await category.create_text_channel(
                    name=final_name,
                    overwrites=overwrites,
                    reason=f"/create by {member} ({member.id})",
                )
        except discord.Forbidden:
            await interaction.followup.send(
                "機器人權限不足，無法建立頻道（請確認機器人身分組位置足夠高）。",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            logger.exception("建立頻道時發生 HTTP 錯誤")
            await interaction.followup.send(
                "Discord API 回應錯誤，請稍後再試。", ephemeral=True
            )
            return

        try:
            db.add_channel(channel.id, guild.id, member.id, type.value, final_name)
        except Exception:
            logger.exception("資料庫寫入失敗，回滾已建立的頻道 %s", channel.id)
            try:
                await channel.delete(reason="資料庫寫入失敗，回滾")
            except discord.HTTPException:
                pass
            await interaction.followup.send(
                "資料庫寫入失敗，已取消建立，請聯絡管理員。", ephemeral=True
            )
            return

        new_text = text_count + (0 if is_voice else 1)
        new_voice = voice_count + (1 if is_voice else 0)
        await interaction.followup.send(
            f"已建立你的私人頻道 {channel.mention}！\n"
            f"目前使用：文字 {new_text}/{config.MAX_TEXT_CHANNELS}、"
            f"語音 {new_voice}/{config.MAX_VOICE_CHANNELS}\n"
            f"用 /add 把朋友加進來吧。",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(CreateChannelCog(bot))
