import sys
import os
from PySide6.QtWidgets import QApplication
from views.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Set application style
    app.setStyleSheet("""
        QMainWindow {
            background-color: #ffffff;
        }
        QWidget {
            background-color: #ffffff;
        }
        QLabel {
            color: #1c242e;
        }
        QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
            border: 2px solid #ccc;
            border-radius: 5px;
            padding: 5px;
            background-color: #ffffff;
            color: #1c242e;
        }
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
            border-color: #4CAF50;
        }
        QScrollArea {
            background: transparent;
            border: none;
        }
        QListWidget {
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 4px;
            background-color: white;
            color: #1c242e;
        }
        QListWidget::item:selected {
            background-color: #4CAF50;
            color: white;
        }
        QListWidget::item:hover {
            background-color: #e8f5e9;
        }
        QTabWidget::pane {
            border: 1px solid #d0d0d0;
            border-radius: 4px;
        }
        QTabBar::tab {
            padding: 8px 16px;
            margin-right: 2px;
            background: #f0f0f0;
            border-radius: 4px 4px 0 0;
        }
        QTabBar::tab:selected {
            background: white;
            border-bottom: 2px solid #4CAF50;
        }
        QTabBar::tab:hover {
            background: #e0e0e0;
        }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())