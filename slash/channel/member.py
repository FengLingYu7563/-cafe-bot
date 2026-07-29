import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
import utils

logger = logging.getLogger("aocafe.member")


class ChannelMemberCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="add", description="把成員加進你的私人頻道")
    @app_commands.describe(member="要加入的成員", channel="目標頻道（不填則為你目前所在的頻道）")
    @app_commands.guild_only()
    async def add(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
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

        if member.bot:
            await interaction.followup.send("不能把機器人加入頻道。", ephemeral=True)
            return

        if member.id == record["owner_id"]:
            await interaction.followup.send(
                f"{member.display_name} 是這個頻道的建立者，本來就看得到。", ephemeral=True
            )
            return

        if db.is_member(resolved_channel.id, member.id):
            await interaction.followup.send(
                f"{member.display_name} 已經在這個頻道裡了。", ephemeral=True
            )
            return

        if len(resolved_channel.overwrites) >= config.OVERWRITE_SAFE_LIMIT:
            await interaction.followup.send(
                "這個頻道的權限覆寫數量已接近 Discord 上限（500），無法再加人。",
                ephemeral=True,
            )
            return

        is_voice = isinstance(resolved_channel, discord.VoiceChannel)
        try:
            await resolved_channel.set_permissions(
                member,
                overwrite=utils.member_allow_overwrite(is_voice),
                reason=f"/add by {interaction.user} ({interaction.user.id})",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "機器人權限不足，無法修改這個頻道的權限。", ephemeral=True
            )
            return

        db.add_member(resolved_channel.id, member.id, interaction.user.id)

        await interaction.followup.send(
            f"已將 {member.mention} 加入 {resolved_channel.mention}。",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="remove", description="把成員移出你的私人頻道")
    @app_commands.describe(member="要移除的成員", channel="目標頻道（不填則為你目前所在的頻道）")
    @app_commands.guild_only()
    async def remove(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
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

        if member.id == record["owner_id"]:
            await interaction.followup.send(
                "不能移除頻道建立者。如果要關閉頻道請使用 /delete。", ephemeral=True
            )
            return

        if not db.is_member(resolved_channel.id, member.id):
            await interaction.followup.send(
                f"{member.display_name} 不在這個頻道的成員名單中。", ephemeral=True
            )
            return

        try:
            await resolved_channel.set_permissions(
                member,
                overwrite=None,
                reason=f"/remove by {interaction.user} ({interaction.user.id})",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "機器人權限不足，無法修改這個頻道的權限。", ephemeral=True
            )
            return

        if isinstance(resolved_channel, discord.VoiceChannel):
            if member.voice and member.voice.channel and member.voice.channel.id == resolved_channel.id:
                try:
                    await member.move_to(None, reason="已被移出私人語音頻道")
                except discord.HTTPException:
                    logger.warning("移除語音成員時無法斷線：%s", member.id)

        db.remove_member(resolved_channel.id, member.id)

        await interaction.followup.send(
            f"已將 {member.display_name} 移出 {resolved_channel.mention}。",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelMemberCog(bot))
