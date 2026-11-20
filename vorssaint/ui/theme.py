"""
vorssaint.ui.theme
~~~~~~~~~~~~~~~~~~
Modern dark styling inspired by Vorssaint & GNOME Libadwaita.
"""

DARK_STYLESHEET = """
QMainWindow, QDialog, QWidget#CentralWidget {
    background-color: #1a1a1e;
    color: #e4e4e7;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Cantarell", sans-serif;
    font-size: 13px;
}

QMenu {
    background-color: #242429;
    color: #f4f4f5;
    border: 1px solid #383842;
    border-radius: 8px;
    padding: 6px;
}

QMenu::item {
    padding: 7px 24px 7px 12px;
    border-radius: 6px;
    margin: 2px 0px;
}

QMenu::item:selected {
    background-color: #3b82f6;
    color: #ffffff;
}

QMenu::separator {
    height: 1px;
    background-color: #33333d;
    margin: 6px 8px;
}

QMenu::item:disabled {
    color: #71717a;
}

/* PushButtons */
QPushButton {
    background-color: #2e2e36;
    color: #f4f4f5;
    border: 1px solid #3f3f4e;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #383844;
    border-color: #525266;
}

QPushButton:pressed {
    background-color: #24242b;
}

QPushButton:disabled {
    background-color: #1f1f24;
    color: #52525b;
    border-color: #27272a;
}

QPushButton#PrimaryButton {
    background-color: #3b82f6;
    color: #ffffff;
    border: none;
}

QPushButton#PrimaryButton:hover {
    background-color: #2563eb;
}

QPushButton#DangerButton {
    background-color: #ef4444;
    color: #ffffff;
    border: none;
}

QPushButton#DangerButton:hover {
    background-color: #dc2626;
}

/* LineEdit & TextEdit */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #222227;
    color: #f4f4f5;
    border: 1px solid #383844;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #3b82f6;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #60a5fa;
    background-color: #26262d;
}

/* ListWidget */
QListWidget {
    background-color: #1f1f24;
    border: 1px solid #31313a;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}

QListWidget::item {
    border-radius: 6px;
    padding: 8px 10px;
    margin: 2px 0px;
}

QListWidget::item:hover {
    background-color: #2a2a33;
}

QListWidget::item:selected {
    background-color: #3b82f6;
    color: #ffffff;
}

/* ScrollBar */
QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 8px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #474755;
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #636377;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* CheckBox / Switches */
QCheckBox {
    spacing: 8px;
    color: #e4e4e7;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #4a4a5a;
    background: #25252b;
}

QCheckBox::indicator:checked {
    background: #3b82f6;
    border-color: #3b82f6;
}

/* TabWidget */
QTabWidget::pane {
    border: 1px solid #31313a;
    border-radius: 8px;
    background: #1e1e23;
    padding: 12px;
}

QTabBar::tab {
    background: #26262d;
    color: #a1a1aa;
    padding: 8px 18px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 4px;
}

QTabBar::tab:selected {
    background: #1e1e23;
    color: #ffffff;
    font-weight: bold;
    border-bottom: 2px solid #3b82f6;
}
"""
