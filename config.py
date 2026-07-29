"""集中管理所有設定值。

本模組是整個專案唯一呼叫 load_dotenv() 與 os.getenv() 的地方，
其他模組一律 `import config` 後直接使用型別化常數。
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    """取得必填設定，缺少時直接讓程式啟動失敗（早失敗優於半殘執行）。"""
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f".env 缺少必要設定：{key}（可參考 .env.example）")
    return value.strip()


def _require_int(key: str) -> int:
    raw = _require(key)
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f".env 設定 {key} 必須是數字（目前值：{raw}）") from None


def _optional_int(key: str) -> int | None:
    raw = os.getenv(key)
    if not raw or not raw.strip():
        return None
    try:
        return int(raw.strip())
    except ValueError:
        raise RuntimeError(f".env 設定 {key} 必須是數字（目前值：{raw}）") from None


# === 必填 ===
DISCORD_TOKEN: str = _require("DISCORD_TOKEN")
CATEGORY_ID: int = _require_int("CATEGORY_ID")
ADMIN_ROLE_ID: int = _require_int("ADMIN_ROLE_ID")

# === 選填 ===
GUILD_ID: int | None = _optional_int("GUILD_ID")
DB_PATH: str = os.getenv("DB_PATH", "data/channels.db").strip()
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").strip().upper()

# === 業務常數 ===
MAX_TEXT_CHANNELS = 3
MAX_VOICE_CHANNELS = 1

ARCHIVE_PREFIX = "🗑已廢棄-"
ARCHIVE_NOTICE = "🗑 此頻道已廢棄"

# Discord 硬性限制
CHANNEL_NAME_LIMIT = 100
CATEGORY_CHANNEL_LIMIT = 50
OVERWRITE_LIMIT = 500
OVERWRITE_SAFE_LIMIT = 495  # 留 5 個緩衝，接近上限就擋下 /add
