import os
import sys
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QMessageBox, QStatusBar, QLabel, QInputDialog, QTextEdit
)
from PySide6.QtCore import Qt
from core.database import StudioDatabase
from core.project_types import ProjectType
from .home_view import HomeView


class MainWindow(QMainWindow):
    """Main window with tabbed project management"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Data Engineering Studio")
        self.setGeometry(100, 100, 1400, 900)

        # Initialize database
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache')
        os.makedirs(cache_dir, exist_ok=True)
        self.db = StudioDatabase(os.path.join(cache_dir, 'studio.db'))

        # Tab tracking
        self.project_tabs = {}  # tab_index -> project_id
        self.tab_widgets = {}  # project_id -> (tab_index, widget)

        self.setup_ui()
        self.show_home_tab()

    def setup_ui(self):
        """Setup the main UI"""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_project_tab)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #d0d0d0;
                background: white;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin-right: 2px;
                background: #f0f0f0;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                background: white;
                border-bottom: 2px solid #4CAF50;
            }
            QTabBar::tab:hover {
                background: #e0e0e0;
            }
            QTabBar::close-button {
                padding: 2px;
            }
        """)

        layout.addWidget(self.tab_widget)
        self.central_widget.setLayout(layout)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel()
        self.status_bar.addWidget(self.status_label)
        self.update_status("Ready")

    def update_status(self, message: str):
        """Update status bar message"""
        self.status_label.setText(f"  {message}")

    def show_home_tab(self):
        """Show the home tab with project overview"""
        # Check if home tab already exists
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "🏠 Home":
                self.tab_widget.setCurrentIndex(i)
                return

        # Create new home tab
        home_view = HomeView(self, self.db)
        tab_index = self.tab_widget.addTab(home_view, "🏠 Home")
        self.tab_widget.setCurrentIndex(tab_index)
        self.update_status("Ready")

    def open_project(self, project_id: int):
        """Open a project in a new tab"""
        project_data = self.db.get_project(project_id)
        if not project_data:
            QMessageBox.warning(self, "Error", "Project not found!")
            return

        # Check if project is already open
        if project_id in self.tab_widgets:
            tab_index = self.tab_widgets[project_id][0]
            self.tab_widget.setCurrentIndex(tab_index)
            return

        # Import views
        from views.data_table_view import DataTableView
        from views.data_research_view import DataResearchView
        from views.data_document_view import DataDocumentView
        from views.data_chat_view import DataChatView  # Add this import

        # Sync schema for data table projects
        if project_data['project_type'] == ProjectType.DATA_TABLE.value:
            self.db.sync_schema_with_metadata(project_id)
            project_data = self.db.get_project(project_id)

        # Create appropriate view based on project type
        if project_data['project_type'] == ProjectType.DATA_TABLE.value:
            view = DataTableView(self, self.db, project_data)
        elif project_data['project_type'] == ProjectType.DATA_RESEARCH.value:
            view = DataResearchView(self, self.db, project_data)
        elif project_data['project_type'] == ProjectType.DATA_DOCUMENT.value:
            view = DataDocumentView(self, self.db, project_data)
        else:  # DATA_CHAT
            view = DataChatView(self, self.db, project_data)

        # Add tab
        tab_name = f"{project_data['name']}"
        tab_index = self.tab_widget.addTab(view, tab_name)
        self.tab_widget.setCurrentIndex(tab_index)

        # Track tab
        self.project_tabs[tab_index] = project_id
        self.tab_widgets[project_id] = (tab_index, view)

        self.update_status(f"Opened: {project_data['name']}")

    def close_project_tab(self, index: int):
        """Close a project tab"""
        if index < 0:
            return

        # Don't close if it's the home tab
        if self.tab_widget.tabText(index) == "🏠 Home":
            return

        # Clean up tracking
        if index in self.project_tabs:
            project_id = self.project_tabs.pop(index)
            if project_id in self.tab_widgets:
                del self.tab_widgets[project_id]

        self.tab_widget.removeTab(index)

        # If no tabs left, show home
        if self.tab_widget.count() == 0:
            self.show_home_tab()

    def rename_project(self, project_id: int):
        """Rename a project"""
        project = self.db.get_project(project_id)
        if not project:
            return

        new_name, ok = QInputDialog.getText(
            self,
            "Rename Project",
            "Enter new project name:",
            text=project['name']
        )

        if ok and new_name:
            self.db.update_project(project_id, name=new_name)
            self.update_status(f"Renamed to: {new_name}")

            # Update tab name if project is open
            if project_id in self.tab_widgets:
                tab_index = self.tab_widgets[project_id][0]
                self.tab_widget.setTabText(tab_index, new_name)

            # Refresh home tab
            self.show_home_tab()

    def delete_project(self, project_id: int):
        """Delete a project"""
        project = self.db.get_project(project_id)
        if not project:
            return

        reply = QMessageBox.question(
            self,
            "Delete Project",
            f"Delete project '{project['name']}' and all its data?\n\nThis action cannot be undone!",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Close tab if open
            if project_id in self.tab_widgets:
                tab_index = self.tab_widgets[project_id][0]
                self.close_project_tab(tab_index)

            self.db.delete_project(project_id)
            self.update_status(f"Deleted: {project['name']}")

            # Refresh home tab
            self.show_home_tab()

    def refresh_table_view(self, project_id):
        """Refresh the table view for a specific project"""
        if project_id in self.tab_widgets:
            tab_index, widget = self.tab_widgets[project_id]
            if hasattr(widget, 'refresh_table_data'):
                widget.refresh_table_data()