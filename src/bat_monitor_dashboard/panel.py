import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional

import psutil
from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from .constants import ANSI_PATTERN, CONTROL_CHAR_PATTERN, console_encoding, user_config_path
from .models import MonitorTask


class MonitorPanel(QWidget):
    def __init__(self, task: MonitorTask, edit_callback=None, log_memory_enabled: bool = True):
        super().__init__()
        self.task = task
        self.edit_callback = edit_callback
        self.log_memory_enabled = log_memory_enabled
        self.process: Optional[QProcess] = None
        self.detached_process: Optional[subprocess.Popen] = None
        self.detached_pid: Optional[int] = None
        self.log_path = user_config_path().parent / "logs" / f"{task.task_id}.log"
        self.pid_path = user_config_path().parent / "logs" / f"{task.task_id}.pid"
        self.log_read_pos = 0
        self.log_buffer: List[str] = []
        self.log_buffer_chars = 0
        self.log_flushing = False

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
        self.log_flush_timer = QTimer(self)
        self.log_flush_timer.timeout.connect(self.flush_log)
        self.log_flush_timer.start(2000)
        if self.log_memory_enabled:
            self._load_recent_log()
            self._restore_detached_pid()
        self.log_tail_timer = QTimer(self)
        self.log_tail_timer.timeout.connect(self._tail_log_file)
        if self.log_memory_enabled:
            self.log_tail_timer.start(1000)

    def _edit(self) -> None:
        if self.edit_callback:
            self.edit_callback(self.task.task_id)

    def is_running(self) -> bool:
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            return True
        if self.detached_process is not None and self.detached_process.poll() is None:
            return True
        if self.detached_process is not None and self.detached_process.poll() is not None:
            self.detached_process = None
        if self.detached_pid is not None and psutil.pid_exists(self.detached_pid):
            return True
        if self.detached_pid is not None:
            self.detached_pid = None
            self._clear_pid_file()
            self.status_label.setText("已停止")
        return False

    def start(self) -> None:
        if self.is_running():
            self.append_line("[dashboard] 任務已在執行中。")
            return

        bat_path = Path(self.task.bat_path)
        if not bat_path.exists():
            self.append_line(f"[dashboard] BAT 不存在：{self.task.bat_path}")
            self.status_label.setText("檔案不存在")
            return

        if self.log_memory_enabled:
            self._start_detached_with_log(bat_path)
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
        env.insert("VUE_CLI_PROGRESS", "false")
        env.insert("WEBPACK_PROGRESS", "false")
        env.insert("TERM", "dumb")
        self.process.setProcessEnvironment(env)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.process.start()
        self.status_label.setText("執行中")
        self.append_line(f"[dashboard] 啟動：{bat_path}")

    def _start_detached_with_log(self, bat_path: Path) -> None:
        env = self._process_environment()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._clear_log_if_over_limit()
        self.append_line(f"[dashboard] 啟動：{bat_path}")
        self.flush_log()

        create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        create_new_process_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        with self.log_path.open("ab") as log_file:
            self.detached_process = subprocess.Popen(
                ["cmd", "/c", "call", str(bat_path)],
                cwd=self.task.workdir or str(bat_path.parent),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
                creationflags=create_no_window | create_new_process_group,
            )
        self.detached_pid = int(self.detached_process.pid)
        self.pid_path.write_text(str(self.detached_pid), encoding="ascii")
        self.log_read_pos = self.log_path.stat().st_size if self.log_path.exists() else 0
        self.status_label.setText("執行中")
        self.log_tail_timer.start(1000)

    def stop(self, wait: bool = False) -> None:
        if not self.is_running():
            self.status_label.setText("已停止")
            return
        pid = self._running_pid()
        if not pid:
            self.status_label.setText("已停止")
            return
        self.status_label.setText("停止中")
        self.append_line(f"[dashboard] 送出停止 process tree 指令：PID {pid}")
        self.flush_log()
        create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        command = ["taskkill", "/PID", str(pid), "/T", "/F"]
        if wait:
            try:
                subprocess.run(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=create_no_window,
                    timeout=8,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                self.append_line(f"[dashboard] 停止逾時：PID {pid}")
            if self.process:
                self.process.waitForFinished(3000)
            self.flush_log()
            if self.detached_pid == pid:
                self.detached_pid = None
                self.detached_process = None
                self._clear_pid_file()
                self.status_label.setText("已停止")
        else:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=create_no_window,
            )
            if self.detached_pid == pid:
                self.detached_pid = None
                self.detached_process = None
                self._clear_pid_file()
                QTimer.singleShot(1200, lambda: self.status_label.setText("已停止"))

    def restart(self) -> None:
        self.stop()
        QTimer.singleShot(1500, self.start)

    def _process_environment(self) -> dict:
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        env["NO_COLOR"] = "1"
        env["FORCE_COLOR"] = "0"
        env["NPM_CONFIG_COLOR"] = "false"
        env["npm_config_color"] = "false"
        env["VUE_CLI_PROGRESS"] = "false"
        env["WEBPACK_PROGRESS"] = "false"
        env["TERM"] = "dumb"
        return env

    def _running_pid(self) -> Optional[int]:
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            return int(self.process.processId())
        if self.detached_process is not None and self.detached_process.poll() is None:
            return int(self.detached_process.pid)
        if self.detached_pid is not None and psutil.pid_exists(self.detached_pid):
            return int(self.detached_pid)
        return None

    def _restore_detached_pid(self) -> None:
        if not self.pid_path.exists():
            return
        try:
            pid = int(self.pid_path.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return
        if psutil.pid_exists(pid):
            self.detached_pid = pid
            self.status_label.setText("執行中")
        else:
            self._clear_pid_file()

    def _clear_pid_file(self) -> None:
        try:
            self.pid_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _clear_log_if_over_limit(self) -> None:
        max_bytes = max(1, self.task.log_max_mb) * 1024 * 1024
        try:
            if self.log_path.exists() and self.log_path.stat().st_size > max_bytes:
                self.log_path.write_text("", encoding="utf-8")
                self.log_read_pos = 0
        except OSError:
            pass

    def _tail_log_file(self) -> None:
        if not self.log_memory_enabled or not self.log_path.exists():
            return
        self._clear_log_if_over_limit()
        try:
            current_size = self.log_path.stat().st_size
            if current_size < self.log_read_pos:
                self.log_read_pos = 0
            if current_size == self.log_read_pos:
                return
            with self.log_path.open("rb") as file:
                file.seek(self.log_read_pos)
                raw = file.read()
                self.log_read_pos = file.tell()
        except OSError:
            return
        if not raw:
            return
        text = self._decode_output(raw)
        self._append_terminal_text(self._prepare_log_text(text))
        self._trim_lines()

    def append_line(self, text: str) -> None:
        self.output.moveCursor(QTextCursor.End)
        line = text.rstrip("\r\n") + "\n"
        self.output.insertPlainText(line)
        self.output.moveCursor(QTextCursor.End)
        self._buffer_log_text(line)
        self._trim_lines()

    def _read_output(self) -> None:
        if not self.process:
            return
        raw = bytes(self.process.readAllStandardOutput())
        text = self._decode_output(raw)
        self._buffer_log_text(self._prepare_log_text(text))
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
                if self._is_noisy_progress_line(self._current_output_line_text()):
                    self._clear_current_output_line()
                else:
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

    def _current_output_line_text(self) -> str:
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.select(QTextCursor.LineUnderCursor)
        return cursor.selectedText()

    def _is_noisy_progress_line(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if stripped == "onPlugin)":
            return True
        if re.fullmatch(r"\d?\)+", stripped):
            return True
        if re.fullmatch(r"\[\d+%]\s+.*", stripped):
            return True
        return False

    def _clear_output(self) -> None:
        self.output.clear()

    def _load_recent_log(self) -> None:
        if not self.log_path.exists():
            return
        try:
            text = self.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        lines = text.splitlines()
        if not lines:
            return
        recent = "\n".join(lines[-self.task.max_lines:])
        self.output.setPlainText(recent + "\n")
        self.output.moveCursor(QTextCursor.End)
        self.log_read_pos = self.log_path.stat().st_size if self.log_path.exists() else 0
        self._trim_lines()

    def _prepare_log_text(self, text: str) -> str:
        prepared = []
        normalized = text.replace("\r\n", "\n").replace("\n\r", "\n")
        for part in normalized.splitlines(keepends=True):
            has_newline = part.endswith("\n")
            line = part[:-1] if has_newline else part
            if "\r" in line:
                line = line.split("\r")[-1]
            if self._is_noisy_progress_line(line):
                continue
            prepared.append(line + ("\n" if has_newline else ""))
        return "".join(prepared)

    def _buffer_log_text(self, text: str) -> None:
        if not self.log_memory_enabled or not text:
            return
        self.log_buffer.append(text)
        self.log_buffer_chars += len(text)
        if self.log_buffer_chars >= 32768 and not self.log_flushing:
            self.flush_log()

    def flush_log(self) -> None:
        if not self.log_memory_enabled:
            self.log_buffer.clear()
            self.log_buffer_chars = 0
            return
        if self.log_flushing:
            return
        self.log_flushing = True
        try:
            if self.process and self.process.bytesAvailable():
                raw = bytes(self.process.readAllStandardOutput())
                if raw:
                    text = self._decode_output(raw)
                    self._buffer_log_text(self._prepare_log_text(text))
                    self._append_terminal_text(text)
            if not self.log_buffer:
                return
            text = "".join(self.log_buffer)
            self.log_buffer.clear()
            self.log_buffer_chars = 0
            encoded = text.encode("utf-8", errors="replace")
            max_bytes = max(1, self.task.log_max_mb) * 1024 * 1024
            if len(encoded) > max_bytes:
                encoded = encoded[-max_bytes:]
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                current_size = self.log_path.stat().st_size if self.log_path.exists() else 0
                mode = "ab"
                if current_size + len(encoded) > max_bytes:
                    mode = "wb"
                with self.log_path.open(mode) as file:
                    file.write(encoded)
            except OSError as exc:
                self.output.moveCursor(QTextCursor.End)
                self.output.insertPlainText(f"[dashboard] Log 寫入失敗：{exc}\n")
                self.output.moveCursor(QTextCursor.End)
        finally:
            self.log_flushing = False

    def set_log_memory_enabled(self, enabled: bool) -> None:
        self.log_memory_enabled = enabled
        if not enabled:
            self.log_buffer.clear()
            self.log_buffer_chars = 0

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
