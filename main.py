"""進入點：Bot 子類別、setup_hook 自動載入 cog、tree sync、全域錯誤處理。"""

import logging
import pathlib
import sys
import traceback

import discord
from discord import app_commands
from discord.ext import commands

import config
import database

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format=LOG_FORMAT,
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logging.getLogger("discord.http").setLevel(logging.WARNING)
logging.getLogger("discord.gateway").setLevel(logging.WARNING)

logger = logging.getLogger("aocafe")

SLASH_DIR = pathlib.Path(__file__).parent / "slash"


class AoCafeBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True  # 解析成員、display_name、成員清單需要
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def _load_extensions(self) -> None:
        loaded, failed = 0, 0
        for path in sorted(SLASH_DIR.rglob("*.py")):
            if path.name.startswith("_"):
                continue
            module_parts = path.relative_to(SLASH_DIR.parent).with_suffix("").parts
            dotted = ".".join(module_parts)
            try:
                await self.load_extension(dotted)
                logger.info("已載入 extension：%s", dotted)
                loaded += 1
            except Exception:
                logger.error(
                    "載入 extension 失敗：%s\n%s", dotted, traceback.format_exc()
                )
                failed += 1
        logger.info("extension 載入完成：成功 %d 個，失敗 %d 個", loaded, failed)

    async def setup_hook(self) -> None:
        database.init_db()

        await self._load_extensions()

        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info("已同步 %d 個指令到測試伺服器 %s（秒生效）", len(synced), config.GUILD_ID)
        else:
            synced = await self.tree.sync()
            logger.info("已全域同步 %d 個指令（最長可能需要 1 小時生效）", len(synced))

    async def on_ready(self) -> None:
        logger.info("已登入：%s (ID: %s)", self.user, self.user.id if self.user else "?")
        logger.info("目前所在伺服器數：%d", len(self.guilds))

    async def close(self) -> None:
        database.close_db()
        await super().close()


bot = AoCafeBot()


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    if isinstance(error, app_commands.CommandOnCooldown):
        msg = f"指令冷卻中，請於 {error.retry_after:.0f} 秒後再試。"
    elif isinstance(error, app_commands.MissingPermissions):
        msg = "你沒有執行這個指令的權限。"
    elif isinstance(error, app_commands.NoPrivateMessage):
        msg = "這個指令只能在伺服器中使用。"
    elif isinstance(error, app_commands.CheckFailure):
        msg = "你不符合執行這個指令的條件。"
    elif isinstance(error, app_commands.CommandInvokeError) and isinstance(
        error.original, discord.Forbidden
    ):
        msg = "機器人權限不足，請確認機器人擁有「管理頻道」與「管理身分組」權限，且身分組位置夠高。"
    else:
        msg = "指令執行時發生未預期的錯誤，已記錄，請聯絡管理員。"

    logger.error(
        "指令錯誤 /%s by %s：%s",
        getattr(interaction.command, "name", "unknown"),
        interaction.user,
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
    )

    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except discord.HTTPException:
        pass


def main() -> None:
    bot.run(config.DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
