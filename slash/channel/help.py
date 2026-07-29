import discord
from discord import app_commands
from discord.ext import commands

HELP_TEXT = (
    "指令說明（`<>` 內為必填參數；`{}` 內為選填參數，不填則使用預設值）\n\n"
    "建立一個屬於你的私人頻道。\n"
    "`/create <文字頻道|語音頻道> {頻道名稱}`\n\n"
    "刪除一個私人頻道。\n"
    "`/delete {頻道}`\n\n"
    "把成員加進你的私人頻道。\n"    
    "`/add <成員> {頻道}`\n\n"
    "把成員移出你的私人頻道。\n"
    "`/remove <成員> {頻道}`\n\n"
    "查看你建立的頻道與成員名單。\n"
    "`/listch`\n"
)


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="查看所有指令的用法說明")
    async def help(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(HELP_TEXT, ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
