import locale
import os
import re
import sys
import time
from pathlib import Path

APP_NAME = "BatMonitorDashboard"
APP_VERSION = "0.3.3"
GITHUB_PROFILE_URL = "https://github.com/Kelu0427"
GITHUB_REPOSITORY_URL = "https://github.com/Kelu0427/BatMonitorDashboardProject"
GITHUB_LATEST_RELEASE_API = "https://api.github.com/repos/Kelu0427/BatMonitorDashboardProject/releases/latest"
RELEASE_ASSET_NAME = "BatMonitorDashboard.exe"
DEFAULT_GEOMETRY = {"x": 40, "y": 40, "w": 560, "h": 280}
DEFAULT_LOG_MAX_MB = 20
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


def resource_path(relative_path: str) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base_path / relative_path
