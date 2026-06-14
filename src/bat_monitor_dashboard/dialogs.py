from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .constants import DEFAULT_GEOMETRY, DISCORD_STATUS_TITLE, task_id
from .models import MonitorTask


class TaskDialog(QDialog):
    def __init__(self, parent: QWidget, task: Optional[MonitorTask] = None):
        super().__init__(parent)
        self.setWindowTitle("編輯監控任務")
        self.setModal(True)
        self.resize(560, 220)
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
        max_lines_minus_btn = QPushButton("-500")
        max_lines_plus_btn = QPushButton("+500")
        max_lines_minus_btn.clicked.connect(lambda: self._adjust_max_lines(-500))
        max_lines_plus_btn.clicked.connect(lambda: self._adjust_max_lines(500))

        max_lines_row = QHBoxLayout()
        max_lines_row.addWidget(self.max_lines_spin)
        max_lines_row.addWidget(max_lines_minus_btn)
        max_lines_row.addWidget(max_lines_plus_btn)
        max_lines_row.addStretch(1)

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

    def _adjust_max_lines(self, delta: int) -> None:
        self.max_lines_spin.setValue(self.max_lines_spin.value() + delta)

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
        self.webhook_edit.setEchoMode(QLineEdit.Password)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setValue(max(1, interval_minutes))
        self.interval_spin.setSuffix(" 分鐘")

        form = QFormLayout()
        form.addRow("", self.enabled_check)
        form.addRow("通知標題", self.status_title_edit)
        form.addRow("Webhook URL", self.webhook_edit)
        form.addRow("回傳間隔", self.interval_spin)

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
        discord_enabled: bool,
        webhook_url: str,
        interval_minutes: int,
        status_title: str,
        open_config_callback,
    ):
        super().__init__(parent)
        self.setWindowTitle("設定")
        self.setModal(True)
        self.resize(660, 300)
        self.result_settings: Optional[Dict] = None
        self.open_config_callback = open_config_callback

        self.restart_enabled_check = QCheckBox("每日定時全部重啟")
        self.restart_enabled_check.setChecked(restart_enabled)
        self.restart_time_edit = QTimeEdit()
        self.restart_time_edit.setDisplayFormat("HH:mm")
        self.restart_time_edit.setTime(restart_time)

        self.discord_enabled_check = QCheckBox("啟用 Discord 狀態更新")
        self.discord_enabled_check.setChecked(discord_enabled)
        self.status_title_edit = QLineEdit(status_title or DISCORD_STATUS_TITLE)
        self.webhook_edit = QLineEdit(webhook_url)
        self.webhook_edit.setEchoMode(QLineEdit.Password)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setValue(max(1, interval_minutes))
        self.interval_spin.setSuffix(" 分鐘")

        config_btn = QPushButton("開啟設定檔位置")
        config_btn.clicked.connect(self.open_config_callback)

        form = QFormLayout()
        form.addRow("", self.restart_enabled_check)
        form.addRow("重啟時間", self.restart_time_edit)
        form.addRow("", self.discord_enabled_check)
        form.addRow("Discord 通知標題", self.status_title_edit)
        form.addRow("Webhook URL", self.webhook_edit)
        form.addRow("Discord 回傳間隔", self.interval_spin)
        form.addRow("設定檔", config_btn)

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
        if self.discord_enabled_check.isChecked() and not webhook_url:
            QMessageBox.warning(self, "欄位錯誤", "啟用 Discord 通知時，請輸入 Webhook URL。")
            return
        self.result_settings = {
            "restart_enabled": self.restart_enabled_check.isChecked(),
            "restart_time": self.restart_time_edit.time(),
            "discord_enabled": self.discord_enabled_check.isChecked(),
            "status_title": self.status_title_edit.text().strip() or DISCORD_STATUS_TITLE,
            "webhook_url": webhook_url,
            "interval_minutes": self.interval_spin.value(),
        }
        self.accept()
