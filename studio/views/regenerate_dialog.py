# studio/views/regenerate_dialog.py
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QDoubleSpinBox, QComboBox, QGroupBox,
    QDialogButtonBox, QCheckBox, QTabWidget, QWidget
)
from PySide6.QtCore import Qt, Signal
from .table_generator import ResponseType


class RegenerateSettingsDialog(QDialog):
    """Dialog for tweaking settings before regeneration."""

    def __init__(self, current_settings: dict, column_index: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"⚙️ Regenerate Column {column_index + 1}")
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout(self)

        # Tab widget for different setting categories
        tabs = QTabWidget()

        # === Basic Settings Tab ===
        basic_tab = QWidget()
        basic_layout = QVBoxLayout(basic_tab)

        # Creativity
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Creativity:"))
        self.creativity_spin = QDoubleSpinBox()
        self.creativity_spin.setRange(0.0, 1.0)
        self.creativity_spin.setSingleStep(0.1)
        self.creativity_spin.setValue(current_settings.get('creativity', 0.5))
        self.creativity_spin.setToolTip("0 = Word-for-word, 1 = Very creative")
        h1.addWidget(self.creativity_spin)
        h1.addStretch()
        basic_layout.addLayout(h1)

        # Max Tokens
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Max Tokens per Item:"))
        self.tokens_spin = QSpinBox()
        self.tokens_spin.setRange(50, 4096)
        self.tokens_spin.setValue(current_settings.get('max_tokens', 200))
        h2.addWidget(self.tokens_spin)
        h2.addStretch()
        basic_layout.addLayout(h2)

        # Response Type
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("Response Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Sentence", "Paragraph", "Article"])
        current_type = current_settings.get('response_type', 'Sentence')
        self.type_combo.setCurrentText(current_type)
        self.type_combo.currentTextChanged.connect(self.on_type_changed)
        h3.addWidget(self.type_combo)
        h3.addStretch()
        basic_layout.addLayout(h3)

        # Response Size
        self.size_widget = QWidget()
        size_layout = QHBoxLayout(self.size_widget)
        size_layout.setContentsMargins(0, 0, 0, 0)

        size_layout.addWidget(QLabel("Min:"))
        self.size_min_spin = QSpinBox()
        self.size_min_spin.setRange(1, 20)
        self.size_min_spin.setValue(current_settings.get('min_size', 2))
        size_layout.addWidget(self.size_min_spin)

        size_layout.addWidget(QLabel("Max:"))
        self.size_max_spin = QSpinBox()
        self.size_max_spin.setRange(1, 20)
        self.size_max_spin.setValue(current_settings.get('max_size', 6))
        size_layout.addWidget(self.size_max_spin)

        self.size_unit_label = QLabel("words")
        size_layout.addWidget(self.size_unit_label)
        size_layout.addStretch()

        basic_layout.addWidget(self.size_widget)

        tabs.addTab(basic_tab, "Basic")

        # === Advanced Settings Tab ===
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)

        # Temperature
        h4 = QHBoxLayout()
        h4.addWidget(QLabel("Temperature:"))
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(current_settings.get('temperature', 0.7))
        h4.addWidget(self.temp_spin)
        h4.addStretch()
        advanced_layout.addLayout(h4)

        # Top P
        h5 = QHBoxLayout()
        h5.addWidget(QLabel("Top P:"))
        self.topp_spin = QDoubleSpinBox()
        self.topp_spin.setRange(0.0, 1.0)
        self.topp_spin.setSingleStep(0.05)
        self.topp_spin.setValue(current_settings.get('top_p', 0.9))
        h5.addWidget(self.topp_spin)
        h5.addStretch()
        advanced_layout.addLayout(h5)

        # Chunk Strategy
        h6 = QHBoxLayout()
        h6.addWidget(QLabel("Chunk Strategy:"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(["Exact Match", "Semantic Match", "Max Semantic"])
        self.strategy_combo.setCurrentText(current_settings.get('strategy', 'Exact Match'))
        self.strategy_combo.currentTextChanged.connect(self.on_strategy_changed)
        h6.addWidget(self.strategy_combo)
        h6.addStretch()
        advanced_layout.addLayout(h6)

        # Strategy parameters
        self.param_widget = QWidget()
        param_layout = QHBoxLayout(self.param_widget)
        param_layout.setContentsMargins(0, 0, 0, 0)

        param_layout.addWidget(QLabel("Top K:"))
        self.top_k_spin = QSpinBox()
        self.top_k_spin.setRange(1, 100)
        self.top_k_spin.setValue(current_settings.get('top_k', 10))
        param_layout.addWidget(self.top_k_spin)

        param_layout.addWidget(QLabel("Prev:"))
        self.prev_spin = QSpinBox()
        self.prev_spin.setRange(0, 10)
        self.prev_spin.setValue(current_settings.get('prev_sentences', 1))
        param_layout.addWidget(self.prev_spin)

        param_layout.addWidget(QLabel("Follow:"))
        self.follow_spin = QSpinBox()
        self.follow_spin.setRange(0, 10)
        self.follow_spin.setValue(current_settings.get('follow_sentences', 1))
        param_layout.addWidget(self.follow_spin)

        param_layout.addWidget(QLabel("Order:"))
        self.order_combo = QComboBox()
        self.order_combo.addItems(["Relevancy", "A-Z", "Z-A"])
        self.order_combo.setCurrentText(current_settings.get('order', 'Relevancy'))
        param_layout.addWidget(self.order_combo)

        self.max_tokens_label = QLabel("Max Tokens:")
        param_layout.addWidget(self.max_tokens_label)
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(100, 4096)
        self.max_tokens_spin.setValue(current_settings.get('max_chunk_tokens', 500))
        self.max_tokens_spin.setVisible(False)
        param_layout.addWidget(self.max_tokens_spin)

        param_layout.addStretch()
        advanced_layout.addWidget(self.param_widget)

        # Only regenerate selected
        self.selected_only_check = QCheckBox("Only regenerate selected items")
        self.selected_only_check.setChecked(True)
        advanced_layout.addWidget(self.selected_only_check)

        tabs.addTab(advanced_tab, "Advanced")

        layout.addWidget(tabs)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self.setLayout(layout)

        # Initialize visibility
        self.on_type_changed(self.type_combo.currentText())
        self.on_strategy_changed(self.strategy_combo.currentText())

    def on_type_changed(self, type_text):
        """Update response size labels."""
        if type_text == "Sentence":
            self.size_unit_label.setText("words")
            self.size_min_spin.setRange(1, 15)
            self.size_max_spin.setRange(1, 15)
        elif type_text == "Paragraph":
            self.size_unit_label.setText("sentences")
            self.size_min_spin.setRange(1, 10)
            self.size_max_spin.setRange(1, 10)
        else:  # Article
            self.size_unit_label.setText("paragraphs")
            self.size_min_spin.setRange(1, 6)
            self.size_max_spin.setRange(1, 6)

    def on_strategy_changed(self, strategy_text):
        """Update parameter visibility."""
        is_max_semantic = strategy_text == "Max Semantic"
        self.top_k_spin.setVisible(not is_max_semantic)
        self.prev_spin.setVisible(not is_max_semantic)
        self.follow_spin.setVisible(not is_max_semantic)
        self.order_combo.setVisible(not is_max_semantic)
        self.max_tokens_label.setVisible(is_max_semantic)
        self.max_tokens_spin.setVisible(is_max_semantic)

    def get_settings(self) -> dict:
        """Get all settings from the dialog."""
        return {
            'creativity': self.creativity_spin.value(),
            'max_tokens': self.tokens_spin.value(),
            'response_type': self.type_combo.currentText(),
            'min_size': self.size_min_spin.value(),
            'max_size': self.size_max_spin.value(),
            'temperature': self.temp_spin.value(),
            'top_p': self.topp_spin.value(),
            'strategy': self.strategy_combo.currentText(),
            'top_k': self.top_k_spin.value(),
            'prev_sentences': self.prev_spin.value(),
            'follow_sentences': self.follow_spin.value(),
            'order': self.order_combo.currentText(),
            'max_chunk_tokens': self.max_tokens_spin.value(),
            'selected_only': self.selected_only_check.isChecked()
        }