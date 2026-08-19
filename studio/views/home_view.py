# studio/views/home_view.py
from typing import Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QFrame, QMessageBox, QDialog,
    QMenu, QInputDialog
)
from PySide6.QtCore import Qt

from .shared_components import ProjectCard
from .shared_components import CreateProjectDialog  # Fixed import


class HomeView(QWidget):
    """Home tab showing all projects with container support"""

    def __init__(self, parent=None, db=None):
        super().__init__(parent)
        self.parent_app = parent
        self.db = db
        self.current_filter = None
        self.setup_ui()
        self.load_projects()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(40, 30, 40, 30)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("📊 Data Engineering Studio")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #1c242e;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        # New Project button with dropdown for container selection
        self.new_btn = QPushButton("+ New Project")
        self.new_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 10px 24px;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        self.new_btn.clicked.connect(self.create_new_project)
        header_layout.addWidget(self.new_btn)

        # New Container button
        new_container_btn = QPushButton("📁 New Folder")
        new_container_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                padding: 10px 18px;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #F57C00; }
        """)
        new_container_btn.clicked.connect(self.create_new_container)
        header_layout.addWidget(new_container_btn)

        layout.addLayout(header_layout)

        # Filter buttons
        self.filter_layout = QHBoxLayout()
        self.filter_layout.setSpacing(10)

        self.all_btn = self._create_filter_button("📂 All Projects", True)
        self.table_btn = self._create_filter_button("📊 Data Tables", False)
        self.research_btn = self._create_filter_button("🌐 Data Research", False)
        self.document_btn = self._create_filter_button("📄 Documents", False)
        self.chat_btn = self._create_filter_button("💬 Chat Projects", False)

        self.filter_layout.addWidget(self.all_btn)
        self.filter_layout.addWidget(self.table_btn)
        self.filter_layout.addWidget(self.research_btn)
        self.filter_layout.addWidget(self.document_btn)
        self.filter_layout.addWidget(self.chat_btn)
        self.filter_layout.addStretch()
        layout.addLayout(self.filter_layout)

        # Projects scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.projects_container = QWidget()
        self.projects_container.setStyleSheet("background: transparent;")
        self.projects_layout = QVBoxLayout()
        self.projects_layout.setAlignment(Qt.AlignTop)
        self.projects_layout.setSpacing(15)
        self.projects_container.setLayout(self.projects_layout)

        self.scroll.setWidget(self.projects_container)
        layout.addWidget(self.scroll)

        self.setLayout(layout)

    def _create_filter_button(self, text, active):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setChecked(active)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda: self._filter_projects(btn.text()))
        self._update_filter_style(btn, active)
        return btn

    def _update_filter_style(self, btn, active):
        btn.setStyleSheet(f"""
            QPushButton {{
                padding: 6px 18px;
                border-radius: 15px;
                font-weight: bold;
                font-size: 13px;
                background-color: {'#4CAF50' if active else '#e0e0e0'};
                color: {'white' if active else '#666'};
            }}
            QPushButton:hover {{
                background-color: {'#45a049' if active else '#d0d0d0'};
            }}
        """)

    def _filter_projects(self, filter_text):
        """Filter projects by type"""
        # Reset all buttons
        for btn in [self.all_btn, self.table_btn, self.research_btn, self.document_btn, self.chat_btn]:
            btn.setChecked(False)
            self._update_filter_style(btn, False)

        # Set the clicked button as active
        if filter_text == "📂 All Projects":
            self.current_filter = None
            self.all_btn.setChecked(True)
            self._update_filter_style(self.all_btn, True)
        elif filter_text == "📊 Data Tables":
            self.current_filter = "data_table"
            self.table_btn.setChecked(True)
            self._update_filter_style(self.table_btn, True)
        elif filter_text == "🌐 Data Research":
            self.current_filter = "data_research"
            self.research_btn.setChecked(True)
            self._update_filter_style(self.research_btn, True)
        elif filter_text == "📄 Documents":
            self.current_filter = "data_document"
            self.document_btn.setChecked(True)
            self._update_filter_style(self.document_btn, True)
        elif filter_text == "💬 Chat Projects":
            self.current_filter = "data_chat"
            self.chat_btn.setChecked(True)
            self._update_filter_style(self.chat_btn, True)

        self.load_projects()

    def load_projects(self):
        """Load and display projects grouped by container"""
        # Clear layout
        while self.projects_layout.count():
            item = self.projects_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        all_projects = self.db.get_all_projects()

        # Apply filter
        if self.current_filter:
            all_projects = [p for p in all_projects if p['project_type'] == self.current_filter]

        if not all_projects:
            self._show_empty_state()
            return

        # Get containers
        containers = self.db.get_container_tree()
        container_map = {}
        for container in containers:
            self._add_container_to_map(container, container_map)

        # Group projects by container
        projects_by_container = {}
        uncategorized = []

        for project in all_projects:
            container_id = project.get('container_id')
            if container_id and container_id in container_map:
                if container_id not in projects_by_container:
                    projects_by_container[container_id] = []
                projects_by_container[container_id].append(project)
            else:
                uncategorized.append(project)

        # Display projects by container
        for container_id, projects in projects_by_container.items():
            container = container_map.get(container_id)
            if container:
                # Container header
                container_label = QLabel(f"📁 {container['name']}")
                container_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #1c242e; margin-top: 10px;")
                self.projects_layout.addWidget(container_label)

                # Projects in this container
                for project in projects:
                    card = ProjectCard(project, self.parent_app)
                    self.projects_layout.addWidget(card)

        # Display uncategorized projects
        if uncategorized:
            uncat_label = QLabel("📁 Uncategorized")
            uncat_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #1c242e; margin-top: 10px;")
            self.projects_layout.addWidget(uncat_label)

            for project in uncategorized:
                card = ProjectCard(project, self.parent_app)
                self.projects_layout.addWidget(card)

        # Add a spacer at the end
        self.projects_layout.addStretch()

    def _add_container_to_map(self, container: Dict, container_map: Dict):
        """Recursively add containers to the map"""
        container_map[container['id']] = container
        for child in container.get('children', []):
            self._add_container_to_map(child, container_map)

    def _show_empty_state(self):
        """Show empty state message"""
        label = QLabel("No projects found.\nClick '+ New Project' to create one!")
        label.setStyleSheet("color: #999; font-size: 16px; padding: 60px;")
        label.setAlignment(Qt.AlignCenter)
        self.projects_layout.addWidget(label)

    def create_new_project(self):
        """Create a new project with container selection"""
        dialog = CreateProjectDialog(self, self.db)
        if dialog.exec() == QDialog.Accepted:
            project_id = dialog.get_project_id()
            if project_id:
                self.load_projects()
                self.parent_app.open_project(project_id)

    def create_new_container(self):
        """Create a new container"""
        name, ok = QInputDialog.getText(self, "New Folder", "Enter folder name:")
        if ok and name.strip():
            self.db.create_container(name.strip())
            self.load_projects()
            self.parent_app.update_status(f"Created folder: {name}")

    def refresh(self):
        """Refresh the home view"""
        self.load_projects()