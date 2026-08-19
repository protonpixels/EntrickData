from typing import List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox, QComboBox,
    QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit,
    QCheckBox, QMessageBox, QTabWidget, QWidget,
    QDialogButtonBox, QInputDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDrag

from views.synthesizer_view.gradual_extraction_tab import GradualExtractionTab
from views.synthesizer_view.table_generator import (
    ColumnDefinition, ResponseType, ChunkStrategy, SourceType
)


class ColumnSetupDialog(QDialog):
    """Dialog for setting up table columns."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📊 Generate Table")
        self.setMinimumSize(800, 700)
        self.columns = []
        self.current_edit_index = -1
        self.parent_app = parent
        self.db = None  # Will be set from parent

        # Try to get db from parent
        if parent:
            if hasattr(parent, 'db'):
                self.db = parent.db
            elif hasattr(parent, 'parent_app') and hasattr(parent.parent_app, 'db'):
                self.db = parent.parent_app.db

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # === Top: Column List ===
        top_layout = QHBoxLayout()

        # Left: Column list
        list_layout = QVBoxLayout()
        list_layout.addWidget(QLabel("Columns:"))

        self.column_list = QListWidget()
        self.column_list.setMinimumWidth(200)
        self.column_list.itemClicked.connect(self.on_column_selected)
        self.column_list.setDragDropMode(QListWidget.InternalMove)
        list_layout.addWidget(self.column_list)

        # Column buttons
        btn_layout = QHBoxLayout()

        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self.add_column)
        btn_layout.addWidget(add_btn)

        # NEW: Load from Table button
        load_btn = QPushButton("📂 Load from Table")
        load_btn.clicked.connect(self.load_from_table)
        load_btn.setStyleSheet("""
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
        btn_layout.addWidget(load_btn)

        remove_btn = QPushButton("− Remove")
        remove_btn.clicked.connect(self.remove_column)
        btn_layout.addWidget(remove_btn)

        move_up_btn = QPushButton("↑")
        move_up_btn.clicked.connect(self.move_column_up)
        move_up_btn.setMaximumWidth(40)
        btn_layout.addWidget(move_up_btn)

        move_down_btn = QPushButton("↓")
        move_down_btn.clicked.connect(self.move_column_down)
        move_down_btn.setMaximumWidth(40)
        btn_layout.addWidget(move_down_btn)

        btn_layout.addStretch()
        list_layout.addLayout(btn_layout)

        top_layout.addLayout(list_layout)

        # Right: Column Editor
        self.editor_widget = self.create_editor()
        top_layout.addWidget(self.editor_widget)

        layout.addLayout(top_layout)

        # === Buttons ===
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        # Add initial empty column
        self.add_column()

    def create_editor(self) -> QGroupBox:
        """Create the column editor with Basic and Gradual Extraction tabs."""
        group = QGroupBox("Column Settings")
        layout = QVBoxLayout(group)

        # Use QTabWidget for different configuration modes
        editor_tabs = QTabWidget()

        # --- Basic Settings Tab ---
        basic_tab = self._create_basic_settings_tab()
        editor_tabs.addTab(basic_tab, "Basic")

        # --- Gradual Extraction Tab ---
        # Get db and project_id from parent
        db = None
        project_id = None

        # Try to get from self.db first
        if hasattr(self, 'db') and self.db:
            db = self.db

        # Try parent_app
        if not db and hasattr(self, 'parent_app'):
            if hasattr(self.parent_app, 'db'):
                db = self.parent_app.db
            if hasattr(self.parent_app, 'project_id'):
                project_id = self.parent_app.project_id

        # Try parent widget chain
        if not db:
            parent = self.parent()
            while parent:
                if hasattr(parent, 'db'):
                    db = parent.db
                    break
                parent = parent.parent()

        if not project_id:
            parent = self.parent()
            while parent:
                if hasattr(parent, 'project_id'):
                    project_id = parent.project_id
                    break
                parent = parent.parent()

        self.gradual_tab = GradualExtractionTab(db, project_id, self)
        self.gradual_tab.parent_app = self.parent_app
        self.gradual_tab.settings_changed.connect(self._on_gradual_settings_changed)
        editor_tabs.addTab(self.gradual_tab, "🎯 Gradual Extraction")

        layout.addWidget(editor_tabs)
        return group

    def _create_basic_settings_tab(self) -> QWidget:
        """Extract basic settings into a separate tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Column Name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Headline, Strength, Technique")
        self.name_input.textChanged.connect(self.on_name_changed)
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        # Request
        request_layout = QHBoxLayout()
        request_layout.addWidget(QLabel("Request:"))
        self.request_input = QLineEdit()
        self.request_input.setPlaceholderText("e.g., proven headlines, ESFP characteristics")
        self.request_input.textChanged.connect(self.on_request_changed)
        request_layout.addWidget(self.request_input)
        layout.addLayout(request_layout)

        # Response Type
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Response Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Sentence", "Paragraph", "Article"])
        self.type_combo.currentTextChanged.connect(self.on_type_changed)
        type_layout.addWidget(self.type_combo)
        layout.addLayout(type_layout)

        # Response Size
        self.size_widget = QWidget()
        self.size_layout = QHBoxLayout(self.size_widget)
        self.size_layout.setContentsMargins(0, 0, 0, 0)

        self.size_min_label = QLabel("Min:")
        self.size_layout.addWidget(self.size_min_label)
        self.size_min_spin = QSpinBox()
        self.size_min_spin.setRange(1, 20)
        self.size_min_spin.setValue(2)
        self.size_min_spin.valueChanged.connect(self.on_size_changed)
        self.size_layout.addWidget(self.size_min_spin)

        self.size_max_label = QLabel("Max:")
        self.size_layout.addWidget(self.size_max_label)
        self.size_max_spin = QSpinBox()
        self.size_max_spin.setRange(1, 20)
        self.size_max_spin.setValue(6)
        self.size_max_spin.valueChanged.connect(self.on_size_changed)
        self.size_layout.addWidget(self.size_max_spin)

        self.size_unit_label = QLabel("words")
        self.size_layout.addWidget(self.size_unit_label)
        self.size_layout.addStretch()

        layout.addWidget(self.size_widget)

        # Creativity
        creativity_layout = QHBoxLayout()
        creativity_layout.addWidget(QLabel("Creativity:"))
        self.creativity_spin = QDoubleSpinBox()
        self.creativity_spin.setRange(0.0, 1.0)
        self.creativity_spin.setSingleStep(0.1)
        self.creativity_spin.setValue(0.5)
        creativity_layout.addWidget(self.creativity_spin)
        creativity_layout.addStretch()
        layout.addLayout(creativity_layout)

        # Source Type
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("Source:"))
        self.source_combo = QComboBox()
        self.source_combo.addItems(["Project Data", "Previous Column Data", "Previous Column Chunks"])
        self.source_combo.currentTextChanged.connect(self.on_source_changed)
        source_layout.addWidget(self.source_combo)
        source_layout.addStretch()
        layout.addLayout(source_layout)

        # Source Column
        self.source_column_widget = QWidget()
        source_col_layout = QHBoxLayout(self.source_column_widget)
        source_col_layout.setContentsMargins(0, 0, 0, 0)
        source_col_layout.addWidget(QLabel("Source Column:"))
        self.source_column_combo = QComboBox()
        self.source_column_combo.addItem("None", -1)
        source_col_layout.addWidget(self.source_column_combo)
        source_col_layout.addStretch()
        self.source_column_widget.setVisible(False)
        layout.addWidget(self.source_column_widget)

        # Chunk Strategy
        strategy_layout = QHBoxLayout()
        strategy_layout.addWidget(QLabel("Chunk Strategy:"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(["Exact Match", "Semantic Match", "Max Semantic"])
        self.strategy_combo.currentTextChanged.connect(self.on_strategy_changed)
        strategy_layout.addWidget(self.strategy_combo)
        strategy_layout.addStretch()
        layout.addLayout(strategy_layout)

        # Strategy Parameters
        self.param_widget = QWidget()
        self.param_layout = QHBoxLayout(self.param_widget)
        self.param_layout.setContentsMargins(0, 0, 0, 0)

        self.param_top_k_label = QLabel("Top K:")
        self.param_layout.addWidget(self.param_top_k_label)
        self.param_top_k_spin = QSpinBox()
        self.param_top_k_spin.setRange(1, 100)
        self.param_top_k_spin.setValue(10)
        self.param_top_k_spin.valueChanged.connect(self.on_param_changed)
        self.param_layout.addWidget(self.param_top_k_spin)

        self.param_prev_label = QLabel("Prev:")
        self.param_layout.addWidget(self.param_prev_label)
        self.param_prev_spin = QSpinBox()
        self.param_prev_spin.setRange(0, 10)
        self.param_prev_spin.setValue(1)
        self.param_prev_spin.valueChanged.connect(self.on_param_changed)
        self.param_layout.addWidget(self.param_prev_spin)

        self.param_follow_label = QLabel("Follow:")
        self.param_layout.addWidget(self.param_follow_label)
        self.param_follow_spin = QSpinBox()
        self.param_follow_spin.setRange(0, 10)
        self.param_follow_spin.setValue(1)
        self.param_follow_spin.valueChanged.connect(self.on_param_changed)
        self.param_layout.addWidget(self.param_follow_spin)

        self.param_order_label = QLabel("Order:")
        self.param_layout.addWidget(self.param_order_label)
        self.param_order_combo = QComboBox()
        self.param_order_combo.addItems(["Relevancy", "A-Z", "Z-A"])
        self.param_order_combo.currentTextChanged.connect(self.on_param_changed)
        self.param_layout.addWidget(self.param_order_combo)

        self.param_max_tokens_label = QLabel("Max Tokens:")
        self.param_max_tokens_label.setVisible(False)
        self.param_layout.addWidget(self.param_max_tokens_label)
        self.param_max_tokens_spin = QSpinBox()
        self.param_max_tokens_spin.setRange(100, 4096)
        self.param_max_tokens_spin.setValue(500)
        self.param_max_tokens_spin.setVisible(False)
        self.param_max_tokens_spin.valueChanged.connect(self.on_param_changed)
        self.param_layout.addWidget(self.param_max_tokens_spin)

        self.param_layout.addStretch()
        layout.addWidget(self.param_widget)

        layout.addStretch()
        return tab

    def _on_gradual_settings_changed(self, settings: dict):
        """Update column definition with gradual extraction settings."""
        if self.current_edit_index >= 0:
            col = self.columns[self.current_edit_index]

            # Set attributes safely
            if hasattr(col, 'seed_pattern'):
                col.seed_pattern = settings.get('seed_pattern')
            if hasattr(col, 'extraction_stage'):
                col.extraction_stage = "seed"
            if hasattr(col, 'confidence_threshold'):
                col.confidence_threshold = settings.get('confidence_threshold', 0.85)
            if hasattr(col, 'use_ml_assist'):
                col.use_ml_assist = settings.get('use_ml_assist', False)
            if hasattr(col, 'ml_model_id'):
                col.ml_model_id = settings.get('ml_model_id')
            if hasattr(col, 'extracted_seed_items'):
                col.extracted_seed_items = settings.get('extracted_seed_items', [])
            if hasattr(col, 'ai_settings'):
                col.ai_settings = {
                    'prompt': settings.get('ai_prompt', ''),
                    'temperature': settings.get('ai_temperature', 0.7),
                    'top_p': settings.get('ai_top_p', 0.9),
                    'max_tokens': settings.get('ai_max_tokens', 200),
                    'format': settings.get('ai_format', 'Sentence')
                }

    def add_column(self):
        """Add a new column."""
        col = ColumnDefinition(
            name=f"Column {len(self.columns) + 1}",
            response_type=ResponseType.SENTENCE,
            request="",
            creativity=0.5,
            chunk_strategy=ChunkStrategy.EXACT_MATCH,
            lookup_params={'top_k': 10, 'previous_sentences': 1, 'following_sentences': 1, 'order': 'relevancy'},
            source_type=SourceType.PROJECT,
            response_size={'words': (2, 6)}
        )
        self.columns.append(col)
        self.update_column_list()
        self.select_column(len(self.columns) - 1)

    def remove_column(self):
        """Remove the selected column."""
        current = self.column_list.currentRow()
        if current >= 0 and len(self.columns) > 1:
            self.columns.pop(current)
            self.update_column_list()
            if current < len(self.columns):
                self.select_column(current)
            else:
                self.select_column(current - 1)

    def move_column_up(self):
        """Move the selected column up."""
        current = self.column_list.currentRow()
        if current > 0:
            self.columns[current], self.columns[current - 1] = self.columns[current - 1], self.columns[current]
            self.update_column_list()
            self.select_column(current - 1)

    def move_column_down(self):
        """Move the selected column down."""
        current = self.column_list.currentRow()
        if current < len(self.columns) - 1:
            self.columns[current], self.columns[current + 1] = self.columns[current + 1], self.columns[current]
            self.update_column_list()
            self.select_column(current + 1)

    def update_column_list(self):
        """Update the column list widget."""
        self.column_list.clear()
        for i, col in enumerate(self.columns):
            name = col.name if col.name else f"Column {i + 1}"
            item = QListWidgetItem(f"{i + 1}. {name}")
            item.setData(Qt.UserRole, i)
            self.column_list.addItem(item)

        self.update_source_columns()

    def update_source_columns(self):
        """Update the source column dropdowns."""
        self.source_column_combo.clear()
        self.source_column_combo.addItem("None", -1)
        for i, col in enumerate(self.columns):
            self.source_column_combo.addItem(f"{i + 1}. {col.name}", i)

    def select_column(self, index):
        """Select a column in the list."""
        if 0 <= index < self.column_list.count():
            self.column_list.setCurrentRow(index)
            self.on_column_selected(self.column_list.item(index))

    def on_column_selected(self, item):
        """Load the selected column into the editor."""
        index = item.data(Qt.UserRole)
        if index is None:
            return

        self.current_edit_index = index
        col = self.columns[index]

        # Load values into Basic tab
        self.name_input.setText(col.name)
        self.request_input.setText(col.request)
        self.creativity_spin.setValue(col.creativity)

        type_map = {
            ResponseType.SENTENCE: "Sentence",
            ResponseType.PARAGRAPH: "Paragraph",
            ResponseType.ARTICLE: "Article"
        }
        self.type_combo.setCurrentText(type_map.get(col.response_type, "Sentence"))

        if col.response_type == ResponseType.SENTENCE:
            words = col.response_size.get('words', (2, 6))
            self.size_min_spin.setValue(words[0])
            self.size_max_spin.setValue(words[1])
            self.size_unit_label.setText("words")
        elif col.response_type == ResponseType.PARAGRAPH:
            sentences = col.response_size.get('sentences', (3, 6))
            self.size_min_spin.setValue(sentences[0])
            self.size_max_spin.setValue(sentences[1])
            self.size_unit_label.setText("sentences")
        else:
            paragraphs = col.response_size.get('paragraphs', (2, 4))
            self.size_min_spin.setValue(paragraphs[0])
            self.size_max_spin.setValue(paragraphs[1])
            self.size_unit_label.setText("paragraphs")

        source_map = {
            SourceType.PROJECT: "Project Data",
            SourceType.PREVIOUS_COLUMN_DATA: "Previous Column Data",
            SourceType.PREVIOUS_COLUMN_CHUNKS: "Previous Column Chunks"
        }
        self.source_combo.setCurrentText(source_map.get(col.source_type, "Project Data"))

        if col.source_column is not None:
            idx = self.source_column_combo.findData(col.source_column)
            if idx >= 0:
                self.source_column_combo.setCurrentIndex(idx)

        strategy_map = {
            ChunkStrategy.EXACT_MATCH: "Exact Match",
            ChunkStrategy.SEMANTIC_MATCH: "Semantic Match",
            ChunkStrategy.MAX_SEMANTIC: "Max Semantic"
        }
        self.strategy_combo.setCurrentText(strategy_map.get(col.chunk_strategy, "Exact Match"))

        params = col.lookup_params
        self.param_top_k_spin.setValue(params.get('top_k', 10))
        self.param_prev_spin.setValue(params.get('previous_sentences', 1))
        self.param_follow_spin.setValue(params.get('following_sentences', 1))
        self.param_order_combo.setCurrentText(params.get('order', 'Relevancy').title())
        self.param_max_tokens_spin.setValue(params.get('max_tokens', 500))

        self.on_type_changed(self.type_combo.currentText())
        self.on_source_changed(self.source_combo.currentText())
        self.on_strategy_changed(self.strategy_combo.currentText())

    def on_name_changed(self):
        """Update column name when text changes."""
        if self.current_edit_index >= 0:
            self.columns[self.current_edit_index].name = self.name_input.text()
            self.update_column_list()

    def on_request_changed(self):
        """Update column request when text changes."""
        if self.current_edit_index >= 0:
            self.columns[self.current_edit_index].request = self.request_input.text()

    def on_type_changed(self, type_text):
        """Update response type."""
        if self.current_edit_index < 0:
            return

        type_map = {
            "Sentence": (ResponseType.SENTENCE, 'words', 'words'),
            "Paragraph": (ResponseType.PARAGRAPH, 'sentences', 'sentences'),
            "Article": (ResponseType.ARTICLE, 'paragraphs', 'paragraphs')
        }

        if type_text in type_map:
            response_type, key, label = type_map[type_text]
            col = self.columns[self.current_edit_index]
            col.response_type = response_type
            col.response_size[key] = (self.size_min_spin.value(), self.size_max_spin.value())
            self.size_unit_label.setText(label)

    def on_size_changed(self):
        """Update response size."""
        if self.current_edit_index < 0:
            return

        col = self.columns[self.current_edit_index]
        if col.response_type == ResponseType.SENTENCE:
            col.response_size['words'] = (self.size_min_spin.value(), self.size_max_spin.value())
        elif col.response_type == ResponseType.PARAGRAPH:
            col.response_size['sentences'] = (self.size_min_spin.value(), self.size_max_spin.value())
        else:
            col.response_size['paragraphs'] = (self.size_min_spin.value(), self.size_max_spin.value())

    def on_source_changed(self, source_text):
        """Update source type."""
        if self.current_edit_index < 0:
            return

        source_map = {
            "Project Data": SourceType.PROJECT,
            "Previous Column Data": SourceType.PREVIOUS_COLUMN_DATA,
            "Previous Column Chunks": SourceType.PREVIOUS_COLUMN_CHUNKS
        }

        if source_text in source_map:
            self.columns[self.current_edit_index].source_type = source_map[source_text]
            self.source_column_widget.setVisible(source_text != "Project Data")

    def on_strategy_changed(self, strategy_text):
        """Update chunk strategy."""
        if self.current_edit_index < 0:
            return

        strategy_map = {
            "Exact Match": ChunkStrategy.EXACT_MATCH,
            "Semantic Match": ChunkStrategy.SEMANTIC_MATCH,
            "Max Semantic": ChunkStrategy.MAX_SEMANTIC
        }

        if strategy_text in strategy_map:
            self.columns[self.current_edit_index].chunk_strategy = strategy_map[strategy_text]

            is_max_semantic = strategy_text == "Max Semantic"
            self.param_top_k_label.setVisible(not is_max_semantic)
            self.param_top_k_spin.setVisible(not is_max_semantic)
            self.param_prev_label.setVisible(not is_max_semantic)
            self.param_prev_spin.setVisible(not is_max_semantic)
            self.param_follow_label.setVisible(not is_max_semantic)
            self.param_follow_spin.setVisible(not is_max_semantic)
            self.param_order_label.setVisible(not is_max_semantic)
            self.param_order_combo.setVisible(not is_max_semantic)
            self.param_max_tokens_label.setVisible(is_max_semantic)
            self.param_max_tokens_spin.setVisible(is_max_semantic)

    def on_param_changed(self):
        """Update lookup parameters."""
        if self.current_edit_index < 0:
            return

        col = self.columns[self.current_edit_index]
        col.lookup_params = {
            'top_k': self.param_top_k_spin.value(),
            'previous_sentences': self.param_prev_spin.value(),
            'following_sentences': self.param_follow_spin.value(),
            'order': self.param_order_combo.currentText().lower(),
            'max_tokens': self.param_max_tokens_spin.value()
        }

    def get_columns(self) -> List[ColumnDefinition]:
        """Get the configured columns with gradual extraction settings."""
        # Save current edits from Basic tab
        if self.current_edit_index >= 0:
            self.on_name_changed()
            self.on_request_changed()
            self.on_type_changed(self.type_combo.currentText())
            self.on_size_changed()
            self.on_source_changed(self.source_combo.currentText())
            self.on_strategy_changed(self.strategy_combo.currentText())
            self.on_param_changed()

        # Get gradual extraction settings from the tab
        if hasattr(self, 'gradual_tab') and self.current_edit_index >= 0:
            gradual_settings = self.gradual_tab.get_settings()
            col = self.columns[self.current_edit_index]

            if hasattr(col, 'seed_pattern'):
                col.seed_pattern = gradual_settings.get('seed_pattern')
            if hasattr(col, 'extraction_stage'):
                col.extraction_stage = "seed"
            if hasattr(col, 'confidence_threshold'):
                col.confidence_threshold = gradual_settings.get('confidence_threshold', 0.85)
            if hasattr(col, 'use_ml_assist'):
                col.use_ml_assist = gradual_settings.get('use_ml_assist', False)
            if hasattr(col, 'ml_model_id'):
                col.ml_model_id = gradual_settings.get('ml_model_id')
            if hasattr(col, 'extracted_seed_items'):
                col.extracted_seed_items = gradual_settings.get('extracted_seed_items', [])
            if hasattr(col, 'ai_settings'):
                col.ai_settings = {
                    'prompt': gradual_settings.get('ai_prompt', ''),
                    'temperature': gradual_settings.get('ai_temperature', 0.7),
                    'top_p': gradual_settings.get('ai_top_p', 0.9),
                    'max_tokens': gradual_settings.get('ai_max_tokens', 200),
                    'format': gradual_settings.get('ai_format', 'Sentence')
                }

        return self.columns

    def load_from_table(self):
        """Load columns from an existing table project."""
        # Make sure we have db access
        if not self.db:
            # Try to get db from parent
            if self.parent_app and hasattr(self.parent_app, 'db'):
                self.db = self.parent_app.db
            else:
                QMessageBox.warning(self, "Error", "Database not available. Please try again.")
                return

        # Get all table projects
        try:
            table_projects = self.db.get_all_data_table_projects()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not load table projects: {e}")
            return

        if not table_projects:
            QMessageBox.information(
                self,
                "No Table Projects",
                "No table projects found to load from.\n\n"
                "Create a table project first by exporting results or creating one manually."
            )
            return

        # Show project selection dialog
        project_names = [p['name'] for p in table_projects]
        selected, ok = QInputDialog.getItem(
            self,
            "Load from Table",
            "Select table project:",
            project_names,
            0,
            False
        )

        if not ok or not selected:
            return

        # Get the selected project
        project = next((p for p in table_projects if p['name'] == selected), None)
        if not project:
            return

        # Get column names from the table
        try:
            columns = self.db.get_table_column_names(project['data_path'])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not load columns: {e}")
            return

        if not columns:
            QMessageBox.information(self, "No Columns", f"Project '{selected}' has no columns.")
            return

        # Show column selection dialog with checkboxes
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QDialogButtonBox

        class ColumnSelectDialog(QDialog):
            def __init__(self, columns, parent):
                super().__init__(parent)
                self.setWindowTitle("Select Columns")
                self.setMinimumSize(300, 400)
                layout = QVBoxLayout(self)

                layout.addWidget(QLabel("Select columns to load:"))
                self.list_widget = QListWidget()
                self.list_widget.setSelectionMode(QListWidget.MultiSelection)
                for col in columns:
                    item = QListWidgetItem(col)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked)
                    self.list_widget.addItem(item)
                layout.addWidget(self.list_widget)

                btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
                btn_box.accepted.connect(self.accept)
                btn_box.rejected.connect(self.reject)
                layout.addWidget(btn_box)

            def get_selected(self):
                return [self.list_widget.item(i).text() for i in range(self.list_widget.count())
                        if self.list_widget.item(i).checkState() == Qt.Checked]

        # Show selection dialog
        select_dialog = ColumnSelectDialog(columns, self)
        if select_dialog.exec_() != QDialog.DialogCode.Accepted:
            return

        selected_columns = select_dialog.get_selected()
        if not selected_columns:
            QMessageBox.information(self, "No Columns", "No columns selected.")
            return

        # Ask if user wants to keep existing columns or replace
        if self.columns:
            reply = QMessageBox.question(
                self,
                "Replace Columns",
                f"Replace existing {len(self.columns)} columns with {len(selected_columns)} loaded columns?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.columns = []

        # Add columns from the table
        for col_name in selected_columns:
            col = ColumnDefinition(
                name=col_name,
                response_type=ResponseType.SENTENCE,
                request=f"Extract {col_name} from the data",
                creativity=0.5,
                chunk_strategy=ChunkStrategy.EXACT_MATCH,
                lookup_params={'top_k': 10, 'previous_sentences': 1, 'following_sentences': 1, 'order': 'relevancy'},
                source_type=SourceType.PROJECT,
                response_size={'words': (2, 6)}
            )
            self.columns.append(col)

        self.update_column_list()
        if self.columns:
            self.select_column(0)

        QMessageBox.information(
            self,
            "Columns Loaded",
            f"Loaded {len(selected_columns)} columns from '{selected}'.\n\n"
            "You can now edit the column settings or add more columns."
        )