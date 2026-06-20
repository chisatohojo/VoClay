from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from voclay.app.main_window import MainWindow  # noqa: E402
from voclay.app.theme import apply_theme, asset_path  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("VoClay")
    app.setOrganizationName("VoClay")
    apply_theme(app)

    icon_file = asset_path("voclay_icon_outer_background_transparent.png")
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
