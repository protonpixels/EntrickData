from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QComboBox, QListWidget, QAbstractItemView,
    QSpinBox, QDoubleSpinBox, QPushButton, QFileDialog,
    QScrollArea, QFrame, QMessageBox, QSizePolicy
)
from PySide6.QtCore import Signal, Qt


class RowEditorPanel(QWidget):
    """Panel for editing a row's values across columns."""

    row_added = Signal(dict)
    row_updated = Signal(int, dict)
    row_deleted = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_row_index = -1
        self.columns = []
        self.row_data = {}
        self.input_widgets = {}
        self.setup_ui()
        self.setEnabled(False)

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(6)
        layout.setContentsMargins(4, 4, 4, 4)

        # Header with buttons
        header_layout = QHBoxLayout()
        self.add_btn = QPushButton("➕ Add Item")
        self.add_btn.clicked.connect(self._add_item)
        header_layout.addWidget(self.add_btn)

        self.update_btn = QPushButton("💾 Update Item")
        self.update_btn.setEnabled(False)
        self.update_btn.clicked.connect(self._update_item)
        header_layout.addWidget(self.update_btn)

        self.delete_btn = QPushButton("🗑️ Delete Item")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._delete_item)
        header_layout.addWidget(self.delete_btn)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #e0e0e0; margin: 4px 0;")
        layout.addWidget(sep)

        # Scroll area for input fields
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        self.fields_widget = QWidget()
        self.fields_layout = QVBoxLayout(self.fields_widget)
        self.fields_layout.setSpacing(6)
        self.fields_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self.fields_widget)

        layout.addWidget(scroll)
        self.setLayout(layout)

    def get_parent_rows(self):
        """Get the rows from the parent synthesizer view."""
        parent = self.parent()
        while parent:
            if hasattr(parent, 'rows'):
                return parent.rows
            parent = parent.parent()
        return []

    def set_columns(self, columns):
        """Set the column definitions and rebuild the input form."""
        self.columns = columns
        self.current_row_index = -1
        self.row_data = {}
        self._rebuild_fields()
        self._update_buttons()

    def _rebuild_fields(self):
        """Build input fields for each column based on its data type."""
        while self.fields_layout.count():
            item = self.fields_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.input_widgets = {}

        if not self.columns:
            label = QLabel("No columns defined.")
            label.setStyleSheet("color: #666; padding: 20px;")
            self.fields_layout.addWidget(label)
            self.setEnabled(False)
            return

        self.setEnabled(True)

        for col in self.columns:
            col_name = col.name
            data_type = getattr(col, 'data_type', 'text')
            required = getattr(col, 'required', False)
            unique = getattr(col, 'unique', False)

            field_widget = QWidget()
            field_layout = QVBoxLayout(field_widget)
            field_layout.setSpacing(2)
            field_layout.setContentsMargins(0, 0, 0, 0)

            label_text = col_name
            if required:
                label_text += " *"
            if unique:
                label_text += " (unique)"
            label = QLabel(label_text)
            label.setStyleSheet("font-weight: 600; font-size: 12px;")
            field_layout.addWidget(label)

            widget = None

            if data_type == 'text':
                widget = QLineEdit()
                widget.setPlaceholderText(f"Enter {col_name}...")
                widget.textChanged.connect(lambda c=col_name: self._field_changed(c))
                field_layout.addWidget(widget)
                self.input_widgets[col_name] = widget

            elif data_type == 'textarea':
                widget = QTextEdit()
                widget.setPlaceholderText(f"Enter {col_name}...")
                widget.setMinimumHeight(120)
                widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                widget.textChanged.connect(lambda c=col_name: self._field_changed(c))
                field_layout.addWidget(widget)
                self.input_widgets[col_name] = widget

            elif data_type == 'category':
                categories = getattr(col, 'categories', [])
                mode = getattr(col, 'category_mode', 'single')
                if mode == 'single':
                    widget = QComboBox()
                    widget.addItems(categories)
                    widget.setEditable(True)
                    widget.currentTextChanged.connect(lambda c=col_name: self._field_changed(c))
                    field_layout.addWidget(widget)
                    self.input_widgets[col_name] = widget
                else:
                    widget = QListWidget()
                    widget.setSelectionMode(QAbstractItemView.MultiSelection)
                    for cat in categories:
                        widget.addItem(cat)
                    widget.itemSelectionChanged.connect(lambda c=col_name: self._field_changed(c))
                    field_layout.addWidget(widget)
                    self.input_widgets[col_name] = widget

            elif data_type == 'integer':
                widget = QSpinBox()
                min_val = getattr(col, 'min_value', None)
                max_val = getattr(col, 'max_value', None)
                step_val = getattr(col, 'step', None)
                if min_val is not None:
                    widget.setRange(int(min_val), int(max_val or 999999))
                else:
                    widget.setRange(-999999, 999999)
                if step_val is not None:
                    widget.setSingleStep(int(step_val))
                else:
                    widget.setSingleStep(1)
                widget.valueChanged.connect(lambda c=col_name: self._field_changed(c))
                field_layout.addWidget(widget)
                self.input_widgets[col_name] = widget

            elif data_type == 'float':
                widget = QDoubleSpinBox()
                min_val = getattr(col, 'min_value', None)
                max_val = getattr(col, 'max_value', None)
                step_val = getattr(col, 'step', None)
                if min_val is not None:
                    widget.setRange(min_val, max_val or 999999.99)
                else:
                    widget.setRange(-999999.99, 999999.99)
                if step_val is not None:
                    widget.setSingleStep(step_val)
                else:
                    widget.setSingleStep(0.1)
                widget.valueChanged.connect(lambda c=col_name: self._field_changed(c))
                field_layout.addWidget(widget)
                self.input_widgets[col_name] = widget

            elif data_type == 'file_path':
                widget_container = QWidget()
                container_layout = QHBoxLayout(widget_container)
                container_layout.setContentsMargins(0, 0, 0, 0)
                widget = QLineEdit()
                widget.setPlaceholderText("Select a file...")
                widget.textChanged.connect(lambda c=col_name: self._field_changed(c))
                container_layout.addWidget(widget)
                browse_btn = QPushButton("Browse...")
                browse_btn.clicked.connect(lambda c=col_name: self._browse_file(c))
                container_layout.addWidget(browse_btn)
                field_layout.addWidget(widget_container)
                self.input_widgets[col_name] = widget

            else:
                widget = QLineEdit()
                widget.setPlaceholderText(f"Enter {col_name}...")
                widget.textChanged.connect(lambda c=col_name: self._field_changed(c))
                field_layout.addWidget(widget)
                self.input_widgets[col_name] = widget

            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet("background-color: #eee; margin: 2px 0;")
            field_layout.addWidget(sep)

            self.fields_layout.addWidget(field_widget)

        self.fields_layout.addStretch()

        if self.current_row_index >= 0 and self.row_data:
            self._populate_fields(self.row_data)

    def _browse_file(self, col_name):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if file_path:
            widget = self.input_widgets.get(col_name)
            if widget and isinstance(widget, QLineEdit):
                widget.setText(file_path)

    def _field_changed(self, col_name):
        """Handle field value change - update the stored row data."""
        widget = self.input_widgets.get(col_name)
        if not widget:
            return

        # Get the value from the widget
        if isinstance(widget, QLineEdit):
            value = widget.text()
        elif isinstance(widget, QTextEdit):
            value = widget.toPlainText()
        elif isinstance(widget, QComboBox):
            value = widget.currentText()
        elif isinstance(widget, QListWidget):
            selected = [widget.item(i).text() for i in range(widget.count()) if widget.item(i).isSelected()]
            value = selected
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            value = widget.value()
        else:
            return

        # Update the stored row data in the parent
        if self.current_row_index >= 0:
            rows = self.get_parent_rows()
            if self.current_row_index < len(rows):
                rows[self.current_row_index][col_name] = value
                self.row_data[col_name] = value
                print(f"🔄 Updated row {self.current_row_index} column {col_name} = {value}")  # Debug

    def _populate_fields(self, row_data):
        """Populate fields with row data."""
        print(f"📝 Populating fields with: {row_data}")  # Debug
        for col_name, widget in self.input_widgets.items():
            value = row_data.get(col_name, "")
            print(f"   {col_name}: {value}")  # Debug

            if isinstance(widget, QLineEdit):
                widget.setText(str(value))
            elif isinstance(widget, QTextEdit):
                widget.setPlainText(str(value))
            elif isinstance(widget, QComboBox):
                idx = widget.findText(str(value))
                if idx >= 0:
                    widget.setCurrentIndex(idx)
                else:
                    widget.setEditText(str(value))
            elif isinstance(widget, QListWidget):
                if isinstance(value, list):
                    selected_texts = value
                else:
                    selected_texts = [v.strip() for v in str(value).split(',') if v.strip()]
                widget.clearSelection()
                for i in range(widget.count()):
                    item = widget.item(i)
                    if item.text() in selected_texts:
                        item.setSelected(True)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                try:
                    if value:
                        widget.setValue(float(value))
                    else:
                        widget.setValue(widget.minimum())
                except (ValueError, TypeError):
                    widget.setValue(widget.minimum())

    def load_row(self, row_index, row_data):
        """Load a row's data into the editor."""
        self.current_row_index = row_index
        self.row_data = row_data.copy()  # Store a copy
        self._populate_fields(row_data)
        self._update_buttons()

    def clear(self):
        """Clear the editor."""
        self.current_row_index = -1
        self.row_data = {}
        self._clear_fields()
        self._update_buttons()

    def _clear_fields(self):
        """Clear all input fields."""
        for widget in self.input_widgets.values():
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QTextEdit):
                widget.clear()
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(-1)
            elif isinstance(widget, QListWidget):
                widget.clearSelection()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(widget.minimum())

    def _update_buttons(self):
        """Enable/disable buttons based on selection state."""
        has_selection = self.current_row_index >= 0
        self.update_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)
        self.add_btn.setEnabled(True)

    def _get_field_values(self):
        """Return a dict of column name -> value from the current fields."""
        values = {}
        for col_name, widget in self.input_widgets.items():
            if isinstance(widget, QLineEdit):
                values[col_name] = widget.text()
            elif isinstance(widget, QTextEdit):
                values[col_name] = widget.toPlainText()
            elif isinstance(widget, QComboBox):
                values[col_name] = widget.currentText()
            elif isinstance(widget, QListWidget):
                selected = [widget.item(i).text() for i in range(widget.count()) if widget.item(i).isSelected()]
                values[col_name] = selected
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                values[col_name] = widget.value()
        return values

    def _add_item(self):
        """Add a new row with current field values."""
        if not self.columns:
            QMessageBox.warning(self, "No Columns", "Please add columns first.")
            return

        new_values = self._get_field_values()

        # Validate required fields
        for col in self.columns:
            if getattr(col, 'required', False):
                val = new_values.get(col.name)
                if not val or (isinstance(val, list) and not val):
                    QMessageBox.warning(self, "Required Field", f"'{col.name}' is required.")
                    return

        # Check unique constraints
        rows = self.get_parent_rows()
        for col in self.columns:
            if getattr(col, 'unique', False):
                val = new_values.get(col.name)
                if val:
                    for row in rows:
                        if row.get(col.name) == val:
                            QMessageBox.warning(self, "Duplicate Value", f"'{val}' already exists in column '{col.name}'.")
                            return

        self.row_added.emit(new_values)
        self._clear_fields()

    def _update_item(self):
        """Update the current row with field values."""
        if self.current_row_index < 0:
            return

        new_values = self._get_field_values()

        # Validate required fields
        for col in self.columns:
            if getattr(col, 'required', False):
                val = new_values.get(col.name)
                if not val or (isinstance(val, list) and not val):
                    QMessageBox.warning(self, "Required Field", f"'{col.name}' is required.")
                    return

        rows = self.get_parent_rows()
        for col in self.columns:
            if getattr(col, 'unique', False):
                val = new_values.get(col.name)
                if val:
                    for idx, row in enumerate(rows):
                        if idx != self.current_row_index and row.get(col.name) == val:
                            QMessageBox.warning(self, "Duplicate Value", f"'{val}' already exists in column '{col.name}'.")
                            return

        self.row_updated.emit(self.current_row_index, new_values)

    def _delete_item(self):
        """Delete the current row."""
        if self.current_row_index < 0:
            return

        reply = QMessageBox.question(self, "Delete Row", "Delete this row?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.row_deleted.emit(self.current_row_index)
            self._clear_fields()
            self.current_row_index = -1
            self._update_buttons()

