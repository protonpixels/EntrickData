from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QFrame, QMessageBox, QDialog
)
from PySide6.QtCore import Qt

from .shared_components import ProjectCard, NewProjectDialog


class HomeView(QWidget):
    """Home tab showing all projects"""

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

        # New Project button
        new_btn = QPushButton("+ New Project")
        new_btn.setStyleSheet("""
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
        new_btn.clicked.connect(self.create_new_project)
        header_layout.addWidget(new_btn)
        layout.addLayout(header_layout)

        # Filter buttons
        self.filter_layout = QHBoxLayout()
        self.filter_layout.setSpacing(10)

        self.all_btn = self._create_filter_button("📂 All Projects", True)
        self.table_btn = self._create_filter_button("📊 Data Tables", False)
        self.research_btn = self._create_filter_button("🌐 Data Research", False)

        self.filter_layout.addWidget(self.all_btn)
        self.filter_layout.addWidget(self.table_btn)
        self.filter_layout.addWidget(self.research_btn)
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
        btn.clicked.connect(lambda: self._filter_projects(btn.text()))
        return btn

    def _filter_projects(self, filter_text):
        """Filter projects by type"""
        if filter_text == "📂 All Projects":
            self.current_filter = None
            self.all_btn.setChecked(True)
            self.table_btn.setChecked(False)
            self.research_btn.setChecked(False)
        elif filter_text == "📊 Data Tables":
            self.current_filter = "data_table"
            self.all_btn.setChecked(False)
            self.table_btn.setChecked(True)
            self.research_btn.setChecked(False)
        elif filter_text == "🌐 Data Research":
            self.current_filter = "data_research"
            self.all_btn.setChecked(False)
            self.table_btn.setChecked(False)
            self.research_btn.setChecked(True)

        self.load_projects()

    def load_projects(self):
        """Load and display projects"""
        # Clear layout
        while self.projects_layout.count():
            item = self.projects_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        projects = self.db.get_all_projects()

        # Apply filter
        if self.current_filter:
            projects = [p for p in projects if p['project_type'] == self.current_filter]

        if not projects:
            self._show_empty_state()
            return

        for project in projects:
            card = ProjectCard(project, self.parent_app)
            self.projects_layout.addWidget(card)

    def _show_empty_state(self):
        """Show empty state message"""
        label = QLabel("No projects found.\nClick '+ New Project' to create one!")
        label.setStyleSheet("color: #999; font-size: 16px; padding: 60px;")
        label.setAlignment(Qt.AlignCenter)
        self.projects_layout.addWidget(label)

    def create_new_project(self):
        """Create a new project"""
        dialog = NewProjectDialog(self)
        if dialog.exec() == QDialog.Accepted:
            name, project_type, headline, metadata = dialog.get_project_data()

            if not name:
                QMessageBox.warning(self, "Invalid", "Project name is required!")
                return

            try:
                project_id = self.db.create_project(name, project_type, headline, metadata)
                self.load_projects()
                self.parent_app.open_project(project_id)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create project:\n{str(e)}")