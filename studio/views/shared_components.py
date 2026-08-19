# studio/views/shared_components.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QDialog, QLineEdit,
    QTextEdit, QDialogButtonBox, QComboBox
)
from PySide6.QtCore import Qt, Signal
from core.project_types import ProjectType
import sqlite3
import os
from typing import List, Dict, Optional


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

        # Container info
        if self.project_data.get('container_id'):
            try:
                if self.parent_app and hasattr(self.parent_app, 'db'):
                    container = self.parent_app.db.get_container(self.project_data['container_id'])
                    if container:
                        container_label = QLabel(f"📁 {container['name']}")
                        container_label.setStyleSheet("color: #666; font-size: 11px;")
                        header_layout.addWidget(container_label)
            except:
                pass

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
        open_btn.clicked.connect(
            lambda: self.parent_app.open_project(self.project_data['id']) if self.parent_app else None)
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
        rename_btn.clicked.connect(
            lambda: self.parent_app.rename_project(self.project_data['id']) if self.parent_app else None)
        btn_layout.addWidget(rename_btn)

        move_btn = QPushButton("📂 Move")
        move_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #F57C00; }
        """)
        move_btn.clicked.connect(
            lambda: self.parent_app._move_project(self.project_data['id']) if self.parent_app else None)
        btn_layout.addWidget(move_btn)

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
        delete_btn.clicked.connect(
            lambda: self.parent_app.delete_project(self.project_data['id']) if self.parent_app else None)
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

    def _get_stats(self) -> str:
        """Get project statistics for display"""
        stats = []
        project_type = self.project_data.get('project_type')
        data_path = self.project_data.get('data_path')

        if not data_path or not os.path.exists(data_path):
            return ""

        try:
            if project_type == ProjectType.DATA_TABLE.value:
                conn = sqlite3.connect(data_path)
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM data')
                count = cursor.fetchone()[0]
                conn.close()
                stats.append(f"Rows: {count}")

            elif project_type in [ProjectType.DATA_RESEARCH.value, ProjectType.DATA_DOCUMENT.value]:
                conn = sqlite3.connect(data_path)
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM pages')
                count = cursor.fetchone()[0]
                conn.close()
                stats.append(f"Pages: {count}")

            elif project_type == ProjectType.DATA_CHAT.value:
                # For chat projects, count messages across all sessions
                try:
                    conn = sqlite3.connect(data_path)
                    cursor = conn.cursor()
                    # Check if chat_messages table exists
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'")
                    if cursor.fetchone():
                        cursor.execute('SELECT COUNT(*) FROM chat_messages')
                        count = cursor.fetchone()[0]
                        stats.append(f"Messages: {count}")
                    else:
                        stats.append("Messages: 0")
                    conn.close()
                except:
                    stats.append("Messages: 0")

        except Exception as e:
            stats.append("Stats unavailable")

        return "  •  ".join(stats) if stats else ""


class CreateProjectDialog(QDialog):
    """Dialog for creating a new project with container selection"""

    project_created = Signal(int)  # Emits project_id when created

    def __init__(self, parent=None, db=None, container_id: int = None):
        super().__init__(parent)
        self.parent_app = parent
        self.db = db
        self.container_id = container_id
        self.project_id = None
        self.setWindowTitle("New Project")
        self.setModal(True)
        self.setMinimumWidth(550)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Container selection (if parent not specified)
        if self.container_id is None and self.db:
            layout.addWidget(QLabel("Location:"))
            self.container_combo = QComboBox()
            self.container_combo.addItem("📁 Root (No Folder)", None)

            # Add all containers
            containers = self.db.get_container_tree()
            self._add_containers_to_combo(containers, "")
            self.container_combo.setStyleSheet(
                "font-size: 14px; padding: 8px; border: 1px solid #ddd; border-radius: 4px;")
            layout.addWidget(self.container_combo)
        elif self.container_id:
            # Show which container the project will be created in
            container = self.db.get_container(self.container_id) if self.db else None
            container_name = container['name'] if container else "Root"
            location_label = QLabel(f"📁 Location: {container_name}")
            location_label.setStyleSheet(
                "font-size: 13px; color: #666; padding: 4px 8px; background-color: #f5f5f5; border-radius: 4px;")
            layout.addWidget(location_label)

        # Project Name
        layout.addWidget(QLabel("Project Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter project name...")
        self.name_input.setStyleSheet("font-size: 14px; padding: 8px; border: 1px solid #ddd; border-radius: 4px;")
        self.name_input.textChanged.connect(self._validate_input)
        layout.addWidget(self.name_input)

        # Project Type
        layout.addWidget(QLabel("Project Type:"))
        self.type_combo = QComboBox()
        for type_val, display_name in ProjectType.get_all_types():
            self.type_combo.addItem(display_name, type_val)
        self.type_combo.setStyleSheet("font-size: 14px; padding: 8px; border: 1px solid #ddd; border-radius: 4px;")
        layout.addWidget(self.type_combo)

        # Type description
        self.type_desc_label = QLabel("")
        self.type_desc_label.setStyleSheet(
            "color: #666; font-size: 11px; padding: 4px 8px; background-color: #f5f5f5; border-radius: 4px;"
        )
        self.type_desc_label.setWordWrap(True)
        self.type_combo.currentIndexChanged.connect(self.update_type_description)
        layout.addWidget(self.type_desc_label)

        # Project Description
        layout.addWidget(QLabel("Description (optional):"))
        self.headline_input = QTextEdit()
        self.headline_input.setPlaceholderText("Enter a brief description...")
        self.headline_input.setMaximumHeight(80)
        self.headline_input.setStyleSheet("font-size: 14px; padding: 8px; border: 1px solid #ddd; border-radius: 4px;")
        layout.addWidget(self.headline_input)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #f44336; font-size: 12px;")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.setStyleSheet("""
            QPushButton {
                padding: 8px 24px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
        """)
        self.ok_button = button_box.button(QDialogButtonBox.Ok)
        self.ok_button.setText("Create")
        self.ok_button.setEnabled(False)
        self.ok_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 24px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:disabled {
                background-color: #ccc;
                color: #888;
            }
        """)
        self.cancel_button = button_box.button(QDialogButtonBox.Cancel)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 8px 24px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)

        button_box.accepted.connect(self._create_project)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)
        self.update_type_description()
        self.name_input.setFocus()

    def _add_containers_to_combo(self, containers: List[Dict], prefix: str):
        """Add containers recursively to the combo box"""
        for container in containers:
            self.container_combo.addItem(f"{prefix}📁 {container['name']}", container['id'])
            if container.get('children'):
                self._add_containers_to_combo(container['children'], f"{prefix}  ")

    def update_type_description(self):
        """Update the type description label"""
        project_type = self.type_combo.currentData()
        description = ProjectType.get_description(project_type)
        self.type_desc_label.setText(f"ℹ️ {description}")

    def _validate_input(self):
        """Validate the input fields"""
        name = self.name_input.text().strip()
        self.ok_button.setEnabled(len(name) > 0)
        self.error_label.setVisible(False)

    def _create_project(self):
        """Create the project"""
        name = self.name_input.text().strip()
        if not name:
            self.error_label.setText("Please enter a project name.")
            self.error_label.setVisible(True)
            return

        project_type = self.type_combo.currentData()
        headline = self.headline_input.toPlainText().strip()
        metadata = self._get_default_metadata(project_type)

        # Get container ID
        container_id = self.container_id
        if container_id is None and hasattr(self, 'container_combo'):
            container_id = self.container_combo.currentData()

        try:
            project_id = self.db.create_project(
                name=name,
                project_type=project_type,
                headline=headline,
                metadata=metadata,
                container_id=container_id
            )
            self.project_id = project_id
            self.project_created.emit(project_id)
            self.accept()
        except Exception as e:
            self.error_label.setText(f"Error creating project: {str(e)}")
            self.error_label.setVisible(True)

    def _get_default_metadata(self, project_type: str) -> Dict:
        """Get default metadata based on project type"""
        if project_type == ProjectType.DATA_TABLE.value:
            return {
                'column_config': [
                    {'name': 'ID', 'type': 'integer', 'required': True},
                    {'name': 'Name', 'type': 'text', 'required': True},
                    {'name': 'Description', 'type': 'text', 'required': False}
                ]
            }
        elif project_type == ProjectType.DATA_DOCUMENT.value:
            return {
                'document_count': 0,
                'page_count': 0
            }
        elif project_type == ProjectType.DATA_RESEARCH.value:
            return {
                'page_count': 0,
                'last_scraped': None
            }
        elif project_type == ProjectType.DATA_CHAT.value:
            return {
                'chat_sessions': {}
            }
        return {}

    def get_project_id(self) -> Optional[int]:
        """Get the created project ID"""
        return self.project_id