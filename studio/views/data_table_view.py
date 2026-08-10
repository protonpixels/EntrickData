import csv

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QTextEdit, QComboBox, QCheckBox,
    QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QScrollArea, QFrame, QSplitter, QListWidget,
    QAbstractItemView, QDialog, QDialogButtonBox, QMessageBox,
    QFileDialog, QProgressDialog, QGroupBox
)
from PySide6.QtGui import QKeySequence, QShortcut, QGuiApplication
import os
import sqlite3
import json
from models.data_types import ColumnType


class ColumnDialog(QDialog):
    """Dialog for adding/editing columns"""

    def __init__(self, parent=None, column_data=None):
        super().__init__(parent)
        self.parent_app = parent
        self.column_data = column_data or {}
        self.imported_files = []
        self.setup_ui()
        if column_data:
            self.load_column_data()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # Column Name
        layout.addWidget(QLabel("Column Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter column name...")
        self.name_input.setStyleSheet("font-size: 14px; padding: 7px;")
        layout.addWidget(self.name_input)

        # Column Description
        layout.addWidget(QLabel("Column Description:"))
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Enter column description...")
        self.desc_input.setStyleSheet("font-size: 14px; padding: 7px;")
        layout.addWidget(self.desc_input)

        # Column Type - using ColumnType enum
        layout.addWidget(QLabel("Column Type:"))
        self.type_input = QComboBox()
        for type_val, display_name in ColumnType.get_all_types():
            self.type_input.addItem(display_name, type_val)
        self.type_input.setStyleSheet("font-size: 14px; padding: 7px;")
        self.type_input.currentIndexChanged.connect(self.on_type_changed)
        layout.addWidget(self.type_input)

        # Checkboxes
        check_layout = QHBoxLayout()
        self.required_check = QCheckBox("Required")
        self.required_check.setChecked(False)
        self.unique_check = QCheckBox("Unique Values")
        self.unique_check.setChecked(False)
        check_layout.addWidget(self.required_check)
        check_layout.addWidget(self.unique_check)
        layout.addLayout(check_layout)

        # ============ FILE IMPORT SECTION (for media types) ============
        self.import_widget = QWidget()
        import_layout = QVBoxLayout()
        import_layout.setSpacing(8)

        # Import header
        import_header = QLabel("📁 File Import Options (for media columns)")
        import_header.setStyleSheet("font-weight: bold; font-size: 13px; color: #1c242e; margin-top: 8px;")
        import_layout.addWidget(import_header)

        # Import button
        import_btn_layout = QHBoxLayout()
        self.import_btn = QPushButton("📂 Select Folder to Import")
        self.import_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        self.import_btn.clicked.connect(self.import_files_from_folder)
        import_btn_layout.addWidget(self.import_btn)

        self.clear_import_btn = QPushButton("Clear Imported")
        self.clear_import_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        self.clear_import_btn.clicked.connect(self.clear_imported_files)
        import_btn_layout.addWidget(self.clear_import_btn)
        import_layout.addLayout(import_btn_layout)

        # Import options
        options_layout = QHBoxLayout()
        options_layout.setSpacing(15)

        # Store as full path or just filename
        self.path_type_combo = QComboBox()
        self.path_type_combo.addItems(["Store as Filename Only", "Store as Full File Path"])
        self.path_type_combo.setStyleSheet("font-size: 12px; padding: 4px;")
        options_layout.addWidget(QLabel("Store:"))
        options_layout.addWidget(self.path_type_combo)

        # File extensions filter
        options_layout.addWidget(QLabel("Extensions:"))
        self.extensions_input = QLineEdit()
        self.extensions_input.setPlaceholderText("e.g., jpg,png,mp4 (leave empty for all)")
        self.extensions_input.setStyleSheet("font-size: 12px; padding: 4px;")
        self.extensions_input.setMaximumWidth(200)
        options_layout.addWidget(self.extensions_input)

        options_layout.addStretch()
        import_layout.addLayout(options_layout)

        # Imported files count and list
        self.import_count_label = QLabel("Files imported: 0")
        self.import_count_label.setStyleSheet("color: #666; font-size: 11px;")
        import_layout.addWidget(self.import_count_label)

        # Scrollable list of imported files
        self.imported_files_list = QListWidget()
        self.imported_files_list.setMaximumHeight(100)
        self.imported_files_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 4px;
                font-size: 11px;
                background-color: #fafafa;
            }
            QListWidget::item:hover { background-color: #e0f0ff; }
        """)
        import_layout.addWidget(self.imported_files_list)

        self.import_widget.setLayout(import_layout)
        self.import_widget.hide()  # Hidden by default
        layout.addWidget(self.import_widget)

        # Category widget
        self.category_widget = QWidget()
        cat_layout = QVBoxLayout()

        cat_mode_layout = QHBoxLayout()
        cat_mode_layout.addWidget(QLabel("Selection mode:"))
        self.category_mode = QComboBox()
        self.category_mode.addItems(["Single Selection", "Multiple Selection"])
        self.category_mode.setStyleSheet("font-size: 13px; padding: 5px;")
        cat_mode_layout.addWidget(self.category_mode)
        cat_mode_layout.addStretch()
        cat_layout.addLayout(cat_mode_layout)

        cat_layout.addWidget(QLabel("Categories (one per line):"))
        self.categories_text = QTextEdit()
        self.categories_text.setMaximumHeight(120)
        self.categories_text.setPlaceholderText("Enter categories...")
        self.categories_text.setStyleSheet("font-size: 14px; background-color: white; color: black;")
        cat_layout.addWidget(self.categories_text)
        self.category_widget.setLayout(cat_layout)
        layout.addWidget(self.category_widget)

        # Numeric widgets
        self.numeric_widget = QWidget()
        numeric_layout = QHBoxLayout()

        min_layout = QVBoxLayout()
        min_layout.addWidget(QLabel("Min:"))
        self.min_input = QSpinBox()
        self.min_input.setRange(-999999, 999999)
        self.min_input.setValue(0)
        min_layout.addWidget(self.min_input)
        numeric_layout.addLayout(min_layout)

        max_layout = QVBoxLayout()
        max_layout.addWidget(QLabel("Max:"))
        self.max_input = QSpinBox()
        self.max_input.setRange(-999999, 999999)
        self.max_input.setValue(100)
        max_layout.addWidget(self.max_input)
        numeric_layout.addLayout(max_layout)

        step_layout = QVBoxLayout()
        step_layout.addWidget(QLabel("Step:"))
        self.step_input = QSpinBox()
        self.step_input.setRange(1, 999999)
        self.step_input.setValue(1)
        step_layout.addWidget(self.step_input)
        numeric_layout.addLayout(step_layout)

        self.numeric_widget.setLayout(numeric_layout)
        layout.addWidget(self.numeric_widget)

        # Float numeric widget
        self.float_widget = QWidget()
        float_layout = QHBoxLayout()

        min_float_layout = QVBoxLayout()
        min_float_layout.addWidget(QLabel("Min:"))
        self.min_float_input = QDoubleSpinBox()
        self.min_float_input.setRange(-999999.99, 999999.99)
        self.min_float_input.setDecimals(2)
        self.min_float_input.setValue(0)
        min_float_layout.addWidget(self.min_float_input)
        float_layout.addLayout(min_float_layout)

        max_float_layout = QVBoxLayout()
        max_float_layout.addWidget(QLabel("Max:"))
        self.max_float_input = QDoubleSpinBox()
        self.max_float_input.setRange(-999999.99, 999999.99)
        self.max_float_input.setDecimals(2)
        self.max_float_input.setValue(100)
        max_float_layout.addWidget(self.max_float_input)
        float_layout.addLayout(max_float_layout)

        step_float_layout = QVBoxLayout()
        step_float_layout.addWidget(QLabel("Step:"))
        self.step_float_input = QDoubleSpinBox()
        self.step_float_input.setRange(0.01, 999999.99)
        self.step_float_input.setDecimals(2)
        self.step_float_input.setValue(0.5)
        step_float_layout.addWidget(self.step_float_input)
        float_layout.addLayout(step_float_layout)

        self.float_widget.setLayout(float_layout)
        layout.addWidget(self.float_widget)

        # Hide special widgets initially
        self.category_widget.hide()
        self.numeric_widget.hide()
        self.float_widget.hide()

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton[text="OK"] {
                background-color: #4CAF50;
                color: white;
            }
            QPushButton[text="OK"]:hover {
                background-color: #45a049;
            }
            QPushButton[text="Cancel"] {
                background-color: #f44336;
                color: white;
            }
            QPushButton[text="Cancel"]:hover {
                background-color: #d32f2f;
            }
        """)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def on_type_changed(self, index):
        """Show/hide appropriate widgets based on type"""
        type_val = self.type_input.currentData()

        self.category_widget.hide()
        self.numeric_widget.hide()
        self.float_widget.hide()
        self.import_widget.hide()

        # Show file import widget for media types
        if type_val in [ColumnType.IMAGE.value, ColumnType.VIDEO.value, ColumnType.AUDIO.value,
                        ColumnType.FILE_PATH.value]:
            self.import_widget.show()

        # Check if the type is Category, Integer, or Float
        type_text = self.type_input.currentText()
        if type_text == "Category":
            self.category_widget.show()
        elif type_text == "Integer":
            self.numeric_widget.show()
        elif type_text == "Float":
            self.float_widget.show()

    def import_files_from_folder(self):
        """Import files from a selected folder"""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Folder with Media Files",
            "",
            QFileDialog.ShowDirsOnly
        )

        if not folder_path:
            return

        # Get extensions filter
        extensions_filter = self.extensions_input.text().strip()
        allowed_extensions = None
        if extensions_filter:
            allowed_extensions = [ext.strip().lower() for ext in extensions_filter.split(',') if ext.strip()]

        # Walk through folder and collect files
        imported_files = []
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                # Get file extension
                _, ext = os.path.splitext(file)
                ext = ext.lower().lstrip('.')

                # Check if extension is allowed
                if allowed_extensions and ext not in allowed_extensions:
                    continue

                # Determine if we store full path or just filename
                if self.path_type_combo.currentIndex() == 0:  # Filename Only
                    imported_files.append(file)
                else:  # Full File Path
                    imported_files.append(os.path.join(root, file))

        if not imported_files:
            QMessageBox.information(
                self,
                "No Files Found",
                f"No files found with extensions: {extensions_filter or 'any'}"
            )
            return

        # Update the imported files list
        self.imported_files = imported_files
        self.update_imported_files_display()

        QMessageBox.information(
            self,
            "Import Complete",
            f"Imported {len(imported_files)} files from:\n{folder_path}"
        )

    def clear_imported_files(self):
        """Clear all imported files"""
        self.imported_files = []
        self.update_imported_files_display()

    def update_imported_files_display(self):
        """Update the displayed list of imported files"""
        self.imported_files_list.clear()
        for file in self.imported_files:
            # Truncate long paths for display
            display_text = file
            if len(display_text) > 80:
                display_text = display_text[:80] + "..."
            self.imported_files_list.addItem(display_text)

        self.import_count_label.setText(f"Files imported: {len(self.imported_files)}")

    def load_column_data(self):
        """Load existing column data into dialog"""
        self.name_input.setText(self.column_data.get('name', ''))
        self.desc_input.setText(self.column_data.get('desc', ''))

        type_val = self.column_data.get('type', 'text')
        index = self.type_input.findData(type_val)
        if index >= 0:
            self.type_input.setCurrentIndex(index)

        self.required_check.setChecked(self.column_data.get('required', False))
        self.unique_check.setChecked(self.column_data.get('unique', False))

        categories = self.column_data.get('categories', [])
        self.categories_text.setText('\n'.join(categories))

        mode = self.column_data.get('category_mode', 'single')
        self.category_mode.setCurrentIndex(0 if mode == 'single' else 1)

        min_val = self.column_data.get('min_size')
        if min_val is not None:
            self.min_input.setValue(int(min_val))
            self.min_float_input.setValue(float(min_val))

        max_val = self.column_data.get('max_size')
        if max_val is not None:
            self.max_input.setValue(int(max_val))
            self.max_float_input.setValue(float(max_val))

        step_val = self.column_data.get('step_size')
        if step_val is not None:
            self.step_input.setValue(int(step_val))
            self.step_float_input.setValue(float(step_val))

        self.on_type_changed(self.type_input.currentIndex())

    def get_column_data(self):
        """Get column data from dialog"""
        type_val = self.type_input.currentData()
        type_text = self.type_input.currentText()

        data = {
            'name': self.name_input.text().strip(),
            'desc': self.desc_input.text().strip(),
            'type': type_val,
            'type_display': type_text,
            'required': self.required_check.isChecked(),
            'unique': self.unique_check.isChecked(),
            'category_mode': 'single' if self.category_mode.currentIndex() == 0 else 'multiple',
            'imported_files': self.imported_files,  # Store imported files
            'store_as_path': self.path_type_combo.currentIndex() == 1,  # True for full path
            'extensions_filter': self.extensions_input.text().strip()
        }

        if type_val == ColumnType.CATEGORY.value:
            categories = self.categories_text.toPlainText().split('\n')
            data['categories'] = [cat.strip() for cat in categories if cat.strip()]
            data['min_size'] = None
            data['max_size'] = None
            data['step_size'] = None
        elif type_val == ColumnType.INTEGER.value:
            data['categories'] = []
            data['min_size'] = self.min_input.value()
            data['max_size'] = self.max_input.value()
            data['step_size'] = self.step_input.value()
        elif type_val == ColumnType.FLOAT.value:
            data['categories'] = []
            data['min_size'] = self.min_float_input.value()
            data['max_size'] = self.max_float_input.value()
            data['step_size'] = self.step_float_input.value()
        else:
            data['categories'] = []
            data['min_size'] = None
            data['max_size'] = None
            data['step_size'] = None

        return data


