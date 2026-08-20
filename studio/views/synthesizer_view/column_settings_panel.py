from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QCheckBox, QTextEdit, QPushButton, QSpinBox,
    QDoubleSpinBox, QRadioButton, QButtonGroup, QFileDialog,
    QScrollArea, QFrame, QGroupBox
)
from PySide6.QtCore import Signal, Qt


class ColumnSettingsPanel(QWidget):
    """Panel for editing column settings (type, required, unique, etc.)"""

    settings_changed = Signal()  # Emitted when any setting changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_column = None
        self.current_column_index = -1
        self.setup_ui()
        self.setEnabled(False)

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(6)
        layout.setContentsMargins(4, 4, 4, 4)

        # Header
        header = QLabel("Column Settings")
        header.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(header)

        # Column Name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Column name...")
        self.name_input.textChanged.connect(self._on_setting_changed)
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        # Data Type
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Textline", "Textarea", "Category", "Integer", "Float", "File Path"])
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        type_layout.addWidget(self.type_combo)
        layout.addLayout(type_layout)

        # Required and Unique checkboxes
        check_layout = QHBoxLayout()
        self.required_check = QCheckBox("Required")
        self.required_check.toggled.connect(self._on_setting_changed)
        check_layout.addWidget(self.required_check)
        self.unique_check = QCheckBox("Unique")
        self.unique_check.toggled.connect(self._on_setting_changed)
        check_layout.addWidget(self.unique_check)
        check_layout.addStretch()
        layout.addLayout(check_layout)

        # === Category-specific options ===
        self.category_widget = QWidget()
        cat_layout = QVBoxLayout(self.category_widget)
        cat_layout.setContentsMargins(0, 0, 0, 0)

        # Selection mode
        cat_mode_layout = QHBoxLayout()
        cat_mode_layout.addWidget(QLabel("Selection mode:"))
        self.cat_mode_combo = QComboBox()
        self.cat_mode_combo.addItems(["Single Selection", "Multiple Selection"])
        self.cat_mode_combo.currentTextChanged.connect(self._on_setting_changed)
        cat_mode_layout.addWidget(self.cat_mode_combo)
        cat_mode_layout.addStretch()
        cat_layout.addLayout(cat_mode_layout)

        # Categories list
        cat_layout.addWidget(QLabel("Categories (one per line):"))
        self.categories_text = QTextEdit()
        self.categories_text.setMaximumHeight(80)
        self.categories_text.textChanged.connect(self._on_setting_changed)
        cat_layout.addWidget(self.categories_text)

        # Toggle edit mode for categories
        cat_edit_layout = QHBoxLayout()
        self.cat_edit_btn = QPushButton("Edit Categories")
        self.cat_edit_btn.setCheckable(True)
        self.cat_edit_btn.setChecked(False)
        self.cat_edit_btn.toggled.connect(self._toggle_category_edit)
        cat_edit_layout.addWidget(self.cat_edit_btn)
        cat_edit_layout.addStretch()
        cat_layout.addLayout(cat_edit_layout)

        # Category buttons (for quick selection)
        self.cat_buttons_container = QWidget()
        cat_btn_layout = QVBoxLayout(self.cat_buttons_container)
        cat_btn_layout.setSpacing(3)
        cat_btn_layout.setContentsMargins(0, 0, 0, 0)
        cat_layout.addWidget(self.cat_buttons_container)

        # Hide category widget initially
        self.category_widget.setVisible(False)
        layout.addWidget(self.category_widget)

        # === Numeric options ===
        self.numeric_widget = QWidget()
        num_layout = QVBoxLayout(self.numeric_widget)
        num_layout.setContentsMargins(0, 0, 0, 0)

        min_layout = QHBoxLayout()
        min_layout.addWidget(QLabel("Min:"))
        self.min_int_spin = QSpinBox()
        self.min_int_spin.setRange(-999999, 999999)
        self.min_int_spin.valueChanged.connect(self._on_setting_changed)
        min_layout.addWidget(self.min_int_spin)
        num_layout.addLayout(min_layout)

        max_layout = QHBoxLayout()
        max_layout.addWidget(QLabel("Max:"))
        self.max_int_spin = QSpinBox()
        self.max_int_spin.setRange(-999999, 999999)
        self.max_int_spin.valueChanged.connect(self._on_setting_changed)
        max_layout.addWidget(self.max_int_spin)
        num_layout.addLayout(max_layout)

        step_layout = QHBoxLayout()
        step_layout.addWidget(QLabel("Step:"))
        self.step_int_spin = QSpinBox()
        self.step_int_spin.setRange(1, 999999)
        self.step_int_spin.valueChanged.connect(self._on_setting_changed)
        step_layout.addWidget(self.step_int_spin)
        num_layout.addLayout(step_layout)

        # Float variants
        self.float_widget = QWidget()
        float_layout = QVBoxLayout(self.float_widget)
        float_layout.setContentsMargins(0, 0, 0, 0)

        min_float_layout = QHBoxLayout()
        min_float_layout.addWidget(QLabel("Min:"))
        self.min_float_spin = QDoubleSpinBox()
        self.min_float_spin.setRange(-999999.99, 999999.99)
        self.min_float_spin.valueChanged.connect(self._on_setting_changed)
        min_float_layout.addWidget(self.min_float_spin)
        float_layout.addLayout(min_float_layout)

        max_float_layout = QHBoxLayout()
        max_float_layout.addWidget(QLabel("Max:"))
        self.max_float_spin = QDoubleSpinBox()
        self.max_float_spin.setRange(-999999.99, 999999.99)
        self.max_float_spin.valueChanged.connect(self._on_setting_changed)
        max_float_layout.addWidget(self.max_float_spin)
        float_layout.addLayout(max_float_layout)

        step_float_layout = QHBoxLayout()
        step_float_layout.addWidget(QLabel("Step:"))
        self.step_float_spin = QDoubleSpinBox()
        self.step_float_spin.setRange(0.01, 999999.99)
        self.step_float_spin.valueChanged.connect(self._on_setting_changed)
        step_float_layout.addWidget(self.step_float_spin)
        float_layout.addLayout(step_float_layout)

        self.numeric_widget.setVisible(False)
        layout.addWidget(self.numeric_widget)

        # === File Path options ===
        self.file_widget = QWidget()
        file_layout = QVBoxLayout(self.file_widget)
        file_layout.setContentsMargins(0, 0, 0, 0)

        # Browse button
        browse_layout = QHBoxLayout()
        self.file_browse_btn = QPushButton("Browse...")
        self.file_browse_btn.clicked.connect(self._browse_file)
        browse_layout.addWidget(self.file_browse_btn)
        self.file_path_display = QLineEdit()
        self.file_path_display.setReadOnly(True)
        self.file_path_display.setPlaceholderText("Selected file path...")
        browse_layout.addWidget(self.file_path_display)
        file_layout.addLayout(browse_layout)

        # Storage mode
        self.file_mode_group = QButtonGroup()
        self.file_filename_radio = QRadioButton("Store as Filename Only")
        self.file_filename_radio.setChecked(True)
        self.file_filename_radio.toggled.connect(self._on_setting_changed)
        file_layout.addWidget(self.file_filename_radio)
        self.file_fullpath_radio = QRadioButton("Store as Full File Path")
        self.file_fullpath_radio.toggled.connect(self._on_setting_changed)
        file_layout.addWidget(self.file_fullpath_radio)
        self.file_mode_group.addButton(self.file_filename_radio)
        self.file_mode_group.addButton(self.file_fullpath_radio)

        self.file_widget.setVisible(False)
        layout.addWidget(self.file_widget)

        layout.addStretch()
        self.setLayout(layout)

    def _on_type_changed(self, type_text):
        """Show/hide relevant widgets based on type."""
        self.category_widget.setVisible(type_text == "Category")
        self.numeric_widget.setVisible(type_text in ["Integer", "Float"])
        self.file_widget.setVisible(type_text == "File Path")
        # Show/hide float vs int spinboxes
        is_int = type_text == "Integer"
        self.min_int_spin.setVisible(is_int)
        self.max_int_spin.setVisible(is_int)
        self.step_int_spin.setVisible(is_int)
        self.min_float_spin.setVisible(not is_int)
        self.max_float_spin.setVisible(not is_int)
        self.step_float_spin.setVisible(not is_int)
        # Update category buttons
        self._update_category_buttons()
        self._on_setting_changed()

    def _toggle_category_edit(self, checked):
        """Toggle edit mode for categories."""
        self.categories_text.setReadOnly(not checked)
        self.cat_edit_btn.setText("Edit Categories" if not checked else "Lock Categories")

    def _update_category_buttons(self):
        """Create category buttons from categories list."""
        # Clear existing buttons
        for i in reversed(range(self.cat_buttons_container.layout().count())):
            widget = self.cat_buttons_container.layout().itemAt(i).widget()
            if widget:
                widget.deleteLater()

        categories = self.categories_text.toPlainText().split('\n')
        categories = [c.strip() for c in categories if c.strip()]
        if not categories:
            return

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)
        for cat in categories:
            btn = QPushButton(cat)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #e0e0e0;
                    border: none;
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #d0d0d0;
                }
            """)
            # Clicking the button could insert the category into the row editor
            btn.clicked.connect(lambda checked, c=cat: self._category_button_clicked(c))
            btn_layout.addWidget(btn)
        self.cat_buttons_container.layout().addLayout(btn_layout)

    def _category_button_clicked(self, category):
        """Emit a signal that a category button was clicked (to be handled by parent)."""
        # We'll just emit a custom signal; parent can intercept.
        self.category_selected.emit(category)

    category_selected = Signal(str)

    def _browse_file(self):
        """Open file dialog to select a file."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if file_path:
            self.file_path_display.setText(file_path)
            self._on_setting_changed()

    def _on_setting_changed(self):
        """Emit settings_changed signal when any setting is modified."""
        self.settings_changed.emit()

    def load_column(self, column_def, index):
        """Load column definition into the panel."""
        self.current_column = column_def
        self.current_column_index = index
        self.setEnabled(True)

        # Name
        self.name_input.setText(column_def.name)

        # Type
        type_map = {
            "text": "Textline",
            "textarea": "Textarea",
            "category": "Category",
            "integer": "Integer",
            "float": "Float",
            "file_path": "File Path"
        }
        current_type = getattr(column_def, 'data_type', 'text')
        self.type_combo.setCurrentText(type_map.get(current_type, "Textline"))

        # Required / Unique
        self.required_check.setChecked(getattr(column_def, 'required', False))
        self.unique_check.setChecked(getattr(column_def, 'unique', False))

        # Category
        categories = getattr(column_def, 'categories', [])
        self.categories_text.setText('\n'.join(categories))
        mode = getattr(column_def, 'category_mode', 'single')
        self.cat_mode_combo.setCurrentText("Single Selection" if mode == 'single' else "Multiple Selection")
        self._update_category_buttons()

        # Numeric
        min_val = getattr(column_def, 'min_value', None)
        max_val = getattr(column_def, 'max_value', None)
        step_val = getattr(column_def, 'step', None)
        if min_val is not None:
            self.min_int_spin.setValue(int(min_val))
            self.min_float_spin.setValue(float(min_val))
        if max_val is not None:
            self.max_int_spin.setValue(int(max_val))
            self.max_float_spin.setValue(float(max_val))
        if step_val is not None:
            self.step_int_spin.setValue(int(step_val))
            self.step_float_spin.setValue(float(step_val))

        # File path
        file_mode = getattr(column_def, 'file_path_mode', 'filename')
        if file_mode == 'filename':
            self.file_filename_radio.setChecked(True)
        else:
            self.file_fullpath_radio.setChecked(True)
        self.file_path_display.clear()

        # Update visibility
        self._on_type_changed(self.type_combo.currentText())

    def get_column_settings(self):
        """Return a dict of settings from the panel."""
        if not self.current_column:
            return {}

        type_text = self.type_combo.currentText()
        data_type_map = {
            "Textline": "text",
            "Textarea": "textarea",
            "Category": "category",
            "Integer": "integer",
            "Float": "float",
            "File Path": "file_path"
        }

        settings = {
            'name': self.name_input.text().strip(),
            'data_type': data_type_map.get(type_text, "text"),
            'required': self.required_check.isChecked(),
            'unique': self.unique_check.isChecked(),
        }

        if type_text == "Category":
            categories = [c.strip() for c in self.categories_text.toPlainText().split('\n') if c.strip()]
            settings['categories'] = categories
            settings['category_mode'] = 'multiple' if self.cat_mode_combo.currentText() == "Multiple Selection" else 'single'

        elif type_text == "Integer":
            settings['min_value'] = self.min_int_spin.value()
            settings['max_value'] = self.max_int_spin.value()
            settings['step'] = self.step_int_spin.value()

        elif type_text == "Float":
            settings['min_value'] = self.min_float_spin.value()
            settings['max_value'] = self.max_float_spin.value()
            settings['step'] = self.step_float_spin.value()

        elif type_text == "File Path":
            settings['file_path_mode'] = 'full_path' if self.file_fullpath_radio.isChecked() else 'filename'
            # The file path itself is not stored in settings; it's stored per row.

        return settings

    def clear(self):
        """Clear the panel."""
        self.setEnabled(False)
        self.name_input.clear()
        self.type_combo.setCurrentIndex(0)
        self.required_check.setChecked(False)
        self.unique_check.setChecked(False)
        self.categories_text.clear()
        self.file_path_display.clear()
        self.current_column = None
        self.current_column_index = -1