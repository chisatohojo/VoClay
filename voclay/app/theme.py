from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


COLORS = {
    "background": "#10131A",
    "background_alt": "#171B24",
    "panel": "#202532",
    "panel_light": "#2A3040",
    "accent": "#79D8D0",
    "accent_alt": "#B89CFF",
    "warning": "#FFB86B",
    "text": "#E8ECF2",
    "text_muted": "#AAB3C2",
    "border": "#353D51",
}


def asset_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / name


def apply_theme(app: QApplication) -> None:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(COLORS["background"]))
    palette.setColor(QPalette.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Base, QColor(COLORS["panel"]))
    palette.setColor(QPalette.AlternateBase, QColor(COLORS["panel_light"]))
    palette.setColor(QPalette.ToolTipBase, QColor(COLORS["panel_light"]))
    palette.setColor(QPalette.ToolTipText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.Button, QColor(COLORS["panel_light"]))
    palette.setColor(QPalette.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Highlight, QColor(COLORS["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor(COLORS["background"]))
    app.setPalette(palette)

    app.setStyleSheet(
        f"""
        QWidget {{
            background-color: {COLORS["background"]};
            color: {COLORS["text"]};
            font-family: "Segoe UI", "Yu Gothic UI", sans-serif;
            font-size: 13px;
        }}

        QFrame#TopBar,
        QFrame#InspectorPanel {{
            background-color: {COLORS["panel"]};
            border: 1px solid {COLORS["border"]};
            border-radius: 8px;
        }}

        QLabel#AppTitle {{
            color: {COLORS["text"]};
            font-size: 18px;
            font-weight: 700;
        }}

        QLabel#MutedLabel {{
            color: {COLORS["text_muted"]};
        }}

        QToolButton,
        QPushButton {{
            background-color: {COLORS["panel_light"]};
            color: {COLORS["text"]};
            border: 1px solid {COLORS["border"]};
            border-radius: 7px;
            padding: 7px 12px;
        }}

        QToolButton:hover,
        QPushButton:hover {{
            border-color: {COLORS["accent"]};
        }}

        QToolButton:pressed,
        QPushButton:pressed {{
            background-color: {COLORS["background_alt"]};
        }}

        QToolButton:disabled,
        QPushButton:disabled {{
            color: {COLORS["text_muted"]};
            background-color: {COLORS["background_alt"]};
            border-color: {COLORS["panel"]};
        }}

        QComboBox {{
            background-color: {COLORS["panel_light"]};
            color: {COLORS["text"]};
            border: 1px solid {COLORS["border"]};
            border-radius: 7px;
            padding: 6px 28px 6px 10px;
            min-width: 92px;
        }}

        QComboBox:hover {{
            border-color: {COLORS["accent"]};
        }}

        QComboBox:disabled {{
            color: {COLORS["text_muted"]};
            background-color: {COLORS["background_alt"]};
            border-color: {COLORS["panel"]};
        }}

        QStatusBar {{
            background-color: {COLORS["background_alt"]};
            color: {COLORS["text_muted"]};
            border-top: 1px solid {COLORS["border"]};
        }}

        QSlider::groove:horizontal {{
            height: 4px;
            background: {COLORS["background_alt"]};
            border-radius: 2px;
        }}

        QSlider::handle:horizontal {{
            width: 14px;
            height: 14px;
            margin: -5px 0;
            background: {COLORS["accent_alt"]};
            border-radius: 7px;
        }}

        QSplitter::handle {{
            background-color: {COLORS["background"]};
        }}
        """
    )
