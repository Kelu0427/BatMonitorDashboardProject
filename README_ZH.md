# BAT 監控儀表板

[English README](README.md)

![BAT Monitor Dashboard](docs/images/dashboard-overview.png)

**BAT 監控儀表板** 是一個 Windows 桌面工具，用來集中監控多個 `.bat` 任務。它可以即時顯示輸出、管理每個任務面板的位置與大小、監控主機狀態，並透過 Discord Webhook 更新同一則狀態訊息，避免洗版。

## 示範影片

[觀看示範影片](https://github.com/Kelu0427/BatMonitorDashboardProject/releases/download/v0.2.3/batmonitor-promo.mp4)

## 功能亮點

- 多任務 BAT 監控：新增、編輯、刪除、啟動、停止、重啟。
- 面板式工作區：每個任務都有可拖曳、可調整大小的輸出面板。
- 即時輸出清理：支援 ANSI 控制碼過濾，並改善 Vue / Node / `npm run serve` 進度列輸出。
- 編碼可調整：支援 `utf-8`、`cp950`、`big5`、系統預設。
- 系統狀態：心跳、CPU、記憶體、系統碟、開機時間、任務數、網路流量。
- Discord 通知：可設定 Webhook、通知標題、回傳間隔，並編輯同一則訊息。
- 定時維運：可設定每日固定時間全部停止後重新啟動。
- 安全停止：使用 `taskkill /T /F` 終止完整 process tree。

## 畫面預覽

| 設定介面 | 任務編輯 |
| --- | --- |
| ![Settings dialog](docs/images/settings-dialog.png) | ![Task dialog](docs/images/task-dialog.png) |

## Discord 通知示意

![Discord notification mock](docs/images/discord-notification-mock.png)

## 安裝與執行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## 打包成 EXE

```powershell
pyinstaller BatMonitorDashboard.spec
```

輸出位置：

```text
dist\BatMonitorDashboard.exe
```

## 設定檔位置

設定會儲存在：

```text
%LOCALAPPDATA%\BatMonitorDashboard\config.json
```

GUI 內可按「設定」→「開啟設定檔位置」快速打開。

## 專案結構

```text
BatMonitorDashboardProject/
  main.py
  BatMonitorDashboard.spec
  requirements.txt
  assets/
  docs/images/
  tools/generate_readme_images.py
  src/bat_monitor_dashboard/
    app.py
    constants.py
    models.py
    dialogs.py
    panel.py
    dashboard.py
```
