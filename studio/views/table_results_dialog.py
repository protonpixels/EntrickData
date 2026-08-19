# studio/views/table_results_dialog.py
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QGroupBox, QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit,
    QCheckBox, QTabWidget, QWidget, QSplitter, QToolBar,
    QProgressBar, QFileDialog, QMenu, QDialogButtonBox, QInputDialog
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QAction, QColor, QBrush
import csv
import json
import io
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.feature_extraction.text import TfidfVectorizer

from views.regenerate_thread import RegenerateThread

class FilterThread(QThread):
    """Thread for ML-based filtering."""

    complete = Signal(list)  # (good_indices, bad_indices)

    def __init__(self, items: list, good_examples: list, bad_examples: list):
        super().__init__()
        self.items = items
        self.good_examples = good_examples
        self.bad_examples = bad_examples

    def run(self):
        try:
            if not self.good_examples or not self.bad_examples:
                self.complete.emit([[], []])
                return

            # Prepare features
            vectorizer = TfidfVectorizer(
                stop_words='english',
                max_features=100,
                ngram_range=(1, 2)
            )

            # Combine examples
            all_texts = self.good_examples + self.bad_examples
            labels = [1] * len(self.good_examples) + [0] * len(self.bad_examples)

            # Vectorize
            vectors = vectorizer.fit_transform(all_texts)

            # Train classifier
            clf = LogisticRegression(max_iter=1000, random_state=42)
            clf.fit(vectors, labels)

            # Classify all items
            item_vectors = vectorizer.transform(self.items)
            predictions = clf.predict(item_vectors)
            probabilities = clf.predict_proba(item_vectors)

            # Separate good and bad
            good_indices = [i for i, pred in enumerate(predictions) if pred == 1]
            bad_indices = [i for i, pred in enumerate(predictions) if pred == 0]

            self.complete.emit([good_indices, bad_indices])

        except Exception as e:
            print(f"⚠️ ML filter error: {e}")
            self.complete.emit([[], []])