class ColumnCard(QWidget):
    """Widget for displaying a column as a card"""

    def __init__(self, column_data, index, parent=None):
        super().__init__(parent)
        self.column_data = column_data
        self.index = index
        self.parent_app = parent
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(3)
        layout.setContentsMargins(10, 8, 10, 8)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(5)

        name_label = QLabel(self.column_data.get('name', 'Unnamed'))
        name_label.setStyleSheet("""
            font-weight: bold; 
            font-size: 14px; 
            color: #1c242e;
            font-family: 'Segoe UI', Arial, sans-serif;
        """)
        header_layout.addWidget(name_label)

        if self.column_data.get('required', False):
            required_badge = QLabel("R")
            required_badge.setStyleSheet("""
                background-color: #f44336;
                color: white;
                padding: 0px 6px;
                border-radius: 8px;
                font-size: 9px;
                font-weight: bold;
            """)
            required_badge.setFixedHeight(16)
            required_badge.setToolTip("Required")
            header_layout.addWidget(required_badge)

        if self.column_data.get('unique', False):
            unique_badge = QLabel("U")
            unique_badge.setStyleSheet("""
                background-color: #2196F3;
                color: white;
                padding: 0px 6px;
                border-radius: 8px;
                font-size: 9px;
                font-weight: bold;
            """)
            unique_badge.setFixedHeight(16)
            unique_badge.setToolTip("Unique")
            header_layout.addWidget(unique_badge)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        type_display = self.column_data.get('type_display', self.column_data.get('type', 'Text'))
        type_label = QLabel(type_display)
        type_label.setStyleSheet("""
            background-color: #01433c; 
            color: #d4f3ef;
            padding: 2px 10px;
            border-radius: 10px;
            font-size: 10px;
            font-weight: 600;
            margin-bottom: 4px;
        """)
        type_label.setFixedHeight(20)
        layout.addWidget(type_label)

        if self.column_data.get('desc'):
            desc_label = QLabel(self.column_data['desc'])
            desc_label.setStyleSheet("color: #666; font-size: 11px; margin-top: 2px;")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(3)
        btn_layout.setContentsMargins(0, 4, 0, 0)

        up_btn = QPushButton("↑")
        up_btn.setFixedSize(26, 26)
        up_btn.setStyleSheet("""
            QPushButton {
                background-color: #1c242e;
                color: #d4f3ef;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #283340; }
        """)
        up_btn.clicked.connect(lambda: self.parent_app.move_column_up(self.index))
        btn_layout.addWidget(up_btn)

        down_btn = QPushButton("↓")
        down_btn.setFixedSize(26, 26)
        down_btn.setStyleSheet("""
            QPushButton {
                background-color: #1c242e;
                color: #d4f3ef;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #283340; }
        """)
        down_btn.clicked.connect(lambda: self.parent_app.move_column_down(self.index))
        btn_layout.addWidget(down_btn)

        edit_btn = QPushButton("✎")
        edit_btn.setFixedSize(26, 26)
        edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        edit_btn.clicked.connect(lambda: self.parent_app.edit_column(self.index))
        btn_layout.addWidget(edit_btn)

        delete_btn = QPushButton("×")
        delete_btn.setFixedSize(26, 26)
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        delete_btn.clicked.connect(lambda: self.parent_app.delete_column(self.index))
        btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.setLayout(layout)
        self.setStyleSheet("""
            ColumnCard {
                background-color: #f5f7fa;
                border: 1px solid #dde1e6;
                border-radius: 6px;
                margin: 3px 0px;
            }
            ColumnCard:hover {
                border-color: #4CAF50;
                background-color: #eef3ef;
            }
        """)


