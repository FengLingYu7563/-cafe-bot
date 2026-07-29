import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
import utils

logger = logging.getLogger("aocafe.delete")


class DeleteChannelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="delete", description="廢棄一個私人頻道（不會真的刪除）🗑")
    @app_commands.describe(channel="要廢棄的頻道（不填則為你目前所在的頻道）")
    @app_commands.guild_only()
    async def delete(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | discord.VoiceChannel | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        try:
            resolved_channel, record = await utils.guard_managed_channel(
                interaction, channel, require_active=True
            )
        except utils.GuardError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return

        guild = interaction.guild
        assert guild is not None
        bot_member = guild.me
        original_name = record["name"]

        # 1. 先發公開廢棄公告——必須在關權限之前，否則清空覆寫後 bot 可能發不出訊息
        notice_sent = True
        try:
            await resolved_channel.send(config.ARCHIVE_NOTICE)
        except discord.HTTPException:
            logger.warning("廢棄公告發送失敗：channel_id=%s", resolved_channel.id)
            notice_sent = False

        # 2. 先寫 DB，確保即使後續 Discord API 失敗，狀態仍是已廢棄、不再佔額度
        db.archive_channel(resolved_channel.id, interaction.user.id)
        db.clear_members(resolved_channel.id)

        # 3. 一次 PATCH 同時清空成員權限並移到分類最底部
        try:
            await resolved_channel.edit(
                overwrites=utils.archived_overwrites(guild, bot_member),
                position=utils.bottom_position(resolved_channel),
                reason=f"/delete by {interaction.user} ({interaction.user.id})",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "機器人權限不足，無法修改這個頻道的權限與位置（頻道已在資料庫中標記為廢棄）。",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            logger.exception("廢棄頻道權限/位置變更失敗：channel_id=%s", resolved_channel.id)
            await interaction.followup.send(
                "Discord API 回應錯誤，權限變更可能未完全生效，請稍後用 /list 確認。",
                ephemeral=True,
            )
            return

        # 4. 最後才改名，獨立呼叫以避免改名的嚴格 rate limit（10 分鐘 2 次）卡住權限變更
        new_name = utils.archived_name(original_name)
        renamed = False
        rename_task = asyncio.create_task(
            resolved_channel.edit(
                name=new_name,
                reason=f"/delete by {interaction.user} ({interaction.user.id})",
            )
        )
        try:
            await asyncio.wait_for(asyncio.shield(rename_task), timeout=10.0)
            renamed = True
        except asyncio.TimeoutError:
            logger.info("改名逾時，將在背景繼續等待完成：channel_id=%s", resolved_channel.id)
        except discord.HTTPException:
            logger.warning("改名失敗：channel_id=%s", resolved_channel.id)

        if renamed:
            await interaction.followup.send(
                f"已廢棄頻道 #{original_name}。成員已全部失去存取權（包含你自己），僅管理員可見。"
                + ("" if notice_sent else "\n（公告訊息發送失敗）"),
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"已廢棄頻道 #{original_name}，權限已收回。\n"
                "頻道改名遇到 Discord 限制（每個頻道 10 分鐘內只能改名 2 次），改名會在稍後自動完成。"
                + ("" if notice_sent else "\n（公告訊息發送失敗）"),
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(DeleteChannelCog(bot))
