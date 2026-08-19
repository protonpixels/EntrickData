import os
import sys
from typing import Dict

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QMessageBox, QStatusBar, QLabel, QInputDialog, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QPushButton, QMenu, QSplitter
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction
from core.database import StudioDatabase
from core.project_types import ProjectType
from .home_view import HomeView
from .shared_components import CreateProjectDialog


class MainWindow(QMainWindow):
    """Main window with tabbed project management and container support"""

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
        self.load_project_tree()
        self.show_home_tab()

    def setup_ui(self):
        """Setup the main UI with project tree and tabs"""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === LEFT PANEL: Project Tree ===
        left_panel = QWidget()
        left_panel.setFixedWidth(300)
        left_panel.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border-right: 1px solid #e0e0e0;
            }
        """)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        left_layout.setSpacing(5)

        # Tree header with buttons
        header_layout = QHBoxLayout()
        header_label = QLabel("📁 Projects")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        # New Folder button
        new_folder_btn = QPushButton("📁")
        new_folder_btn.setFixedSize(28, 28)
        new_folder_btn.setToolTip("New Folder")
        new_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                border-radius: 4px;
            }
        """)
        new_folder_btn.clicked.connect(self._create_container)
        header_layout.addWidget(new_folder_btn)

        # New Project button
        new_project_btn = QPushButton("📄")
        new_project_btn.setFixedSize(28, 28)
        new_project_btn.setToolTip("New Project")
        new_project_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                border-radius: 4px;
            }
        """)
        new_project_btn.clicked.connect(self._create_project)
        header_layout.addWidget(new_project_btn)

        left_layout.addLayout(header_layout)

        # Project tree
        self.project_tree = QTreeWidget()
        self.project_tree.setHeaderHidden(True)
        self.project_tree.setIndentation(20)
        self.project_tree.setStyleSheet("""
            QTreeWidget {
                background-color: transparent;
                border: none;
                font-size: 13px;
                outline: none;
            }
            QTreeWidget::item {
                padding: 4px 0px;
            }
            QTreeWidget::item:hover {
                background-color: #e8f0fe;
                border-radius: 4px;
            }
            QTreeWidget::item:selected {
                background-color: #d0e4ff;
                border-radius: 4px;
            }
        """)
        self.project_tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        self.project_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.project_tree.customContextMenuRequested.connect(self._show_tree_context_menu)

        left_layout.addWidget(self.project_tree)

        # === RIGHT PANEL: Tab Widget ===
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

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

        right_layout.addWidget(self.tab_widget)

        # Add panels to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)
        self.central_widget.setLayout(main_layout)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel()
        self.status_bar.addWidget(self.status_label)
        self.update_status("Ready")

    def load_project_tree(self):
        """Load projects into the tree with containers"""
        self.project_tree.clear()

        # Get container tree
        containers = self.db.get_container_tree()

        # Add containers and their projects
        for container in containers:
            self._add_container_to_tree(container, None)

        # Add uncategorized projects
        uncategorized = self.db.get_uncategorized_projects()
        if uncategorized:
            uncat_item = QTreeWidgetItem(self.project_tree)
            uncat_item.setText(0, "📁 Uncategorized")
            uncat_item.setData(0, Qt.UserRole, {'type': 'uncategorized'})
            uncat_item.setExpanded(True)
            for project in uncategorized:
                self._add_project_to_tree(project, uncat_item)

    def _add_container_to_tree(self, container: Dict, parent_item: QTreeWidgetItem):
        """Recursively add container and its contents"""
        item = QTreeWidgetItem(parent_item if parent_item else self.project_tree)
        item.setText(0, f"📁 {container['name']}")
        item.setData(0, Qt.UserRole, {'type': 'container', 'id': container['id']})
        item.setExpanded(True)

        # Add projects
        for project in container['projects']:
            self._add_project_to_tree(project, item)

        # Add child containers
        for child in container['children']:
            self._add_container_to_tree(child, item)

    def _add_project_to_tree(self, project: Dict, parent_item: QTreeWidgetItem):
        """Add a project to the tree"""
        icon = self._get_project_icon(project['project_type'])
        item = QTreeWidgetItem(parent_item)
        item.setText(0, f"{icon} {project['name']}")
        item.setData(0, Qt.UserRole, {'type': 'project', 'id': project['id']})

    def _get_project_icon(self, project_type: str) -> str:
        icons = {
            'data_table': '📊',
            'data_research': '🌐',
            'data_document': '📄',
            'data_chat': '💬'
        }
        return icons.get(project_type, '📁')

    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double-click on tree items"""
        data = item.data(0, Qt.UserRole)
        if data and data.get('type') == 'project':
            self.open_project(data['id'])

    def _show_tree_context_menu(self, position):
        """Show context menu for tree items"""
        item = self.project_tree.itemAt(position)
        menu = QMenu()

        if item is None:
            # Empty space
            new_container = QAction("📁 New Folder", self)
            new_container.triggered.connect(self._create_container)
            menu.addAction(new_container)

            new_project = QAction("📄 New Project", self)
            new_project.triggered.connect(self._create_project)
            menu.addAction(new_project)
        else:
            data = item.data(0, Qt.UserRole)
            if data:
                if data.get('type') == 'container':
                    self._add_container_menu(menu, item, data)
                elif data.get('type') == 'project':
                    self._add_project_menu(menu, item, data)
                elif data.get('type') == 'uncategorized':
                    new_project = QAction("📄 New Project", self)
                    new_project.triggered.connect(self._create_project)
                    menu.addAction(new_project)

        menu.exec_(self.project_tree.mapToGlobal(position))

    def _add_container_menu(self, menu: QMenu, item: QTreeWidgetItem, data: Dict):
        """Add container-specific menu items"""
        new_project = QAction("📄 New Project", self)
        new_project.triggered.connect(lambda: self._create_project_in_container(data['id']))
        menu.addAction(new_project)

        new_container = QAction("📁 New Sub-Folder", self)
        new_container.triggered.connect(lambda: self._create_sub_container(data['id']))
        menu.addAction(new_container)

        menu.addSeparator()

        rename = QAction("✏️ Rename", self)
        rename.triggered.connect(lambda: self._rename_container(item, data['id']))
        menu.addAction(rename)

        delete = QAction("🗑️ Delete", self)
        delete.triggered.connect(lambda: self._delete_container(item, data['id']))
        menu.addAction(delete)

    def _add_project_menu(self, menu: QMenu, item: QTreeWidgetItem, data: Dict):
        """Add project-specific menu items"""
        open_action = QAction("📖 Open", self)
        open_action.triggered.connect(lambda: self.open_project(data['id']))
        menu.addAction(open_action)

        move_to = QAction("📂 Move to Folder", self)
        move_to.triggered.connect(lambda: self._move_project(data['id']))
        menu.addAction(move_to)

        menu.addSeparator()

        rename = QAction("✏️ Rename", self)
        rename.triggered.connect(lambda: self._rename_project_item(data['id']))
        menu.addAction(rename)

        delete = QAction("🗑️ Delete", self)
        delete.triggered.connect(lambda: self._delete_project_item(data['id']))
        menu.addAction(delete)

    # ========== CONTAINER OPERATIONS ==========

    def _create_container(self):
        """Create a new root container"""
        name, ok = QInputDialog.getText(self, "New Folder", "Enter folder name:")
        if ok and name.strip():
            self.db.create_container(name.strip())
            self.load_project_tree()
            self.update_status(f"Created folder: {name}")

    def _create_sub_container(self, parent_id: int):
        """Create a sub-container"""
        name, ok = QInputDialog.getText(self, "New Sub-Folder", "Enter sub-folder name:")
        if ok and name.strip():
            self.db.create_container(name.strip(), parent_id)
            self.load_project_tree()
            self.update_status(f"Created sub-folder: {name}")

    def _create_project_in_container(self, container_id: int):
        """Create a new project in a container"""
        # Reuse the existing project creation logic
        self._create_project(container_id)

    def _rename_container(self, item: QTreeWidgetItem, container_id: int):
        """Rename a container"""
        container = self.db.get_container(container_id)
        if not container:
            return

        new_name, ok = QInputDialog.getText(
            self, "Rename Folder", "Enter new name:",
            text=container['name']
        )
        if ok and new_name.strip():
            self.db.rename_container(container_id, new_name.strip())
            self.load_project_tree()
            self.update_status(f"Renamed folder to: {new_name}")

    def _delete_container(self, item: QTreeWidgetItem, container_id: int):
        """Delete a container"""
        container = self.db.get_container(container_id)
        if not container:
            return

        reply = QMessageBox.question(
            self,
            "Delete Folder",
            f"Delete folder '{container['name']}'?\n\nProjects will be moved to the parent folder.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.db.delete_container(container_id, move_to_parent=True)
            self.load_project_tree()
            self.update_status(f"Deleted folder: {container['name']}")

    def _move_project(self, project_id: int):
        """Move a project to a different container"""
        project = self.db.get_project(project_id)
        if not project:
            return

        # Get all containers for selection
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
            self.load_project_tree()
            self.update_status(f"Moved project to: {selected}")

    def _rename_project_item(self, project_id: int):
        """Rename a project from the tree"""
        self.rename_project(project_id)

    def _delete_project_item(self, project_id: int):
        """Delete a project from the tree"""
        self.delete_project(project_id)

    def _create_project(self, container_id: int = None):
        """Create a new project"""
        dialog = CreateProjectDialog(self, self.db, container_id)
        if dialog.exec_():
            project_id = dialog.get_project_id()
            if project_id:
                self.load_project_tree()
                self.open_project(project_id)
                self.update_status("Project created successfully")

    # ========== PROJECT OPERATIONS ==========

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
        from views.data_chat_view import DataChatView

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
        tab_name = project_data['name']
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

            # Refresh tree
            self.load_project_tree()

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

            # Refresh tree
            self.load_project_tree()

    def refresh_table_view(self, project_id):
        """Refresh the table view for a specific project"""
        if project_id in self.tab_widgets:
            tab_index, widget = self.tab_widgets[project_id]
            if hasattr(widget, 'refresh_table_data'):
                widget.refresh_table_data()

    def update_status(self, message: str):
        """Update status bar message"""
        self.status_label.setText(f"  {message}")