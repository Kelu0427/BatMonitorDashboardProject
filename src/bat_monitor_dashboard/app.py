import sys

from PySide6.QtWidgets import QApplication

from .dashboard import DashboardWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("BAT 監控儀表板")
    window = DashboardWindow()
    window.show()
    sys.exit(app.exec())
