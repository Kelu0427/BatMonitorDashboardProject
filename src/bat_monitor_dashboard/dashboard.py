import json
import platform
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import psutil
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QRect, QSize, Qt, QTime, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QFont, QIcon, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMdiArea,
    QMdiSubWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QTimeEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .constants import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_GEOMETRY,
    DEFAULT_LOG_MAX_MB,
    DISCORD_STATUS_TITLE,
    GITHUB_LATEST_RELEASE_API,
    GITHUB_REPOSITORY_URL,
    RELEASE_ASSET_NAME,
    TEXT_COLOR_OPTIONS,
    resource_path,
    user_config_path,
)
from .dialogs import AppSettingsDialog, DiscordSettingsDialog, TaskDialog
from .models import MonitorTask
from .panel import MonitorPanel


class DashboardSignals(QObject):
    discord_message_id_changed = Signal(str)
    update_available = Signal(object)
    update_current = Signal(str)
    update_progress = Signal(object)
    update_downloaded = Signal(str, str)
    update_failed = Signal(str, bool)


class DashboardWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_path = user_config_path()
        self.tasks: List[MonitorTask] = []
        self.panels: Dict[str, MonitorPanel] = {}
        self.windows: Dict[str, QMdiSubWindow] = {}
        self.last_restart_key = ""
        self.restart_times = ["05:00"]
        self.sidebar_collapsed = False
        self.theme_name = "dark"
        self.text_color_name = "default"
        self.layout_mode = "grid_2"
        self.auto_update_enabled = True
        self.update_checking = False
        self.updating_now = False
        self.update_progress_dialog: Optional[QProgressDialog] = None
        self.active_settings_dialog: Optional[QDialog] = None
        self.pending_update_source: Optional[Path] = None
        self.pending_update_target: Optional[Path] = None
        self.log_memory_enabled = True
        self.log_max_mb = DEFAULT_LOG_MAX_MB
        self.discord_enabled = False
        self.discord_status_title = DISCORD_STATUS_TITLE
        self.discord_webhook_url = ""
        self.discord_interval_minutes = 5
        self.discord_message_id = ""
        self.last_discord_sent_at = 0.0
        self.discord_sending = False
        self.latest_metrics: Dict = {}
        self.signals = DashboardSignals()
        self.signals.discord_message_id_changed.connect(self._store_discord_message_id)
        self.signals.update_available.connect(self._handle_update_available)
        self.signals.update_current.connect(self._handle_update_current)
        self.signals.update_progress.connect(self._handle_update_progress)
        self.signals.update_downloaded.connect(self._handle_update_downloaded)
        self.signals.update_failed.connect(self._handle_update_failed)

        self.setWindowTitle("BAT 監控儀表板")
        self.resize(1280, 760)

        self.task_list = QListWidget()
        self.task_list.setMinimumWidth(0)
        self.task_list.setFixedWidth(230)
        self.task_list.currentItemChanged.connect(self._focus_selected_panel)
        self.sidebar_panel = self._build_sidebar()

        self.mdi = QMdiArea()
        self.mdi.setViewMode(QMdiArea.SubWindowView)

        self.metrics_box = self._build_metrics_box()
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        right_layout.addWidget(self.metrics_box)
        right_layout.addWidget(self.mdi, 1)

        splitter = QSplitter()
        splitter.addWidget(self.sidebar_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self.setCentralWidget(splitter)

        self.restart_enabled = QCheckBox("每日定時全部重啟")
        self.restart_time = QTimeEdit()
        self.restart_time.setDisplayFormat("HH:mm")

        self._build_toolbar()
        self.load_config()
        self._apply_style()
        self._apply_sidebar_state()
        self._refresh_task_list()
        self._create_panels()

        for task in self.tasks:
            if task.auto_start and task.task_id in self.panels:
                self.panels[task.task_id].start()

        self.schedule_timer = QTimer(self)
        self.schedule_timer.timeout.connect(self._check_restart_schedule)
        self.schedule_timer.start(15000)

        self.metrics_timer = QTimer(self)
        self.metrics_timer.timeout.connect(self._update_metrics)
        self.metrics_timer.start(5000)
        self._update_metrics()
        if self.auto_update_enabled:
            QTimer.singleShot(2500, self.check_for_updates)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("工具列")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        actions = [
            ("新增", self.add_task),
            ("編輯", self.edit_task),
            ("刪除", self.delete_task),
            ("全部啟動", self.start_all),
            ("全部停止", self.stop_all),
            ("全部重啟", self.restart_all),
            ("儲存版面", self.save_layout),
            ("整理版面", self.arrange_panels),
            ("設定", self.edit_app_settings),
        ]
        for label, handler in actions:
            action = QAction(label, self)
            action.triggered.connect(handler)
            toolbar.addAction(action)

        toolbar.addSeparator()
        self.sidebar_action = QAction("收合側欄", self)
        self.sidebar_action.triggered.connect(self.toggle_sidebar)
        toolbar.addAction(self.sidebar_action)

    def edit_app_settings(self) -> None:
        dialog = AppSettingsDialog(
            self,
            self.restart_enabled.isChecked(),
            self.restart_times,
            self.auto_update_enabled,
            self.theme_name,
            self.text_color_name,
            self.layout_mode,
            self.log_memory_enabled,
            self.log_max_mb,
            self.discord_enabled,
            self.discord_webhook_url,
            self.discord_interval_minutes,
            self.discord_status_title,
            self.open_config_folder,
            self.check_for_updates_manual,
            self.rollback_to_release,
        )
        self.active_settings_dialog = dialog
        try:
            accepted = dialog.exec() == QDialog.Accepted and dialog.result_settings
        finally:
            if self.active_settings_dialog is dialog:
                self.active_settings_dialog = None
        if accepted:
            old_webhook_url = self.discord_webhook_url
            self.restart_enabled.setChecked(dialog.result_settings["restart_enabled"])
            self.restart_times = dialog.result_settings["restart_times"]
            if self.restart_times:
                parsed_restart_time = QTime.fromString(self.restart_times[0], "HH:mm")
                if parsed_restart_time.isValid():
                    self.restart_time.setTime(parsed_restart_time)
            old_auto_update_enabled = self.auto_update_enabled
            self.auto_update_enabled = dialog.result_settings["auto_update_enabled"]
            old_theme_name = self.theme_name
            old_text_color_name = self.text_color_name
            old_layout_mode = self.layout_mode
            self.theme_name = dialog.result_settings["theme_name"]
            self.text_color_name = dialog.result_settings["text_color_name"]
            self.layout_mode = dialog.result_settings["layout_mode"]
            self.log_memory_enabled = dialog.result_settings["log_memory_enabled"]
            self.log_max_mb = dialog.result_settings["log_max_mb"]
            for task in self.tasks:
                task.log_max_mb = self.log_max_mb
            for panel in self.panels.values():
                panel.task.log_max_mb = self.log_max_mb
                panel.set_log_memory_enabled(self.log_memory_enabled)
            self.discord_enabled = dialog.result_settings["discord_enabled"]
            self.discord_status_title = dialog.result_settings["status_title"]
            self.discord_webhook_url = dialog.result_settings["webhook_url"]
            self.discord_interval_minutes = dialog.result_settings["interval_minutes"]
            if self.discord_webhook_url != old_webhook_url:
                self.discord_message_id = ""
            self.last_discord_sent_at = 0.0
            self.save_config()
            if self.theme_name != old_theme_name or self.text_color_name != old_text_color_name:
                self._apply_style()
            if self.layout_mode != old_layout_mode:
                self.arrange_panels()
            if self.auto_update_enabled and not old_auto_update_enabled:
                self.check_for_updates()
            self._update_metrics(force_discord=True)

    def _build_metrics_box(self) -> QGroupBox:
        box = QGroupBox("系統狀態")
        grid = QGridLayout(box)
        self.metric_labels: Dict[str, QLabel] = {}
        items = [
            ("heartbeat", "心跳"),
            ("cpu", "CPU"),
            ("memory", "記憶體"),
            ("disk", "系統碟"),
            ("uptime", "開機時間"),
            ("tasks", "監控任務"),
            ("network", "網路"),
            ("discord", "Discord"),
        ]
        for idx, (key, title) in enumerate(items):
            title_label = QLabel(title)
            value_label = QLabel("-")
            value_label.setObjectName("metricValue")
            self.metric_labels[key] = value_label
            row = idx // 4
            col = (idx % 4) * 2
            grid.addWidget(title_label, row, col)
            grid.addWidget(value_label, row, col + 1)
        return box

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.task_list, 1)
        layout.addWidget(self._build_sidebar_footer())
        sidebar.setFixedWidth(230)
        return sidebar

    def _build_sidebar_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("sidebarFooter")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)

        version_label = QLabel(f"v{APP_VERSION}")
        version_label.setObjectName("footerText")

        github_btn = QToolButton()
        github_btn.setObjectName("footerGitHubButton")
        github_icon = QIcon(str(resource_path("assets/github-mark.png")))
        if not github_icon.isNull():
            github_btn.setIcon(github_icon)
        github_btn.setIconSize(QSize(18, 18))
        github_btn.setAutoRaise(True)
        github_btn.setToolTip("開啟 GitHub 專案")
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_REPOSITORY_URL)))

        layout.addWidget(version_label)
        layout.addStretch(1)
        layout.addWidget(github_btn)
        return footer

    def edit_discord_settings(self) -> None:
        dialog = DiscordSettingsDialog(
            self,
            self.discord_enabled,
            self.discord_webhook_url,
            self.discord_interval_minutes,
            self.discord_status_title,
        )
        if dialog.exec() == QDialog.Accepted and dialog.result_settings:
            old_webhook_url = self.discord_webhook_url
            self.discord_enabled = dialog.result_settings["enabled"]
            self.discord_status_title = dialog.result_settings["status_title"]
            self.discord_webhook_url = dialog.result_settings["webhook_url"]
            self.discord_interval_minutes = dialog.result_settings["interval_minutes"]
            if self.discord_webhook_url != old_webhook_url:
                self.discord_message_id = ""
            self.last_discord_sent_at = 0.0
            self.save_config()
            self._update_metrics(force_discord=True)

    def toggle_sidebar(self) -> None:
        self.sidebar_collapsed = not self.sidebar_collapsed
        self._apply_sidebar_state()
        self.save_config()

    def _apply_sidebar_state(self) -> None:
        if self.sidebar_collapsed:
            self.sidebar_panel.setVisible(False)
            if hasattr(self, "sidebar_action"):
                self.sidebar_action.setText("展開側欄")
        else:
            self.sidebar_panel.setVisible(True)
            self.sidebar_panel.setFixedWidth(230)
            if hasattr(self, "sidebar_action"):
                self.sidebar_action.setText("收合側欄")

    def add_task(self) -> None:
        dialog = TaskDialog(self)
        if dialog.exec() == QDialog.Accepted and dialog.result_task:
            dialog.result_task.log_max_mb = self.log_max_mb
            self.tasks.append(dialog.result_task)
            self._refresh_task_list()
            self._create_panel(dialog.result_task)
            self.save_config()

    def edit_task(self) -> None:
        task = self._selected_task()
        if not task:
            QMessageBox.information(self, "提示", "請先選擇任務。")
            return
        self._edit_task_object(task)

    def edit_task_by_id(self, task_id_value: str) -> None:
        for task in self.tasks:
            if task.task_id == task_id_value:
                self._edit_task_object(task)
                return

    def _edit_task_object(self, task: MonitorTask) -> None:
        dialog = TaskDialog(self, task)
        if dialog.exec() == QDialog.Accepted and dialog.result_task:
            idx = self.tasks.index(task)
            self.tasks[idx] = dialog.result_task
            self._refresh_task_list()
            self._rebuild_panel(dialog.result_task)
            self.save_config()

    def delete_task(self) -> None:
        task = self._selected_task()
        if not task:
            QMessageBox.information(self, "提示", "請先選擇任務。")
            return
        if QMessageBox.question(self, "確認刪除", f"確定要刪除「{task.name}」嗎？") != QMessageBox.Yes:
            return
        if task.task_id in self.panels:
            self.panels[task.task_id].stop()
        if task.task_id in self.windows:
            self.windows[task.task_id].close()
        self.tasks = [t for t in self.tasks if t.task_id != task.task_id]
        self.panels.pop(task.task_id, None)
        self.windows.pop(task.task_id, None)
        self._refresh_task_list()
        self.save_config()

    def start_all(self) -> None:
        for panel in self.panels.values():
            panel.start()

    def stop_all(self) -> None:
        for panel in self.panels.values():
            panel.stop()

    def restart_all(self) -> None:
        self.stop_all()
        QTimer.singleShot(1500, self.start_all)

    def save_layout(self) -> None:
        self._capture_layout()
        self.save_config()

    def open_config_folder(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        if self.config_path.exists():
            subprocess.Popen(["explorer", "/select,", str(self.config_path)])
        else:
            subprocess.Popen(["explorer", str(self.config_path.parent)])

    def check_for_updates_manual(self) -> None:
        self.check_for_updates(manual=True)

    def rollback_to_release(self) -> None:
        try:
            releases = self._fetch_releases()
        except Exception as exc:
            QMessageBox.warning(self._update_dialog_parent(), "退版失敗", f"無法讀取版本清單：{exc}")
            return
        choices = []
        releases_by_label = {}
        current_version = self._version_tuple(APP_VERSION)
        for release in releases:
            tag = str(release.get("tag_name", "")).strip()
            if not tag or self._version_tuple(tag) >= current_version:
                continue
            asset_url = self._release_asset_url(release)
            if not asset_url:
                continue
            label = tag
            published_at = str(release.get("published_at", "")).strip()
            if published_at:
                label = f"{tag}  ({published_at[:10]})"
            choices.append(label)
            releases_by_label[label] = {"tag": tag, "asset_url": asset_url}
        if not choices:
            QMessageBox.information(self._update_dialog_parent(), "退版", "沒有找到可退版的歷史版本。")
            return
        selected, ok = QInputDialog.getItem(
            self._update_dialog_parent(),
            "選擇退版版本",
            "版本",
            choices,
            0,
            False,
        )
        if not ok or not selected:
            return
        info = releases_by_label[selected]
        result = QMessageBox.question(
            self._update_dialog_parent(),
            "確認退版",
            f"目前版本：v{APP_VERSION}\n退回版本：{info['tag']}\n\n是否下載並準備退版？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return
        self._show_update_progress(str(info["tag"]))
        thread = threading.Thread(target=self._download_update_worker, args=(info,), daemon=True)
        thread.start()

    def _fetch_releases(self) -> List[Dict]:
        releases_api = GITHUB_LATEST_RELEASE_API.rsplit("/latest", 1)[0]
        request = urllib.request.Request(
            releases_api,
            headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"},
        )
        with urllib.request.urlopen(request, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        if not isinstance(data, list):
            return []
        return data

    def check_for_updates(self, manual: bool = False) -> None:
        if self.update_checking:
            if manual:
                QMessageBox.information(self._update_dialog_parent(), "檢查更新", "正在檢查更新，請稍候。")
            return
        self.update_checking = True
        thread = threading.Thread(target=self._check_for_updates_worker, args=(manual,), daemon=True)
        thread.start()

    def _check_for_updates_worker(self, manual: bool) -> None:
        try:
            request = urllib.request.Request(
                GITHUB_LATEST_RELEASE_API,
                headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"},
            )
            with urllib.request.urlopen(request, timeout=12) as response:
                release = json.loads(response.read().decode("utf-8", errors="replace"))
            latest_tag = str(release.get("tag_name", "")).strip()
            if not latest_tag or not self._is_newer_version(latest_tag, APP_VERSION):
                if manual:
                    self.signals.update_current.emit(latest_tag or f"v{APP_VERSION}")
                return
            asset_url = self._release_asset_url(release)
            if not asset_url:
                self.signals.update_failed.emit(f"新版 {latest_tag} 沒有找到 {RELEASE_ASSET_NAME}。", manual)
                return
            self.signals.update_available.emit({"tag": latest_tag, "asset_url": asset_url, "manual": manual})
        except Exception as exc:
            self.signals.update_failed.emit(f"檢查更新失敗：{exc}", manual)
        finally:
            self.update_checking = False

    def _release_asset_url(self, release: Dict) -> str:
        for asset in release.get("assets", []):
            if str(asset.get("name", "")).lower() == RELEASE_ASSET_NAME.lower():
                return str(asset.get("browser_download_url", ""))
        for asset in release.get("assets", []):
            name = str(asset.get("name", "")).lower()
            if name.endswith(".exe"):
                return str(asset.get("browser_download_url", ""))
        return ""

    def _is_newer_version(self, latest: str, current: str) -> bool:
        return self._version_tuple(latest) > self._version_tuple(current)

    def _version_tuple(self, value: str) -> tuple[int, ...]:
        text = value.strip().lstrip("vV")
        parts = []
        for part in text.split("."):
            digits = ""
            for char in part:
                if char.isdigit():
                    digits += char
                else:
                    break
            parts.append(int(digits or "0"))
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts)

    def _handle_update_available(self, info: Dict) -> None:
        tag = str(info.get("tag", "")).strip()
        parent = self._update_dialog_parent()
        result = QMessageBox.question(
            parent,
            "發現新版本",
            f"目前版本：v{APP_VERSION}\n最新版本：{tag}\n\n是否立即下載並安裝？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if result != QMessageBox.Yes:
            return
        self._show_update_progress(tag)
        thread = threading.Thread(target=self._download_update_worker, args=(info,), daemon=True)
        thread.start()

    def _handle_update_current(self, latest_tag: str) -> None:
        QMessageBox.information(
            self._update_dialog_parent(),
            "檢查更新",
            f"目前已是最新版。\n\n目前版本：v{APP_VERSION}\nGitHub 最新版：{latest_tag}",
        )

    def _download_update_worker(self, info: Dict) -> None:
        tag = str(info.get("tag", "")).strip()
        asset_url = str(info.get("asset_url", "")).strip()
        try:
            target = Path(tempfile.gettempdir()) / f"{APP_NAME}-{tag}-{RELEASE_ASSET_NAME}"
            request = urllib.request.Request(
                asset_url,
                headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"},
            )
            with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as output:
                total = int(response.headers.get("Content-Length") or "0")
                downloaded = 0
                self.signals.update_progress.emit({"downloaded": downloaded, "total": total, "tag": tag})
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    self.signals.update_progress.emit({"downloaded": downloaded, "total": total, "tag": tag})
            self.signals.update_downloaded.emit(str(target), tag)
        except Exception as exc:
            self.signals.update_failed.emit(f"下載更新失敗：{exc}", True)

    def _update_dialog_parent(self) -> QWidget:
        if self.active_settings_dialog and self.active_settings_dialog.isVisible():
            return self.active_settings_dialog
        active_modal = QApplication.activeModalWidget()
        if active_modal and active_modal is not self.update_progress_dialog:
            return active_modal
        active_window = QApplication.activeWindow()
        if active_window and active_window is not self.update_progress_dialog:
            return active_window
        return self

    def _show_update_progress(self, tag: str) -> None:
        if self.update_progress_dialog:
            self.update_progress_dialog.close()
        parent = self._update_dialog_parent()
        dialog = QProgressDialog(f"正在下載 {tag}...", "", 0, 100, parent)
        dialog.setWindowTitle("下載更新")
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        dialog.setCancelButton(None)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)
        self.update_progress_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _close_update_progress(self) -> None:
        if not self.update_progress_dialog:
            return
        self.update_progress_dialog.close()
        self.update_progress_dialog.deleteLater()
        self.update_progress_dialog = None

    def _handle_update_progress(self, progress: Dict) -> None:
        dialog = self.update_progress_dialog
        if not dialog:
            return
        downloaded = int(progress.get("downloaded", 0))
        total = int(progress.get("total", 0))
        tag = str(progress.get("tag", "")).strip()
        downloaded_mb = downloaded / (1024 * 1024)
        if total > 0:
            percent = max(0, min(100, int(downloaded * 100 / total)))
            total_mb = total / (1024 * 1024)
            dialog.setRange(0, 100)
            dialog.setValue(percent)
            dialog.setLabelText(f"正在下載 {tag}... {percent}%\n{downloaded_mb:.1f} / {total_mb:.1f} MB")
            return
        dialog.setRange(0, 0)
        dialog.setLabelText(f"正在下載 {tag}...\n已下載 {downloaded_mb:.1f} MB")

    def _handle_update_downloaded(self, downloaded_path: str, tag: str) -> None:
        self._close_update_progress()
        source = Path(downloaded_path)
        if not source.exists():
            QMessageBox.warning(self._update_dialog_parent(), "更新失敗", "更新檔下載完成後找不到檔案。")
            return
        if getattr(sys, "frozen", False):
            target = Path(sys.executable)
            if self._confirm_update_restart(tag):
                self.updating_now = True
                self._launch_updater(source, target)
                self.close()
                return
            self.pending_update_source = source
            self.pending_update_target = target
            return

        dist_dir = Path.cwd() / "dist"
        dist_dir.mkdir(parents=True, exist_ok=True)
        target = dist_dir / RELEASE_ASSET_NAME
        source.replace(target)
        QMessageBox.information(
            self._update_dialog_parent(),
            "更新已下載",
            f"目前是原始碼執行模式，無法替換正在執行的 Python。\n\n"
            f"已將 {tag} 下載到：\n{target}",
        )

    def _confirm_update_restart(self, tag: str) -> bool:
        box = QMessageBox(self._update_dialog_parent())
        box.setWindowTitle("準備更新")
        box.setIcon(QMessageBox.Information)
        box.setText(f"{tag} 更新檔已下載完成。")
        box.setInformativeText("立即重啟會關閉程式、替換檔案並重新啟動。\n選擇稍後重啟時，程式會在下次關閉時套用更新。")
        restart_button = box.addButton("立即重啟更新", QMessageBox.AcceptRole)
        box.addButton("稍後重啟", QMessageBox.RejectRole)
        box.setDefaultButton(restart_button)
        box.setWindowModality(Qt.ApplicationModal)
        box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        box.show()
        box.raise_()
        box.activateWindow()
        box.exec()
        return box.clickedButton() is restart_button

    def _launch_updater(self, source: Path, target: Path) -> None:
        updater = Path(tempfile.gettempdir()) / f"{APP_NAME}-update.bat"
        script = (
            "@echo off\n"
            "setlocal\n"
            "timeout /t 2 /nobreak >nul\n"
            ":retry\n"
            f'move /Y "{source}" "{target}" >nul\n'
            "if errorlevel 1 (\n"
            "  timeout /t 1 /nobreak >nul\n"
            "  goto retry\n"
            ")\n"
            "timeout /t 2 /nobreak >nul\n"
            "set PYINSTALLER_RESET_ENVIRONMENT=1\n"
            f'start "" "{target}"\n'
            'del "%~f0"\n'
        )
        updater.write_text(script, encoding="utf-8")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(["cmd", "/c", str(updater)], creationflags=creationflags)

    def _handle_update_failed(self, message: str, manual: bool) -> None:
        self._close_update_progress()
        if manual:
            QMessageBox.warning(self._update_dialog_parent(), "檢查更新", message)
            return
        print(message)

    def _selected_task(self) -> Optional[MonitorTask]:
        item = self.task_list.currentItem()
        if not item:
            return None
        task_id_value = item.data(Qt.UserRole)
        for task in self.tasks:
            if task.task_id == task_id_value:
                return task
        return None

    def _focus_selected_panel(self, current: Optional[QListWidgetItem]) -> None:
        if not current:
            return
        task_id_value = current.data(Qt.UserRole)
        window = self.windows.get(task_id_value)
        if window:
            self.mdi.setActiveSubWindow(window)

    def _refresh_task_list(self) -> None:
        selected_id = self.task_list.currentItem().data(Qt.UserRole) if self.task_list.currentItem() else None
        self.task_list.clear()
        for task in self.tasks:
            item = QListWidgetItem(task.name)
            item.setData(Qt.UserRole, task.task_id)
            self.task_list.addItem(item)
            if task.task_id == selected_id:
                self.task_list.setCurrentItem(item)

    def _create_panels(self) -> None:
        self.mdi.closeAllSubWindows()
        self.panels.clear()
        self.windows.clear()
        for task in self.tasks:
            self._create_panel(task)

    def _create_panel(self, task: MonitorTask) -> None:
        panel = MonitorPanel(task, edit_callback=self.edit_task_by_id, log_memory_enabled=self.log_memory_enabled)
        window = QMdiSubWindow()
        window.setWidget(panel)
        window.setWindowTitle(task.name)
        window.setAttribute(Qt.WA_DeleteOnClose, False)
        self.mdi.addSubWindow(window)
        window.setGeometry(self._geometry_rect(task.geometry))
        window.show()
        self.panels[task.task_id] = panel
        self.windows[task.task_id] = window

    def _rebuild_panel(self, task: MonitorTask) -> None:
        old_panel = self.panels.get(task.task_id)
        if old_panel:
            old_panel.flush_log()
            old_panel.stop()
        old_window = self.windows.get(task.task_id)
        if old_window:
            task.geometry = {
                "x": old_window.x(),
                "y": old_window.y(),
                "w": old_window.width(),
                "h": old_window.height(),
            }
            old_window.close()
        self.panels.pop(task.task_id, None)
        self.windows.pop(task.task_id, None)
        self._create_panel(task)

    def _capture_layout(self) -> None:
        for task in self.tasks:
            window = self.windows.get(task.task_id)
            if not window:
                continue
            task.geometry = {
                "x": window.x(),
                "y": window.y(),
                "w": max(280, window.width()),
                "h": max(180, window.height()),
            }

    def _geometry_rect(self, geometry: Dict[str, int]) -> QRect:
        return QRect(
            int(geometry.get("x", DEFAULT_GEOMETRY["x"])),
            int(geometry.get("y", DEFAULT_GEOMETRY["y"])),
            max(280, int(geometry.get("w", DEFAULT_GEOMETRY["w"]))),
            max(180, int(geometry.get("h", DEFAULT_GEOMETRY["h"]))),
        )

    def _bounded_rect(self, geometry: Dict[str, int]) -> QRect:
        area = self.mdi.viewport().rect()
        margin = 8
        min_w = 280
        min_h = 180
        max_w = max(min_w, area.width() - margin * 2)
        max_h = max(min_h, area.height() - margin * 2)

        w = min(max(min_w, int(geometry.get("w", DEFAULT_GEOMETRY["w"]))), max_w)
        h = min(max(min_h, int(geometry.get("h", DEFAULT_GEOMETRY["h"]))), max_h)
        max_x = max(margin, area.width() - w - margin)
        max_y = max(margin, area.height() - h - margin)
        x = min(max(margin, int(geometry.get("x", DEFAULT_GEOMETRY["x"]))), max_x)
        y = min(max(margin, int(geometry.get("y", DEFAULT_GEOMETRY["y"]))), max_y)
        return QRect(x, y, w, h)

    def _rect_to_geometry(self, rect: QRect) -> Dict[str, int]:
        return {"x": rect.x(), "y": rect.y(), "w": rect.width(), "h": rect.height()}

    def arrange_panels(self) -> None:
        windows = [self.windows[task.task_id] for task in self.tasks if task.task_id in self.windows]
        if not windows:
            return
        area = self.mdi.viewport().rect()
        margin = 8
        mode = self.layout_mode if self.layout_mode in {"grid_auto", "grid_2", "vertical", "horizontal", "cascade"} else "grid_2"

        if mode == "cascade":
            width = min(max(420, int(area.width() * 0.58)), max(420, area.width() - margin * 2))
            height = min(max(240, int(area.height() * 0.48)), max(240, area.height() - margin * 2))
            step = 32
            for idx, window in enumerate(windows):
                rect = self._bounded_rect({
                    "x": margin + idx * step,
                    "y": margin + idx * step,
                    "w": width,
                    "h": height,
                })
                window.setGeometry(rect)
            self.save_config()
            return

        if mode == "vertical":
            columns = 1
        elif mode == "horizontal":
            columns = len(windows)
        elif mode == "grid_auto":
            columns = max(1, int(len(windows) ** 0.5))
            if columns * columns < len(windows):
                columns += 1
        else:
            columns = 2 if len(windows) > 1 else 1

        rows = (len(windows) + columns - 1) // columns
        cell_w = max(280, (area.width() - margin * (columns + 1)) // columns)
        cell_h = max(180, (area.height() - margin * (rows + 1)) // rows)
        for idx, window in enumerate(windows):
            row = idx // columns
            col = idx % columns
            rect = self._bounded_rect({
                "x": margin + col * (cell_w + margin),
                "y": margin + row * (cell_h + margin),
                "w": cell_w,
                "h": cell_h,
            })
            window.setGeometry(rect)
        self.save_config()

    def _check_restart_schedule(self) -> None:
        if not self.restart_enabled.isChecked():
            return
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        if current_time not in set(self.restart_times):
            return
        key = now.strftime("%Y%m%d%H%M")
        if key == self.last_restart_key:
            return
        self.last_restart_key = key
        self.restart_all()

    def _collect_metrics(self) -> Dict:
        now = datetime.now().astimezone()
        cpu_percent = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(Path.home().anchor or "C:\\"))
        boot_time = datetime.fromtimestamp(psutil.boot_time()).astimezone()
        uptime_seconds = int(time.time() - psutil.boot_time())
        net = psutil.net_io_counters()
        running_tasks = sum(1 for panel in self.panels.values() if panel.is_running())
        total_tasks = len(self.panels)
        task_statuses = []
        for task in self.tasks:
            panel = self.panels.get(task.task_id)
            running = bool(panel and panel.is_running())
            task_statuses.append({
                "name": task.name,
                "state": "running" if running else "stopped",
                "label": "正常" if running else "已停止",
            })
        return {
            "timestamp": now,
            "hostname": socket.gethostname(),
            "os": f"{platform.system()} {platform.release()}",
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_used_gb": memory.used / (1024 ** 3),
            "memory_total_gb": memory.total / (1024 ** 3),
            "disk_percent": disk.percent,
            "disk_free_gb": disk.free / (1024 ** 3),
            "disk_total_gb": disk.total / (1024 ** 3),
            "boot_time": boot_time,
            "uptime": self._format_duration(uptime_seconds),
            "running_tasks": running_tasks,
            "total_tasks": total_tasks,
            "task_statuses": task_statuses,
            "net_sent_mb": net.bytes_sent / (1024 ** 2),
            "net_recv_mb": net.bytes_recv / (1024 ** 2),
        }

    def _update_metrics(self, force_discord: bool = False) -> None:
        self.latest_metrics = self._collect_metrics()
        metrics = self.latest_metrics
        self.metric_labels["heartbeat"].setText(metrics["timestamp"].strftime("%Y-%m-%d %H:%M:%S"))
        self.metric_labels["cpu"].setText(f'{metrics["cpu_percent"]:.1f}%')
        self.metric_labels["memory"].setText(
            f'{metrics["memory_percent"]:.1f}% ({metrics["memory_used_gb"]:.1f}/{metrics["memory_total_gb"]:.1f} GB)'
        )
        self.metric_labels["disk"].setText(
            f'{metrics["disk_percent"]:.1f}% 使用，剩餘 {metrics["disk_free_gb"]:.1f} GB'
        )
        self.metric_labels["uptime"].setText(metrics["uptime"])
        self.metric_labels["tasks"].setText(f'{metrics["running_tasks"]}/{metrics["total_tasks"]} 執行中')
        self.metric_labels["network"].setText(
            f'↑ {metrics["net_sent_mb"]:.0f} MB / ↓ {metrics["net_recv_mb"]:.0f} MB'
        )
        self.metric_labels["discord"].setText(
            "啟用" if self.discord_enabled else "停用"
        )
        self._maybe_send_discord_metrics(force=force_discord)

    def _maybe_send_discord_metrics(self, force: bool = False) -> None:
        if not self.discord_enabled or not self.discord_webhook_url:
            return
        if self.discord_sending:
            return
        now = time.time()
        interval_seconds = max(1, self.discord_interval_minutes) * 60
        if not force and now - self.last_discord_sent_at < interval_seconds:
            return
        self.discord_sending = True
        metrics = dict(self.latest_metrics)
        thread = threading.Thread(target=self._send_discord_metrics_worker, args=(metrics,), daemon=True)
        thread.start()

    def _send_discord_metrics_worker(self, metrics: Dict) -> None:
        try:
            payload = self._build_discord_payload(metrics)
            chart_png = self._build_discord_chart_png(metrics)
            message_id = self._send_or_edit_webhook_message(payload, chart_png)
            self.last_discord_sent_at = time.time()
            if message_id and message_id != self.discord_message_id:
                self.signals.discord_message_id_changed.emit(message_id)
        except Exception as exc:
            print(f"Discord metrics send failed: {exc}")
        finally:
            self.discord_sending = False

    def _store_discord_message_id(self, message_id: str) -> None:
        self.discord_message_id = message_id
        self.save_config()

    def _send_or_edit_webhook_message(self, payload: Dict, chart_png: Optional[bytes] = None) -> Optional[str]:
        webhook_url = self.discord_webhook_url.strip().split("?", 1)[0].rstrip("/")
        if self.discord_message_id:
            edit_url = f"{webhook_url}/messages/{self.discord_message_id}"
            ok, data = self._discord_request("PATCH", edit_url, payload, chart_png)
            if ok:
                return data.get("id", self.discord_message_id)
            self.discord_message_id = ""

        separator = "&" if "?" in webhook_url else "?"
        ok, data = self._discord_request("POST", f"{webhook_url}{separator}wait=true", payload, chart_png)
        if ok:
            return data.get("id")
        return None

    def _discord_request(
        self,
        method: str,
        url: str,
        payload: Dict,
        chart_png: Optional[bytes] = None,
    ) -> tuple[bool, Dict]:
        if chart_png:
            body, content_type = self._build_discord_multipart(payload, chart_png)
        else:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Content-Type": content_type,
                "User-Agent": f"{APP_NAME}/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                response_body = response.read().decode("utf-8", errors="replace")
                return 200 <= response.status < 300, json.loads(response_body) if response_body else {}
        except urllib.error.HTTPError as exc:
            exc.read()
            return False, {}
        except urllib.error.URLError:
            return False, {}

    def _build_discord_multipart(self, payload: Dict, chart_png: bytes) -> tuple[bytes, str]:
        boundary = f"----{APP_NAME}-{uuid.uuid4().hex}"
        payload = dict(payload)
        payload["attachments"] = [{"id": 0, "filename": "status.png"}]
        payload_json = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        parts = [
            f"--{boundary}\r\n".encode("ascii"),
            b'Content-Disposition: form-data; name="payload_json"\r\n',
            b"Content-Type: application/json; charset=utf-8\r\n\r\n",
            payload_json,
            b"\r\n",
            f"--{boundary}\r\n".encode("ascii"),
            b'Content-Disposition: form-data; name="files[0]"; filename="status.png"\r\n',
            b"Content-Type: image/png\r\n\r\n",
            chart_png,
            b"\r\n",
            f"--{boundary}--\r\n".encode("ascii"),
        ]
        return b"".join(parts), f"multipart/form-data; boundary={boundary}"

    def _build_discord_payload(self, metrics: Dict) -> Dict:
        return {
            "content": "",
            "embeds": [],
            "allowed_mentions": {"parse": []},
        }

    def _build_discord_chart_png(self, metrics: Dict) -> bytes:
        width = 960
        height = 560
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(QColor("#0b1118"))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        def set_font(size: int, bold: bool = False) -> None:
            font = QFont()
            font.setFamilies([
                "Microsoft JhengHei UI",
                "Microsoft JhengHei",
                "Noto Sans CJK TC",
                "PingFang TC",
                "Arial Unicode MS",
                "Segoe UI",
            ])
            font.setPointSize(size)
            font.setBold(bold)
            painter.setFont(font)

        def metric_color(value: float, warning: float, danger: float) -> QColor:
            if value >= danger:
                return QColor("#ff5c6c")
            if value >= warning:
                return QColor("#f6c343")
            return QColor("#38d98b")

        def elide_text(text: str, max_chars: int) -> str:
            return text if len(text) <= max_chars else text[: max_chars - 1] + "..."

        def fill_rounded(rect: QRect, color: QColor, radius: int = 12) -> None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, radius, radius)

        def draw_bar(rect: QRect, ratio: float, color: QColor) -> None:
            fill_rounded(rect, QColor("#263241"), rect.height() // 2)
            width_px = max(rect.height(), int(rect.width() * max(0.0, min(1.0, ratio))))
            fill_rounded(QRect(rect.x(), rect.y(), width_px, rect.height()), color, rect.height() // 2)

        def draw_status_light(cx: int, cy: int, color: QColor) -> None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 46))
            painter.drawEllipse(cx - 9, cy - 9, 18, 18)
            painter.setBrush(color)
            painter.drawEllipse(cx - 5, cy - 5, 10, 10)

        def draw_metric_card(rect: QRect, title: str, value: str, detail: str, color: QColor, ratio: Optional[float] = None) -> None:
            fill_rounded(rect, QColor("#151f2a"), 14)
            painter.setPen(QColor("#9caebb"))
            set_font(10, True)
            painter.drawText(rect.adjusted(18, 16, -18, -16), Qt.AlignmentFlag.AlignTop, title)

            painter.setPen(QColor("#f4fbff"))
            set_font(24, True)
            painter.drawText(rect.adjusted(18, 42, -18, -16), Qt.AlignmentFlag.AlignTop, value)

            painter.setPen(QColor("#c7d3df"))
            set_font(10)
            painter.drawText(rect.adjusted(18, 86, -18, -16), Qt.AlignmentFlag.AlignTop, detail)

            if ratio is not None:
                draw_bar(QRect(rect.x() + 18, rect.bottom() - 24, rect.width() - 36, 9), ratio, color)

        set_font(19, True)
        painter.setPen(QColor("#f4fbff"))
        painter.drawText(30, 38, self.discord_status_title or DISCORD_STATUS_TITLE)
        set_font(10)
        painter.setPen(QColor("#9fb0bf"))
        painter.drawText(32, 64, metrics["timestamp"].strftime("%Y-%m-%d %H:%M:%S %Z"))

        task_statuses = list(metrics.get("task_statuses", []))
        total_tasks = max(1, metrics["total_tasks"])
        running_ratio = max(0.0, min(metrics["running_tasks"] / total_tasks, 1.0))

        draw_metric_card(
            QRect(30, 92, 206, 132),
            "CPU",
            f'{metrics["cpu_percent"]:.1f}%',
            "處理器使用率",
            metric_color(metrics["cpu_percent"], 75, 90),
            metrics["cpu_percent"] / 100,
        )
        draw_metric_card(
            QRect(252, 92, 206, 132),
            "記憶體",
            f'{metrics["memory_percent"]:.1f}%',
            f'{metrics["memory_used_gb"]:.1f}/{metrics["memory_total_gb"]:.1f} GB',
            metric_color(metrics["memory_percent"], 80, 90),
            metrics["memory_percent"] / 100,
        )
        draw_metric_card(
            QRect(474, 92, 206, 132),
            "系統碟",
            f'{metrics["disk_percent"]:.1f}%',
            f'剩餘 {metrics["disk_free_gb"]:.1f} GB',
            metric_color(metrics["disk_percent"], 80, 90),
            metrics["disk_percent"] / 100,
        )

        draw_metric_card(
            QRect(696, 92, 234, 132),
            "監控任務",
            f'{metrics["running_tasks"]}/{metrics["total_tasks"]}',
            "BAT 任務執行中",
            QColor("#38d98b"),
            running_ratio,
        )

        info_panel = QRect(30, 246, 900, 78)
        fill_rounded(info_panel, QColor("#111a24"), 14)
        summary_items = [
            ("主機", str(metrics.get("hostname", "-"))),
            ("開機時間", str(metrics["uptime"])),
            ("累計網路", f'↑ {metrics["net_sent_mb"]:.0f} MB / ↓ {metrics["net_recv_mb"]:.0f} MB'),
            ("作業系統", str(metrics.get("os", "-"))),
        ]
        for idx, (label, value) in enumerate(summary_items):
            x = 54 + idx * 220
            painter.setPen(QColor("#91a4b5"))
            set_font(10)
            painter.drawText(QRect(x, 264, 190, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            painter.setPen(QColor("#e7f0f7"))
            set_font(11, True)
            painter.drawText(QRect(x, 288, 190, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elide_text(value, 20))

        tasks_panel = QRect(30, 348, 900, 176)
        fill_rounded(tasks_panel, QColor("#151f2a"), 14)

        set_font(15, True)
        painter.setPen(QColor("#f4fbff"))
        painter.drawText(54, 382, "BAT 任務生命狀態")
        set_font(10)
        painter.setPen(QColor("#9fb0bf"))
        painter.drawText(224, 382, f'{metrics["running_tasks"]}/{metrics["total_tasks"]} 執行中')

        if not task_statuses:
            painter.setPen(QColor("#9fb0bf"))
            set_font(12)
            painter.drawText(QRect(54, 420, 840, 48), Qt.AlignmentFlag.AlignVCenter, "尚未設定監控任務")
        else:
            visible = task_statuses[:8]
            columns = 2
            row_h = 30
            start_y = 414
            col_w = 430
            for idx, task_status in enumerate(visible):
                col = idx % columns
                row = idx // columns
                x = 56 + col * col_w
                y = start_y + row * row_h
                state = str(task_status.get("state", "stopped"))
                label = str(task_status.get("label", "已停止"))
                color = QColor("#38d98b") if state == "running" else QColor("#ff5c6c")
                row_rect = QRect(x - 8, y - 3, 392, 26)
                fill_rounded(row_rect, QColor("#101821"), 8)

                draw_status_light(x + 10, y + 10, color)
                painter.setPen(QColor("#f4fbff"))
                set_font(11, True)
                painter.drawText(QRect(x + 32, y - 2, 230, 24), Qt.AlignmentFlag.AlignVCenter, elide_text(str(task_status.get("name", "未命名任務")), 20))
                painter.setPen(color)
                set_font(10, True)
                painter.drawText(QRect(x + 292, y - 2, 80, 24), Qt.AlignmentFlag.AlignVCenter, label)
            if len(task_statuses) > len(visible):
                painter.setPen(QColor("#9fb0bf"))
                set_font(10)
                painter.drawText(QRect(56, 500, 820, 20), Qt.AlignmentFlag.AlignVCenter, f"另有 {len(task_statuses) - len(visible)} 個任務未顯示")

        painter.end()

        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        return bytes(data)

    def _format_duration(self, seconds: int) -> str:
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        if days:
            return f"{days} 天 {hours} 小時 {minutes} 分"
        return f"{hours} 小時 {minutes} 分"

    def load_config(self) -> None:
        if not self.config_path.exists():
            self.restart_time.setTime(QTime.fromString("05:00", "HH:mm"))
            self.restart_times = ["05:00"]
            return
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            self.tasks = [MonitorTask.from_dict(item) for item in data.get("tasks", [])]
            settings = data.get("settings", {})
            self.restart_enabled.setChecked(bool(settings.get("restart_enabled", False)))
            self.sidebar_collapsed = bool(settings.get("sidebar_collapsed", False))
            self.theme_name = str(settings.get("theme_name", "dark"))
            if self.theme_name not in {"dark", "light", "warm"}:
                self.theme_name = "dark"
            valid_text_colors = {value for _, value in TEXT_COLOR_OPTIONS}
            self.text_color_name = str(settings.get("text_color_name", "default"))
            if self.text_color_name not in valid_text_colors:
                self.text_color_name = "default"
            self.layout_mode = str(settings.get("layout_mode", "grid_2"))
            if self.layout_mode not in {"grid_auto", "grid_2", "vertical", "horizontal", "cascade"}:
                self.layout_mode = "grid_2"
            self.auto_update_enabled = bool(settings.get("auto_update_enabled", True))
            self.log_memory_enabled = bool(settings.get("log_memory_enabled", True))
            self.log_max_mb = max(1, int(settings.get("log_max_mb", DEFAULT_LOG_MAX_MB)))
            self.discord_enabled = bool(settings.get("discord_enabled", False))
            self.discord_status_title = str(settings.get("discord_status_title", DISCORD_STATUS_TITLE)).strip() or DISCORD_STATUS_TITLE
            self.discord_webhook_url = str(settings.get("discord_webhook_url", ""))
            self.discord_interval_minutes = max(1, int(settings.get("discord_interval_minutes", 5)))
            self.discord_message_id = str(settings.get("discord_message_id", ""))
            self.restart_times = self._load_restart_times(settings)
            restart_time = self.restart_times[0] if self.restart_times else "05:00"
            parsed_time = QTime.fromString(restart_time, "HH:mm")
            self.restart_time.setTime(parsed_time if parsed_time.isValid() else QTime.fromString("05:00", "HH:mm"))
            geometry = settings.get("window_geometry")
            if isinstance(geometry, str) and geometry:
                self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
        except Exception as exc:
            QMessageBox.warning(self, "設定讀取失敗", f"無法讀取設定，將使用空白設定：{exc}")
            self.tasks = []

    def save_config(self, capture_layout: bool = True) -> None:
        if not hasattr(self, "config_path"):
            return
        if capture_layout:
            self._capture_layout()
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "settings": {
                "restart_enabled": self.restart_enabled.isChecked(),
                "restart_time": self.restart_times[0] if self.restart_times else "05:00",
                "restart_times": self.restart_times,
                "sidebar_collapsed": self.sidebar_collapsed,
                "theme_name": self.theme_name,
                "text_color_name": self.text_color_name,
                "layout_mode": self.layout_mode,
                "auto_update_enabled": self.auto_update_enabled,
                "log_memory_enabled": self.log_memory_enabled,
                "log_max_mb": self.log_max_mb,
                "discord_enabled": self.discord_enabled,
                "discord_status_title": self.discord_status_title,
                "discord_webhook_url": self.discord_webhook_url,
                "discord_interval_minutes": self.discord_interval_minutes,
                "discord_message_id": self.discord_message_id,
                "window_geometry": bytes(self.saveGeometry().toBase64()).decode("ascii"),
            },
            "tasks": [task.to_dict() for task in self.tasks],
        }
        self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_restart_times(self, settings: Dict) -> List[str]:
        raw_times = settings.get("restart_times")
        candidates = raw_times if isinstance(raw_times, list) else [settings.get("restart_time", "05:00")]
        restart_times: List[str] = []
        for value in candidates:
            parsed_time = QTime.fromString(str(value), "HH:mm")
            if not parsed_time.isValid():
                continue
            time_text = parsed_time.toString("HH:mm")
            if time_text not in restart_times:
                restart_times.append(time_text)
        return sorted(restart_times) or ["05:00"]

    def closeEvent(self, event) -> None:
        running_count = sum(1 for panel in self.panels.values() if panel.is_running())
        if running_count and not self.log_memory_enabled and not self.updating_now:
            result = QMessageBox.warning(
                self,
                "Log 記憶功能未啟用",
                "目前有任務正在執行，且尚未啟用 Log 記憶功能。\n\n"
                "關閉程式會中斷所有進行中的任務；下次開啟時，設定為自動啟動的任務會重新啟動。\n\n"
                "確定要關閉嗎？",
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if result != QMessageBox.Ok:
                event.ignore()
                return
        self.save_config()
        for panel in self.panels.values():
            panel.flush_log()
            if not self.log_memory_enabled:
                panel.stop(wait=True)
                panel.flush_log()
        if (
            self.pending_update_source
            and self.pending_update_target
            and self.pending_update_source.exists()
            and getattr(sys, "frozen", False)
        ):
            self.updating_now = True
            self._launch_updater(self.pending_update_source, self.pending_update_target)
            self.pending_update_source = None
            self.pending_update_target = None
        event.accept()

    def _text_color_styles(self) -> str:
        if self.text_color_name == "default":
            return ""
        palettes = {
            "dark": {
                "red": "#ff7b72",
                "blue": "#8bd3ff",
                "green": "#b7f7c1",
                "amber": "#f6c343",
                "violet": "#d8b4fe",
            },
            "light": {
                "red": "#cf222e",
                "blue": "#0969da",
                "green": "#116329",
                "amber": "#9a6700",
                "violet": "#8250df",
            },
            "warm": {
                "red": "#b42318",
                "blue": "#1d4ed8",
                "green": "#15803d",
                "amber": "#9a3412",
                "violet": "#7e22ce",
            },
        }
        theme_palette = palettes.get(self.theme_name, palettes["dark"])
        color = theme_palette.get(self.text_color_name)
        if not color:
            return ""
        return f"""
            QMainWindow, QWidget, QLabel, QCheckBox, QRadioButton,
            QGroupBox::title, QGroupBox#settingsSection::title,
            QLabel#metricValue, QLabel#statusLabel, QLabel#aboutName, QLabel#footerText {{
                color: {color};
            }}
            QToolButton, QPushButton, QLineEdit, QSpinBox, QTimeEdit, QListWidget, QComboBox,
            QTextEdit#terminalOutput, QTabBar::tab {{
                color: {color};
            }}
            QListWidget::item:selected, QTabBar::tab:selected {{
                color: #ffffff;
            }}
        """

    def _apply_style(self) -> None:
        light_overrides = """
            QMainWindow, QWidget {
                background: #f6f8fa;
                color: #1f2328;
            }
            QLabel, QCheckBox {
                background: transparent;
            }
            QWidget#previewCard {
                background: transparent;
            }
            QRadioButton {
                background: transparent;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border-radius: 7px;
                border: 1px solid #8c959f;
                background: #ffffff;
            }
            QRadioButton::indicator:checked {
                border: 4px solid #0969da;
                background: #ffffff;
            }
            QToolBar {
                background: #ffffff;
                border-bottom: 1px solid #d0d7de;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d0d7de;
            }
            QGroupBox::title {
                background: transparent;
                color: #0969da;
            }
            QGroupBox#settingsSection {
                background: transparent;
                border: 1px solid #d0d7de;
            }
            QGroupBox#settingsSection::title {
                background: transparent;
                color: #1f2328;
            }
            QLabel#metricValue {
                color: #116329;
            }
            QToolButton, QPushButton {
                background: #f6f8fa;
                color: #24292f;
                border: 1px solid #d0d7de;
            }
            QToolButton:hover, QPushButton:hover {
                background: #eef2f6;
            }
            QLineEdit, QSpinBox, QTimeEdit, QListWidget, QComboBox {
                background: #ffffff;
                color: #1f2328;
                border: 1px solid #d0d7de;
                selection-background-color: #0969da;
            }
            QListWidget::item:selected {
                background: #0969da;
                color: #ffffff;
            }
            QMdiArea {
                background: #eef2f6;
            }
            QMdiSubWindow {
                background: #ffffff;
                border: 1px solid #d0d7de;
            }
            QTextEdit#terminalOutput {
                background: #ffffff;
                color: #116329;
                border: 1px solid #d0d7de;
            }
            QLabel#statusLabel {
                color: #0969da;
            }
            QTabWidget::pane {
                background: #ffffff;
                border: 1px solid #d0d7de;
            }
            QTabBar::tab {
                background: #f6f8fa;
                color: #24292f;
                border: 1px solid #d0d7de;
            }
            QTabBar::tab:selected {
                background: #0969da;
                color: #ffffff;
            }
            QLabel#aboutName {
                color: #1f2328;
            }
            QWidget#sidebarFooter {
                background: transparent;
            }
            QLabel#footerText {
                color: #57606a;
            }
            QToolButton#footerGitHubButton {
                background: transparent;
                border: 0;
            }
            QToolButton#footerGitHubButton:hover {
                background: #eef2f6;
            }
        """
        warm_overrides = """
            QMainWindow, QWidget {
                background: #fff7ed;
                color: #431407;
            }
            QLabel, QCheckBox {
                background: transparent;
            }
            QWidget#previewCard {
                background: transparent;
            }
            QRadioButton {
                background: transparent;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border-radius: 7px;
                border: 1px solid #d97706;
                background: #fff7ed;
            }
            QRadioButton::indicator:checked {
                border: 4px solid #c2410c;
                background: #ffffff;
            }
            QToolBar {
                background: #fffbeb;
                border-bottom: 1px solid #fed7aa;
            }
            QGroupBox {
                background: #fffbeb;
                border: 1px solid #fed7aa;
            }
            QGroupBox::title {
                background: transparent;
                color: #c2410c;
            }
            QGroupBox#settingsSection {
                background: transparent;
                border: 1px solid #fed7aa;
            }
            QGroupBox#settingsSection::title {
                background: transparent;
                color: #431407;
            }
            QLabel#metricValue {
                color: #9a3412;
            }
            QToolButton, QPushButton {
                background: #fffbeb;
                color: #431407;
                border: 1px solid #fdba74;
            }
            QToolButton:hover, QPushButton:hover {
                background: #fed7aa;
            }
            QLineEdit, QSpinBox, QTimeEdit, QListWidget, QComboBox {
                background: #ffffff;
                color: #431407;
                border: 1px solid #fdba74;
                selection-background-color: #c2410c;
            }
            QListWidget::item:selected {
                background: #c2410c;
                color: #ffffff;
            }
            QMdiArea {
                background: #ffedd5;
            }
            QMdiSubWindow {
                background: #ffffff;
                border: 1px solid #fdba74;
            }
            QTextEdit#terminalOutput {
                background: #fffaf0;
                color: #7c2d12;
                border: 1px solid #fdba74;
            }
            QLabel#statusLabel {
                color: #c2410c;
            }
            QTabWidget::pane {
                background: #fffbeb;
                border: 1px solid #fed7aa;
            }
            QTabBar::tab {
                background: #fff7ed;
                color: #431407;
                border: 1px solid #fed7aa;
            }
            QTabBar::tab:selected {
                background: #c2410c;
                color: #ffffff;
            }
            QLabel#aboutName {
                color: #431407;
            }
            QWidget#sidebarFooter {
                background: transparent;
            }
            QLabel#footerText {
                color: #9a3412;
            }
            QToolButton#footerGitHubButton {
                background: transparent;
                border: 0;
            }
            QToolButton#footerGitHubButton:hover {
                background: #fed7aa;
            }
        """
        theme_overrides = ""
        mdi_background = "#0b0f14"
        if self.theme_name == "light":
            theme_overrides = light_overrides
            mdi_background = "#eef2f6"
        elif self.theme_name == "warm":
            theme_overrides = warm_overrides
            mdi_background = "#ffedd5"
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #111418;
                color: #e6edf3;
                font-family: "Microsoft JhengHei UI", "Microsoft JhengHei", "Segoe UI";
                font-size: 10pt;
            }
            QLabel, QCheckBox {
                background: transparent;
            }
            QWidget#previewCard {
                background: transparent;
            }
            QRadioButton {
                background: transparent;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border-radius: 7px;
                border: 1px solid #8b949e;
                background: #0d1117;
            }
            QRadioButton::indicator:checked {
                border: 4px solid #1f6feb;
                background: #ffffff;
            }
            QToolBar {
                background: #171b21;
                border: 0;
                spacing: 6px;
                padding: 6px;
            }
            QGroupBox {
                background: #151a20;
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 10px;
                padding: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                background: transparent;
                color: #8bd3ff;
            }
            QGroupBox#settingsSection {
                background: transparent;
                border: 1px solid #30363d;
                border-radius: 6px;
                margin-top: 10px;
                padding: 8px;
            }
            QGroupBox#settingsSection::title {
                background: transparent;
                color: #e6edf3;
            }
            QLabel#metricValue {
                color: #b7f7c1;
                font-weight: 600;
            }
            QToolButton, QPushButton {
                background: #26313d;
                color: #e6edf3;
                border: 1px solid #3a4654;
                border-radius: 4px;
                padding: 5px 10px;
            }
            QToolButton:hover, QPushButton:hover {
                background: #334152;
            }
            QLineEdit, QSpinBox, QTimeEdit, QListWidget, QComboBox {
                background: #0d1117;
                color: #e6edf3;
                border: 1px solid #30363d;
                selection-background-color: #1f6feb;
            }
            QListWidget::item {
                padding: 8px;
            }
            QListWidget::item:selected {
                background: #1f6feb;
            }
            QMdiArea {
                background: #0b0f14;
            }
            QMdiSubWindow {
                background: #151a20;
                border: 1px solid #30363d;
            }
            QTextEdit#terminalOutput {
                background: #05070a;
                color: #b7f7c1;
                border: 1px solid #26313d;
                font-family: Consolas, "Cascadia Mono", monospace;
                font-size: 10pt;
            }
            QLabel#statusLabel {
                color: #8bd3ff;
                padding: 0 8px;
            }
            QCheckBox {
                spacing: 6px;
            }
            QTabWidget::pane {
                border: 1px solid #30363d;
                border-radius: 6px;
                background: #151a20;
            }
            QTabBar::tab {
                background: #26313d;
                color: #e6edf3;
                border: 1px solid #3a4654;
                padding: 7px 14px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #1f6feb;
            }
            QLabel#aboutName {
                color: #f4fbff;
                font-size: 16pt;
                font-weight: 700;
            }
            QWidget#sidebarFooter {
                background: transparent;
            }
            QLabel#footerText {
                color: #9fb0bf;
                font-size: 9pt;
            }
            QToolButton#footerGitHubButton {
                background: transparent;
                border: 0;
                padding: 2px;
                min-width: 22px;
                min-height: 22px;
            }
            QToolButton#footerGitHubButton:hover {
                background: #26313d;
                border-radius: 4px;
            }
            """
            + theme_overrides
            + self._text_color_styles()
        )
        self.mdi.setBackground(QBrush(QColor(mdi_background)))
