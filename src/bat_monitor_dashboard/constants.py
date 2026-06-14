import locale
import os
import re
import time
from pathlib import Path

APP_NAME = "BatMonitorDashboard"
DEFAULT_GEOMETRY = {"x": 40, "y": 40, "w": 560, "h": 280}
DISCORD_STATUS_TITLE = "交易監控主機狀態"
DISCORD_CHART_TITLE = "交易監控即時狀態"
DISCORD_FOOTER_TEXT = f"{APP_NAME} 會編輯同一則 Webhook 訊息，避免洗版"
ANSI_PATTERN = re.compile(r"\x1b(?:\[[0-?]*[ -~]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|[@-Z\\-_])")
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x07\x0b\x0c\x0e-\x1f\x7f]")


def user_config_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
    else:
        base = Path.home() / "AppData" / "Local"
    return base / APP_NAME / "config.json"


def console_encoding() -> str:
    return locale.getpreferredencoding(False) or "cp950"


def task_id() -> str:
    return f"task-{int(time.time() * 1000)}"