class DataTableView(QWidget):
    """Data Table project view - for structured data entry"""

    def __init__(self, parent=None, db=None, project_data=None):
        super().__init__(parent)
        self.parent_app = parent
        self.db = db
        self.project_data = project_data
        self.project_id = project_data.get('id')
        self.data_path = project_data.get('data_path')

        # Get column config from metadata
        self.columns = project_data.get('metadata', {}).get('column_config', [])

        # Data stores
        self.rows = []
        self.row_ids = []
        self.search_filter = ""
        self.selected_row_indices = []
        self.filtered_row_mapping = []

        # Reference table search
        self.linked_table_data = []  # Data from linked table
        self.linked_table_columns = []  # Columns from linked table
        self.linked_table_row_ids = []  # Row IDs from linked table
        self.linked_table_project_id = None
        self.linked_table_name = None
        self.linked_table_data_path = None
        self.is_linked_search_mode = False
        self.persistent_selected_row = None  # Store selected row when searching

        # Initialize attributes
        self.row_counter_label = None
        self.row_inputs = {}
        self.column_cards_layout = None
        self.status_label = None
        self.add_row_btn = None
        self.project_name_label = None
        self.project_desc_label = None

        self.setup_ui()
        self.setup_shortcuts()
        self.load_data()
        self.update_status("Ready")

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)

        # Top bar with project info and buttons
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)
        top_bar.setContentsMargins(5, 0, 5, 0)

        # Back button
        back_btn = QPushButton("← Back to Projects")
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #666;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #555; }
        """)
        back_btn.clicked.connect(self.go_back_to_projects)
        top_bar.addWidget(back_btn)

        # Project name
        if self.project_data:
            self.project_name_label = QLabel(self.project_data.get('name', 'Unnamed Project'))
            self.project_name_label.setStyleSheet("""
                font-weight: bold; 
                font-size: 16px; 
                color: #1c242e;
                font-family: 'Segoe UI', Arial, sans-serif;
            """)
            top_bar.addWidget(self.project_name_label)

            if self.project_data.get('headline'):
                self.project_desc_label = QLabel(f"• {self.project_data['headline']}")
                self.project_desc_label.setStyleSheet("color: #666; font-size: 13px;")
                top_bar.addWidget(self.project_desc_label)

        top_bar.addStretch()

        # Export button (add this)
        export_btn = QPushButton("📤 Export")
        export_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        export_btn.clicked.connect(self.export_data)
        top_bar.addWidget(export_btn)

        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        refresh_btn.clicked.connect(self.refresh_table_data)
        top_bar.addWidget(refresh_btn)

        # Reset Columns button
        reset_cols_btn = QPushButton("🗑️ Reset Columns")
        reset_cols_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #7B1FA2; }
        """)
        reset_cols_btn.clicked.connect(self.reset_columns)
        top_bar.addWidget(reset_cols_btn)

        # Reset Table button
        reset_btn = QPushButton("🔄 Reset Table")
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff9800;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #f57c00; }
        """)
        reset_btn.clicked.connect(self.reset_table)
        top_bar.addWidget(reset_btn)

        layout.addLayout(top_bar)


        # Main content area with three sections
        content_layout = QHBoxLayout()
        content_layout.setSpacing(5)
        content_layout.setContentsMargins(0, 0, 0, 0)

        self.setup_columns_aside()
        self.setup_table_section()
        self.setup_rows_aside()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.columns_aside_widget)
        self.splitter.addWidget(self.table_section_widget)
        self.splitter.addWidget(self.rows_aside_widget)

        self.splitter.setSizes([280, 650, 280])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        content_layout.addWidget(self.splitter)
        layout.addLayout(content_layout)

        self.setLayout(layout)
        self.refresh_table()

    def get_main_window(self):
        """Get the main window by walking up the parent chain"""
        parent = self.parent()
        while parent:
            from PySide6.QtWidgets import QMainWindow
            if isinstance(parent, QMainWindow) and hasattr(parent, 'show_home_tab'):
                return parent
            parent = parent.parent()
        return None

    def go_back_to_projects(self):
        """Navigate back to projects view"""
        main_window = self.get_main_window()
        if main_window and hasattr(main_window, 'show_home_tab'):
            main_window.show_home_tab()
        else:
            from PySide6.QtWidgets import QApplication
            active = QApplication.activeWindow()
            if active and hasattr(active, 'show_home_tab'):
                active.show_home_tab()

    def update_status(self, message):
        """Update status via parent window"""
        if self.parent_app and hasattr(self.parent_app, 'update_status'):
            self.parent_app.update_status(message)

    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self.add_row)

        escape_shortcut = QShortcut(QKeySequence("Escape"), self)
        escape_shortcut.activated.connect(self.clear_selection)

        delete_shortcut = QShortcut(QKeySequence("Delete"), self)
        delete_shortcut.activated.connect(self.delete_selected_rows)

    def setup_columns_aside(self):
        """Setup the columns aside section with cards"""
        self.columns_aside_widget = QWidget()
        self.columns_aside_widget.setMinimumWidth(180)
        self.columns_aside_widget.setMaximumWidth(350)

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)

        add_btn = QPushButton("+ Add Column")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 6px;
                font-size: 13px;
                margin-bottom: 5px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        add_btn.clicked.connect(self.show_add_column_dialog)
        layout.addWidget(add_btn)

        title = QLabel("Columns")
        title.setStyleSheet("font-weight: bold; font-size: 16px; margin-bottom: 3px; color: #1c242e;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.column_cards_container = QWidget()
        self.column_cards_container.setStyleSheet("background: transparent;")
        self.column_cards_layout = QVBoxLayout()
        self.column_cards_layout.setAlignment(Qt.AlignTop)
        self.column_cards_layout.setSpacing(3)
        self.column_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.column_cards_container.setLayout(self.column_cards_layout)

        scroll.setWidget(self.column_cards_container)
        layout.addWidget(scroll)

        self.columns_aside_widget.setLayout(layout)
        self.update_column_cards()

    def setup_table_section(self):
        """Setup the table section with search and table"""
        self.table_section_widget = QWidget()
        self.table_section_widget.setMinimumWidth(300)

        layout = QVBoxLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)

        # Search bar with advanced options
        search_layout = QHBoxLayout()
        search_layout.setSpacing(5)

        # Main search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search data...")
        self.search_input.setStyleSheet("""
            font-size: 13px; 
            padding: 6px 10px; 
            border-radius: 6px;  
            background: #fff; 
            color: #283340;
            border: 2px solid #ddd;
        """)
        self.search_input.textChanged.connect(self.on_search_changed)
        search_layout.addWidget(self.search_input, 1)

        # Column filter dropdown
        self.column_filter_combo = QComboBox()
        self.column_filter_combo.setMaximumWidth(150)
        self.column_filter_combo.addItem("All Columns", None)
        self.column_filter_combo.setStyleSheet("font-size: 12px; padding: 4px;")
        self.column_filter_combo.currentIndexChanged.connect(self.on_search_changed)
        search_layout.addWidget(self.column_filter_combo)

        # Current table checkbox
        self.current_table_check = QCheckBox("Current Table")
        self.current_table_check.setChecked(True)
        self.current_table_check.setMaximumWidth(120)
        self.current_table_check.setStyleSheet("font-size: 12px;")
        self.current_table_check.stateChanged.connect(self.on_search_changed)
        search_layout.addWidget(self.current_table_check)

        # Linked table dropdown
        self.linked_table_combo = QComboBox()
        self.linked_table_combo.setMaximumWidth(180)
        self.linked_table_combo.addItem("Select linked table...", None)
        self.linked_table_combo.setStyleSheet("font-size: 12px; padding: 4px;")
        self.linked_table_combo.currentIndexChanged.connect(self.on_linked_table_changed)
        search_layout.addWidget(self.linked_table_combo)

        # Deselect button
        deselect_btn = QPushButton("✕")
        deselect_btn.setFixedSize(32, 32)
        deselect_btn.setToolTip("Deselect rows")
        deselect_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                color: #1c242e;
                border: 2px solid #ddd;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                border-color: #999;
            }
        """)
        deselect_btn.clicked.connect(self.clear_selection)
        search_layout.addWidget(deselect_btn)

        layout.addLayout(search_layout)

        # Table widget
        self.table_widget = QTableWidget()

        self.table_widget = QTableWidget()
        self.table_widget.setStyleSheet("""
            QTableWidget {
                font-size: 13px;
                gridline-color: #e0e0e0;
                color: #1c242e;
                background-color: #fff;
                alternate-background-color: #fafafa;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QTableWidget::item:selected {
                background-color: #1c242e;
                color: #d4f3ef;
            }
            QHeaderView::section {
                background-color: #f5f7fa;
                padding: 6px 4px;
                font-weight: 600;
                font-size: 12px;
                border-bottom: 2px solid #1c242e;
                color: #1c242e;
                border-right: 1px solid #e0e0e0;
            }
            QHeaderView::section:last { border-right: none; }
        """)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table_widget.itemSelectionChanged.connect(self.on_table_selection_changed)

        self.table_widget.horizontalHeader().setSectionsMovable(True)
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.setShowGrid(True)

        layout.addWidget(self.table_widget)
        self.table_section_widget.setLayout(layout)

    def setup_rows_aside(self):
        """Setup the rows aside section for adding data"""
        self.rows_aside_widget = QWidget()
        self.rows_aside_widget.setMinimumWidth(180)
        self.rows_aside_widget.setMaximumWidth(350)

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)

        title = QLabel("Row Data")
        title.setStyleSheet("font-weight: bold; font-size: 16px; margin-bottom: 3px; color: #1c242e;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.row_inputs_container = QWidget()
        self.row_inputs_container.setStyleSheet("background: transparent;")
        self.row_inputs_layout = QVBoxLayout()
        self.row_inputs_layout.setAlignment(Qt.AlignTop)
        self.row_inputs_layout.setSpacing(2)
        self.row_inputs_layout.setContentsMargins(0, 0, 0, 0)
        self.row_inputs_container.setLayout(self.row_inputs_layout)

        scroll.setWidget(self.row_inputs_container)
        layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(5)

        self.add_row_btn = QPushButton("Add Row (Ctrl+Enter)")
        self.add_row_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 6px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        self.add_row_btn.clicked.connect(self.add_row)
        btn_layout.addWidget(self.add_row_btn)

        clear_row_btn = QPushButton("Clear")
        clear_row_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 6px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        clear_row_btn.clicked.connect(self.clear_row_inputs)
        btn_layout.addWidget(clear_row_btn)

        layout.addLayout(btn_layout)

        self.row_counter_label = QLabel("Rows: 0")
        self.row_counter_label.setStyleSheet("color: #666; font-size: 11px; padding: 3px;")
        layout.addWidget(self.row_counter_label)

        self.rows_aside_widget.setLayout(layout)
        self.update_row_inputs()

    def load_data(self):
        """Load data from the project database"""
        if self.data_path and os.path.exists(self.data_path):
            conn = sqlite3.connect(self.data_path)
            cursor = conn.cursor()

            try:
                cursor.execute('SELECT * FROM data ORDER BY id')
                rows_with_ids = cursor.fetchall()
                conn.close()

                # Get column order from database (excluding internal columns)
                conn2 = sqlite3.connect(self.data_path)
                cursor2 = conn2.cursor()
                cursor2.execute("PRAGMA table_info(data)")
                db_columns = cursor2.fetchall()
                conn2.close()

                # Get the column names in database order
                db_column_names = []
                for col in db_columns:
                    col_name = col[1]
                    if col_name not in ['id', '_row_created_at', '_row_updated_at']:
                        db_column_names.append(col_name)

                # Get column order from self.columns (application order)
                app_column_names = [col['name'] for col in self.columns]

                self.row_ids = []
                self.rows = []
                for row in rows_with_ids:
                    self.row_ids.append(row[0])  # id is always first

                    # Skip the first 3 columns (id, _row_created_at, _row_updated_at)
                    # and take the rest in database order
                    db_order_values = list(row[3:])  # Skip id and timestamp columns

                    # Now map from database order to application order
                    app_order_values = []
                    for app_col_name in app_column_names:
                        # Find the value for this column in database order
                        found = False
                        for i, db_col_name in enumerate(db_column_names):
                            if db_col_name == app_col_name:
                                app_order_values.append(db_order_values[i] if i < len(db_order_values) else '')
                                found = True
                                break
                        if not found:
                            app_order_values.append('')

                    self.rows.append(app_order_values)

            except sqlite3.OperationalError:
                conn.close()
                self.rows = []
                self.row_ids = []
        else:
            self.rows = []
            self.row_ids = []
        self.refresh_table()

        # Load linked tables
        self.load_linked_tables()
        self.update_column_filter()

    def refresh_table_data(self):
        """Refresh the table data from the database"""
        self.load_data()
        self.update_status("Table refreshed")

    def reset_columns(self):
        """Reset/delete all columns from the table"""
        if not self.columns:
            QMessageBox.information(self, "Reset Columns", "No columns to reset!")
            return

        # Check if there are rows with data
        has_data = any(any(cell for cell in row) for row in self.rows)

        if has_data:
            reply = QMessageBox.question(
                self, "Reset Columns",
                "This will delete ALL columns AND ALL ROW DATA in the table. "
                "This action cannot be undone!\n\nAre you sure you want to continue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        else:
            reply = QMessageBox.question(
                self, "Reset Columns",
                "This will delete ALL columns. The table will be empty.\n\n"
                "This action cannot be undone!\n\nAre you sure?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        try:
            # Delete all rows from the database first
            if self.db and self.data_path:
                # Drop the entire data table and recreate it
                conn = sqlite3.connect(self.data_path)
                cursor = conn.cursor()

                # Drop the data table
                cursor.execute("DROP TABLE IF EXISTS data")

                # Recreate the data table with just the internal columns
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        _row_created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        _row_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                conn.commit()
                conn.close()

            # Clear the columns list and rows data
            self.columns = []
            self.rows = []
            self.row_ids = []
            self.selected_row_indices = []
            self.search_filter = ""

            # Update project metadata in the main database
            if self.db and self.project_id:
                metadata = self.project_data.get('metadata', {})
                metadata['column_config'] = self.columns
                self.db.update_project(self.project_id, metadata=metadata)

            # Refresh the UI
            self.refresh_table()
            self.update_column_cards()
            self.update_row_inputs()
            self.search_input.clear()

            self.update_status("Columns reset - table is empty")
            QMessageBox.information(self, "Success", "All columns have been removed.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to reset columns:\n{str(e)}")
            self.update_status("Error resetting columns")

    def reset_table(self):
        """Reset/clear all data from the table"""
        if not self.rows:
            QMessageBox.information(self, "Reset Table", "Table is already empty!")
            return

        reply = QMessageBox.question(
            self, "Reset Table",
            "This will delete ALL rows in the table. This action cannot be undone!\n\nAre you sure?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.db and self.data_path:
                for i in range(len(self.rows) - 1, -1, -1):
                    db_row_id = self.row_ids[i]
                    self.db.delete_table_row(self.data_path, db_row_id)

            self.rows = []
            self.row_ids = []
            self.selected_row_indices = []
            self.refresh_table()
            self.clear_row_inputs()
            if self.add_row_btn:
                self.add_row_btn.setText("Add Row (Ctrl+Enter)")
            self.update_status("Table reset - all rows deleted")

    # ========== COLUMN METHODS ==========
    def show_add_column_dialog(self):
        """Show dialog to add a new column"""
        dialog = ColumnDialog(self)
        if dialog.exec() == QDialog.Accepted:
            column_data = dialog.get_column_data()
            if column_data['name']:
                self.columns.append(column_data)

                # Add the column to the database
                if self.db and self.project_id:
                    metadata = self.project_data.get('metadata', {})
                    metadata['column_config'] = self.columns
                    self.db.update_project(self.project_id, metadata=metadata)
                    self.db.add_table_column(self.data_path, column_data['name'], column_data['type'])

                # If there are imported files, populate the column with them
                imported_files = column_data.get('imported_files', [])
                if imported_files:
                    # Add rows for each imported file
                    for file_path in imported_files:
                        row_data = [""] * len(self.columns)
                        row_data[-1] = file_path  # Add to the new column
                        self.rows.append(row_data)
                        if self.db and self.data_path:
                            self.db.add_table_row(self.data_path, row_data)
                            # Get the new row ID
                            conn = sqlite3.connect(self.data_path)
                            cursor = conn.cursor()
                            cursor.execute('SELECT last_insert_rowid()')
                            new_id = cursor.fetchone()[0]
                            conn.close()
                            self.row_ids.append(new_id)

                self.refresh_table()
                self.update_column_cards()
                self.update_row_inputs()
                self.update_status(f"Added column: {column_data['name']} with {len(imported_files)} files")

    def edit_column(self, index):
        """Edit an existing column"""
        if 0 <= index < len(self.columns):
            if self.rows:
                reply = QMessageBox.question(
                    self, "Edit Column",
                    "Editing a column will clear all existing row data. Continue?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return

            dialog = ColumnDialog(self, self.columns[index])
            if dialog.exec() == QDialog.Accepted:
                column_data = dialog.get_column_data()
                if column_data['name']:
                    self.columns[index] = column_data
                    if self.db and self.project_id:
                        metadata = self.project_data.get('metadata', {})
                        metadata['column_config'] = self.columns
                        self.db.update_project(self.project_id, metadata=metadata)
                    self.rows = []
                    self.row_ids = []
                    self.selected_row_indices = []
                    self.refresh_table()
                    self.update_column_cards()
                    self.update_row_inputs()
                    self.update_status(f"Updated column: {column_data['name']}")

    def delete_column(self, index):
        """Delete a column"""
        if 0 <= index < len(self.columns):
            column_name = self.columns[index]['name']
            reply = QMessageBox.question(
                self, "Delete Column",
                f"Delete column '{column_name}'? This will clear all row data.",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                # Remove column from database
                if self.db and self.data_path:
                    conn = sqlite3.connect(self.data_path)
                    cursor = conn.cursor()

                    # SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
                    # 1. Get current table info
                    cursor.execute("PRAGMA table_info(data)")
                    columns = cursor.fetchall()

                    # 2. Get all column names except the one to delete
                    keep_columns = []
                    for col in columns:
                        col_name = col[1]
                        if col_name != column_name and col_name not in ['id', '_row_created_at', '_row_updated_at']:
                            keep_columns.append(col_name)

                    # 3. Create a new table without the column
                    cursor.execute("ALTER TABLE data RENAME TO data_old")

                    # 4. Create new table with columns we want to keep
                    create_sql = '''
                        CREATE TABLE data (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            _row_created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            _row_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    '''
                    cursor.execute(create_sql)

                    # 5. Add back the columns we want to keep
                    for col in keep_columns:
                        cursor.execute(f"ALTER TABLE data ADD COLUMN '{col}' TEXT")

                    # 6. Copy data from old table to new table
                    if keep_columns:
                        columns_str = ', '.join([f'"{col}"' for col in keep_columns])
                        cursor.execute(f"INSERT INTO data ({columns_str}) SELECT {columns_str} FROM data_old")

                    # 7. Drop old table
                    cursor.execute("DROP TABLE data_old")

                    conn.commit()
                    conn.close()

                # Remove from metadata
                del self.columns[index]
                if self.db and self.project_id:
                    metadata = self.project_data.get('metadata', {})
                    metadata['column_config'] = self.columns
                    self.db.update_project(self.project_id, metadata=metadata)

                self.rows = []
                self.row_ids = []
                self.selected_row_indices = []
                self.refresh_table()
                self.update_column_cards()
                self.update_row_inputs()
                self.update_status(f"Deleted column: {column_name}")

    def move_column_up(self, index):
        if index > 0:
            self.columns[index], self.columns[index - 1] = self.columns[index - 1], self.columns[index]
            if self.db and self.project_id:
                metadata = self.project_data.get('metadata', {})
                metadata['column_config'] = self.columns
                self.db.update_project(self.project_id, metadata=metadata)
            self.update_column_cards()
            self.refresh_table()
            self.update_row_inputs()

    def move_column_down(self, index):
        if index < len(self.columns) - 1:
            self.columns[index], self.columns[index + 1] = self.columns[index + 1], self.columns[index]
            if self.db and self.project_id:
                metadata = self.project_data.get('metadata', {})
                metadata['column_config'] = self.columns
                self.db.update_project(self.project_id, metadata=metadata)
            self.update_column_cards()
            self.refresh_table()
            self.update_row_inputs()

    def update_column_cards(self):
        """Update the column cards display"""
        while self.column_cards_layout.count():
            item = self.column_cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, column in enumerate(self.columns):
            card = ColumnCard(column, i, self)
            self.column_cards_layout.addWidget(card)

        if not self.columns:
            label = QLabel("No columns defined.\nClick '+ Add Column' to start.")
            label.setStyleSheet("color: #999; padding: 20px; font-size: 13px;")
            label.setAlignment(Qt.AlignCenter)
            self.column_cards_layout.addWidget(label)

    # ========== TABLE METHODS ==========
    def refresh_table(self):
        """Refresh the table with current columns and rows"""
        if self.is_linked_search_mode:
            # Don't refresh if we're showing linked search results
            return

        if not self.columns:
            self.table_widget.setColumnCount(0)
            self.table_widget.setRowCount(0)
            self.table_widget.setHorizontalHeaderLabels([])
            if self.row_counter_label:
                self.row_counter_label.setText("Rows: 0")
            return

        # Get column names from self.columns (which should already be in correct order)
        column_names = [col['name'] for col in self.columns]
        self.table_widget.setColumnCount(len(column_names))
        self.table_widget.setHorizontalHeaderLabels(column_names)

        for i in range(len(column_names)):
            self.table_widget.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)

        self.filtered_row_mapping = []
        filtered_rows = []

        if self.search_filter:
            for row_idx, row in enumerate(self.rows):
                row_matches = False
                for value in row:
                    if self.search_filter.lower() in str(value).lower():
                        row_matches = True
                        break
                if row_matches:
                    filtered_rows.append(row)
                    self.filtered_row_mapping.append(row_idx)
        else:
            filtered_rows = self.rows
            self.filtered_row_mapping = list(range(len(self.rows)))

        self.table_widget.setRowCount(len(filtered_rows))

        for i, row in enumerate(filtered_rows):
            for j, col_name in enumerate(column_names):
                # Get the value for this column
                if j < len(row):
                    value = row[j]
                else:
                    value = ''
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                self.table_widget.setItem(i, j, item)

        if self.row_counter_label:
            total_rows = len(self.rows)
            showing = len(filtered_rows)
            if total_rows == showing:
                self.row_counter_label.setText(f"Rows: {total_rows}")
            else:
                self.row_counter_label.setText(f"Rows: {total_rows} (Showing: {showing})")

    def on_search_changed(self, text=None):
        """Handle search changes"""
        query = self.search_input.text().strip()

        if not query:
            # Reset to normal view
            self.is_linked_search_mode = False
            # Disconnect double-click signal when exiting search mode
            try:
                self.table_widget.itemDoubleClicked.disconnect()
            except:
                pass
            self.refresh_table()
            self.restore_persistent_selection()
            return

        if self.current_table_check.isChecked():
            # Search in current table
            self.search_current_table(query)
        else:
            # Search in linked table
            self.search_linked_table(query)
            
    def search_current_table(self, query):
        """Search in the current table"""
        self.is_linked_search_mode = False

        # Get column filter
        column_filter = self.column_filter_combo.currentData()

        # Filter rows
        self.filtered_row_mapping = []
        filtered_rows = []

        for row_idx, row in enumerate(self.rows):
            row_matches = False
            for j, value in enumerate(row):
                # Check column filter
                if column_filter and j < len(self.columns) and self.columns[j]['name'] != column_filter:
                    continue
                if query.lower() in str(value).lower():
                    row_matches = True
                    break
            if row_matches:
                filtered_rows.append(row)
                self.filtered_row_mapping.append(row_idx)

        self.display_filtered_rows(filtered_rows)
        self.restore_persistent_selection()

    def search_linked_table(self, query):
        """Search in the linked table"""
        if not self.linked_table_data:
            QMessageBox.information(self, "No Linked Table", "Please select a linked table first.")
            return

        self.is_linked_search_mode = True

        # Get column filter
        column_filter = self.column_filter_combo.currentData()

        # Search in linked table
        matches = []
        for row_idx, row in enumerate(self.linked_table_data):
            row_matches = False
            for j, value in enumerate(row):
                # Check column filter
                if column_filter and j < len(self.linked_table_columns) and self.linked_table_columns[
                    j] != column_filter:
                    continue
                if query.lower() in str(value).lower():
                    row_matches = True
                    break
            if row_matches:
                matches.append((row_idx, row))

        # Display results in the table
        self.display_linked_search_results(matches)

    def display_filtered_rows(self, filtered_rows):
        """Display filtered rows in the table"""
        if not self.columns:
            self.table_widget.setColumnCount(0)
            self.table_widget.setRowCount(0)
            self.table_widget.setHorizontalHeaderLabels([])
            return

        column_names = [col['name'] for col in self.columns]
        self.table_widget.setColumnCount(len(column_names))
        self.table_widget.setHorizontalHeaderLabels(column_names)

        self.table_widget.setRowCount(len(filtered_rows))

        for i, row in enumerate(filtered_rows):
            for j, value in enumerate(row):
                if j < len(column_names):
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignCenter)
                    self.table_widget.setItem(i, j, item)

        if self.row_counter_label:
            total_rows = len(self.rows)
            showing = len(filtered_rows)
            if total_rows == showing:
                self.row_counter_label.setText(f"Rows: {total_rows}")
            else:
                self.row_counter_label.setText(f"Rows: {total_rows} (Showing: {showing})")

    def display_linked_search_results(self, matches):
        """Display linked table search results"""
        if not matches:
            self.table_widget.setColumnCount(0)
            self.table_widget.setRowCount(0)
            self.table_widget.setHorizontalHeaderLabels([])
            if self.row_counter_label:
                self.row_counter_label.setText(f"Linked Results: 0")
            return

        # Use linked table columns
        column_names = self.linked_table_columns
        self.table_widget.setColumnCount(len(column_names))
        self.table_widget.setHorizontalHeaderLabels(column_names)

        self.table_widget.setRowCount(len(matches))

        for i, (row_idx, row) in enumerate(matches):
            for j, value in enumerate(row):
                if j < len(column_names):
                    # Make items clickable
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignCenter)
                    # Store the actual row index from the linked table data
                    # The row_idx is the index in self.linked_table_data
                    item.setData(Qt.UserRole, row_idx)
                    self.table_widget.setItem(i, j, item)

        # Disconnect any existing connections to avoid duplicates
        try:
            self.table_widget.itemDoubleClicked.disconnect()
        except:
            pass

        # Connect the double-click signal
        self.table_widget.itemDoubleClicked.connect(self.view_linked_row_details)

        if self.row_counter_label:
            self.row_counter_label.setText(f"Linked Results: {len(matches)}")

    # ========== ROW METHODS ==========
    def update_row_inputs(self):
        """Update row input fields based on current columns"""
        while self.row_inputs_layout.count():
            item = self.row_inputs_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.row_inputs = {}
        for i, column in enumerate(self.columns):
            widget = QWidget()
            widget.setStyleSheet("background: transparent;")
            layout = QVBoxLayout()
            layout.setSpacing(2)
            layout.setContentsMargins(0, 3, 0, 3)

            label = QLabel(column['name'])
            label.setStyleSheet("font-weight: 600; font-size: 12px; color: #1c242e;")
            layout.addWidget(label)

            if column.get('desc'):
                desc_label = QLabel(column['desc'])
                desc_label.setStyleSheet("color: #888; font-size: 10px;")
                desc_label.setWordWrap(True)
                layout.addWidget(desc_label)

            input_widget = None
            is_media_type = column['type'] in [ColumnType.IMAGE.value, ColumnType.VIDEO.value,
                                               ColumnType.AUDIO.value, ColumnType.FILE_PATH.value]

            if column['type'] == ColumnType.CATEGORY.value:
                if column.get('category_mode', 'single') == 'multiple':
                    input_widget = QListWidget()
                    input_widget.setStyleSheet("""
                        QListWidget {
                            padding: 3px 5px;
                            font-size: 12px;
                            border: 1px solid #ccc;
                            border-radius: 4px;
                            max-height: 80px;
                            background: white;
                        }
                        QListWidget::item:selected {
                            background-color: #1c242e;
                            color: #d4f3ef;
                        }
                    """)
                    input_widget.setSelectionMode(QAbstractItemView.MultiSelection)
                    for cat in column.get('categories', []):
                        input_widget.addItem(cat)
                else:
                    input_widget = QComboBox()
                    input_widget.setStyleSheet("padding: 3px 5px; font-size: 12px;")
                    input_widget.addItems(column.get('categories', []))
                    input_widget.setEditable(True)
            elif column['type'] == ColumnType.INTEGER.value:
                input_widget = QSpinBox()
                input_widget.setStyleSheet("padding: 3px 5px; font-size: 12px;")
                if column.get('min_size') is not None:
                    input_widget.setRange(int(column['min_size']), int(column['max_size'] or 999999))
                else:
                    input_widget.setRange(-999999, 999999)
                if column.get('step_size'):
                    input_widget.setSingleStep(int(column['step_size']))
            elif column['type'] == ColumnType.FLOAT.value:
                input_widget = QDoubleSpinBox()
                input_widget.setStyleSheet("padding: 3px 5px; font-size: 12px;")
                input_widget.setDecimals(2)
                if column.get('min_size') is not None:
                    input_widget.setRange(column['min_size'], column['max_size'] or 999999.99)
                else:
                    input_widget.setRange(-999999.99, 999999.99)
                if column.get('step_size'):
                    input_widget.setSingleStep(column['step_size'])
            else:
                # For text and file path types
                if is_media_type:
                    # Create a horizontal layout for text input + view button
                    media_widget = QWidget()
                    media_layout = QHBoxLayout()
                    media_layout.setSpacing(4)
                    media_layout.setContentsMargins(0, 0, 0, 0)

                    input_widget = QTextEdit()
                    input_widget.setStyleSheet("""
                        QTextEdit {
                            padding: 3px 5px;
                            font-size: 13px;
                            border: 1px solid #ccc;
                            border-radius: 4px;
                            max-height: 60px;
                            background: #fff; 
                            color: #283340;
                        }
                    """)
                    input_widget.setPlaceholderText(f"Enter {column['name']}...")
                    input_widget.installEventFilter(self)
                    media_layout.addWidget(input_widget, 1)

                    # View button for media files
                    view_btn = QPushButton("View")
                    view_btn.setFixedWidth(50)
                    view_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #2196F3;
                            color: white;
                            font-weight: bold;
                            padding: 4px 8px;
                            border-radius: 4px;
                            font-size: 11px;
                        }
                        QPushButton:hover { background-color: #1976D2; }
                    """)
                    view_btn.clicked.connect(lambda checked, col_idx=i: self.view_media_file(col_idx))
                    media_layout.addWidget(view_btn)

                    media_widget.setLayout(media_layout)
                    layout.addWidget(media_widget)
                    self.row_inputs[i] = input_widget
                    # Store reference to view button row for later use
                    self.row_inputs[f'view_{i}'] = view_btn
                else:
                    input_widget = QTextEdit()
                    input_widget.setStyleSheet("""
                        QTextEdit {
                            padding: 3px 5px;
                            font-size: 13px;
                            border: 1px solid #ccc;
                            border-radius: 4px;
                            max-height: 60px;
                            background: #fff; 
                            color: #283340;
                        }
                    """)
                    input_widget.setPlaceholderText(f"Enter {column['name']}...")
                    input_widget.installEventFilter(self)

            if input_widget and not is_media_type:
                layout.addWidget(input_widget)
                self.row_inputs[i] = input_widget

            # Add badges
            if input_widget or is_media_type:
                badge_layout = QHBoxLayout()
                badge_layout.setSpacing(5)

                if column.get('required', False):
                    req_badge = QLabel("Required")
                    req_badge.setStyleSheet("color: #f44336; font-size: 9px; font-weight: bold;")
                    badge_layout.addWidget(req_badge)

                if column.get('unique', False):
                    unique_badge = QLabel("Unique")
                    unique_badge.setStyleSheet("color: #2196F3; font-size: 9px; font-weight: bold;")
                    badge_layout.addWidget(unique_badge)

                badge_layout.addStretch()
                layout.addLayout(badge_layout)

            widget.setMaximumHeight(150 if not is_media_type else 120)
            widget.setLayout(layout)

            if i < len(self.columns) - 1:
                separator = QFrame()
                separator.setFrameShape(QFrame.HLine)
                separator.setFrameShadow(QFrame.Sunken)
                separator.setStyleSheet("margin: 1px 0px; background: #e0e0e0;")
                separator.setFixedHeight(1)
                self.row_inputs_layout.addWidget(separator)

            self.row_inputs_layout.addWidget(widget)

    def view_media_file(self, col_index):
        """Open the media file using system default application"""
        if col_index < 0 or col_index >= len(self.columns):
            return

        # Get the value from the input widget
        if col_index not in self.row_inputs:
            return

        widget = self.row_inputs[col_index]
        if not widget:
            return

        file_path = widget.toPlainText().strip()
        if not file_path:
            QMessageBox.information(self, "No File", "No file path specified.")
            return

        # Check if file exists
        if not os.path.exists(file_path):
            # Try to find the file in the project directory or data path
            base_dir = os.path.dirname(self.data_path) if self.data_path else ""
            if base_dir:
                # Try relative path
                possible_path = os.path.join(base_dir, file_path)
                if os.path.exists(possible_path):
                    file_path = possible_path
                else:
                    QMessageBox.warning(self, "File Not Found", f"File not found:\n{file_path}")
                    return
            else:
                QMessageBox.warning(self, "File Not Found", f"File not found:\n{file_path}")
                return

        try:
            # Open with system default application
            import subprocess
            import sys
            if sys.platform.startswith('darwin'):  # macOS
                subprocess.run(['open', file_path])
            elif sys.platform.startswith('win'):  # Windows
                os.startfile(file_path)
            else:  # Linux
                subprocess.run(['xdg-open', file_path])
            self.update_status(f"Opened: {os.path.basename(file_path)}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open file:\n{str(e)}")

    def eventFilter(self, obj, event):
        """Handle Tab key in QTextEdit to move to next input"""
        if isinstance(obj, QTextEdit) and event.type() == event.type().KeyPress:
            if event.key() == Qt.Key_Tab:
                self.focusNextChild()
                return True
        return super().eventFilter(obj, event)

    def load_row_data(self, row_index):
        if 0 <= row_index < len(self.rows):
            row_data = self.rows[row_index]
            for i, column in enumerate(self.columns):
                if i in self.row_inputs:
                    widget = self.row_inputs[i]
                    # Get the value for this column - if the row has fewer columns, use empty string
                    value = row_data[i] if i < len(row_data) else ''

                    if isinstance(widget, QLineEdit):
                        widget.setText(str(value))
                    elif isinstance(widget, QTextEdit):
                        widget.setText(str(value))
                    elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                        try:
                            widget.setValue(float(value) if value else widget.minimum())
                        except (ValueError, TypeError):
                            widget.setValue(widget.minimum())
                    elif isinstance(widget, QComboBox):
                        idx = widget.findText(str(value))
                        if idx >= 0:
                            widget.setCurrentIndex(idx)
                        else:
                            widget.setEditText(str(value))
                    elif isinstance(widget, QListWidget):
                        widget.clearSelection()
                        items = str(value).split(',') if value else []
                        for item_text in items:
                            item_text = item_text.strip()
                            for j in range(widget.count()):
                                if widget.item(j).text() == item_text:
                                    widget.item(j).setSelected(True)
                                    break

    def clear_row_inputs(self):
        for widget in self.row_inputs.values():
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QTextEdit):
                widget.clear()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(widget.minimum())
            elif isinstance(widget, QComboBox):
                if widget.count() > 0:
                    widget.setCurrentIndex(-1)
            elif isinstance(widget, QListWidget):
                widget.clearSelection()
        self.selected_row_indices = []
        if self.add_row_btn:
            self.add_row_btn.setText("Add Row (Ctrl+Enter)")
        self.update_status("Inputs cleared")

    def clear_selection(self):
        self.table_widget.clearSelection()
        self.selected_row_indices = []
        self.clear_row_inputs()
        if self.add_row_btn:
            self.add_row_btn.setText("Add Row (Ctrl+Enter)")
        self.update_status("Selection cleared")

    def get_row_data_from_inputs(self):
        row_data = []
        for i in range(len(self.columns)):
            if i in self.row_inputs:
                widget = self.row_inputs[i]
                if isinstance(widget, QLineEdit):
                    value = widget.text()
                elif isinstance(widget, QTextEdit):
                    value = widget.toPlainText()
                elif isinstance(widget, QSpinBox):
                    value = widget.value()
                elif isinstance(widget, QDoubleSpinBox):
                    value = widget.value()
                elif isinstance(widget, QComboBox):
                    value = widget.currentText()
                elif isinstance(widget, QListWidget):
                    selected = [widget.item(j).text() for j in range(widget.count()) if widget.item(j).isSelected()]
                    value = ', '.join(selected) if selected else ''
                else:
                    value = ""
                row_data.append(value)
            else:
                row_data.append("")
        return row_data

    def add_row(self):
        if not self.columns:
            QMessageBox.warning(self, "No Columns", "Please add columns first!")
            return

        row_data = self.get_row_data_from_inputs()

        # Validate required fields
        for i, column in enumerate(self.columns):
            if column.get('required', False):
                value = row_data[i]
                if i in self.row_inputs and isinstance(self.row_inputs[i], QListWidget):
                    widget = self.row_inputs[i]
                    has_selection = any(widget.item(j).isSelected() for j in range(widget.count()))
                    if not has_selection:
                        QMessageBox.warning(self, "Required Field", f"'{column['name']}' is required!")
                        return
                elif not str(value).strip():
                    QMessageBox.warning(self, "Required Field", f"'{column['name']}' is required!")
                    return

        if self.selected_row_indices:
            if len(self.selected_row_indices) == 1:
                row_idx = self.selected_row_indices[0]
                existing_row = self.rows[row_idx]

                if row_data != existing_row:
                    reply = QMessageBox.question(self, "Update Row", "Update the selected row?",
                                                 QMessageBox.Yes | QMessageBox.No)
                    if reply == QMessageBox.Yes:
                        self.rows[row_idx] = row_data
                        if self.db and self.data_path:
                            db_row_id = self.row_ids[row_idx]

                            # Get the actual column order from the database
                            conn = sqlite3.connect(self.data_path)
                            cursor = conn.cursor()
                            cursor.execute("PRAGMA table_info(data)")
                            db_columns = cursor.fetchall()
                            conn.close()

                            # Get non-internal column names in database order
                            db_column_names = []
                            for col in db_columns:
                                col_name = col[1]
                                if col_name not in ['id', '_row_created_at', '_row_updated_at']:
                                    db_column_names.append(col_name)

                            # Create a mapping from column name to value from row_data
                            # row_data is in self.columns order
                            col_to_value = {}
                            for i, col in enumerate(self.columns):
                                col_to_value[col['name']] = row_data[i] if i < len(row_data) else ''

                            # Create row data in database column order
                            db_row_data = []
                            for db_col_name in db_column_names:
                                db_row_data.append(col_to_value.get(db_col_name, ''))

                            # Update the row with data in database order
                            self.db.update_table_row(self.data_path, db_row_id, db_row_data)

                        self.refresh_table()
                        self.clear_row_inputs()
                        self.update_status(f"Updated row {row_idx + 1}")
                        return
                    else:
                        return
                else:
                    self.clear_row_inputs()
                    return
            else:
                # Multiple rows update
                reply = QMessageBox.question(
                    self, "Update Multiple Rows",
                    f"Apply changes to {len(self.selected_row_indices)} selected rows?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    for row_idx in self.selected_row_indices:
                        self.rows[row_idx] = row_data.copy()
                        if self.db and self.data_path:
                            db_row_id = self.row_ids[row_idx]

                            # Get database column order
                            conn = sqlite3.connect(self.data_path)
                            cursor = conn.cursor()
                            cursor.execute("PRAGMA table_info(data)")
                            db_columns = cursor.fetchall()
                            conn.close()

                            db_column_names = []
                            for col in db_columns:
                                col_name = col[1]
                                if col_name not in ['id', '_row_created_at', '_row_updated_at']:
                                    db_column_names.append(col_name)

                            # Create column to value mapping
                            col_to_value = {}
                            for i, col in enumerate(self.columns):
                                col_to_value[col['name']] = row_data[i] if i < len(row_data) else ''

                            # Map data to database order
                            db_row_data = []
                            for db_col_name in db_column_names:
                                db_row_data.append(col_to_value.get(db_col_name, ''))

                            self.db.update_table_row(self.data_path, db_row_id, db_row_data)

                    self.refresh_table()
                    self.clear_row_inputs()
                    self.update_status(f"Updated {len(self.selected_row_indices)} rows")
                    return
                else:
                    return

        # Add new row - ensure data is in the correct order
        if self.db and self.data_path:
            conn = sqlite3.connect(self.data_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(data)")
            db_columns = cursor.fetchall()
            conn.close()

            db_column_names = []
            for col in db_columns:
                col_name = col[1]
                if col_name not in ['id', '_row_created_at', '_row_updated_at']:
                    db_column_names.append(col_name)

            # Create column to value mapping
            col_to_value = {}
            for i, col in enumerate(self.columns):
                col_to_value[col['name']] = row_data[i] if i < len(row_data) else ''

            # Create row data in database order
            db_row_data = []
            for db_col_name in db_column_names:
                db_row_data.append(col_to_value.get(db_col_name, ''))

            self.rows.append(row_data)  # Keep in app order for display
            self.db.add_table_row(self.data_path, db_row_data)  # Save in database order

            # Get the new row ID
            conn = sqlite3.connect(self.data_path)
            cursor = conn.cursor()
            cursor.execute('SELECT last_insert_rowid()')
            new_id = cursor.fetchone()[0]
            conn.close()
            self.row_ids.append(new_id)
        else:
            self.rows.append(row_data)

        self.refresh_table()
        self.clear_row_inputs()
        self.update_status(f"Added row {len(self.rows)}")

    def delete_selected_rows(self):
        if not self.selected_row_indices:
            QMessageBox.information(self, "No Selection", "Please select rows to delete.")
            return

        count = len(self.selected_row_indices)
        reply = QMessageBox.question(
            self, "Delete Rows",
            f"Delete {count} selected row(s)?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            for row_idx in sorted(self.selected_row_indices, reverse=True):
                if self.db and self.data_path:
                    db_row_id = self.row_ids[row_idx]
                    self.db.delete_table_row(self.data_path, db_row_id)
                del self.rows[row_idx]
                del self.row_ids[row_idx]

            self.selected_row_indices = []
            self.refresh_table()
            self.clear_row_inputs()
            self.update_status(f"Deleted {count} row(s)")

    def export_data(self):
        """Export table data to CSV, TSV, or JSON"""
        if not self.rows or not self.columns:
            QMessageBox.information(self, "No Data", "No data to export.")
            return

        # Create export dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Export Data")
        dialog.setModal(True)
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout()

        # File format selection
        layout.addWidget(QLabel("Export Format:"))
        format_combo = QComboBox()
        format_combo.addItems(["CSV", "TSV", "JSON"])
        format_combo.setStyleSheet("font-size: 13px; padding: 5px;")
        layout.addWidget(format_combo)

        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout()

        include_headers_check = QCheckBox("Include Column Headers")
        include_headers_check.setChecked(True)
        options_layout.addWidget(include_headers_check)

        # Which rows to export
        layout.addWidget(QLabel("Rows to Export:"))
        rows_combo = QComboBox()
        rows_combo.addItems(["All Rows", "Selected Rows Only"])
        rows_combo.setStyleSheet("font-size: 13px; padding: 5px;")
        options_layout.addWidget(rows_combo)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton[text="OK"] {
                background-color: #4CAF50;
                color: white;
            }
            QPushButton[text="OK"]:hover {
                background-color: #45a049;
            }
            QPushButton[text="Cancel"] {
                background-color: #f44336;
                color: white;
            }
            QPushButton[text="Cancel"]:hover {
                background-color: #d32f2f;
            }
        """)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)

        if dialog.exec() != QDialog.Accepted:
            return

        # Get export options
        format_type = format_combo.currentText().lower()
        include_headers = include_headers_check.isChecked()
        export_selected_only = rows_combo.currentIndex() == 1

        # Determine which rows to export
        if export_selected_only and self.selected_row_indices:
            rows_to_export = [self.rows[i] for i in self.selected_row_indices if i < len(self.rows)]
            if not rows_to_export:
                QMessageBox.warning(self, "No Selection", "No rows selected for export.")
                return
        else:
            rows_to_export = self.rows

        # Get column names
        column_names = [col['name'] for col in self.columns]

        # Get file extension and filter
        if format_type == 'csv':
            ext = '.csv'
            file_filter = "CSV Files (*.csv)"
        elif format_type == 'tsv':
            ext = '.tsv'
            file_filter = "TSV Files (*.tsv)"
        else:  # json
            ext = '.json'
            file_filter = "JSON Files (*.json)"

        # Ask for save location
        default_filename = f"{self.project_data.get('name', 'export')}{ext}"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Data",
            default_filename,
            file_filter
        )

        if not file_path:
            return

        # Show progress dialog for large exports
        progress = QProgressDialog("Exporting data...", "Cancel", 0, len(rows_to_export), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        try:
            if format_type in ['csv', 'tsv']:
                self._export_to_delimited(file_path, rows_to_export, column_names,
                                          include_headers, format_type, progress)
            else:  # json
                self._export_to_json(file_path, rows_to_export, column_names, include_headers, progress)

            progress.setValue(len(rows_to_export))
            QMessageBox.information(
                self,
                "Export Complete",
                f"Successfully exported {len(rows_to_export)} rows to:\n{file_path}"
            )
            self.update_status(f"Exported {len(rows_to_export)} rows to {format_type.upper()}")

        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Export Error", f"Failed to export data:\n{str(e)}")

    def _export_to_delimited(self, file_path, rows, column_names, include_headers, format_type, progress):
        """Export to CSV or TSV format"""
        delimiter = '\t' if format_type == 'tsv' else ','

        with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)

            # Write headers
            if include_headers:
                writer.writerow(column_names)

            # Write data rows
            for i, row in enumerate(rows):
                if progress.wasCanceled():
                    raise Exception("Export cancelled by user")

                # Ensure row has the same number of columns as headers
                if len(row) < len(column_names):
                    # Pad with empty strings if row is too short
                    padded_row = row + [''] * (len(column_names) - len(row))
                    writer.writerow(padded_row)
                else:
                    writer.writerow(row[:len(column_names)])

                progress.setValue(i + 1)

    def _export_to_json(self, file_path, rows, column_names, include_headers, progress):
        """Export to JSON format"""
        data = []

        for i, row in enumerate(rows):
            if progress.wasCanceled():
                raise Exception("Export cancelled by user")

            if include_headers:
                # Create object with column names as keys
                row_dict = {}
                for j, col_name in enumerate(column_names):
                    if j < len(row):
                        row_dict[col_name] = row[j]
                    else:
                        row_dict[col_name] = None
                data.append(row_dict)
            else:
                # Just export the rows as arrays
                data.append(row[:len(column_names)])

            progress.setValue(i + 1)

        # Write JSON with pretty formatting
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_linked_tables(self):
        """Load all data table projects for linked search"""
        self.linked_table_combo.blockSignals(True)
        self.linked_table_combo.clear()
        self.linked_table_combo.addItem("Select linked table...", None)

        # Get all data table projects except the current one
        all_projects = self.db.get_all_data_table_projects()
        for project in all_projects:
            if project['id'] != self.project_id:
                self.linked_table_combo.addItem(f"📊 {project['name']}", project['id'])

        self.linked_table_combo.blockSignals(False)

    def on_linked_table_changed(self, index):
        """Handle linked table selection"""
        project_id = self.linked_table_combo.currentData()

        if project_id:
            # Load the linked table data
            self.load_linked_table(project_id)
        else:
            # Clear linked table data
            self.linked_table_data = []
            self.linked_table_columns = []
            self.linked_table_row_ids = []
            self.linked_table_project_id = None
            self.is_linked_search_mode = False
            self.refresh_table()

    def load_linked_table(self, project_id):
        """Load data from a linked table"""
        project = next((p for p in self.db.get_all_data_table_projects() if p['id'] == project_id), None)
        if not project:
            return

        self.linked_table_project_id = project_id
        self.linked_table_name = project['name']
        self.linked_table_data_path = project['data_path']

        # Get columns and data
        self.linked_table_columns = self.db.get_table_column_names(project['data_path'])
        data = self.db.get_table_data(project['data_path'])

        # Get row IDs from the data
        conn = sqlite3.connect(project['data_path'])
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM data ORDER BY id")
        row_ids = cursor.fetchall()
        conn.close()
        self.linked_table_row_ids = [row[0] for row in row_ids]
        self.linked_table_data = data

        self.update_status(f"Loaded linked table: {project['name']}")

        # Update column filter with linked table columns
        self.update_column_filter()

    def update_column_filter(self):
        """Update the column filter dropdown"""
        self.column_filter_combo.blockSignals(True)
        self.column_filter_combo.clear()
        self.column_filter_combo.addItem("All Columns", None)

        # Add columns from current table
        for col in self.columns:
            self.column_filter_combo.addItem(col['name'], col['name'])

        self.column_filter_combo.blockSignals(False)

    def view_linked_row_details(self, item):
        """View details of a linked table row in a popup"""
        if not self.is_linked_search_mode:
            return

        # Get the actual row index from the item's data
        row_idx = item.data(Qt.UserRole)
        if row_idx is None or row_idx < 0 or row_idx >= len(self.linked_table_data):
            return

        row_data = self.linked_table_data[row_idx]
        row_id = self.linked_table_row_ids[row_idx] if row_idx < len(self.linked_table_row_ids) else row_idx + 1

        # Create popup dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Linked Row Details - {self.linked_table_name} (Row {row_id})")
        dialog.setMinimumWidth(500)
        dialog.setModal(True)

        layout = QVBoxLayout()

        # Create scrollable area for row data
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        for i, col_name in enumerate(self.linked_table_columns):
            if i < len(row_data):
                # Column label
                label = QLabel(col_name)
                label.setStyleSheet("font-weight: bold; font-size: 13px; color: #1c242e; margin-top: 8px;")
                scroll_layout.addWidget(label)

                # Value with copy button
                value_widget = QWidget()
                value_layout = QHBoxLayout()
                value_layout.setContentsMargins(0, 0, 0, 0)

                value_text = QTextEdit()
                value_text.setPlainText(str(row_data[i]) if row_data[i] else "")
                value_text.setReadOnly(True)
                value_text.setMaximumHeight(60)
                value_text.setStyleSheet("""
                    QTextEdit {
                        border: 1px solid #ddd;
                        border-radius: 4px;
                        padding: 4px;
                        font-size: 12px;
                        background-color: #fafafa;
                    }
                """)
                value_layout.addWidget(value_text, 1)

                copy_btn = QPushButton("📋 Copy")
                copy_btn.setFixedWidth(70)
                copy_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2196F3;
                        color: white;
                        font-weight: bold;
                        padding: 4px 8px;
                        border-radius: 4px;
                        font-size: 11px;
                    }
                    QPushButton:hover { background-color: #1976D2; }
                """)
                # Use lambda with default argument to capture the current text
                copy_btn.clicked.connect(
                    lambda checked, text=value_text.toPlainText(): QGuiApplication.clipboard().setText(text)
                )
                value_layout.addWidget(copy_btn)

                value_widget.setLayout(value_layout)
                scroll_layout.addWidget(value_widget)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #666;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #555; }
        """)
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

        dialog.setLayout(layout)
        dialog.exec()

    def restore_persistent_selection(self):
        """Restore the persistent row selection after search"""
        if self.persistent_selected_row is not None:
            # Find if the row still exists
            if self.persistent_selected_row < len(self.rows):
                self.load_row_data(self.persistent_selected_row)
                self.selected_row_indices = [self.persistent_selected_row]
                # Highlight the row in the table
                self.table_widget.selectRow(self.persistent_selected_row)
            else:
                self.persistent_selected_row = None

    def on_table_selection_changed(self):
        """Handle table selection changes (supports multi-select)"""
        selected_items = self.table_widget.selectedItems()
        if selected_items:
            # Get unique row indices
            rows = set()
            for item in selected_items:
                rows.add(item.row())

            # Map to actual row indices
            self.selected_row_indices = []
            for r in rows:
                if r < len(self.filtered_row_mapping):
                    self.selected_row_indices.append(self.filtered_row_mapping[r])

            # Store persistent selection
            if self.selected_row_indices:
                self.persistent_selected_row = self.selected_row_indices[0]
                self.load_row_data(self.persistent_selected_row)
                if self.add_row_btn:
                    if len(self.selected_row_indices) > 1:
                        self.add_row_btn.setText(f"Update {len(self.selected_row_indices)} Rows")
                    else:
                        self.add_row_btn.setText("Update Row (Ctrl+Enter)")
                self.update_status(f"Selected {len(self.selected_row_indices)} row(s)")
        else:
            # Only clear selection if we're not in the middle of a search
            if not self.is_linked_search_mode:
                self.selected_row_indices = []
                self.persistent_selected_row = None
                self.clear_row_inputs()
                if self.add_row_btn:
                    self.add_row_btn.setText("Add Row (Ctrl+Enter)")