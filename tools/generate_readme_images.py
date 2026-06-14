from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "images"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path(r"C:\Windows\Fonts\msjhbd.ttc" if bold else r"C:\Windows\Fonts\msjh.ttc"),
        Path(r"C:\Windows\Fonts\NotoSansCJK-Regular.ttc"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


FONT_10 = font(10)
FONT_11 = font(11)
FONT_12 = font(12)
FONT_13 = font(13)
FONT_14 = font(14)
FONT_16 = font(16)
FONT_16_B = font(16, True)
FONT_18_B = font(18, True)
FONT_22_B = font(22, True)


def text(draw: ImageDraw.ImageDraw, xy, value: str, fill="#e6edf3", fnt=FONT_12) -> None:
    draw.text(xy, value, fill=fill, font=fnt)


def rounded(draw: ImageDraw.ImageDraw, box, fill, outline=None, radius=8, width=1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def button(draw: ImageDraw.ImageDraw, box, label: str, active=False) -> None:
    fill = "#1f6feb" if active else "#26313d"
    rounded(draw, box, fill, "#3a4654", radius=5)
    x1, y1, x2, y2 = box
    bbox = draw.textbbox((0, 0), label, font=FONT_12)
    text(draw, (x1 + (x2 - x1 - (bbox[2] - bbox[0])) / 2, y1 + 7), label, "#e6edf3", FONT_12)


def draw_terminal(draw: ImageDraw.ImageDraw, box, lines, title: str, running=True) -> None:
    x1, y1, x2, y2 = box
    rounded(draw, box, "#151a20", "#30363d", radius=8)
    text(draw, (x1 + 14, y1 + 12), title, "#f4fbff", FONT_13)
    text(draw, (x2 - 330, y1 + 12), "執行中" if running else "已停止", "#8bd3ff", FONT_12)
    labels = ["編輯", "啟動", "停止", "重啟", "清空"]
    bx = x2 - 280
    for idx, label in enumerate(labels):
        button(draw, (bx + idx * 52, y1 + 8, bx + idx * 52 + 44, y1 + 36), label, active=label == "啟動" and running)

    term = (x1 + 12, y1 + 48, x2 - 12, y2 - 12)
    rounded(draw, term, "#05070a", "#26313d", radius=3)
    yy = term[1] + 12
    for line in lines:
        text(draw, (term[0] + 12, yy), line, "#b7f7c1", FONT_12)
        yy += 20


def dashboard_overview() -> None:
    image = Image.new("RGB", (1440, 860), "#0b0f14")
    draw = ImageDraw.Draw(image)

    rounded(draw, (0, 0, 1440, 42), "#171b21", radius=0)
    toolbar = ["新增", "編輯", "刪除", "全部啟動", "全部停止", "全部重啟", "儲存版面", "整理版面", "設定"]
    x = 16
    for label in toolbar:
        w = 58 if len(label) <= 2 else 92
        button(draw, (x, 7, x + w, 34), label)
        x += w + 10

    rounded(draw, (0, 42, 230, 860), "#111418", "#30363d", radius=0)
    text(draw, (18, 62), "監控任務", "#8bd3ff", FONT_16_B)
    for idx, name in enumerate(["台股-前端", "台股-API", "策略排程"]):
        y = 102 + idx * 54
        fill = "#1f6feb" if idx == 0 else "#0d1117"
        rounded(draw, (14, y, 214, y + 38), fill, "#30363d", radius=6)
        text(draw, (28, y + 9), name, "#e6edf3", FONT_13)

    rounded(draw, (246, 54, 1418, 126), "#151a20", "#30363d", radius=8)
    text(draw, (266, 48), "系統狀態", "#8bd3ff", FONT_13)
    metrics = [
        ("心跳", "2026-06-14 15:42:08"),
        ("CPU", "18.4%"),
        ("記憶體", "43.7% (13.8/31.6 GB)"),
        ("系統碟", "61.2% 使用，剩餘 186.5 GB"),
        ("開機時間", "2 天 4 小時 18 分"),
        ("監控任務", "3/3 執行中"),
        ("網路", "↑ 1248 MB / ↓ 9621 MB"),
        ("Discord", "啟用"),
    ]
    for idx, (label, value) in enumerate(metrics):
        col = idx % 4
        row = idx // 4
        mx = 266 + col * 286
        my = 76 + row * 28
        text(draw, (mx, my), label, "#c9d1d9", FONT_12)
        text(draw, (mx + 74, my), value, "#b7f7c1", FONT_12)

    draw_terminal(
        draw,
        (246, 146, 828, 418),
        [
            r"[dashboard] 啟動：C:\Trading\Run_Frontend.bat",
            "Frontend: http://192.168.0.235:8081",
            "> vue-cli-service serve --host 192.168.0.235 --port 8081",
            "INFO  Starting development server...",
            "DONE  Compiled successfully in 6292ms",
            "App running at: http://192.168.0.235:8081/",
        ],
        "台股-前端",
    )
    draw_terminal(
        draw,
        (846, 146, 1418, 418),
        [
            r"[dashboard] 啟動：C:\Trading\Run_API.bat",
            "INFO: Started server process [18240]",
            "INFO: Application startup complete.",
            "INFO: Uvicorn running on http://192.168.0.235:8000",
        ],
        "台股-API",
    )
    draw_terminal(
        draw,
        (246, 438, 1418, 808),
        [
            r"[dashboard] 啟動：C:\Trading\Run_Worker.bat",
            "2026-06-14 15:41:55 [scheduler] market heartbeat ok",
            "2026-06-14 15:42:00 [strategy] positions synced",
            "2026-06-14 15:42:05 [risk] exposure within limits",
            "2026-06-14 15:42:08 [discord] status message updated",
        ],
        "策略排程",
    )

    image.save(OUT_DIR / "dashboard-overview.png")


def settings_dialog() -> None:
    image = Image.new("RGB", (760, 420), "#111418")
    draw = ImageDraw.Draw(image)
    rounded(draw, (24, 24, 736, 396), "#151a20", "#30363d", radius=8)
    text(draw, (50, 48), "設定", "#f4fbff", FONT_18_B)

    rows = [
        ("每日定時全部重啟", "☑"),
        ("重啟時間", "05:00"),
        ("啟用 Discord 狀態更新", "☑"),
        ("Discord 通知標題", "交易監控主機狀態"),
        ("Webhook URL", "https://discord.com/api/webhooks/..."),
        ("Discord 回傳間隔", "5 分鐘"),
    ]
    y = 92
    for label, value in rows:
        text(draw, (62, y + 8), label, "#c9d1d9", FONT_13)
        rounded(draw, (260, y, 690, y + 34), "#0d1117", "#30363d", radius=5)
        text(draw, (274, y + 8), value, "#e6edf3", FONT_13)
        y += 44

    button(draw, (386, 344, 480, 376), "開啟設定檔")
    button(draw, (500, 344, 584, 376), "儲存", active=True)
    button(draw, (602, 344, 686, 376), "取消")
    image.save(OUT_DIR / "settings-dialog.png")


def task_dialog() -> None:
    image = Image.new("RGB", (760, 360), "#111418")
    draw = ImageDraw.Draw(image)
    rounded(draw, (24, 24, 736, 336), "#151a20", "#30363d", radius=8)
    text(draw, (50, 48), "編輯監控任務", "#f4fbff", FONT_18_B)
    rows = [
        ("任務名稱", "台股-前端"),
        ("BAT 路徑", r"C:\Trading\Run_Frontend.bat"),
        ("工作目錄", r"C:\Trading\frontend"),
        ("保留最近行數", "3000"),
        ("輸出編碼", "utf-8"),
        ("啟動儀表板時自動執行", "☑"),
    ]
    y = 92
    for label, value in rows:
        text(draw, (62, y + 8), label, "#c9d1d9", FONT_13)
        rounded(draw, (260, y, 690, y + 34), "#0d1117", "#30363d", radius=5)
        text(draw, (274, y + 8), value, "#e6edf3", FONT_13)
        y += 38
    button(draw, (500, 286, 584, 318), "儲存", active=True)
    button(draw, (602, 286, 686, 318), "取消")
    image.save(OUT_DIR / "task-dialog.png")


def discord_mock() -> None:
    image = Image.new("RGB", (1120, 760), "#313338")
    draw = ImageDraw.Draw(image)
    rounded(draw, (42, 38, 1078, 722), "#2b2d31", radius=8)
    rounded(draw, (70, 66, 142, 138), "#1e1f22", radius=36)
    text(draw, (89, 91), "BM", "#23a559", FONT_22_B)
    text(draw, (164, 72), "BatMonitorDashboard", "#f2f3f5", FONT_16_B)
    text(draw, (350, 75), "BOT  Today at 15:42", "#949ba4", FONT_11)

    rounded(draw, (164, 124, 170, 594), "#23a559", radius=3)
    rounded(draw, (176, 124, 1012, 594), "#2f3136", radius=8)
    text(draw, (202, 154), "交易監控主機狀態", "#f2f3f5", FONT_18_B)
    text(draw, (202, 188), "正常 - Windows 11", "#dbdee1", FONT_13)

    fields = [
        ("心跳", "2026-06-14 15:42:08"),
        ("主機", "TRADING-HOST-01"),
        ("狀態", "正常"),
        ("CPU", "18.4%"),
        ("記憶體", "43.7%\n13.8/31.6 GB"),
        ("系統碟", "61.2% 使用\n剩餘 186.5 GB"),
        ("監控任務", "3/3 執行中"),
        ("開機時間", "2 天 4 小時 18 分"),
        ("累計網路", "↑ 1248 MB / ↓ 9621 MB"),
    ]
    x_positions = [202, 470, 738]
    for idx, (name, value) in enumerate(fields):
        x = x_positions[idx % 3]
        y = 238 + (idx // 3) * 92
        text(draw, (x, y), name, "#f2f3f5", FONT_12)
        text(draw, (x, y + 24), value, "#dbdee1", FONT_11)

    text(draw, (202, 548), "BatMonitorDashboard 會編輯同一則 Webhook 訊息，避免洗版", "#949ba4", FONT_10)
    text(draw, (70, 682), "示意圖：實際通知會依照目前主機狀態與設定標題更新。", "#dbdee1", FONT_12)
    image.save(OUT_DIR / "discord-notification-mock.png")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dashboard_overview()
    settings_dialog()
    task_dialog()
    discord_mock()
    print(f"Generated README images in {OUT_DIR}")


if __name__ == "__main__":
    main()
