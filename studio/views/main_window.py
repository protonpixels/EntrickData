import os
import sys
from typing import Dict

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QMessageBox, QStatusBar, QLabel, QInputDialog, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QPushButton, QMenu, QSplitter,
    QScrollArea, QFrame, QToolButton, QSizePolicy, QLineEdit,
    QComboBox, QListWidget, QListWidgetItem, QToolBar, QTabBar
)
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QFont, QColor

from core.database import StudioDatabase
from core.project_types import ProjectType
from .shared_components import CreateProjectDialog, ProjectCard


class MainWindow(QMainWindow):
    """Main window with clean tab bar at top."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Data Engineering Studio")
        self.setGeometry(100, 100, 1400, 900)

        # Initialize database
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache')
        os.makedirs(cache_dir, exist_ok=True)
        self.db = StudioDatabase(os.path.join(cache_dir, 'studio.db'))

        # State
        self.current_container_id = None
        self.current_filter = None
        self.container_cache = {}
        self.home_tab_index = 0

        # Tab tracking
        self.project_tabs = {}
        self.tab_widgets = {}

        self.setup_ui()
        self.load_sidebar()
        self.load_projects()
        self.update_status("Ready")

    def setup_ui(self):
        """Setup the main UI with clean tab bar."""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === TAB WIDGET ===
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #d0d0d0;
                background: white;
                border-top: none;
            }
            QTabBar {
                background-color: #f5f7fa;
                border-bottom: 1px solid #e0e0e0;
            }
            QTabBar::tab {
                padding: 8px 20px;
                margin-right: 2px;
                background: #e8e8e8;
                font-size: 13px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: white;
                border-bottom: 2px solid #4CAF50;
            }
            QTabBar::tab:hover {
                background: #d0d0d0;
            }
            QTabBar::tab:!selected {
                color: #666;
            }
            QTabBar::close-button {
                padding: 2px 4px;
                border-radius: 2px;
            }
            QTabBar::close-button:hover {
                background-color: #ff6b6b;
                color: white;
            }
        """)
        main_layout.addWidget(self.tab_widget)

        # === STATUS BAR ===
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel()
        self.status_bar.addWidget(self.status_label)
        self.status_bar.setStyleSheet("""
            QStatusBar {
                background-color: #f5f7fa;
                border-top: 1px solid #e0e0e0;
            }
        """)

        self.central_widget.setLayout(main_layout)

        # Create home tab
        self.create_home_tab()

    def create_home_tab(self):
        """Create the home tab with sidebar and project list."""
        home_widget = QWidget()
        home_layout = QHBoxLayout()
        home_layout.setContentsMargins(0, 0, 0, 0)
        home_layout.setSpacing(0)

        # === SIDEBAR ===
        sidebar = self._create_sidebar()
        home_layout.addWidget(sidebar)

        # === CONTENT ===
        content_panel = self._create_content_panel()
        home_layout.addWidget(content_panel)

        home_widget.setLayout(home_layout)

        # Add tab at position 0 (far left)
        tab_index = self.tab_widget.insertTab(0, home_widget, "🏠 Home")
        self.tab_widget.setTabToolTip(tab_index, "Home")
        self.home_tab_index = tab_index

        # Make home tab not closable
        self.tab_widget.tabBar().tabButton(tab_index, QTabBar.RightSide)
        self.tab_widget.tabBar().tabButton(tab_index, QTabBar.LeftSide)

        self.tab_widget.setCurrentIndex(tab_index)

    def _create_sidebar(self):
        """Create the sidebar for the home tab."""
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("""
            QWidget {
                background-color: #f5f7fa;
                border-right: 1px solid #e0e0e0;
            }
            QListWidget {
                background-color: transparent;
                border: none;
                outline: none;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 8px 12px;
                border-radius: 4px;
                margin: 1px 4px;
            }
            QListWidget::item:hover {
                background-color: #e8f0fe;
            }
            QListWidget::item:selected {
                background-color: #d0e4ff;
                color: #1a237e;
            }
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 6px 12px;
                text-align: left;
                font-size: 13px;
                font-weight: bold;
                color: #1c242e;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e8f0fe;
            }
            QLineEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
                background-color: white;
            }
            QLineEdit:focus {
                border-color: #4CAF50;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Logo
        logo = QLabel("📊 Projects")
        logo.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #1c242e;
            padding: 8px 8px 4px 8px;
        """)
        layout.addWidget(logo)

        # Search in sidebar
        self.sidebar_search = QLineEdit()
        self.sidebar_search.setPlaceholderText("🔍 Filter...")
        self.sidebar_search.textChanged.connect(self.filter_sidebar)
        layout.addWidget(self.sidebar_search)

        # Quick actions
        action_layout = QHBoxLayout()
        action_layout.setSpacing(4)

        new_project_btn = QPushButton("📄 New")
        new_project_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        new_project_btn.clicked.connect(self._create_project)
        action_layout.addWidget(new_project_btn)

        new_folder_btn = QPushButton("📁 Folder")
        new_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        new_folder_btn.clicked.connect(self._create_container)
        action_layout.addWidget(new_folder_btn)

        action_layout.addStretch()
        layout.addLayout(action_layout)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #e0e0e0; margin: 4px 0;")
        layout.addWidget(sep)

        # Sidebar list
        self.sidebar_list = QListWidget()
        self.sidebar_list.setSelectionMode(QListWidget.SingleSelection)
        self.sidebar_list.itemClicked.connect(self.on_sidebar_item_clicked)
        layout.addWidget(self.sidebar_list)

        layout.addStretch()

        # Bottom action
        show_all_btn = QPushButton("📂 Show All")
        show_all_btn.setStyleSheet("font-size: 11px; color: #666; padding: 4px 8px;")
        show_all_btn.clicked.connect(self.show_all_projects)
        layout.addWidget(show_all_btn)

        sidebar.setLayout(layout)
        return sidebar

    def _create_content_panel(self):
        """Create the content panel for the home tab."""
        panel = QWidget()
        panel_layout = QVBoxLayout()
        panel_layout.setContentsMargins(8, 8, 8, 8)
        panel_layout.setSpacing(8)

        # Filter buttons
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.filter_buttons = {}
        filter_names = [
            ("📂 All", None),
            ("📊 Tables", "data_table"),
            ("🌐 Research", "data_research"),
            ("📄 Documents", "data_document"),
            ("💬 Chat", "data_chat"),
            ("🧬 Synthesizers", "data_synthesizer")
        ]

        for label, filter_type in filter_names:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    padding: 4px 14px;
                    border-radius: 14px;
                    font-size: 12px;
                    font-weight: 600;
                    background-color: #e0e0e0;
                    color: #666;
                    border: none;
                }
                QPushButton:checked {
                    background-color: #4CAF50;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #d0d0d0;
                }
                QPushButton:checked:hover {
                    background-color: #45a049;
                }
            """)
            btn.clicked.connect(lambda checked, ft=filter_type: self.set_filter(ft))
            if filter_type is None:
                btn.setChecked(True)
            self.filter_buttons[filter_type] = btn
            top_bar.addWidget(btn)

        top_bar.addStretch()
        panel_layout.addLayout(top_bar)

        # Scroll area for projects
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setAlignment(Qt.AlignTop)
        self.content_layout.setSpacing(12)
        self.content_widget.setLayout(self.content_layout)

        scroll.setWidget(self.content_widget)
        panel_layout.addWidget(scroll)

        panel.setLayout(panel_layout)
        return panel

    # ========== SIDEBAR METHODS ==========

    def load_sidebar(self):
        """Load the sidebar with containers and projects."""
        self.sidebar_list.clear()
        self.container_cache = {}

        # Root item
        root_item = QListWidgetItem("📁 Root")
        root_item.setData(Qt.UserRole, None)
        root_item.setToolTip("All projects")
        self.sidebar_list.addItem(root_item)

        # Get containers
        containers = self.db.get_container_tree()

        # Add containers recursively
        self._add_containers_to_sidebar(containers, "")

        # Select root by default
        self.sidebar_list.setCurrentRow(0)
        self.current_container_id = None

    def _add_containers_to_sidebar(self, containers, prefix):
        """Recursively add containers to sidebar."""
        for container in containers:
            item_text = f"{prefix}📁 {container['name']}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, container['id'])
            item.setToolTip(f"Container: {container['name']}")
            self.sidebar_list.addItem(item)

            # Store in cache
            self.container_cache[container['id']] = container

            # Add children
            if container.get('children'):
                self._add_containers_to_sidebar(container['children'], "  ")

    def filter_sidebar(self, text):
        """Filter sidebar items."""
        text = text.lower().strip()
        for i in range(self.sidebar_list.count()):
            item = self.sidebar_list.item(i)
            item.setHidden(text not in item.text().lower())

    def on_sidebar_item_clicked(self, item):
        """Handle sidebar item click."""
        container_id = item.data(Qt.UserRole)
        self.current_container_id = container_id
        self.load_projects()

    def set_filter(self, filter_type):
        """Set the project filter."""
        self.current_filter = filter_type

        # Update button states
        for ft, btn in self.filter_buttons.items():
            btn.setChecked(ft == filter_type)

        self.load_projects()

    def show_all_projects(self):
        """Show all projects (reset container filter)."""
        self.sidebar_list.setCurrentRow(0)
        self.current_container_id = None
        self.load_projects()

    def load_projects(self):
        """Load projects into the content area."""
        # Clear layout
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Get projects
        all_projects = self.db.get_all_projects()

        # Apply filter
        if self.current_filter:
            all_projects = [p for p in all_projects if p['project_type'] == self.current_filter]

        # Filter by container
        if self.current_container_id is not None:
            all_projects = [p for p in all_projects if p.get('container_id') == self.current_container_id]

        if not all_projects:
            empty_label = QLabel("No projects found.\nClick 'New' to create one!")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("color: #999; font-size: 16px; padding: 60px;")
            self.content_layout.addWidget(empty_label)
            return

        # Display projects as cards
        for project in all_projects:
            card = ProjectCard(project, self)
            self.content_layout.addWidget(card)

        self.content_layout.addStretch()

    # ========== TAB MANAGEMENT ==========
    def open_project(self, project_id: int):
        """Open a project in a new tab."""
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
        from views.data_chat_view import DataChatView
        from views.data_synthesizer_view import DataSynthesizerView

        # Sync schema for data table projects
        if project_data['project_type'] == ProjectType.DATA_TABLE.value:
            self.db.sync_schema_with_metadata(project_id)
            project_data = self.db.get_project(project_id)

        # Create appropriate view
        if project_data['project_type'] == ProjectType.DATA_TABLE.value:
            view = DataTableView(self, self.db, project_data)
            icon = "📊"
        elif project_data['project_type'] == ProjectType.DATA_RESEARCH.value:
            view = DataResearchView(self, self.db, project_data)
            icon = "🌐"
        elif project_data['project_type'] == ProjectType.DATA_DOCUMENT.value:
            view = DataDocumentView(self, self.db, project_data)
            icon = "📄"
        elif project_data['project_type'] == ProjectType.DATA_CHAT.value:
            view = DataChatView(self, self.db, project_data)
            icon = "💬"
        elif project_data['project_type'] == ProjectType.DATA_SYNTHESIZER.value:
            view = DataSynthesizerView(self, self.db, project_data)
            icon = "🧬"
        else:
            QMessageBox.warning(self, "Error", f"Unknown project type: {project_data['project_type']}")
            return

        # Insert tab after Home tab (at position 1)
        tab_name = f"{icon} {project_data['name']}"
        tab_index = self.tab_widget.insertTab(1, view, tab_name)
        self.tab_widget.setTabToolTip(tab_index, project_data['name'])
        self.tab_widget.setCurrentIndex(tab_index)

        # Track tab
        self.project_tabs[tab_index] = project_id
        self.tab_widgets[project_id] = (tab_index, view)

        self.update_status(f"Opened: {project_data['name']}")



    def close_tab(self, index: int):
        """Close a tab."""
        # Don't close home tab
        if index == self.home_tab_index:
            return

        # Clean up tracking
        if index in self.project_tabs:
            project_id = self.project_tabs.pop(index)
            if project_id in self.tab_widgets:
                del self.tab_widgets[project_id]

        self.tab_widget.removeTab(index)

        # Home tab index is always 0
        self.home_tab_index = 0

    def on_tab_changed(self, index):
        """Handle tab change (just update status)."""
        if index == self.home_tab_index:
            self.update_status("Home")
        elif index in self.project_tabs:
            project_id = self.project_tabs[index]
            project_data = self.db.get_project(project_id)
            if project_data:
                self.update_status(f"Viewing: {project_data['name']}")

    # ========== PROJECT OPERATIONS ==========

    def _create_container(self):
        """Create a new container."""
        name, ok = QInputDialog.getText(self, "New Folder", "Enter folder name:")
        if ok and name.strip():
            self.db.create_container(name.strip())
            self.load_sidebar()
            self.load_projects()
            self.update_status(f"Created folder: {name}")

    def _create_project(self, container_id: int = None):
        """Create a new project."""
        dialog = CreateProjectDialog(self, self.db, container_id)
        if dialog.exec_():
            project_id = dialog.get_project_id()
            if project_id:
                self.load_sidebar()
                self.load_projects()
                self.open_project(project_id)
                self.update_status("Project created successfully")

    def rename_project(self, project_id: int):
        """Rename a project."""
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
                icon = ProjectType.get_icon(project['project_type'])
                self.tab_widget.setTabText(tab_index, f"{icon} {new_name}")

            # Refresh
            self.load_sidebar()
            self.load_projects()

    def delete_project(self, project_id: int):
        """Delete a project."""
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
                self.close_tab(tab_index)

            self.db.delete_project(project_id)
            self.update_status(f"Deleted: {project['name']}")

            # Refresh
            self.load_sidebar()
            self.load_projects()

    def refresh_table_view(self, project_id):
        """Refresh the table view for a specific project."""
        if project_id in self.tab_widgets:
            tab_index, widget = self.tab_widgets[project_id]
            if hasattr(widget, 'refresh_table_data'):
                widget.refresh_table_data()

    def update_status(self, message: str):
        """Update status bar message."""
        self.status_label.setText(f"  {message}")

    def show_home_tab(self):
        """Show the home tab."""
        self.tab_widget.setCurrentIndex(self.home_tab_index)
        self.load_projects()
        self.update_status("Ready")

    def _move_project(self, project_id: int):
        """Move a project to a different container."""
        project = self.db.get_project(project_id)
        if not project:
            return

        # Get all containers
        containers = self.db.get_container_tree()
        container_names = ["Uncategorized"]
        container_ids = [None]

        def flatten_containers(container_list, prefix=""):
            for container in container_list:
                container_names.append(f"{prefix}{container['name']}")
                container_ids.append(container['id'])
                if container.get('children'):
                    flatten_containers(container['children'], f"{prefix}  ")

        flatten_containers(containers)

        # Show selection dialog
        current_idx = 0
        current_container = project.get('container_id')
        if current_container in container_ids:
            current_idx = container_ids.index(current_container)

        selected, ok = QInputDialog.getItem(
            self,
            "Move Project",
            f"Move '{project['name']}' to:",
            container_names,
            current_idx,
            False
        )

        if ok and selected:
            idx = container_names.index(selected)
            container_id = container_ids[idx]
            self.db.move_to_container(project_id, container_id)
            self.load_sidebar()
            self.load_projects()
            self.update_status(f"Moved project to: {selected}")