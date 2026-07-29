import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
import utils


class ListChannelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="listch", description="查看你建立的私人頻道與成員名單")
    @app_commands.guild_only()
    async def list_channels(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        assert guild is not None
        member = interaction.user
        assert isinstance(member, discord.Member)

        admin_view = utils.is_admin(member)

        if admin_view:
            rows = db.list_all_channels(guild.id, include_archived=False)
        else:
            rows = db.list_channels_by_owner(guild.id, member.id, include_archived=False)

        # 清理已被管理員真刪除、但 DB 仍有紀錄的殘留
        live_rows = []
        for row in rows:
            if guild.get_channel(row["channel_id"]) is None:
                db.delete_channel_record(row["channel_id"])
                continue
            live_rows.append(row)
        rows = live_rows

        if not rows:
            if admin_view:
                await interaction.followup.send(
                    "目前伺服器沒有由機器人管理的私人頻道。", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "你目前沒有建立任何私人頻道，可以用 /create 建立一個。", ephemeral=True
                )
            return

        text_count = await utils.count_live_channels(guild, member.id, "text")
        voice_count = await utils.count_live_channels(guild, member.id, "voice")

        embeds = utils.build_list_embeds(
            rows,
            is_admin_view=admin_view,
            max_text=config.MAX_TEXT_CHANNELS,
            max_voice=config.MAX_VOICE_CHANNELS,
            text_count=text_count,
            voice_count=voice_count,
        )

        await interaction.followup.send(embeds=embeds[:10], ephemeral=True)
        for extra in embeds[10:]:
            await interaction.followup.send(embeds=[extra], ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ListChannelCog(bot))
