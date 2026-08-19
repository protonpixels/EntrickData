from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSplitter, QTabWidget, QGroupBox, QListWidget, QListWidgetItem,
    QCheckBox, QMessageBox, QProgressDialog, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit, QDialog,
    QDialogButtonBox, QScrollArea, QFrame, QInputDialog,
    QToolBar, QToolButton, QSizePolicy, QMenu, QAbstractItemView, QSlider
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QAction, QColor, QBrush, QIcon
import re
from typing import List, Dict, Optional

from core.project_types import ProjectType
from views.synthesizer_view.gradual_extraction_tab import GradualExtractionTab
from views.synthesizer_view.pattern_rule_builder import PatternRuleBuilder
from views.synthesizer_view.table_generator import ColumnDefinition, ResponseType, ChunkStrategy, SourceType


class ColumnManagerDialog(QDialog):
    """Popup dialog for managing columns."""

    def __init__(self, columns: List[ColumnDefinition], parent=None):
        super().__init__(parent)
        self.columns = columns
        self.setWindowTitle("Manage Columns")
        self.setMinimumSize(400, 500)
        self.setModal(True)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Columns:"))
        self.column_list = QListWidget()
        self.column_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.column_list.setStyleSheet("""
            QListWidget::item { padding: 6px; }
            QListWidget::item:selected { background-color: #d0e4ff; }
        """)
        self._update_list()
        layout.addWidget(self.column_list)

        btn_layout = QHBoxLayout()

        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._add_column)
        btn_layout.addWidget(add_btn)

        rename_btn = QPushButton("✏️ Rename")
        rename_btn.clicked.connect(self._rename_column)
        btn_layout.addWidget(rename_btn)

        delete_btn = QPushButton("🗑️ Delete")
        delete_btn.clicked.connect(self._delete_column)
        btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _update_list(self):
        self.column_list.clear()
        for i, col in enumerate(self.columns):
            item = QListWidgetItem(f"{i + 1}. {col.name}")
            item.setData(Qt.UserRole, i)
            self.column_list.addItem(item)

    def _add_column(self):
        from views.synthesizer_view.table_generator import ColumnDefinition, ResponseType, ChunkStrategy, SourceType

        name, ok = QInputDialog.getText(self, "Add Column", "Enter column name:")
        if ok and name.strip():
            col = ColumnDefinition(
                name=name.strip(),
                response_type=ResponseType.SENTENCE,
                request="",
                creativity=0.5,
                chunk_strategy=ChunkStrategy.EXACT_MATCH,
                lookup_params={'top_k': 10, 'previous_sentences': 1, 'following_sentences': 1, 'order': 'relevancy'},
                source_type=SourceType.PROJECT,
                response_size={'words': (2, 6)}
            )
            self.columns.append(col)
            self._update_list()

    def _rename_column(self):
        current = self.column_list.currentRow()
        if current < 0 or current >= len(self.columns):
            return

        new_name, ok = QInputDialog.getText(
            self, "Rename Column", "Enter new name:",
            text=self.columns[current].name
        )
        if ok and new_name.strip():
            self.columns[current].name = new_name.strip()
            self._update_list()

    def _delete_column(self):
        current = self.column_list.currentRow()
        if current < 0 or current >= len(self.columns):
            return

        reply = QMessageBox.question(
            self,
            "Delete Column",
            f"Delete column '{self.columns[current].name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.columns.pop(current)
            self._update_list()


class DataSynthesizerView(QWidget):
    """Data Synthesizer project view - Automated list/table generation."""

    def __init__(self, parent=None, db=None, project_data=None):
        super().__init__(parent)
        self.parent_app = parent
        self.db = db
        self.project_data = project_data
        self.project_id = project_data.get('id')
        self.metadata = project_data.get('metadata', {})

        self.selected_sources = []
        self.current_columns: List[ColumnDefinition] = []
        self.current_results = []
        self.column_data = {}
        self.review_items = []  # List of (item_text, confidence_score, is_edited)
        self.good_examples = []
        self.bad_examples = []
        self.review_mode = True
        self.ml_trained = False
        self.ml_model = None
        self.confidence_threshold = 0.5
        self.top_k = 20
        self.ml_results = []  # List of (item, confidence)

        self.setup_ui()
        self.load_available_projects()
        self.load_synthesizer_state()
        self.update_status("Ready - Define columns and start extracting")

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(3)
        layout.setContentsMargins(0, 0, 0, 0)

        top_bar = self._create_top_toolbar()
        layout.addWidget(top_bar)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.left_panel = self._create_source_panel()
        self.main_splitter.addWidget(self.left_panel)
        self.right_panel = self._create_main_panel()
        self.main_splitter.addWidget(self.right_panel)
        self.main_splitter.setSizes([250, 700])
        layout.addWidget(self.main_splitter)

        self.setLayout(layout)

    def _create_top_toolbar(self):
        """Create the top toolbar with collapsible toggle."""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: #f5f7fa;
                border: none;
                border-bottom: 1px solid #e0e0e0;
                padding: 4px;
                spacing: 4px;
            }
            QToolButton {
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
            }
            QToolButton:hover {
                background-color: #e8f0fe;
            }
            QPushButton {
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }
            QComboBox {
                padding: 3px 6px;
                border-radius: 4px;
                font-size: 11px;
                border: 1px solid #ddd;
                background: white;
            }
        """)

        # Toggle left panel button
        self.toggle_panel_btn = QToolButton()
        self.toggle_panel_btn.setText("◀ Sources")
        self.toggle_panel_btn.setCheckable(True)
        self.toggle_panel_btn.setChecked(True)
        self.toggle_panel_btn.clicked.connect(self._toggle_left_panel)
        toolbar.addWidget(self.toggle_panel_btn)

        toolbar.addSeparator()

        # Back button
        back_btn = QToolButton()
        back_btn.setText("← Back")
        back_btn.clicked.connect(self.go_back)
        back_btn.setStyleSheet("""
            QToolButton {
                background-color: #666;
                color: white;
                font-weight: bold;
                padding: 4px 12px;
                border-radius: 4px;
            }
            QToolButton:hover { background-color: #555; }
        """)
        toolbar.addWidget(back_btn)

        # Project name
        name_label = QLabel(f"🧬 {self.project_data.get('name', 'Data Synthesizer')}")
        name_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #1c242e; padding: 2px 8px;")
        toolbar.addWidget(name_label)

        toolbar.addSeparator()

        # Manage Columns button
        manage_btn = QPushButton("📋 Columns")
        manage_btn.clicked.connect(self._show_column_manager)
        manage_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                font-weight: bold;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #7B1FA2; }
        """)
        toolbar.addWidget(manage_btn)

        # Column dropdown (moved from tabs to here)
        toolbar.addWidget(QLabel("Column:"))
        self.column_dropdown = QComboBox()
        self.column_dropdown.setMaximumWidth(150)
        self.column_dropdown.setToolTip("Select column to work with")
        self.column_dropdown.currentIndexChanged.connect(self._on_column_changed)
        toolbar.addWidget(self.column_dropdown)

        toolbar.addSeparator()

        # Confidence threshold (moved from preview tab)
        toolbar.addWidget(QLabel("Conf:"))
        self.confidence_slider = QSlider(Qt.Horizontal)
        self.confidence_slider.setRange(0, 100)
        self.confidence_slider.setValue(50)
        self.confidence_slider.setFixedWidth(100)
        self.confidence_slider.setTickInterval(25)
        self.confidence_slider.setTickPosition(QSlider.TicksBelow)
        self.confidence_slider.valueChanged.connect(self._on_confidence_changed)
        toolbar.addWidget(self.confidence_slider)

        self.confidence_label = QLabel("0.50")
        self.confidence_label.setFixedWidth(35)
        self.confidence_label.setStyleSheet("font-size: 11px;")
        toolbar.addWidget(self.confidence_label)

        toolbar.addSeparator()

        # View Good/Bad buttons
        view_good_btn = QPushButton("✅ Good")
        view_good_btn.clicked.connect(self._view_good_examples)
        view_good_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 3px 8px;
                border-radius: 4px;
                font-size: 10px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        toolbar.addWidget(view_good_btn)

        view_bad_btn = QPushButton("❌ Bad")
        view_bad_btn.clicked.connect(self._view_bad_examples)
        view_bad_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 3px 8px;
                border-radius: 4px;
                font-size: 10px;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        toolbar.addWidget(view_bad_btn)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        # Status indicator
        self.status_indicator = QLabel("● Ready")
        self.status_indicator.setStyleSheet("color: #4CAF50; font-size: 10px; padding: 0px 4px;")
        toolbar.addWidget(self.status_indicator)

        return toolbar
    def _toggle_left_panel(self, checked):
        self.left_panel_visible = checked
        if checked:
            self.left_panel.show()
            self.toggle_panel_btn.setText("◀ Sources")
        else:
            self.left_panel.hide()
            self.toggle_panel_btn.setText("▶ Sources")
        self.main_splitter.setSizes([250 if checked else 0, 700])

    def _create_source_panel(self):
        panel = QWidget()
        panel.setMinimumWidth(200)
        panel.setMaximumWidth(300)

        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        header_layout = QHBoxLayout()
        header = QLabel("📚 Sources")
        header.setStyleSheet("font-weight: bold; font-size: 13px;")
        header_layout.addWidget(header)
        header_layout.addStretch()
        self.source_count_label = QLabel("0")
        self.source_count_label.setStyleSheet(
            "color: #666; font-size: 11px; background: #e0e0e0; padding: 0px 8px; border-radius: 10px;")
        header_layout.addWidget(self.source_count_label)
        layout.addLayout(header_layout)

        select_layout = QHBoxLayout()
        select_all_btn = QPushButton("All")
        select_all_btn.setFixedWidth(40)
        select_all_btn.clicked.connect(self.select_all_sources)
        select_layout.addWidget(select_all_btn)

        clear_btn = QPushButton("None")
        clear_btn.setFixedWidth(40)
        clear_btn.clicked.connect(self.clear_all_sources)
        select_layout.addWidget(clear_btn)

        select_layout.addStretch()
        layout.addLayout(select_layout)

        self.source_list = QListWidget()
        self.source_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 12px;
                padding: 2px;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-radius: 3px;
            }
            QListWidget::item:hover {
                background-color: #e8f0fe;
            }
            QListWidget::item:selected {
                background-color: #d0e4ff;
            }
        """)
        self.source_list.itemChanged.connect(self.update_source_count)
        layout.addWidget(self.source_list)

        layout.addStretch()
        panel.setLayout(layout)
        return panel

    def _create_main_panel(self):
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self.workflow_tabs = QTabWidget()
        self.workflow_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ddd;
                background: white;
            }
            QTabBar::tab {
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: white;
                border-bottom: 2px solid #4CAF50;
            }
        """)

        preview_tab = self._create_preview_tab()
        self.workflow_tabs.addTab(preview_tab, "📊 Preview")

        pattern_tab = self._create_pattern_tab()
        self.workflow_tabs.addTab(pattern_tab, "🎯 Pattern")

        ml_tab = self._create_ml_tab()
        self.workflow_tabs.addTab(ml_tab, "🧠 ML")

        ai_tab = self._create_ai_tab()
        self.workflow_tabs.addTab(ai_tab, "✨ AI")

        layout.addWidget(self.workflow_tabs)

        panel.setLayout(layout)
        return panel

    def _create_preview_tab(self):
        """Create the Preview/Review tab with simplified toolbar."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        # Toolbar (simplified - no duplicate controls)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        # Mode toggle
        self.review_mode_check = QCheckBox("Review Mode")
        self.review_mode_check.setChecked(True)
        self.review_mode_check.stateChanged.connect(self._toggle_review_mode)
        self.review_mode_check.setStyleSheet("font-size: 11px;")
        toolbar.addWidget(self.review_mode_check)

        toolbar.addStretch()

        # Mark Good button
        self.mark_good_btn = QPushButton("✅ Mark Good")
        self.mark_good_btn.clicked.connect(self._mark_selected_good)
        self.mark_good_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        toolbar.addWidget(self.mark_good_btn)

        # Mark Bad button
        self.mark_bad_btn = QPushButton("❌ Mark Bad")
        self.mark_bad_btn.clicked.connect(self._mark_selected_bad)
        self.mark_bad_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        toolbar.addWidget(self.mark_bad_btn)

        # Commit button
        self.commit_btn = QPushButton("✅ Commit")
        self.commit_btn.clicked.connect(self._commit_review)
        self.commit_btn.setEnabled(False)
        self.commit_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #1976D2; }
            QPushButton:disabled {
                background-color: #ccc;
                color: #888;
            }
        """)
        toolbar.addWidget(self.commit_btn)

        # Clear buttons
        clear_review_btn = QPushButton("🗑️ Review")
        clear_review_btn.clicked.connect(self._clear_review)
        clear_review_btn.setStyleSheet("""
            QPushButton {
                background-color: #666;
                color: white;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 10px;
            }
            QPushButton:hover { background-color: #555; }
        """)
        toolbar.addWidget(clear_review_btn)

        clear_examples_btn = QPushButton("🗑️ Examples")
        clear_examples_btn.clicked.connect(self._clear_examples)
        clear_examples_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 10px;
            }
            QPushButton:hover { background-color: #7B1FA2; }
        """)
        toolbar.addWidget(clear_examples_btn)

        # Info label
        self.preview_status = QLabel("Ready")
        self.preview_status.setStyleSheet("color: #666; font-size: 10px; padding: 0px 4px;")
        toolbar.addWidget(self.preview_status)

        layout.addLayout(toolbar)

        # Table
        self.preview_table = QTableWidget()
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 13px;
            }
            QHeaderView::section {
                background-color: #f5f7fa;
                padding: 6px;
                font-weight: 600;
            }
        """)
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.preview_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.preview_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.preview_table.itemChanged.connect(self._on_preview_item_changed)
        self.preview_table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        # Enable keyboard delete
        self.preview_table.keyPressEvent = self._table_key_press_event
        layout.addWidget(self.preview_table)

        # Status bar
        status_layout = QHBoxLayout()
        status_layout.addStretch()
        self.good_bad_count_label = QLabel("✅ Good: 0 | ❌ Bad: 0")
        self.good_bad_count_label.setStyleSheet("color: #666; font-size: 11px;")
        status_layout.addWidget(self.good_bad_count_label)

        self.item_count_label = QLabel("0 items")
        self.item_count_label.setStyleSheet("color: #666; font-size: 11px;")
        status_layout.addWidget(self.item_count_label)
        layout.addLayout(status_layout)

        return tab

    def _create_pattern_tab(self):
        """Create the Pattern extraction tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        # REMOVED: Column selector (now in top toolbar)
        info_label = QLabel("Extracting to current column (select in toolbar)")
        info_label.setStyleSheet("color: #666; font-size: 11px; padding: 2px;")
        layout.addWidget(info_label)

        # Rule builder
        self.rule_builder = PatternRuleBuilder()
        layout.addWidget(self.rule_builder)

        # Action buttons
        btn_layout = QHBoxLayout()
        test_btn = QPushButton("🧪 Test Pattern")
        test_btn.clicked.connect(self._test_pattern)
        btn_layout.addWidget(test_btn)
        btn_layout.addStretch()
        extract_btn = QPushButton("🔍 Extract Seeds")
        extract_btn.clicked.connect(self._extract_with_pattern)
        extract_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 4px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        btn_layout.addWidget(extract_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()
        return tab

    def _create_ml_tab(self):
        """Create the ML tab with chunking and ranking."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        # REMOVED: Column selector (now in top toolbar)
        info_label = QLabel("Training/scanning for current column (select in toolbar)")
        info_label.setStyleSheet("color: #666; font-size: 11px; padding: 2px;")
        layout.addWidget(info_label)

        # Chunking Settings
        chunk_group = QGroupBox("📄 Chunking Settings")
        chunk_layout = QVBoxLayout(chunk_group)

        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Chunk Size:"))
        self.chunk_size_combo = QComboBox()
        self.chunk_size_combo.addItems(["Sentences", "Paragraphs", "Lines", "Words"])
        size_layout.addWidget(self.chunk_size_combo)

        size_layout.addWidget(QLabel("Count:"))
        self.chunk_count_spin = QSpinBox()
        self.chunk_count_spin.setRange(1, 50)
        self.chunk_count_spin.setValue(3)
        size_layout.addWidget(self.chunk_count_spin)
        size_layout.addStretch()
        chunk_layout.addLayout(size_layout)

        rank_layout = QHBoxLayout()
        rank_layout.addWidget(QLabel("Ranking Order:"))
        self.rank_order_combo = QComboBox()
        self.rank_order_combo.addItems(["Most Relevant First", "Least Relevant First"])
        rank_layout.addWidget(self.rank_order_combo)

        rank_layout.addWidget(QLabel("Top K:"))
        self.top_k_spin = QSpinBox()
        self.top_k_spin.setRange(1, 100)
        self.top_k_spin.setValue(20)
        rank_layout.addWidget(self.top_k_spin)
        rank_layout.addStretch()
        chunk_layout.addLayout(rank_layout)

        ref_layout = QHBoxLayout()
        ref_layout.addWidget(QLabel("Reference Phrase:"))
        self.ref_phrase_input = QLineEdit()
        self.ref_phrase_input.setPlaceholderText("Enter phrase for similarity ranking...")
        ref_layout.addWidget(self.ref_phrase_input)
        ref_layout.addStretch()
        chunk_layout.addLayout(ref_layout)

        layout.addWidget(chunk_group)

        # ML Training
        train_group = QGroupBox("🧠 ML Training")
        train_layout = QVBoxLayout(train_group)

        # Example counts
        example_layout = QHBoxLayout()
        self.good_count_label = QLabel("✅ Good: 0")
        example_layout.addWidget(self.good_count_label)
        self.bad_count_label = QLabel("❌ Bad: 0")
        example_layout.addWidget(self.bad_count_label)
        example_layout.addStretch()
        train_layout.addLayout(example_layout)

        # === PASTE EXAMPLES SECTION ===
        paste_group = QGroupBox("📋 Paste Examples")
        paste_layout = QVBoxLayout(paste_group)

        # Instructions
        paste_info = QLabel("Paste examples (one per line) to quickly add multiple Good or Bad items:")
        paste_info.setStyleSheet("color: #666; font-size: 11px;")
        paste_layout.addWidget(paste_info)

        # Text area for pasting
        self.paste_text = QTextEdit()
        self.paste_text.setPlaceholderText(
            "Paste your examples here, one per line...\n\nExample:\nHow to win friends and influence people\nThe secret of making people like you\nBuild a body you can be proud of")
        self.paste_text.setMaximumHeight(80)
        self.paste_text.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 12px;
                padding: 4px;
                background-color: #fafafa;
            }
            QTextEdit:focus {
                border-color: #4CAF50;
            }
        """)
        paste_layout.addWidget(self.paste_text)

        # Paste buttons
        paste_btn_layout = QHBoxLayout()

        paste_good_btn = QPushButton("✅ Add as Good")
        paste_good_btn.clicked.connect(self._paste_good_examples)
        paste_good_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 4px 16px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        paste_btn_layout.addWidget(paste_good_btn)

        paste_bad_btn = QPushButton("❌ Add as Bad")
        paste_bad_btn.clicked.connect(self._paste_bad_examples)
        paste_bad_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 4px 16px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        paste_btn_layout.addWidget(paste_bad_btn)

        paste_btn_layout.addStretch()

        clear_paste_btn = QPushButton("🗑️ Clear")
        clear_paste_btn.clicked.connect(lambda: self.paste_text.clear())
        clear_paste_btn.setStyleSheet("""
            QPushButton {
                background-color: #666;
                color: white;
                padding: 4px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #555; }
        """)
        paste_btn_layout.addWidget(clear_paste_btn)

        paste_layout.addLayout(paste_btn_layout)
        train_layout.addWidget(paste_group)

        # Train button
        train_btn_layout = QHBoxLayout()
        self.train_ml_btn = QPushButton("🎯 Train ML Model")
        self.train_ml_btn.clicked.connect(self._train_ml)
        self.train_ml_btn.setEnabled(False)
        train_btn_layout.addWidget(self.train_ml_btn)

        self.ml_status_label = QLabel("Not trained")
        self.ml_status_label.setStyleSheet("color: #888; font-size: 11px;")
        train_btn_layout.addWidget(self.ml_status_label)
        train_btn_layout.addStretch()
        train_layout.addLayout(train_btn_layout)

        layout.addWidget(train_group)

        # Scan controls
        scan_group = QGroupBox("🔍 ML Scan")
        scan_layout = QVBoxLayout(scan_group)

        gen_candidates_btn = QPushButton("🎯 Generate Candidates")
        gen_candidates_btn.clicked.connect(self._generate_candidates)
        gen_candidates_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                padding: 4px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #F57C00; }
        """)
        scan_layout.addWidget(gen_candidates_btn)

        scan_btn_layout = QHBoxLayout()
        self.scan_ml_btn = QPushButton("🔎 Scan with ML")
        self.scan_ml_btn.clicked.connect(self._scan_with_ml)
        self.scan_ml_btn.setEnabled(False)
        scan_btn_layout.addWidget(self.scan_ml_btn)

        self.scan_status_label = QLabel("")
        self.scan_status_label.setStyleSheet("color: #888; font-size: 11px;")
        scan_btn_layout.addWidget(self.scan_status_label)
        scan_btn_layout.addStretch()
        scan_layout.addLayout(scan_btn_layout)

        layout.addWidget(scan_group)

        layout.addStretch()
        return tab

    def _create_ai_tab(self):
        """Create the AI tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        # REMOVED: Column selector (now in top toolbar)
        info_label = QLabel("Generating into current column (select in toolbar)")
        info_label.setStyleSheet("color: #666; font-size: 11px; padding: 2px;")
        layout.addWidget(info_label)

        # Prompt
        prompt_group = QGroupBox("📝 Prompt Template")
        prompt_layout = QVBoxLayout(prompt_group)

        self.ai_prompt_input = QTextEdit()
        self.ai_prompt_input.setPlaceholderText(
            "Summarize {{item}} in one sentence...\nUse {{item}} as placeholder for each item")
        self.ai_prompt_input.setMaximumHeight(80)
        prompt_layout.addWidget(self.ai_prompt_input)
        layout.addWidget(prompt_group)

        # Parameters
        param_group = QGroupBox("⚙️ AI Parameters")
        param_layout = QHBoxLayout(param_group)

        param_layout.addWidget(QLabel("Temp:"))
        self.ai_temp = QDoubleSpinBox()
        self.ai_temp.setRange(0.0, 1.0)
        self.ai_temp.setSingleStep(0.1)
        self.ai_temp.setValue(0.7)
        self.ai_temp.setMaximumWidth(60)
        param_layout.addWidget(self.ai_temp)

        param_layout.addSpacing(10)

        param_layout.addWidget(QLabel("Top P:"))
        self.ai_top_p = QDoubleSpinBox()
        self.ai_top_p.setRange(0.0, 1.0)
        self.ai_top_p.setSingleStep(0.05)
        self.ai_top_p.setValue(0.9)
        self.ai_top_p.setMaximumWidth(60)
        param_layout.addWidget(self.ai_top_p)

        param_layout.addSpacing(10)

        param_layout.addWidget(QLabel("Max Tokens:"))
        self.ai_tokens = QSpinBox()
        self.ai_tokens.setRange(50, 2000)
        self.ai_tokens.setValue(200)
        self.ai_tokens.setMaximumWidth(80)
        param_layout.addWidget(self.ai_tokens)

        param_layout.addSpacing(10)

        param_layout.addWidget(QLabel("Format:"))
        self.ai_format = QComboBox()
        self.ai_format.addItems(["Sentence", "Paragraph", "Article"])
        self.ai_format.setMaximumWidth(100)
        param_layout.addWidget(self.ai_format)

        param_layout.addStretch()
        layout.addWidget(param_group)

        # Generate button
        gen_layout = QHBoxLayout()
        self.ai_generate_btn = QPushButton("🚀 Generate AI Items")
        self.ai_generate_btn.clicked.connect(self._generate_ai_items)
        self.ai_generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #7B1FA2; }
        """)
        gen_layout.addWidget(self.ai_generate_btn)
        gen_layout.addStretch()
        layout.addLayout(gen_layout)

        layout.addStretch()
        return tab
    # ========== COLUMN MANAGEMENT ==========

    def _show_column_manager(self):
        dialog = ColumnManagerDialog(self.current_columns, self)
        if dialog.exec_() == QDialog.DialogCode.Accepted:
            self._update_column_dropdowns()
            self._update_preview()
            self._save_synthesizer_state()

    def _update_column_dropdowns(self):
        """Update the column dropdown (only one now)."""
        names = [col.name for col in self.current_columns]

        # Only update the main column dropdown
        self.column_dropdown.blockSignals(True)
        self.column_dropdown.clear()
        self.column_dropdown.addItems(names)
        if names:
            self.column_dropdown.setCurrentIndex(0)
        self.column_dropdown.blockSignals(False)

        # Update preview with new column
        self._update_preview()

    def _on_column_changed(self, index):
        """Handle column dropdown change."""
        if index >= 0 and index < len(self.current_columns):
            col = self.current_columns[index]
            self.current_results = self.column_data.get(col.name, [])
            self._update_preview()

    def _update_pattern_column(self, index):
        pass

    def _update_ml_column(self, index):
        pass

    def _update_ai_column(self, index):
        pass

    # ========== PREVIEW / REVIEW ==========


    def _on_confidence_changed(self, value):
        """Update confidence threshold."""
        self.confidence_threshold = value / 100.0
        self.confidence_label.setText(f"{self.confidence_threshold:.2f}")
        self._update_preview()

    def _toggle_review_mode(self, checked):
        self.review_mode = checked
        self._update_preview()

    def _update_preview(self):
        """Update the preview table."""
        col_index = self.column_dropdown.currentIndex()
        if col_index < 0 or col_index >= len(self.current_columns):
            self.preview_table.setColumnCount(0)
            self.preview_table.setRowCount(0)
            self.item_count_label.setText("0 items")
            return

        col = self.current_columns[col_index]
        column_name = col.name

        # Determine what to display
        if self.review_mode and self.review_items:
            display_items = self._filter_review_items()
        else:
            display_items = self.column_data.get(column_name, [])
            # If we have ML results with confidence, show them
            if self.ml_results:
                display_items = self._filter_ml_results()

        # Set up table columns
        if self.review_mode and self.review_items:
            self.preview_table.setColumnCount(4)
            self.preview_table.setHorizontalHeaderLabels(["", "Confidence", column_name, "Edit"])
        elif self.ml_results and not self.review_mode:
            self.preview_table.setColumnCount(2)
            self.preview_table.setHorizontalHeaderLabels(["Confidence", column_name])
        else:
            self.preview_table.setColumnCount(1)
            self.preview_table.setHorizontalHeaderLabels([column_name])

        self.preview_table.setRowCount(len(display_items))

        for i, item_data in enumerate(display_items):
            if isinstance(item_data, tuple):
                if len(item_data) == 2:
                    item_text, confidence = item_data
                else:
                    item_text, confidence, is_edited = item_data
                confidence_val = confidence if isinstance(confidence, float) else 0.0
            else:
                item_text = item_data
                confidence_val = None

            col_idx = 0

            if self.review_mode and self.review_items:
                # Checkbox
                check_item = QTableWidgetItem()
                check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                check_item.setCheckState(Qt.Checked)
                self.preview_table.setItem(i, 0, check_item)
                col_idx = 1

                # Confidence score
                if confidence_val is not None:
                    conf_item = QTableWidgetItem(f"{confidence_val:.2f}")
                    if confidence_val >= 0.8:
                        conf_item.setBackground(QBrush(QColor(200, 255, 200)))
                    elif confidence_val >= 0.6:
                        conf_item.setBackground(QBrush(QColor(255, 255, 200)))
                    else:
                        conf_item.setBackground(QBrush(QColor(255, 200, 200)))
                    self.preview_table.setItem(i, 1, conf_item)
                else:
                    self.preview_table.setItem(i, 1, QTableWidgetItem("N/A"))
                col_idx = 2

                # Item text (editable)
                text_item = QTableWidgetItem(item_text)
                text_item.setFlags(text_item.flags() | Qt.ItemIsEditable)

                # Check if this item was edited
                if isinstance(item_data, tuple) and len(item_data) == 3 and item_data[2]:
                    text_item.setBackground(QBrush(QColor(200, 220, 255)))
                    edit_indicator = QTableWidgetItem("✎ Edited")
                    edit_indicator.setFlags(Qt.ItemIsEnabled)
                    edit_indicator.setTextAlignment(Qt.AlignCenter)
                    edit_indicator.setBackground(QBrush(QColor(200, 220, 255)))
                    self.preview_table.setItem(i, 3, edit_indicator)
                else:
                    edit_item = QTableWidgetItem("✎")
                    edit_item.setFlags(Qt.ItemIsEnabled)
                    edit_item.setTextAlignment(Qt.AlignCenter)
                    self.preview_table.setItem(i, 3, edit_item)

                self.preview_table.setItem(i, 2, text_item)

            elif self.ml_results and not self.review_mode:
                if confidence_val is not None:
                    conf_item = QTableWidgetItem(f"{confidence_val:.2f}")
                    if confidence_val >= 0.8:
                        conf_item.setBackground(QBrush(QColor(200, 255, 200)))
                    elif confidence_val >= 0.6:
                        conf_item.setBackground(QBrush(QColor(255, 255, 200)))
                    else:
                        conf_item.setBackground(QBrush(QColor(255, 200, 200)))
                    self.preview_table.setItem(i, 0, conf_item)
                else:
                    self.preview_table.setItem(i, 0, QTableWidgetItem("N/A"))

                text_item = QTableWidgetItem(item_text)
                self.preview_table.setItem(i, 1, text_item)

            else:
                text_item = QTableWidgetItem(item_text)
                self.preview_table.setItem(i, 0, text_item)

        # Resize columns
        for col in range(self.preview_table.columnCount()):
            self.preview_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        if self.preview_table.columnCount() > 0:
            self.preview_table.horizontalHeader().setSectionResizeMode(
                self.preview_table.columnCount() - 1, QHeaderView.Stretch
            )

        self.item_count_label.setText(f"{len(display_items)} items")
        self.commit_btn.setEnabled(self.review_mode and bool(self.review_items))

        # Update Good/Bad count
        self.good_bad_count_label.setText(f"✅ Good: {len(self.good_examples)} | ❌ Bad: {len(self.bad_examples)}")

        if self.review_mode and self.review_items:
            self.preview_status.setText("📋 Review Mode - Edit items, mark Good/Bad, commit")
            self.preview_status.setStyleSheet("color: #FF9800; font-size: 11px;")
        else:
            self.preview_status.setText("📊 Table Mode")
            self.preview_status.setStyleSheet("color: #4CAF50; font-size: 11px;")

    def _filter_review_items(self):
        """Filter review items by confidence threshold."""
        filtered = []
        for item_data in self.review_items:
            if isinstance(item_data, tuple) and len(item_data) >= 2:
                item_text, confidence = item_data[0], item_data[1]
                if confidence >= self.confidence_threshold:
                    filtered.append(item_data)
            else:
                # Items without confidence always shown
                filtered.append(item_data)
        return filtered

    def _filter_ml_results(self):
        """Filter ML results by confidence threshold."""
        return [item for item in self.ml_results if item[1] >= self.confidence_threshold]

    def _on_preview_item_changed(self, item):
        """Handle item changes in the preview table."""
        # Check if this is the item column being edited
        if self.review_mode and item.column() == 2:  # Item column in review mode
            row = item.row()
            if row < len(self.review_items):
                new_text = item.text()
                old_data = self.review_items[row]

                # Update the review item with new text
                if isinstance(old_data, tuple):
                    # Preserve confidence score, mark as edited
                    if len(old_data) == 3:
                        self.review_items[row] = (new_text, old_data[1], True)  # True = edited
                    else:
                        self.review_items[row] = (new_text, old_data[1])
                else:
                    self.review_items[row] = new_text

                # If this item is already in the column, update it too
                col_index = self.column_dropdown.currentIndex()
                if col_index >= 0 and col_index < len(self.current_columns):
                    col = self.current_columns[col_index]
                    if col.name in self.column_data:
                        # Find and update the item in column data
                        old_text = old_data[0] if isinstance(old_data, tuple) else old_data
                        if old_text in self.column_data[col.name]:
                            idx = self.column_data[col.name].index(old_text)
                            self.column_data[col.name][idx] = new_text

                            # If this item was in good or bad examples, update those too
                            self._update_examples(old_text, new_text)

                            self._save_synthesizer_state()

                self.update_status(f"✏️ Item edited: '{new_text[:50]}...'")

        # Handle checkbox changes
        elif self.review_mode and item.column() == 0:
            checked = 0
            for i in range(self.preview_table.rowCount()):
                check_item = self.preview_table.item(i, 0)
                if check_item and check_item.checkState() == Qt.Checked:
                    checked += 1
            self.commit_btn.setEnabled(checked > 0)

    def _update_examples(self, old_text: str, new_text: str):
        """Update good/bad examples when an item is edited."""
        # Update good examples
        if old_text in self.good_examples:
            idx = self.good_examples.index(old_text)
            self.good_examples[idx] = new_text
            print(f"🔄 Updated good example: '{old_text}' -> '{new_text}'")

        # Update bad examples
        if old_text in self.bad_examples:
            idx = self.bad_examples.index(old_text)
            self.bad_examples[idx] = new_text
            print(f"🔄 Updated bad example: '{old_text}' -> '{new_text}'")

    def _mark_selected_good(self):
        """Mark selected rows as Good examples and auto-add to column."""
        selected = self.preview_table.selectedIndexes()
        rows = set([idx.row() for idx in selected])

        if not rows:
            QMessageBox.information(self, "No Selection", "Please select rows to mark as Good.")
            return

        # Get current column
        col_index = self.column_dropdown.currentIndex()
        if col_index < 0 or col_index >= len(self.current_columns):
            return

        col = self.current_columns[col_index]

        # Determine which items to use
        if self.review_mode and self.review_items:
            display_items = self._filter_review_items()
        elif self.ml_results:
            display_items = self._filter_ml_results()
        else:
            display_items = self.column_data.get(col.name, [])

        added_to_column = 0
        added_to_good = 0
        edited_items = []

        for row in rows:
            if row < len(display_items):
                item_data = display_items[row]

                # Get the text (might be edited)
                if isinstance(item_data, tuple):
                    item_text = item_data[0]
                    # Check if this was edited
                    if len(item_data) == 3 and item_data[2]:  # Edited flag
                        edited_items.append(item_text)
                else:
                    item_text = item_data

                if not item_text:
                    continue

                # Add to good examples (always)
                if item_text not in self.good_examples:
                    self.good_examples.append(item_text)
                    added_to_good += 1

                # Auto-add to column if not already there
                if col.name not in self.column_data:
                    self.column_data[col.name] = []

                if item_text not in self.column_data[col.name]:
                    self.column_data[col.name].append(item_text)
                    added_to_column += 1

        # Remove from review items if they were in review
        if self.review_mode and self.review_items:
            marked_texts = []
            for row in rows:
                if row < len(self.review_items):
                    item_data = self.review_items[row]
                    if isinstance(item_data, tuple):
                        marked_texts.append(item_data[0])
                    else:
                        marked_texts.append(item_data)

            self.review_items = [item for item in self.review_items
                                 if (item[0] if isinstance(item, tuple) else item) not in marked_texts]

        self._update_counts()
        self._update_preview()
        self._save_synthesizer_state()

        # Enable train button if we have both good and bad
        if len(self.good_examples) >= 2 and len(self.bad_examples) >= 2:
            self.train_ml_btn.setEnabled(True)

        edit_msg = f" ({len(edited_items)} edited)" if edited_items else ""
        self.update_status(
            f"Marked {added_to_good} as Good, added {added_to_column} to column{edit_msg}"
        )

        QMessageBox.information(
            self,
            "Good Items Processed",
            f"✅ Added {added_to_good} items to Good examples\n"
            f"📋 Added {added_to_column} items to column '{col.name}'\n"
            f"✏️ Edited items: {len(edited_items)}"
        )

    def _view_good_examples(self):
        """Open a dialog to view and manage good examples."""
        if not self.good_examples:
            QMessageBox.information(self, "No Good Examples", "No good examples have been marked yet.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("✅ Good Examples")
        dialog.setMinimumSize(600, 450)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        # Header with count
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel(f"Good Examples ({len(self.good_examples)})"))
        header_layout.addStretch()

        # Submit all to column button
        submit_all_btn = QPushButton("📋 Submit All to Column")
        submit_all_btn.clicked.connect(lambda: self._submit_all_good_to_column(dialog))
        submit_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 4px 12px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        header_layout.addWidget(submit_all_btn)

        layout.addLayout(header_layout)

        # List of good examples
        self.good_list_widget = QListWidget()
        self.good_list_widget.setSelectionMode(QListWidget.MultiSelection)
        self.good_list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 6px 10px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #d0e4ff;
            }
            QListWidget::item:hover {
                background-color: #e8f0fe;
            }
        """)

        for example in self.good_examples:
            item = QListWidgetItem(example)
            self.good_list_widget.addItem(item)

        layout.addWidget(self.good_list_widget)

        # Buttons
        btn_layout = QHBoxLayout()

        remove_btn = QPushButton("🗑️ Remove Selected")
        remove_btn.clicked.connect(lambda: self._remove_selected_good(dialog))
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 4px 12px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        btn_layout.addWidget(remove_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        dialog.exec_()

    def _remove_selected_good(self, dialog):
        """Remove selected items from good examples."""
        selected_items = self.good_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Please select items to remove.")
            return

        reply = QMessageBox.question(
            self,
            "Remove Good Examples",
            f"Remove {len(selected_items)} selected items from Good examples?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            texts_to_remove = [item.text() for item in selected_items]
            self.good_examples = [e for e in self.good_examples if e not in texts_to_remove]

            # Refresh the list
            self.good_list_widget.clear()
            for example in self.good_examples:
                item = QListWidgetItem(example)
                self.good_list_widget.addItem(item)

            self._update_counts()
            self._save_synthesizer_state()

            # Disable train if not enough examples
            if len(self.good_examples) < 2 or len(self.bad_examples) < 2:
                self.train_ml_btn.setEnabled(False)

            QMessageBox.information(self, "Removed", f"Removed {len(texts_to_remove)} items from Good examples.")

    def _submit_all_good_to_column(self, dialog):
        """Submit all good examples to the current column."""
        col_index = self.column_dropdown.currentIndex()
        if col_index < 0 or col_index >= len(self.current_columns):
            QMessageBox.warning(self, "No Column", "Please select a target column first.")
            return

        col = self.current_columns[col_index]

        if col.name not in self.column_data:
            self.column_data[col.name] = []

        # Find items not already in column
        new_items = [item for item in self.good_examples if item not in self.column_data[col.name]]

        if not new_items:
            QMessageBox.information(self, "No New Items", "All good examples are already in the column.")
            return

        # Ask for confirmation
        reply = QMessageBox.question(
            self,
            "Submit All Good Examples",
            f"Submit {len(new_items)} good examples to column '{col.name}'?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.column_data[col.name].extend(new_items)
            self._update_preview()
            self._save_synthesizer_state()

            dialog.accept()

            QMessageBox.information(
                self,
                "Submitted",
                f"Added {len(new_items)} items to column '{col.name}'."
            )

    def _view_bad_examples(self):
        """Open a dialog to view and manage bad examples."""
        if not self.bad_examples:
            QMessageBox.information(self, "No Bad Examples", "No bad examples have been marked yet.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("❌ Bad Examples")
        dialog.setMinimumSize(600, 450)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        # Header with count
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel(f"Bad Examples ({len(self.bad_examples)})"))
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # List of bad examples
        self.bad_list_widget = QListWidget()
        self.bad_list_widget.setSelectionMode(QListWidget.MultiSelection)
        self.bad_list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 6px 10px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #ffe0e0;
            }
            QListWidget::item:hover {
                background-color: #ffd0d0;
            }
        """)

        for example in self.bad_examples:
            item = QListWidgetItem(example)
            self.bad_list_widget.addItem(item)

        layout.addWidget(self.bad_list_widget)

        # Buttons
        btn_layout = QHBoxLayout()

        remove_btn = QPushButton("🗑️ Remove Selected")
        remove_btn.clicked.connect(lambda: self._remove_selected_bad(dialog))
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 4px 12px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        btn_layout.addWidget(remove_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        dialog.exec_()

    def _remove_selected_bad(self, dialog):
        """Remove selected items from bad examples."""
        selected_items = self.bad_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Please select items to remove.")
            return

        reply = QMessageBox.question(
            self,
            "Remove Bad Examples",
            f"Remove {len(selected_items)} selected items from Bad examples?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            texts_to_remove = [item.text() for item in selected_items]
            self.bad_examples = [e for e in self.bad_examples if e not in texts_to_remove]

            # Refresh the list
            self.bad_list_widget.clear()
            for example in self.bad_examples:
                item = QListWidgetItem(example)
                self.bad_list_widget.addItem(item)

            self._update_counts()
            self._save_synthesizer_state()

            # Disable train if not enough examples
            if len(self.good_examples) < 2 or len(self.bad_examples) < 2:
                self.train_ml_btn.setEnabled(False)

            QMessageBox.information(self, "Removed", f"Removed {len(texts_to_remove)} items from Bad examples.")

    def _mark_selected_bad(self):
        """Mark selected rows as Bad examples for ML training."""
        selected = self.preview_table.selectedIndexes()
        rows = set([idx.row() for idx in selected])

        if not rows:
            QMessageBox.information(self, "No Selection", "Please select rows to mark as Bad.")
            return

        col_index = self.column_dropdown.currentIndex()
        if col_index < 0:
            return

        col = self.current_columns[col_index]

        # Determine which items to use
        if self.review_mode and self.review_items:
            display_items = self._filter_review_items()
        elif self.ml_results:
            display_items = self._filter_ml_results()
        else:
            display_items = self.column_data.get(col.name, [])

        added = 0
        for row in rows:
            if row < len(display_items):
                item_data = display_items[row]
                if isinstance(item_data, tuple):
                    item_text = item_data[0]
                else:
                    item_text = item_data

                if item_text and item_text not in self.bad_examples:
                    self.bad_examples.append(item_text)
                    added += 1

        self._update_counts()
        self._save_synthesizer_state()

        if len(self.good_examples) >= 2 and len(self.bad_examples) >= 2:
            self.train_ml_btn.setEnabled(True)

        self.update_status(f"Marked {added} items as Bad")

    def _update_counts(self):
        """Update all count labels."""
        # Preview tab counts
        self.good_bad_count_label.setText(f"✅ Good: {len(self.good_examples)} | ❌ Bad: {len(self.bad_examples)}")

        # ML tab counts (if they exist)
        if hasattr(self, 'good_count_label'):
            self.good_count_label.setText(f"✅ Good: {len(self.good_examples)}")
        if hasattr(self, 'bad_count_label'):
            self.bad_count_label.setText(f"❌ Bad: {len(self.bad_examples)}")

        # Enable train button if enough examples
        if hasattr(self, 'train_ml_btn'):
            if len(self.good_examples) >= 2 and len(self.bad_examples) >= 2:
                self.train_ml_btn.setEnabled(True)
    def _commit_review(self):
        """Commit selected review items to the column with edits preserved."""
        col_index = self.column_dropdown.currentIndex()
        if col_index < 0 or col_index >= len(self.current_columns):
            return

        col = self.current_columns[col_index]

        selected = []
        for i in range(self.preview_table.rowCount()):
            check_item = self.preview_table.item(i, 0)
            if check_item and check_item.checkState() == Qt.Checked:
                # Get the text from the item column (which may have been edited)
                if self.review_mode:
                    text_item = self.preview_table.item(i, 2)  # Item column
                else:
                    text_item = self.preview_table.item(i, 0)
                if text_item:
                    selected.append(text_item.text())

        if not selected:
            return

        if col.name not in self.column_data:
            self.column_data[col.name] = []

        # Add only items not already in the column
        new_items = []
        for item in selected:
            if item not in self.column_data[col.name]:
                new_items.append(item)

        if new_items:
            self.column_data[col.name].extend(new_items)

        # Remove committed items from review
        self.review_items = []
        self.ml_results = []
        self._update_preview()
        self._save_synthesizer_state()

        QMessageBox.information(
            self,
            "Commit Complete",
            f"Added {len(new_items)} new items to column '{col.name}'.\n"
            f"({len(selected) - len(new_items)} were already in the column)"
        )
    def _clear_review(self):
        reply = QMessageBox.question(
            self,
            "Clear Review",
            "Clear all review items?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.review_items = []
            self.ml_results = []
            self._update_preview()

    def _add_to_review(self, items, confidences=None):
        """Add items to review with optional confidence scores."""
        if not items:
            return

        if confidences and len(confidences) == len(items):
            for item, conf in zip(items, confidences):
                self.review_items.append((item, conf))
        else:
            self.review_items.extend(items)

        self._update_preview()
        self.workflow_tabs.setCurrentIndex(0)

    # ========== PATTERN EXTRACTION ==========

    def _test_pattern(self):
        pattern = self.rule_builder.get_regex_pattern()
        if not pattern:
            QMessageBox.warning(self, "No Pattern", "Please build a pattern first.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Test Pattern")
        dialog.setMinimumSize(600, 400)

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Sample Text:"))
        sample_input = QTextEdit()
        sample_input.setPlaceholderText("Paste sample text here...")
        sample_input.setMaximumHeight(150)
        layout.addWidget(sample_input)
        layout.addWidget(QLabel("Extracted Items:"))
        result_display = QTextEdit()
        result_display.setReadOnly(True)
        layout.addWidget(result_display)
        btn_layout = QHBoxLayout()
        test_btn = QPushButton("🔍 Test")
        test_btn.clicked.connect(lambda: self._run_test(sample_input.toPlainText(), pattern, result_display))
        btn_layout.addWidget(test_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        dialog.exec_()

    def _run_test(self, text, pattern, result_display):
        if not text:
            return
        matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
        items = []
        for match in matches:
            if isinstance(match, tuple):
                item = ' '.join(str(part).strip() for part in match if part)
            else:
                item = str(match).strip()
            item = re.sub(r'\s+', ' ', item)
            item = item.strip('"\'“”‘’')
            if item and len(item) > 3:
                items.append(item)
        if items:
            result_display.setText('\n'.join([f"{i + 1}. {item}" for i, item in enumerate(items)]))
            result_display.append(f"\n--- Found {len(items)} items ---")
        else:
            result_display.setText("No items found with this pattern.")

    def _extract_with_pattern(self):
        """Extract items using the current pattern."""
        pattern = self.rule_builder.get_regex_pattern()
        if not pattern:
            QMessageBox.warning(self, "No Pattern", "Please build a pattern first.")
            return

        source_ids = self.get_selected_source_ids()
        if not source_ids:
            QMessageBox.warning(self, "No Sources", "Please select at least one source.")
            return

        # Use main column dropdown
        col_index = self.column_dropdown.currentIndex()
        if col_index < 0 or col_index >= len(self.current_columns):
            QMessageBox.warning(self, "No Column", "Please create a target column first.")
            return


        progress = QProgressDialog("Extracting with pattern...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        try:
            all_text = []
            for i, source_id in enumerate(source_ids):
                text = self.db.get_project_text_pool(source_id)
                if text:
                    all_text.append(text)
                progress.setValue(int((i + 1) / len(source_ids) * 50))

            if not all_text:
                progress.close()
                QMessageBox.warning(self, "No Text", "No text found in selected sources.")
                return

            combined_text = '\n\n'.join(all_text)
            progress.setValue(70)

            matches = re.findall(pattern, combined_text, re.IGNORECASE | re.DOTALL)
            items = []
            for match in matches:
                if isinstance(match, tuple):
                    item = ' '.join(str(part).strip() for part in match if part)
                else:
                    item = str(match).strip()
                item = re.sub(r'\s+', ' ', item)
                item = item.strip('"\'“”‘’')
                if item and len(item) > 3:
                    items.append(item)

            progress.setValue(100)

            if items:
                self._add_to_review(items)
                QMessageBox.information(
                    self,
                    "Extraction Complete",
                    f"Extracted {len(items)} items. Review them in the Preview tab."
                )
            else:
                QMessageBox.information(self, "No Matches", "No items found with this pattern.")

        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Error", f"Extraction failed:\n{str(e)}")
        progress.close()

    # ========== ML TAB ==========

    def _generate_candidates(self):
        """Generate candidate chunks for review."""
        source_ids = self.get_selected_source_ids()
        if not source_ids:
            QMessageBox.warning(self, "No Sources", "Please select sources.")
            return

        # Get all text from sources
        all_text = []
        for source_id in source_ids:
            text = self.db.get_project_text_pool(source_id)
            if text:
                all_text.append(text)

        combined_text = '\n\n'.join(all_text)

        # Chunk the text based on settings
        chunk_size = self.chunk_size_combo.currentText()
        chunk_count = self.chunk_count_spin.value()

        if chunk_size == "Sentences":
            chunks = combined_text.split('. ')
        elif chunk_size == "Paragraphs":
            chunks = combined_text.split('\n\n')
        elif chunk_size == "Lines":
            chunks = combined_text.split('\n')
        else:  # Words
            words = combined_text.split()
            chunks = [' '.join(words[i:i + chunk_count]) for i in range(0, len(words), chunk_count)]

        # Clean chunks
        cleaned = []
        for chunk in chunks:
            chunk = chunk.strip()
            if len(chunk) > 20 and len(chunk) < 500:
                cleaned.append(chunk)

        # Rank by relevance to reference phrase
        ref_phrase = self.ref_phrase_input.text().strip()
        if ref_phrase:
            words = ref_phrase.lower().split()
            scored = []
            for chunk in cleaned:
                score = sum(1 for w in words if w in chunk.lower())
                scored.append((chunk, score))

            if self.rank_order_combo.currentText() == "Most Relevant First":
                scored.sort(key=lambda x: x[1], reverse=True)
            else:
                scored.sort(key=lambda x: x[1])

            top_k = self.top_k_spin.value()
            results = [item for item, score in scored[:top_k]]
            # Store with confidence (score normalized)
            max_score = max([s for _, s in scored[:top_k]]) if scored else 1
            confidences = [score / max_score if max_score > 0 else 0.5 for _, score in scored[:top_k]]
        else:
            results = cleaned[:self.top_k_spin.value()]
            confidences = [0.5] * len(results)

        if results:
            self._add_to_review(results, confidences)
            QMessageBox.information(
                self,
                "Candidates Generated",
                f"Generated {len(results)} candidates. Review them in the Preview tab."
            )
        else:
            QMessageBox.information(self, "No Candidates", "No candidates generated.")

    def _train_ml(self):
        """Train ML model with embeddings + handcrafted features."""
        if len(self.good_examples) < 2 or len(self.bad_examples) < 2:
            QMessageBox.warning(
                self,
                "Need More Examples",
                f"Need at least 2 good and 2 bad examples.\n"
                f"Current: {len(self.good_examples)} good, {len(self.bad_examples)} bad"
            )
            return

        # Get selected source IDs
        source_ids = self.get_selected_source_ids()
        if not source_ids:
            QMessageBox.warning(self, "No Sources", "Please select at least one source project.")
            return

        # Show progress
        progress = QProgressDialog("Training ML model with features...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        try:
            # Collect text from ALL selected sources
            all_text = []
            for i, source_id in enumerate(source_ids):
                text = self.db.get_project_text_pool(source_id)
                if text:
                    all_text.append(text)
                    progress.setValue(int((i + 1) / len(source_ids) * 50))
                else:
                    print(f"⚠️ No text found in source {source_id}")

            if not all_text:
                progress.close()
                QMessageBox.warning(
                    self,
                    "No Text",
                    "No text content found in selected sources.\n\n"
                    "Make sure your sources contain text data (research pages, documents, chat messages, or table data)."
                )
                return

            full_text = '\n\n'.join(all_text)
            print(f"📄 Combined text length: {len(full_text)} characters")
            progress.setValue(60)

            # Train using pipeline with features
            self.ml_status_label.setText("Training with embeddings + features...")
            self.ml_status_label.setStyleSheet("color: #FF9800; font-size: 11px;")
            self.train_ml_btn.setEnabled(False)

            # Use the pipeline - pass the combined text directly
            from studio.core.extraction_pipeline import ExtractionPipeline

            # Create pipeline but override the text pool
            pipeline = ExtractionPipeline(self.db, self.project_id, "ml_training")

            # Manually set the text pool for training
            # We need to modify the pipeline to use our combined text
            # Since the pipeline uses _get_project_text_pool(), we need to use a different approach

            # Use the pipeline's train_ml_model method with the combined text
            # But we need to pass the text directly to the training method
            # Let me check the pipeline method signature...

            # Actually, let me use the pipeline's method directly with the combined text
            # The train_ml_model method expects seed_items and then internally calls _get_project_text_pool()
            # We need to bypass that and pass the text directly

            # Alternative: Use a custom training function
            success, result = self._train_ml_with_text(pipeline, self.good_examples, full_text)

            progress.setValue(80)

            if success:
                self.ml_model_id = result.get('model_id')
                self.ml_trained = True

                self.ml_status_label.setText(
                    f"✅ Trained on {result['training_samples']} samples "
                    f"({result.get('feature_count', 0)} features)"
                )
                self.ml_status_label.setStyleSheet("color: #4CAF50; font-size: 11px;")
                self.scan_ml_btn.setEnabled(True)

                # Show feature importance
                top_features = result.get('top_features', {})
                feature_text = "\n".join([f"  {k}: {v:.3f}" for k, v in top_features.items()])
                progress.setValue(100)

                QMessageBox.information(
                    self,
                    "ML Training Complete",
                    f"Model trained with {result['training_samples']} samples.\n"
                    f"Accuracy: {result['accuracy']:.2%}\n"
                    f"Features: {result.get('feature_count', 0)}\n\n"
                    f"Top features:\n{feature_text}"
                )

                self._save_synthesizer_state()
            else:
                error = result.get('error', 'Unknown error')
                self.ml_status_label.setText(f"❌ Error: {error[:50]}")
                self.ml_status_label.setStyleSheet("color: #f44336; font-size: 11px;")
                QMessageBox.critical(self, "Training Error", f"Failed to train ML model:\n{error}")

            self.train_ml_btn.setEnabled(True)

        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Error", f"Training failed:\n{str(e)}")
            import traceback
            traceback.print_exc()

        progress.close()

    def _train_ml_with_text(self, pipeline, seed_items, full_text):
        """
        Train ML model using the pipeline but with provided text.
        This uses the current (edited) versions of items.
        """
        try:
            # Get candidate segments from the text
            candidates = pipeline._get_candidate_segments(full_text)
            if len(candidates) < 10:
                return False, {
                    "error": f"Not enough text content to extract candidates. Found {len(candidates)} segments."}

            # Label data using the current (edited) seed items
            X_texts = []
            y_labels = []
            seed_set = set(seed_items)  # These are the edited versions

            # Positives: all seed items that appear in candidates
            positive_count = 0
            for seg in candidates:
                # Check against edited seed items
                if seg in seed_set or any(seed in seg for seed in seed_set):
                    X_texts.append(seg)
                    y_labels.append(1)
                    positive_count += 1

            if positive_count < 3:
                return False, {"error": f"Not enough seed items found in the text. Found {positive_count} matches."}

            # Negatives: sample random segments that are NOT seeds
            non_seeds = [s for s in candidates if s not in seed_set]
            num_negatives = min(len(non_seeds), int(positive_count * 2.0))

            if num_negatives < 3:
                return False, {"error": f"Not enough negative examples. Found {len(non_seeds)} non-matches."}

            import random
            neg_samples = random.sample(non_seeds, num_negatives)
            X_texts.extend(neg_samples)
            y_labels.extend([0] * len(neg_samples))

            print(f"📊 Training data: {len(X_texts)} samples ({positive_count} positive, {num_negatives} negative)")
            print(f"📝 Seed items (edited): {seed_items[:5]}...")

            # Feature Engineering with TF-IDF + Handcrafted
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.feature_extraction.text import TfidfVectorizer
            import numpy as np

            # 1. TF-IDF embeddings - uses the current text versions
            vectorizer = TfidfVectorizer(
                max_features=300,
                stop_words='english',
                ngram_range=(1, 2),
                min_df=2,
                max_df=0.9,
            )
            tfidf_features = vectorizer.fit_transform(X_texts)

            # 2. Handcrafted features - calculated from current text
            handcrafted_features = []
            for text in X_texts:
                features = pipeline.extract_features(text)
                handcrafted_features.append(list(features.values()))
            handcrafted = np.array(handcrafted_features)

            # 3. Combine features
            tfidf_dense = tfidf_features.toarray()
            feature_matrix = np.hstack([tfidf_dense, handcrafted])

            # Get feature names
            tfidf_names = vectorizer.get_feature_names_out().tolist()
            handcrafted_names = pipeline.get_feature_names()
            feature_names = tfidf_names + handcrafted_names

            # Train RandomForest
            clf = RandomForestClassifier(
                n_estimators=100,
                random_state=42,
                class_weight='balanced',
                n_jobs=-1,
                max_depth=10,
                min_samples_split=5,
            )
            clf.fit(feature_matrix, y_labels)

            # Calculate feature importance
            feature_importance = dict(zip(feature_names, clf.feature_importances_))
            top_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:10]
            print(f"📊 Top 10 features: {top_features}")

            # Save model to database
            import pickle
            model_pickle = pickle.dumps({
                'classifier': clf,
                'vectorizer': vectorizer,
                'feature_names': feature_names,
                'feature_importance': feature_importance,
            })

            from studio.models.ml_model import MLModel
            ml_storage = MLModel(self.db.db_path)

            model_id = ml_storage.save_model(
                project_id=self.project_id,
                column_name="ml_training",
                model_pickle=model_pickle,
                feature_names=feature_names,
                training_count=len(X_texts),
                positive_count=positive_count,
                negative_count=len(X_texts) - positive_count,
                accuracy_score=clf.score(feature_matrix, y_labels)
            )

            # Store in pipeline
            pipeline.ml_model_id = model_id
            pipeline.model = clf
            pipeline.vectorizer = vectorizer
            pipeline.feature_names = feature_names

            return True, {
                "model_id": model_id,
                "training_samples": len(X_texts),
                "positive_samples": positive_count,
                "negative_samples": len(X_texts) - positive_count,
                "accuracy": clf.score(feature_matrix, y_labels),
                "feature_count": len(feature_names),
                "top_features": dict(top_features[:5]),
            }

        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, {"error": str(e)}

    def _on_ml_trained(self):
        self.ml_trained = True
        self.ml_status_label.setText("✅ Trained")
        self.ml_status_label.setStyleSheet("color: #4CAF50; font-size: 11px;")
        self.train_ml_btn.setEnabled(True)
        self.scan_ml_btn.setEnabled(True)
        self.scan_status_label.setText("Ready to scan")
        QMessageBox.information(self, "ML Training Complete", "Model trained successfully!")

    def _scan_with_ml(self):
        """Scan sources with ML and return ranked results with confidence scores."""
        if not self.ml_trained:
            QMessageBox.warning(self, "Not Trained", "Please train the ML model first.")
            return

        source_ids = self.get_selected_source_ids()
        if not source_ids:
            QMessageBox.warning(self, "No Sources", "Please select sources.")
            return

        # Get all text from selected sources
        all_text = []
        for source_id in source_ids:
            text = self.db.get_project_text_pool(source_id)
            if text:
                all_text.append(text)

        if not all_text:
            QMessageBox.warning(
                self,
                "No Text",
                "No text content found in selected sources.\n\n"
                "Make sure your sources contain text data."
            )
            return

        combined_text = '\n\n'.join(all_text)
        print(f"📄 Scanning text length: {len(combined_text)} characters")

        # Load the trained model
        from studio.core.extraction_pipeline import ExtractionPipeline
        pipeline = ExtractionPipeline(self.db, self.project_id, "ml_training")

        if self.ml_model_id:
            success = pipeline.load_ml_model(self.ml_model_id)
            if not success:
                QMessageBox.critical(self, "Error", "Failed to load ML model.")
                return
        else:
            QMessageBox.warning(self, "No Model", "No trained model found.")
            return

        try:
            # Override the pipeline's text pool
            # Since scan_with_ml uses _get_project_text_pool(), we need to use a different approach
            # Let's use the pipeline's internal methods directly

            candidates = pipeline._get_candidate_segments(combined_text)
            if not candidates:
                QMessageBox.information(self, "No Candidates", "No candidates found in the text.")
                return

            # Get features for all candidates
            feature_matrix = pipeline.combine_features(candidates)

            # Predict probabilities
            probs = pipeline.model.predict_proba(feature_matrix)[:, 1]

            # Filter by threshold
            threshold = self.confidence_threshold
            results = []
            for text, prob in zip(candidates, probs):
                if prob >= threshold:
                    features = pipeline.extract_features(text)
                    results.append({
                        "text": text,
                        "confidence": float(prob),
                        "word_count": features['word_count'],
                        "char_count": features['char_count'],
                        "sentence_count": features['sentence_count'],
                        "question_count": features['question_count'],
                        "digit_count": features['digit_count'],
                        "upper_ratio": features['upper_ratio'],
                    })

            results.sort(key=lambda x: x["confidence"], reverse=True)

            # Apply Top K
            top_k = self.top_k_spin.value()
            results = results[:top_k]

            if results:
                # Store for review
                self.ml_results = [(r['text'], r['confidence']) for r in results]

                # Extract items and confidences
                items = [r['text'] for r in results]
                confidences = [r['confidence'] for r in results]
                self._add_to_review(items, confidences)

                top_confidence = results[0]['confidence'] if results else 0
                self.scan_status_label.setText(
                    f"Found {len(results)} candidates (top confidence: {top_confidence:.2f})"
                )

                QMessageBox.information(
                    self,
                    "ML Scan Complete",
                    f"Found {len(results)} candidates with confidence scores.\n"
                    f"Top confidence: {top_confidence:.2f}\n"
                    f"Use the confidence slider in Preview tab to filter results."
                )
            else:
                QMessageBox.information(self, "No Results", "No candidates found above the confidence threshold.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"ML scan failed:\n{str(e)}")
            import traceback
            traceback.print_exc()
    # ========== AI TAB ==========

    def _generate_ai_items(self):
        """Generate items using AI."""
        # Use main column dropdown
        col_index = self.column_dropdown.currentIndex()
        if col_index < 0 or col_index >= len(self.current_columns):
            QMessageBox.warning(self, "No Column", "Please create a target column first.")
            return

        all_items = []
        for col in self.current_columns:
            all_items.extend(self.column_data.get(col.name, []))

        if not all_items:
            QMessageBox.warning(
                self,
                "No Items",
                "Please extract some items first using Pattern or ML."
            )
            return

        prompt_template = self.ai_prompt_input.toPlainText().strip()
        if not prompt_template:
            QMessageBox.warning(self, "Missing Prompt", "Enter a prompt template.")
            return

        # Generate AI items
        results = []
        for item in all_items[:10]:
            ai_item = f"AI: {prompt_template.replace('{{item}}', item)[:50]}..."
            results.append(ai_item)

        if results:
            self._add_to_review(results)
            QMessageBox.information(
                self,
                "AI Generation Complete",
                f"Generated {len(results)} items. Review them in the Preview tab."
            )

    # ========== SOURCE MANAGEMENT ==========

    def load_available_projects(self):
        self.source_list.clear()
        all_projects = self.db.get_all_projects()

        for project in all_projects:
            if project['id'] == self.project_id:
                continue
            icon = ProjectType.get_icon(project['project_type'])
            item = QListWidgetItem(f"{icon} {project['name']}")
            item.setData(Qt.UserRole, project['id'])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.source_list.addItem(item)

        self.update_source_count()

    def select_all_sources(self):
        for i in range(self.source_list.count()):
            self.source_list.item(i).setCheckState(Qt.Checked)
        self.update_source_count()

    def clear_all_sources(self):
        for i in range(self.source_list.count()):
            self.source_list.item(i).setCheckState(Qt.Unchecked)
        self.update_source_count()

    def update_source_count(self):
        count = sum(1 for i in range(self.source_list.count())
                    if self.source_list.item(i).checkState() == Qt.Checked)
        self.source_count_label.setText(str(count))

    def get_selected_source_ids(self):
        ids = []
        for i in range(self.source_list.count()):
            if self.source_list.item(i).checkState() == Qt.Checked:
                ids.append(self.source_list.item(i).data(Qt.UserRole))
        return ids

    # ========== SAVE / LOAD ==========

    def _save_synthesizer_state(self):
        import json

        columns_data = []
        for col in self.current_columns:
            columns_data.append({
                'name': col.name,
                'request': col.request,
                'response_type': col.response_type.value if hasattr(col.response_type, 'value') else 'sentence',
                'creativity': col.creativity,
                'chunk_strategy': col.chunk_strategy.value if hasattr(col.chunk_strategy, 'value') else 'exact_match',
                'lookup_params': col.lookup_params,
                'source_type': col.source_type.value if hasattr(col.source_type, 'value') else 'project',
                'response_size': col.response_size
            })

        column_data_dict = {k: v for k, v in self.column_data.items()}

        selected_sources = []
        for i in range(self.source_list.count()):
            if self.source_list.item(i).checkState() == Qt.Checked:
                selected_sources.append(self.source_list.item(i).data(Qt.UserRole))

        self.metadata['synthesizer_state'] = {
            'columns': columns_data,
            'column_data': column_data_dict,
            'selected_sources': selected_sources,
            'good_examples': self.good_examples,
            'bad_examples': self.bad_examples,
            'ml_trained': self.ml_trained
        }

        self.db.update_project(self.project_id, metadata=self.metadata)
        self.update_status("State saved")

    def load_synthesizer_state(self):
        state = self.metadata.get('synthesizer_state', {})

        if not state:
            if not self.current_columns:
                from views.synthesizer_view.table_generator import ColumnDefinition, ResponseType, ChunkStrategy, \
                    SourceType
                default_col = ColumnDefinition(
                    name="Items",
                    response_type=ResponseType.SENTENCE,
                    request="Extract items",
                    creativity=0.5,
                    chunk_strategy=ChunkStrategy.EXACT_MATCH,
                    lookup_params={'top_k': 10, 'previous_sentences': 1, 'following_sentences': 1,
                                   'order': 'relevancy'},
                    source_type=SourceType.PROJECT,
                    response_size={'words': (2, 6)}
                )
                self.current_columns.append(default_col)

            self._update_column_dropdowns()
            self._update_preview()
            return

        from views.synthesizer_view.table_generator import ColumnDefinition, ResponseType, ChunkStrategy, SourceType

        response_type_map = {
            'sentence': ResponseType.SENTENCE,
            'paragraph': ResponseType.PARAGRAPH,
            'article': ResponseType.ARTICLE
        }
        chunk_strategy_map = {
            'exact_match': ChunkStrategy.EXACT_MATCH,
            'semantic_match': ChunkStrategy.SEMANTIC_MATCH,
            'max_semantic': ChunkStrategy.MAX_SEMANTIC
        }
        source_type_map = {
            'project': SourceType.PROJECT,
            'previous_column_data': SourceType.PREVIOUS_COLUMN_DATA,
            'previous_column_chunks': SourceType.PREVIOUS_COLUMN_CHUNKS
        }

        columns_data = state.get('columns', [])
        self.current_columns = []
        for col_data in columns_data:
            col = ColumnDefinition(
                name=col_data.get('name', ''),
                request=col_data.get('request', ''),
                response_type=response_type_map.get(col_data.get('response_type', 'sentence'), ResponseType.SENTENCE),
                creativity=col_data.get('creativity', 0.5),
                chunk_strategy=chunk_strategy_map.get(col_data.get('chunk_strategy', 'exact_match'),
                                                      ChunkStrategy.EXACT_MATCH),
                lookup_params=col_data.get('lookup_params',
                                           {'top_k': 10, 'previous_sentences': 1, 'following_sentences': 1,
                                            'order': 'relevancy'}),
                source_type=source_type_map.get(col_data.get('source_type', 'project'), SourceType.PROJECT),
                response_size=col_data.get('response_size', {'words': (2, 6)})
            )
            self.current_columns.append(col)

        self.column_data = state.get('column_data', {})

        selected_sources = state.get('selected_sources', [])
        for i in range(self.source_list.count()):
            source_id = self.source_list.item(i).data(Qt.UserRole)
            if source_id in selected_sources:
                self.source_list.item(i).setCheckState(Qt.Checked)

        self.good_examples = state.get('good_examples', [])
        self.bad_examples = state.get('bad_examples', [])
        self.ml_trained = state.get('ml_trained', False)

        self._update_column_dropdowns()
        self._update_preview()
        self.update_source_count()
        self.good_count_label.setText(f"✅ Good: {len(self.good_examples)}")
        self.bad_count_label.setText(f"❌ Bad: {len(self.bad_examples)}")
        self.good_bad_count_label.setText(f"✅ Good: {len(self.good_examples)} | ❌ Bad: {len(self.bad_examples)}")

        if len(self.good_examples) >= 2 and len(self.bad_examples) >= 2:
            self.train_ml_btn.setEnabled(True)
            if self.ml_trained:
                self.ml_status_label.setText("✅ Trained")
                self.ml_status_label.setStyleSheet("color: #4CAF50; font-size: 11px;")
                self.scan_ml_btn.setEnabled(True)

    def load_saved_pipelines(self):
        pipelines = self.metadata.get('extraction_pipelines', [])
        if pipelines:
            print(f"📋 Loaded {len(pipelines)} saved pipelines")

    # ========== UTILITY ==========

    def go_back(self):
        if self.parent_app and hasattr(self.parent_app, 'show_home_tab'):
            self.parent_app.show_home_tab()

    def update_status(self, message):
        self.status_indicator.setText(f"● {message}")
        if self.parent_app and hasattr(self.parent_app, 'update_status'):
            self.parent_app.update_status(message)

    def _clear_examples(self):
        """Clear all good and bad examples with confirmation."""
        if not self.good_examples and not self.bad_examples:
            QMessageBox.information(self, "No Examples", "No examples to clear.")
            return

        reply = QMessageBox.question(
            self,
            "Clear Examples",
            f"Clear {len(self.good_examples)} good and {len(self.bad_examples)} bad examples?\n\n"
            "This will reset ML training data.\n"
            "Note: Items already in columns will remain.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.good_examples = []
            self.bad_examples = []
            self.ml_trained = False
            self.ml_model_id = None
            self.ml_model = None

            self._update_counts()
            self.train_ml_btn.setEnabled(False)
            self.scan_ml_btn.setEnabled(False)
            self.ml_status_label.setText("Not trained")
            self.ml_status_label.setStyleSheet("color: #888; font-size: 11px;")
            self.scan_status_label.setText("")

            self._save_synthesizer_state()
            self.update_status("Examples cleared")

            QMessageBox.information(self, "Cleared", "All examples have been cleared.")

    def _clear_edits(self):
        """Clear all edit flags from review items."""
        if not self.review_items:
            return

        reply = QMessageBox.question(
            self,
            "Clear Edits",
            "Reset edit flags on all review items?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Remove edit flags but keep text
            new_items = []
            for item in self.review_items:
                if isinstance(item, tuple):
                    if len(item) == 3:
                        new_items.append((item[0], item[1], False))
                    else:
                        new_items.append(item)
                else:
                    new_items.append(item)
            self.review_items = new_items
            self._update_preview()
            self.update_status("Edit flags cleared")

    def _table_key_press_event(self, event):
        """Handle keyboard events on the table."""
        from PySide6.QtGui import QKeyEvent

        # Check if Delete key was pressed
        if event.key() == Qt.Key_Delete:
            self._delete_selected_items()
            event.accept()
        else:
            # Call the original event handler
            QTableWidget.keyPressEvent(self.preview_table, event)

    def _delete_selected_items(self):
        """Delete selected items from the current column."""
        selected = self.preview_table.selectedIndexes()
        rows = set([idx.row() for idx in selected])

        if not rows:
            QMessageBox.information(self, "No Selection", "Please select rows to delete.")
            return

        # Get current column
        col_index = self.column_dropdown.currentIndex()
        if col_index < 0 or col_index >= len(self.current_columns):
            QMessageBox.warning(self, "No Column", "No column selected.")
            return

        col = self.current_columns[col_index]

        # Determine which items to delete
        if self.review_mode and self.review_items:
            display_items = self._filter_review_items()
            is_review_mode = True
        else:
            display_items = self.column_data.get(col.name, [])
            is_review_mode = False

        # Get items to delete
        items_to_delete = []
        for row in rows:
            if row < len(display_items):
                item_data = display_items[row]
                if isinstance(item_data, tuple):
                    items_to_delete.append(item_data[0])
                else:
                    items_to_delete.append(item_data)

        if not items_to_delete:
            return

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Delete Items",
            f"Delete {len(items_to_delete)} item(s)?\n\n"
            "This will remove them from the column.\n"
            "Good/Bad examples will be updated automatically.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if is_review_mode:
                # Remove from review items
                self.review_items = [item for item in self.review_items
                                     if (item[0] if isinstance(item, tuple) else item) not in items_to_delete]
            else:
                # Remove from column data
                if col.name in self.column_data:
                    self.column_data[col.name] = [item for item in self.column_data[col.name]
                                                  if item not in items_to_delete]

            # Also remove from good/bad examples
            self.good_examples = [item for item in self.good_examples if item not in items_to_delete]
            self.bad_examples = [item for item in self.bad_examples if item not in items_to_delete]

            # Disable train if not enough examples
            if len(self.good_examples) < 2 or len(self.bad_examples) < 2:
                self.train_ml_btn.setEnabled(False)

            self._update_counts()
            self._update_preview()
            self._save_synthesizer_state()

            self.update_status(f"🗑️ Deleted {len(items_to_delete)} items")

            QMessageBox.information(
                self,
                "Items Deleted",
                f"Deleted {len(items_to_delete)} items from column '{col.name}'."
            )

    def _paste_good_examples(self):
        """Add pasted items as Good examples."""
        text = self.paste_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "No Text", "Please paste some examples first.")
            return

        # Split by newline and clean
        items = [item.strip() for item in text.split('\n') if item.strip()]

        if not items:
            QMessageBox.warning(self, "No Items", "No valid items found in pasted text.")
            return

        # Filter out duplicates
        new_items = [item for item in items if item not in self.good_examples]

        if not new_items:
            QMessageBox.information(self, "No New Items", "All pasted items are already in Good examples.")
            return

        # Ask for confirmation
        reply = QMessageBox.question(
            self,
            "Add Good Examples",
            f"Add {len(new_items)} new items to Good examples?\n\n"
            f"First few:\n{chr(10).join(new_items[:3])}",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.good_examples.extend(new_items)

            # Also auto-add to column if not already there
            col_index = self.column_dropdown.currentIndex()
            if col_index >= 0 and col_index < len(self.current_columns):
                col = self.current_columns[col_index]
                if col.name not in self.column_data:
                    self.column_data[col.name] = []

                added_to_column = 0
                for item in new_items:
                    if item not in self.column_data[col.name]:
                        self.column_data[col.name].append(item)
                        added_to_column += 1

            self._update_counts()
            self._update_preview()
            self._save_synthesizer_state()

            # Enable train button if we have both good and bad
            if len(self.good_examples) >= 2 and len(self.bad_examples) >= 2:
                self.train_ml_btn.setEnabled(True)

            # Clear the paste text area
            self.paste_text.clear()

            QMessageBox.information(
                self,
                "Examples Added",
                f"✅ Added {len(new_items)} items to Good examples\n"
                f"📋 Added {added_to_column} items to column '{col.name}'"
            )

    def _paste_bad_examples(self):
        """Add pasted items as Bad examples."""
        text = self.paste_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "No Text", "Please paste some examples first.")
            return

        # Split by newline and clean
        items = [item.strip() for item in text.split('\n') if item.strip()]

        if not items:
            QMessageBox.warning(self, "No Items", "No valid items found in pasted text.")
            return

        # Filter out duplicates
        new_items = [item for item in items if item not in self.bad_examples]

        if not new_items:
            QMessageBox.information(self, "No New Items", "All pasted items are already in Bad examples.")
            return

        # Ask for confirmation
        reply = QMessageBox.question(
            self,
            "Add Bad Examples",
            f"Add {len(new_items)} new items to Bad examples?\n\n"
            f"First few:\n{chr(10).join(new_items[:3])}",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.bad_examples.extend(new_items)

            self._update_counts()
            self._update_preview()
            self._save_synthesizer_state()

            # Enable train button if we have both good and bad
            if len(self.good_examples) >= 2 and len(self.bad_examples) >= 2:
                self.train_ml_btn.setEnabled(True)

            # Clear the paste text area
            self.paste_text.clear()

            QMessageBox.information(
                self,
                "Examples Added",
                f"❌ Added {len(new_items)} items to Bad examples"
            )