class TableResultsDialog(QDialog):
    """Dialog for displaying and filtering table results."""

    def __init__(self, results: list, columns: list, parent=None):
        super().__init__(parent)
        self.results = results  # List of columns, each column is list of row dicts
        self.columns = columns  # List of ColumnDefinition objects
        self.parent_app = parent
        self.filter_thread = None
        self.good_indices = []
        self.bad_indices = []
        self.selected_indices = []
        self.good_examples = []
        self.bad_examples = []

        self.setWindowTitle("📊 Table Results")
        self.setMinimumSize(1000, 700)
        self.setModal(True)

        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # === Toolbar ===
        toolbar = QToolBar()
        toolbar.setStyleSheet("QToolBar { spacing: 4px; }")

        # Filtering actions
        filter_action = QAction("🔍 ML Filter", self)
        filter_action.triggered.connect(self.apply_ml_filter)
        toolbar.addAction(filter_action)

        toolbar.addSeparator()

        # Selection actions
        select_all_action = QAction("✅ Select All", self)
        select_all_action.triggered.connect(self.select_all)
        toolbar.addAction(select_all_action)

        deselect_all_action = QAction("❌ Deselect All", self)
        deselect_all_action.triggered.connect(self.deselect_all)
        toolbar.addAction(deselect_all_action)

        toolbar.addSeparator()

        # Marking actions
        mark_good_action = QAction("👍 Mark Good", self)
        mark_good_action.triggered.connect(self.mark_selected_good)
        toolbar.addAction(mark_good_action)

        mark_bad_action = QAction("👎 Mark Bad", self)
        mark_bad_action.triggered.connect(self.mark_selected_bad)
        toolbar.addAction(mark_bad_action)

        toolbar.addSeparator()

        # Display actions
        show_good_action = QAction("✅ Show Good", self)
        show_good_action.triggered.connect(self.show_good)
        toolbar.addAction(show_good_action)

        show_bad_action = QAction("❌ Show Bad", self)
        show_bad_action.triggered.connect(self.show_bad)
        toolbar.addAction(show_bad_action)

        show_all_action = QAction("📋 Show All", self)
        show_all_action.triggered.connect(self.show_all)
        toolbar.addAction(show_all_action)

        toolbar.addSeparator()

        # Export actions
        export_csv_action = QAction("📊 CSV", self)
        export_csv_action.triggered.connect(self.export_csv)
        toolbar.addAction(export_csv_action)

        export_json_action = QAction("📄 JSON", self)
        export_json_action.triggered.connect(self.export_json)
        toolbar.addAction(export_json_action)

        create_table_action = QAction("📋 Create Table Project", self)
        create_table_action.triggered.connect(self.create_table_project)
        toolbar.addAction(create_table_action)

        toolbar.addSeparator()

        regenerate_action = QAction("🔄 Regenerate Selected", self)
        regenerate_action.triggered.connect(self.regenerate_selected)
        toolbar.addAction(regenerate_action)

        layout.addWidget(toolbar)

        # === Status Bar ===
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Ready")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        self.row_count_label = QLabel("Rows: 0")
        status_layout.addWidget(self.row_count_label)
        layout.addLayout(status_layout)

        # === Table ===
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        layout.addWidget(self.table)

        # === Buttons ===
        btn_layout = QHBoxLayout()

        # Column filter (for displaying specific columns)
        btn_layout.addWidget(QLabel("Show Column:"))
        self.column_filter_combo = QComboBox()
        self.column_filter_combo.addItem("All Columns", -1)
        self.column_filter_combo.currentIndexChanged.connect(self.filter_columns)
        btn_layout.addWidget(self.column_filter_combo)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        # Set layout
        self.setLayout(layout)

    def load_data(self):
        """Load data into the table."""
        if not self.results or not self.results[0]:
            self.row_count_label.setText("Rows: 0")
            return

        # Get column names
        column_names = [col.name for col in self.columns]
        self.table.setColumnCount(len(column_names))
        self.table.setHorizontalHeaderLabels(column_names)

        # Add column filter options
        for i, name in enumerate(column_names):
            self.column_filter_combo.addItem(name, i)

        # Load data
        rows = len(self.results[0])
        self.table.setRowCount(rows)

        # Count items with content
        non_empty = 0
        for row_idx in range(rows):
            for col_idx, col in enumerate(self.columns):
                if col_idx < len(self.results) and row_idx < len(self.results[col_idx]):
                    item_data = self.results[col_idx][row_idx]
                    value = item_data.get('item', '')
                    if value and value != "[Error: No content]":
                        non_empty += 1
                else:
                    value = ''

                table_item = QTableWidgetItem(value)
                table_item.setData(Qt.UserRole, row_idx)
                self.table.setItem(row_idx, col_idx, table_item)

                # Store full data in the last column's item
                if col_idx == len(self.columns) - 1:
                    table_item.setData(Qt.UserRole + 1, item_data if col_idx < len(self.results) and row_idx < len(
                        self.results[col_idx]) else {})

        self.row_count_label.setText(f"Rows: {rows} (non-empty: {non_empty})")

        # Resize columns
        for i in range(self.table.columnCount()):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)

    def filter_columns(self, index):
        """Filter which columns to show."""
        if index <= 0:  # All columns
            self.table.setColumnCount(len(self.columns))
            self.table.setHorizontalHeaderLabels([col.name for col in self.columns])
            for col_idx in range(len(self.columns)):
                self.table.horizontalHeader().setSectionResizeMode(col_idx, QHeaderView.ResizeToContents)
            return

        col_index = self.column_filter_combo.currentData()
        if col_index is not None:
            self.table.setColumnCount(1)
            self.table.setHorizontalHeaderLabels([self.columns[col_index].name])
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)

    def apply_ml_filter(self):
        """Apply ML-based filtering."""
        if len(self.good_examples) < 2 or len(self.bad_examples) < 2:
            QMessageBox.warning(
                self,
                "Need More Examples",
                "Please mark at least 2 examples as 'Good' and 2 as 'Bad' before using ML filter."
            )
            return

        # Get items from the first column
        items = []
        for row in self.results[0]:
            items.append(row.get('item', ''))

        self.filter_thread = FilterThread(items, self.good_examples, self.bad_examples)
        self.filter_thread.complete.connect(self.on_filter_complete)
        self.filter_thread.start()

        self.status_label.setText("🔍 Applying ML filter...")

    def on_filter_complete(self, result):
        """Handle filter completion."""
        good_indices, bad_indices = result

        self.good_indices = good_indices
        self.bad_indices = bad_indices

        # Highlight good and bad rows
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    if row in good_indices:
                        item.setBackground(QBrush(QColor(200, 255, 200)))  # Light green
                    elif row in bad_indices:
                        item.setBackground(QBrush(QColor(255, 200, 200)))  # Light red
                    else:
                        item.setBackground(QBrush(Qt.white))

        self.status_label.setText(f"✅ ML filter applied: {len(good_indices)} good, {len(bad_indices)} bad")

    def mark_selected_good(self):
        """Mark selected rows as good examples."""
        selected = self.table.selectedIndexes()
        rows = set([idx.row() for idx in selected])

        # Get items from the first column
        for row in rows:
            if row < len(self.results[0]):
                item = self.results[0][row].get('item', '')
                if item and item not in self.good_examples:
                    self.good_examples.append(item)

        self.status_label.setText(f"✅ Marked {len(rows)} rows as good (Total: {len(self.good_examples)})")

    def mark_selected_bad(self):
        """Mark selected rows as bad examples."""
        selected = self.table.selectedIndexes()
        rows = set([idx.row() for idx in selected])

        # Get items from the first column
        for row in rows:
            if row < len(self.results[0]):
                item = self.results[0][row].get('item', '')
                if item and item not in self.bad_examples:
                    self.bad_examples.append(item)

        self.status_label.setText(f"❌ Marked {len(rows)} rows as bad (Total: {len(self.bad_examples)})")

    def select_all(self):
        """Select all rows."""
        self.table.selectAll()

    def deselect_all(self):
        """Deselect all rows."""
        self.table.clearSelection()

    def show_good(self):
        """Show only good rows."""
        if not self.good_indices:
            QMessageBox.information(self, "No Good Items", "Run ML filter first or mark items as good.")
            return

        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, row not in self.good_indices)

        self.status_label.setText(f"✅ Showing {len(self.good_indices)} good items")

    def show_bad(self):
        """Show only bad rows."""
        if not self.bad_indices:
            QMessageBox.information(self, "No Bad Items", "Run ML filter first or mark items as bad.")
            return

        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, row not in self.bad_indices)

        self.status_label.setText(f"❌ Showing {len(self.bad_indices)} bad items")

    def show_all(self):
        """Show all rows."""
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, False)

        self.status_label.setText("📋 Showing all items")

    def on_selection_changed(self):
        """Update selection count."""
        selected = len(self.table.selectedIndexes())
        self.status_label.setText(f"Selected: {selected} rows")

    def export_csv(self):
        """Export table as CSV."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save CSV", "", "CSV Files (*.csv)"
        )
        if not path:
            return

        try:
            output = io.StringIO()
            writer = csv.writer(output)

            # Header
            writer.writerow([col.name for col in self.columns])

            # Data
            for row_idx in range(len(self.results[0])):
                row_data = []
                for col_idx in range(len(self.columns)):
                    if col_idx < len(self.results) and row_idx < len(self.results[col_idx]):
                        item = self.results[col_idx][row_idx].get('item', '')
                    else:
                        item = ''
                    row_data.append(item)
                writer.writerow(row_data)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(output.getvalue())

            QMessageBox.information(self, "Export Successful", f"CSV saved to:\n{path}")

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to save CSV:\n{str(e)}")

    def export_json(self):
        """Export table as JSON."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save JSON", "", "JSON Files (*.json)"
        )
        if not path:
            return

        try:
            # Build JSON structure
            data = []
            for row_idx in range(len(self.results[0])):
                row = {}
                for col_idx, col in enumerate(self.columns):
                    if col_idx < len(self.results) and row_idx < len(self.results[col_idx]):
                        row[col.name] = self.results[col_idx][row_idx].get('item', '')
                    else:
                        row[col.name] = ''
                data.append(row)

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            QMessageBox.information(self, "Export Successful", f"JSON saved to:\n{path}")

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to save JSON:\n{str(e)}")

    def create_table_project(self):
        """Create a data table project from results."""
        name, ok = QInputDialog.getText(self, "New Table Project", "Enter project name:")
        if not ok or not name:
            return

        try:
            # Build metadata
            metadata = {
                'column_config': [
                    {'name': col.name, 'type': 'text', 'required': False}
                    for col in self.columns
                ]
            }

            # Create project
            project_id = self.parent_app.db.create_project(
                name=name,
                project_type='data_table',
                metadata=metadata
            )

            if not project_id:
                QMessageBox.critical(self, "Error", "Failed to create project.")
                return

            # Get data path
            project_data = self.parent_app.db.get_project(project_id)
            data_path = project_data['data_path']

            # Add rows
            for row_idx in range(len(self.results[0])):
                row_data = []
                for col_idx in range(len(self.columns)):
                    if col_idx < len(self.results) and row_idx < len(self.results[col_idx]):
                        row_data.append(self.results[col_idx][row_idx].get('item', ''))
                    else:
                        row_data.append('')
                self.parent_app.db.add_table_row(data_path, row_data)

            QMessageBox.information(
                self,
                "Success",
                f"Table project '{name}' created with {len(self.results[0])} rows."
            )

            # Open the new table view
            self.parent_app.open_project(project_id)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create table:\n{str(e)}")

    def regenerate_selected(self):
        """Regenerate selected items with new settings."""
        # Get selected rows
        selected = self.table.selectedIndexes()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select rows to regenerate.")
            return

        rows = set([idx.row() for idx in selected])

        # Get current settings from the first selected item
        first_row = next(iter(rows)) if rows else 0
        current_settings = {
            'creativity': 0.5,
            'max_tokens': 200,
            'response_type': 'Sentence',
            'min_size': 2,
            'max_size': 6,
            'temperature': 0.7,
            'top_p': 0.9,
            'strategy': 'Exact Match',
            'top_k': 10,
            'prev_sentences': 1,
            'follow_sentences': 1,
            'order': 'Relevancy',
            'max_chunk_tokens': 500
        }

        # Show regenerate dialog
        from .regenerate_dialog import RegenerateSettingsDialog
        dialog = RegenerateSettingsDialog(current_settings, 0, self)

        if dialog.exec_() != QDialog.DialogCode.Accepted:
            return

        new_settings = dialog.get_settings()

        # Get the column index (first column by default)
        col_index = 0
        selected_only = new_settings.pop('selected_only', True)

        # Start regeneration thread
        self.regenerate_thread = RegenerateThread(
            self.results,
            self.columns,
            col_index,
            rows,
            new_settings,
            selected_only,
            self.parent_app.llm,
            self.parent_app.db
        )
        self.regenerate_thread.progress_update.connect(self.on_regenerate_progress)
        self.regenerate_thread.item_complete.connect(self.on_regenerate_item)
        self.regenerate_thread.complete.connect(self.on_regenerate_complete)
        self.regenerate_thread.start()

        self.status_label.setText(f"🔄 Regenerating {len(rows)} items...")

    def on_regenerate_progress(self, current: int, total: int):
        """Update regeneration progress."""
        self.status_label.setText(f"🔄 Regenerating {current}/{total} items...")

    def on_regenerate_item(self, row: int, new_item: str, new_chunks: list):
        """Handle regenerated item."""
        # Update the table
        item = QTableWidgetItem(new_item)
        item.setData(Qt.UserRole, row)

        # Store full data
        if row < len(self.results[0]):
            self.results[0][row]['item'] = new_item
            self.results[0][row]['chunks'] = new_chunks
            item.setData(Qt.UserRole + 1, self.results[0][row])

        self.table.setItem(row, 0, item)

        # Highlight updated row
        item.setBackground(QBrush(QColor(255, 255, 200)))  # Light yellow

    def on_regenerate_complete(self, results: list):
        """Handle regeneration complete."""
        self.results = results
        self.status_label.setText("✅ Regeneration complete")
        QMessageBox.information(self, "Complete", f"Successfully regenerated items.")