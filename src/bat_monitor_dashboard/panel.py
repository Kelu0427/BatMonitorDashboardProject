import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from .constants import ANSI_PATTERN, CONTROL_CHAR_PATTERN, console_encoding
from .models import MonitorTask


class MonitorPanel(QWidget):
    def __init__(self, task: MonitorTask, edit_callback=None):
        super().__init__()
        self.task = task
        self.edit_callback = edit_callback
        self.process: Optional[QProcess] = None

        self.status_label = QLabel("已停止")
        self.status_label.setObjectName("statusLabel")
        self.edit_btn = QPushButton("編輯")
        self.start_btn = QPushButton("啟動")
        self.stop_btn = QPushButton("停止")
        self.restart_btn = QPushButton("重啟")
        self.clear_btn = QPushButton("清空")

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QTextEdit.NoWrap)
        self.output.setObjectName("terminalOutput")

        top = QHBoxLayout()
        top.addWidget(QLabel(task.name))
        top.addStretch(1)
        top.addWidget(self.status_label)
        top.addWidget(self.edit_btn)
        top.addWidget(self.start_btn)
        top.addWidget(self.stop_btn)
        top.addWidget(self.restart_btn)
        top.addWidget(self.clear_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(top)
        layout.addWidget(self.output, 1)

        self.edit_btn.clicked.connect(self._edit)
        self.start_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)
        self.restart_btn.clicked.connect(self.restart)
        self.clear_btn.clicked.connect(self._clear_output)

    def _edit(self) -> None:
        if self.edit_callback:
            self.edit_callback(self.task.task_id)

    def is_running(self) -> bool:
        return self.process is not None and self.process.state() != QProcess.NotRunning

    def start(self) -> None:
        if self.is_running():
            self.append_line("[dashboard] 任務已在執行中。")
            return

        bat_path = Path(self.task.bat_path)
        if not bat_path.exists():
            self.append_line(f"[dashboard] BAT 不存在：{self.task.bat_path}")
            self.status_label.setText("檔案不存在")
            return

        self.process = QProcess(self)
        self.process.setProgram("cmd")
        self.process.setArguments(["/c", "call", str(bat_path)])
        self.process.setWorkingDirectory(self.task.workdir or str(bat_path.parent))
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("NO_COLOR", "1")
        env.insert("FORCE_COLOR", "0")
        env.insert("NPM_CONFIG_COLOR", "false")
        env.insert("npm_config_color", "false")
        env.insert("TERM", "dumb")
        self.process.setProcessEnvironment(env)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.process.start()
        self.status_label.setText("執行中")
        self.append_line(f"[dashboard] 啟動：{bat_path}")

    def stop(self) -> None:
        if not self.is_running():
            self.status_label.setText("已停止")
            return
        pid = int(self.process.processId())
        self.status_label.setText("停止中")
        self.append_line(f"[dashboard] 送出停止 process tree 指令：PID {pid}")
        create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        subprocess.Popen(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=create_no_window,
        )

    def restart(self) -> None:
        self.stop()
        QTimer.singleShot(1500, self.start)

    def append_line(self, text: str) -> None:
        self.output.moveCursor(QTextCursor.End)
        self.output.insertPlainText(text.rstrip("\r\n") + "\n")
        self.output.moveCursor(QTextCursor.End)
        self._trim_lines()

    def _read_output(self) -> None:
        if not self.process:
            return
        raw = bytes(self.process.readAllStandardOutput())
        text = self._decode_output(raw)
        self._append_terminal_text(text)
        self._trim_lines()

    def _decode_output(self, raw: bytes) -> str:
        encodings = []
        configured = self.task.output_encoding
        if configured == "系統預設":
            encodings.append(console_encoding())
        else:
            encodings.append(configured)
        for fallback in ("utf-8", console_encoding(), "cp950", "big5"):
            if fallback not in encodings:
                encodings.append(fallback)
        for encoding in encodings:
            try:
                return self._clean_terminal_text(raw.decode(encoding, errors="strict"))
            except UnicodeDecodeError:
                continue
        return self._clean_terminal_text(raw.decode(encodings[0], errors="replace"))

    def _clean_terminal_text(self, text: str) -> str:
        text = ANSI_PATTERN.sub("", text)
        text = CONTROL_CHAR_PATTERN.sub("", text)
        return text.replace("\r\n", "\n").replace("\n\r", "\n")

    def _append_terminal_text(self, text: str) -> None:
        self.output.moveCursor(QTextCursor.End)
        for char in text:
            if char == "\r":
                self._clear_current_output_line()
            elif char == "\n":
                self.output.insertPlainText("\n")
            elif char == "\b":
                self.output.textCursor().deletePreviousChar()
            else:
                self.output.insertPlainText(char)
        self.output.moveCursor(QTextCursor.End)

    def _clear_current_output_line(self) -> None:
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.select(QTextCursor.LineUnderCursor)
        cursor.removeSelectedText()
        self.output.setTextCursor(cursor)

    def _clear_output(self) -> None:
        self.output.clear()

    def _trim_lines(self) -> None:
        max_lines = self.task.max_lines
        document = self.output.document()
        extra = document.blockCount() - max_lines
        if extra <= 0:
            return
        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.Start)
        for _ in range(extra):
            cursor.select(QTextCursor.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

    def _finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self.status_label.setText(f"已停止 ({exit_code})")
        self.append_line(f"[dashboard] 任務已停止，結束代碼：{exit_code}")

    def _error(self, error: QProcess.ProcessError) -> None:
        self.status_label.setText("錯誤")
        self.append_line(f"[dashboard] process 錯誤：{error}")
