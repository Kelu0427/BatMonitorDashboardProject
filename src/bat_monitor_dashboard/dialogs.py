from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QTime, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .constants import (
    APP_VERSION,
    DEFAULT_GEOMETRY,
    DEFAULT_LOG_MAX_MB,
    DISCORD_STATUS_TITLE,
    GITHUB_PROFILE_URL,
    GITHUB_REPOSITORY_URL,
    resource_path,
    task_id,
)
from .models import MonitorTask


def build_spin_row(spin: QSpinBox) -> QHBoxLayout:
    spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    row = QHBoxLayout()
    row.addWidget(spin)
    row.addStretch(1)
    return row


class TaskDialog(QDialog):
    def __init__(self, parent: QWidget, task: Optional[MonitorTask] = None):
        super().__init__(parent)
        self.setWindowTitle("編輯監控任務")
        self.setModal(True)
        self.resize(560, 260)
        self.result_task: Optional[MonitorTask] = None
        self.original_task = task

        self.name_edit = QLineEdit(task.name if task else "")
        self.bat_edit = QLineEdit(task.bat_path if task else "")
        self.workdir_edit = QLineEdit(task.workdir if task else "")
        self.auto_start_check = QCheckBox("啟動儀表板時自動執行")
        self.auto_start_check.setChecked(task.auto_start if task else True)
        self.max_lines_spin = QSpinBox()
        self.max_lines_spin.setRange(100, 50000)
        self.max_lines_spin.setSingleStep(500)
        self.max_lines_spin.setValue(task.max_lines if task else 3000)
        self.max_lines_spin.setMinimumWidth(110)
        self.log_max_mb_spin = QSpinBox()
        self.log_max_mb_spin.setRange(1, 1024)
        self.log_max_mb_spin.setSingleStep(5)
        self.log_max_mb_spin.setValue(task.log_max_mb if task else DEFAULT_LOG_MAX_MB)
        self.log_max_mb_spin.setSuffix(" MB")
        self.log_max_mb_spin.setMinimumWidth(110)
        max_lines_row = build_spin_row(self.max_lines_spin)
        log_max_mb_row = build_spin_row(self.log_max_mb_spin)

        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(["utf-8", "cp950", "big5", "系統預設"])
        current_encoding = task.output_encoding if task else "utf-8"
        if current_encoding not in ["utf-8", "cp950", "big5", "系統預設"]:
            current_encoding = "utf-8"
        self.encoding_combo.setCurrentText(current_encoding)

        browse_bat_btn = QPushButton("瀏覽...")
        browse_bat_btn.clicked.connect(self._browse_bat)
        browse_workdir_btn = QPushButton("瀏覽...")
        browse_workdir_btn.clicked.connect(self._browse_workdir)

        bat_row = QHBoxLayout()
        bat_row.addWidget(self.bat_edit, 1)
        bat_row.addWidget(browse_bat_btn)

        workdir_row = QHBoxLayout()
        workdir_row.addWidget(self.workdir_edit, 1)
        workdir_row.addWidget(browse_workdir_btn)

        form = QFormLayout()
        form.addRow("任務名稱", self.name_edit)
        form.addRow("BAT 路徑", bat_row)
        form.addRow("工作目錄", workdir_row)
        form.addRow("保留最近行數", max_lines_row)
        form.addRow("Log 檔案上限", log_max_mb_row)
        form.addRow("輸出編碼", self.encoding_combo)
        form.addRow("", self.auto_start_check)

        save_btn = QPushButton("儲存")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)

    def _browse_bat(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "選擇 BAT 檔案", "", "Batch 檔 (*.bat);;所有檔案 (*.*)")
        if file_path:
            self.bat_edit.setText(file_path)
            if not self.workdir_edit.text().strip():
                self.workdir_edit.setText(str(Path(file_path).parent))

    def _browse_workdir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "選擇工作目錄")
        if folder:
            self.workdir_edit.setText(folder)

    def _save(self) -> None:
        name = self.name_edit.text().strip()
        bat_path = self.bat_edit.text().strip()
        workdir = self.workdir_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "欄位錯誤", "請輸入任務名稱。")
            return
        if not bat_path:
            QMessageBox.warning(self, "欄位錯誤", "請選擇 BAT 路徑。")
            return
        if not Path(bat_path).exists():
            QMessageBox.warning(self, "檔案不存在", "BAT 檔案不存在，請確認路徑。")
            return
        if not workdir:
            workdir = str(Path(bat_path).parent)
        if not Path(workdir).exists():
            QMessageBox.warning(self, "資料夾不存在", "工作目錄不存在，請確認路徑。")
            return

        geometry = self.original_task.geometry if self.original_task else dict(DEFAULT_GEOMETRY)
        self.result_task = MonitorTask(
            task_id=self.original_task.task_id if self.original_task else task_id(),
            name=name,
            bat_path=bat_path,
            workdir=workdir,
            auto_start=self.auto_start_check.isChecked(),
            max_lines=self.max_lines_spin.value(),
            log_max_mb=self.log_max_mb_spin.value(),
            output_encoding=self.encoding_combo.currentText(),
            geometry=geometry,
        )
        self.accept()

class DiscordSettingsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        enabled: bool,
        webhook_url: str,
        interval_minutes: int,
        status_title: str,
    ):
        super().__init__(parent)
        self.setWindowTitle("Discord 通知設定")
        self.setModal(True)
        self.resize(620, 230)
        self.result_settings: Optional[Dict] = None

        self.enabled_check = QCheckBox("啟用 Discord 狀態更新")
        self.enabled_check.setChecked(enabled)
        self.status_title_edit = QLineEdit(status_title or DISCORD_STATUS_TITLE)
        self.webhook_edit = QLineEdit(webhook_url)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setValue(max(1, interval_minutes))
        self.interval_spin.setSuffix(" 分鐘")
        interval_row = build_spin_row(self.interval_spin)

        form = QFormLayout()
        form.addRow("", self.enabled_check)
        form.addRow("通知標題", self.status_title_edit)
        form.addRow("Webhook URL", self.webhook_edit)
        form.addRow("回傳間隔", interval_row)

        save_btn = QPushButton("儲存")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)

    def _save(self) -> None:
        webhook_url = self.webhook_edit.text().strip()
        if self.enabled_check.isChecked() and not webhook_url:
            QMessageBox.warning(self, "欄位錯誤", "啟用 Discord 通知時，請輸入 Webhook URL。")
            return
        self.result_settings = {
            "enabled": self.enabled_check.isChecked(),
            "status_title": self.status_title_edit.text().strip() or DISCORD_STATUS_TITLE,
            "webhook_url": webhook_url,
            "interval_minutes": self.interval_spin.value(),
        }
        self.accept()

class AppSettingsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        restart_enabled: bool,
        restart_time: QTime,
        auto_update_enabled: bool,
        log_memory_enabled: bool,
        log_max_mb: int,
        discord_enabled: bool,
        webhook_url: str,
        interval_minutes: int,
        status_title: str,
        open_config_callback,
        check_update_callback,
    ):
        super().__init__(parent)
        self.setWindowTitle("設定")
        self.setModal(True)
        self.resize(660, 370)
        self.result_settings: Optional[Dict] = None
        self.open_config_callback = open_config_callback
        self.check_update_callback = check_update_callback

        self.restart_enabled_check = QCheckBox("每日定時全部重啟")
        self.restart_enabled_check.setChecked(restart_enabled)
        self.restart_time_edit = QTimeEdit()
        self.restart_time_edit.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.restart_time_edit.setDisplayFormat("HH:mm")
        self.restart_time_edit.setTime(restart_time)
        self.auto_update_enabled_check = QCheckBox("自動檢查更新")
        self.auto_update_enabled_check.setChecked(auto_update_enabled)
        self.log_memory_enabled_check = QCheckBox("啟用 Log 記憶功能")
        self.log_memory_enabled_check.setChecked(log_memory_enabled)
        self.log_max_mb_spin = QSpinBox()
        self.log_max_mb_spin.setRange(1, 1024)
        self.log_max_mb_spin.setSingleStep(5)
        self.log_max_mb_spin.setValue(max(1, log_max_mb))
        self.log_max_mb_spin.setSuffix(" MB")
        log_max_mb_row = build_spin_row(self.log_max_mb_spin)

        self.discord_enabled_check = QCheckBox("啟用 Discord 狀態更新")
        self.discord_enabled_check.setChecked(discord_enabled)
        self.status_title_edit = QLineEdit(status_title or DISCORD_STATUS_TITLE)
        self.webhook_edit = QLineEdit(webhook_url)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setValue(max(1, interval_minutes))
        self.interval_spin.setSuffix(" 分鐘")
        interval_row = build_spin_row(self.interval_spin)

        config_btn = QPushButton("開啟設定檔位置")
        config_btn.clicked.connect(self.open_config_callback)
        check_update_btn = QPushButton("立即檢查更新")
        check_update_btn.clicked.connect(self.check_update_callback)

        tabs = QTabWidget()

        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        general_layout.setContentsMargins(10, 10, 10, 10)
        general_layout.setSpacing(10)

        schedule_group = QGroupBox("啟動與排程")
        schedule_form = QFormLayout(schedule_group)
        schedule_form.addRow("", self.restart_enabled_check)
        schedule_form.addRow("重啟時間", self.restart_time_edit)

        update_group = QGroupBox("更新")
        update_form = QFormLayout(update_group)
        update_form.addRow("", self.auto_update_enabled_check)
        update_form.addRow("手動更新", check_update_btn)

        config_group = QGroupBox("設定檔")
        config_form = QFormLayout(config_group)
        config_form.addRow("位置", config_btn)

        general_layout.addWidget(schedule_group)
        general_layout.addWidget(update_group)
        general_layout.addWidget(config_group)
        general_layout.addStretch(1)
        tabs.addTab(general_tab, "一般")

        log_tab = QWidget()
        log_form = QFormLayout(log_tab)
        log_form.addRow("", self.log_memory_enabled_check)
        log_form.addRow("全部任務 Log 上限", log_max_mb_row)
        tabs.addTab(log_tab, "Log")

        discord_tab = QWidget()
        discord_form = QFormLayout(discord_tab)
        discord_form.addRow("", self.discord_enabled_check)
        discord_form.addRow("Discord 通知標題", self.status_title_edit)
        discord_form.addRow("Webhook URL", self.webhook_edit)
        discord_form.addRow("Discord 回傳間隔", interval_row)
        tabs.addTab(discord_tab, "Discord")

        tabs.addTab(self._build_about_tab(), "關於")

        save_btn = QPushButton("儲存")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addLayout(buttons)

    def _save(self) -> None:
        webhook_url = self.webhook_edit.text().strip()
        if self.discord_enabled_check.isChecked() and not webhook_url:
            QMessageBox.warning(self, "欄位錯誤", "啟用 Discord 通知時，請輸入 Webhook URL。")
            return
        self.result_settings = {
            "restart_enabled": self.restart_enabled_check.isChecked(),
            "restart_time": self.restart_time_edit.time(),
            "auto_update_enabled": self.auto_update_enabled_check.isChecked(),
            "log_memory_enabled": self.log_memory_enabled_check.isChecked(),
            "log_max_mb": self.log_max_mb_spin.value(),
            "discord_enabled": self.discord_enabled_check.isChecked(),
            "status_title": self.status_title_edit.text().strip() or DISCORD_STATUS_TITLE,
            "webhook_url": webhook_url,
            "interval_minutes": self.interval_spin.value(),
        }
        self.accept()

    def _build_about_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        avatar_label = QLabel()
        avatar = QPixmap(str(resource_path("assets/github-avatar.png")))
        if not avatar.isNull():
            avatar_label.setPixmap(self._rounded_pixmap(avatar, 112))
        avatar_label.setAlignment(Qt.AlignCenter)

        name_label = QLabel("Kelu0427")
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setObjectName("aboutName")

        version_label = QLabel(f"BAT Monitor Dashboard v{APP_VERSION}")
        version_label.setAlignment(Qt.AlignCenter)

        intro_label = QLabel(
            "持續學習、喜歡打造有想像力工具的開發者。\n"
            "專注於：軟體開發、自動化、介面優化，以及更好的人機互動體驗。"
        )
        intro_label.setWordWrap(True)
        intro_label.setAlignment(Qt.AlignCenter)

        profile_btn = QPushButton("GitHub 個人頁")
        profile_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_PROFILE_URL)))
        repo_btn = QPushButton("專案頁面")
        repo_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_REPOSITORY_URL)))

        link_row = QHBoxLayout()
        link_row.addStretch(1)
        link_row.addWidget(profile_btn)
        link_row.addWidget(repo_btn)
        link_row.addStretch(1)

        layout.addStretch(1)
        layout.addWidget(avatar_label)
        layout.addWidget(name_label)
        layout.addWidget(version_label)
        layout.addWidget(intro_label)
        layout.addLayout(link_row)
        layout.addStretch(1)
        return tab

    def _rounded_pixmap(self, source: QPixmap, size: int) -> QPixmap:
        scaled = source.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = max(0, (scaled.width() - size) // 2)
        y = max(0, (scaled.height() - size) // 2)
        cropped = scaled.copy(x, y, size, size)

        rounded = QPixmap(size, size)
        rounded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, cropped)
        painter.end()
        return rounded
