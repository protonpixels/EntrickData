from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QMessageBox, QDialog, QLineEdit,
    QTextEdit, QDialogButtonBox, QComboBox
)
from PySide6.QtCore import Qt
from core.project_types import ProjectType
import sqlite3


class ProjectCard(QFrame):
    """Styled card for displaying a project in the home view"""

    def __init__(self, project_data, parent=None):
        super().__init__(parent)
        self.project_data = project_data
        self.parent_app = parent
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(15, 15, 15, 15)

        # Header
        header_layout = QHBoxLayout()

        # Project type icon and name
        icon = ProjectType.get_icon(self.project_data['project_type'])
        name_label = QLabel(f"{icon} {self.project_data['name']}")
        name_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #1c242e;")
        header_layout.addWidget(name_label)

        # Type badge
        type_display = ProjectType.get_display_name(self.project_data['project_type'])
        type_badge = QLabel(type_display)
        type_badge.setStyleSheet("""
            background-color: #01433c;
            color: #d4f3ef;
            padding: 2px 12px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: 600;
        """)
        header_layout.addWidget(type_badge)

        header_layout.addStretch()

        date_label = QLabel(f"Updated: {self.project_data['updated_at'][:10]}")
        date_label.setStyleSheet("color: #666; font-size: 11px;")
        header_layout.addWidget(date_label)

        layout.addLayout(header_layout)

        # Headline
        if self.project_data.get('headline'):
            headline_label = QLabel(self.project_data['headline'])
            headline_label.setStyleSheet("color: #444; font-size: 13px;")
            headline_label.setWordWrap(True)
            layout.addWidget(headline_label)

        # Stats
        stats = self._get_stats()
        if stats:
            stats_label = QLabel(stats)
            stats_label.setStyleSheet("color: #888; font-size: 12px;")
            layout.addWidget(stats_label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        open_btn = QPushButton("Open")
        open_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        open_btn.clicked.connect(lambda: self.parent_app.open_project(self.project_data['id']))
        btn_layout.addWidget(open_btn)

        rename_btn = QPushButton("Rename")
        rename_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        rename_btn.clicked.connect(lambda: self.parent_app.rename_project(self.project_data['id']))
        btn_layout.addWidget(rename_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        delete_btn.clicked.connect(lambda: self.parent_app.delete_project(self.project_data['id']))
        btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.setLayout(layout)
        self.setStyleSheet("""
            ProjectCard {
                background-color: white;
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                margin: 5px;
            }
            ProjectCard:hover {
                border-color: #4CAF50;
                background-color: #f8f9fa;
            }
        """)

    # In shared_components.py, update _get_stats method:
    def _get_stats(self) -> str:
        stats = []

        if self.project_data['project_type'] == ProjectType.DATA_TABLE.value:
            try:
                data_path = self.project_data.get('data_path')
                if data_path and data_path != '':
                    conn = sqlite3.connect(data_path)
                    cursor = conn.cursor()
                    cursor.execute('SELECT COUNT(*) FROM data')
                    count = cursor.fetchone()[0]
                    conn.close()
                    stats.append(f"Rows: {count}")
                else:
                    stats.append("Rows: 0")
            except Exception:
                stats.append("Rows: 0")

        elif self.project_data['project_type'] == ProjectType.DATA_RESEARCH.value:
            try:
                data_path = self.project_data.get('data_path')
                if data_path and data_path != '':
                    conn = sqlite3.connect(data_path)
                    cursor = conn.cursor()
                    cursor.execute('SELECT COUNT(*) FROM pages')
                    count = cursor.fetchone()[0]
                    conn.close()
                    stats.append(f"Pages: {count}")
                else:
                    stats.append("Pages: 0")
            except Exception:
                stats.append("Pages: 0")

        elif self.project_data['project_type'] == ProjectType.DATA_DOCUMENT.value:
            try:
                data_path = self.project_data.get('data_path')
                if data_path and data_path != '':
                    conn = sqlite3.connect(data_path)
                    cursor = conn.cursor()
                    cursor.execute('SELECT COUNT(*) FROM pages')
                    count = cursor.fetchone()[0]
                    conn.close()
                    stats.append(f"Pages: {count}")
                else:
                    stats.append("Pages: 0")
            except Exception:
                stats.append("Pages: 0")

        return "  •  ".join(stats) if stats else ""


class NewProjectDialog(QDialog):
    """Dialog for creating a new project"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)

        # Project Name
        layout.addWidget(QLabel("Project Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter project name...")
        self.name_input.setStyleSheet("font-size: 14px; padding: 8px;")
        layout.addWidget(self.name_input)

        # Project Type
        layout.addWidget(QLabel("Project Type:"))
        self.type_combo = QComboBox()
        for type_val, display_name in ProjectType.get_all_types():
            self.type_combo.addItem(display_name, type_val)
        self.type_combo.setStyleSheet("font-size: 14px; padding: 8px;")

        # Add description label that updates when type changes
        self.type_desc_label = QLabel("")
        self.type_desc_label.setStyleSheet(
            "color: #666; font-size: 11px; padding: 4px 8px; background-color: #f5f5f5; border-radius: 4px;")
        self.type_desc_label.setWordWrap(True)
        self.type_combo.currentIndexChanged.connect(self.update_type_description)

        layout.addWidget(self.type_combo)
        layout.addWidget(self.type_desc_label)

        # Project Description
        layout.addWidget(QLabel("Description:"))
        self.headline_input = QTextEdit()
        self.headline_input.setPlaceholderText("Enter a brief description...")
        self.headline_input.setMaximumHeight(80)
        self.headline_input.setStyleSheet("font-size: 14px; padding: 8px;")
        layout.addWidget(self.headline_input)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.setStyleSheet("""
            QPushButton {
                padding: 8px 24px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton[text="OK"] {
                background-color: #4CAF50;
                color: white;
            }
            QPushButton[text="OK"]:hover { background-color: #45a049; }
            QPushButton[text="Cancel"] {
                background-color: #f44336;
                color: white;
            }
            QPushButton[text="Cancel"]:hover { background-color: #d32f2f; }
        """)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

        # Initialize description
        self.update_type_description()

    def update_type_description(self):
        """Update the type description label"""
        project_type = self.type_combo.currentData()
        description = ProjectType.get_description(project_type)
        self.type_desc_label.setText(f"ℹ️ {description}")

    def get_project_data(self):
        """Get the project data from the dialog"""
        name = self.name_input.text().strip()
        project_type = self.type_combo.currentData()
        headline = self.headline_input.toPlainText().strip()

        # Default metadata based on project type
        if project_type == ProjectType.DATA_TABLE.value:
            metadata = {
                'column_config': [
                    {'name': 'ID', 'type': 'integer', 'required': True},
                    {'name': 'Name', 'type': 'text', 'required': True},
                    {'name': 'Description', 'type': 'text', 'required': False}
                ]
            }
        elif project_type == ProjectType.DATA_DOCUMENT.value:
            metadata = {
                'document_count': 0,
                'page_count': 0
            }
        else:
            metadata = {}

        return name, project_type, headline, metadata