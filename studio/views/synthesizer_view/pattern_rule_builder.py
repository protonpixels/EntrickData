from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QLineEdit, QGroupBox, QCheckBox,
    QListWidget, QListWidgetItem, QSplitter, QTextEdit,
    QMessageBox, QDialog, QDialogButtonBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush
import re
from typing import List, Dict, Optional, Tuple


class RuleStep:
    """A single step in the extraction rule."""

    def __init__(self, step_type: str, params: Dict = None):
        self.step_type = step_type  # "find", "skip", "select", "loop"
        self.params = params or {}

    def to_dict(self) -> Dict:
        return {
            'type': self.step_type,
            'params': self.params
        }

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(data['type'], data.get('params', {}))


class PatternRuleBuilder(QWidget):
    """Visual builder for pattern/rule extraction."""

    rule_changed = Signal(dict)  # Emit when rule is built

    def __init__(self, parent=None):
        super().__init__(parent)
        self.steps = []
        self.mode = "singular"
        self._updating = False
        self._current_editing_index = -1
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Mode selection
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Singular Item", "Multiple Items"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left: Step list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("Steps:"))
        self.step_list = QListWidget()
        self.step_list.itemClicked.connect(self._on_step_selected)
        left_layout.addWidget(self.step_list)

        # Step controls
        step_controls = QHBoxLayout()
        self.add_step_btn = QPushButton("+ Add Step")
        self.add_step_btn.clicked.connect(self._add_step)
        step_controls.addWidget(self.add_step_btn)

        self.remove_step_btn = QPushButton("− Remove")
        self.remove_step_btn.clicked.connect(self._remove_step)
        step_controls.addWidget(self.remove_step_btn)

        self.move_up_btn = QPushButton("↑")
        self.move_up_btn.setMaximumWidth(30)
        self.move_up_btn.clicked.connect(self._move_step_up)
        step_controls.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton("↓")
        self.move_down_btn.setMaximumWidth(30)
        self.move_down_btn.clicked.connect(self._move_step_down)
        step_controls.addWidget(self.move_down_btn)


        step_controls.addStretch()
        left_layout.addLayout(step_controls)

        splitter.addWidget(left_widget)

        # Right: Step editor
        self.step_editor = self._create_step_editor()
        splitter.addWidget(self.step_editor)

        splitter.setSizes([250, 500])
        layout.addWidget(splitter)

        # Add initial step
        self._add_step()

    def _create_step_editor(self) -> QGroupBox:
        """Create the step editor panel."""
        group = QGroupBox("Step Settings")
        layout = QVBoxLayout(group)

        # Step type
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Step Type:"))
        self.step_type_combo = QComboBox()
        self.step_type_combo.addItems([
            "Find Text",
            "Skip Text",
            "Select From/To",
            "Skip Count",
            "Loop"
        ])
        self.step_type_combo.currentTextChanged.connect(self._on_step_type_changed)
        type_layout.addWidget(self.step_type_combo)
        type_layout.addStretch()
        layout.addLayout(type_layout)

        # Parameters area (dynamic)
        self.params_widget = QWidget()
        self.params_layout = QVBoxLayout(self.params_widget)
        self.params_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.params_widget)

        # Common params
        self._build_common_params()

        # Update for initial step type
        self._on_step_type_changed("Find Text")

        return group

    def _build_common_params(self):
        """Build common parameter controls."""
        # Search text
        text_layout = QHBoxLayout()
        text_layout.addWidget(QLabel("Search Text:"))
        self.search_text_input = QLineEdit()
        self.search_text_input.setPlaceholderText("e.g., PROVEN HEADLINE")
        self.search_text_input.textChanged.connect(self._on_params_changed)
        text_layout.addWidget(self.search_text_input)
        self.params_layout.addLayout(text_layout)

        # Direction
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Direction:"))
        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["Forward", "Backward"])
        self.direction_combo.currentTextChanged.connect(self._on_params_changed)
        dir_layout.addWidget(self.direction_combo)
        dir_layout.addStretch()
        self.params_layout.addLayout(dir_layout)

        # Case sensitivity
        self.case_check = QCheckBox("Case Sensitive")
        self.case_check.toggled.connect(self._on_params_changed)
        self.params_layout.addWidget(self.case_check)

        # Skip count (number of characters/words to skip)
        skip_layout = QHBoxLayout()
        skip_layout.addWidget(QLabel("Skip:"))
        self.skip_count_spin = QSpinBox()
        self.skip_count_spin.setRange(0, 1000)
        self.skip_count_spin.setValue(0)
        self.skip_count_spin.valueChanged.connect(self._on_params_changed)
        skip_layout.addWidget(self.skip_count_spin)

        self.skip_unit_combo = QComboBox()
        self.skip_unit_combo.addItems(["Characters", "Words", "Lines"])
        self.skip_unit_combo.currentTextChanged.connect(self._on_params_changed)
        skip_layout.addWidget(self.skip_unit_combo)
        skip_layout.addStretch()
        self.params_layout.addLayout(skip_layout)



        # Stop phrase with clearer options
        stop_layout = QHBoxLayout()
        stop_layout.addWidget(QLabel("Stop at:"))
        self.stop_text_input = QLineEdit()
        self.stop_text_input.setPlaceholderText('e.g., " (quote), newline, comma')
        self.stop_text_input.textChanged.connect(self._on_params_changed)
        stop_layout.addWidget(self.stop_text_input)

        # Quick add buttons for common stop phrases
        stop_btn_layout = QHBoxLayout()

        quote_btn = QPushButton('"')
        quote_btn.setFixedWidth(30)
        quote_btn.clicked.connect(lambda: self.stop_text_input.setText('quote'))
        stop_btn_layout.addWidget(quote_btn)

        newline_btn = QPushButton('↵')
        newline_btn.setFixedWidth(30)
        newline_btn.clicked.connect(lambda: self.stop_text_input.setText('newline'))
        stop_btn_layout.addWidget(newline_btn)

        comma_btn = QPushButton(',')
        comma_btn.setFixedWidth(30)
        comma_btn.clicked.connect(lambda: self.stop_text_input.setText('comma'))
        stop_btn_layout.addWidget(comma_btn)

        period_btn = QPushButton('.')
        period_btn.setFixedWidth(30)
        period_btn.clicked.connect(lambda: self.stop_text_input.setText('period'))
        stop_btn_layout.addWidget(period_btn)

        colon_btn = QPushButton(':')
        colon_btn.setFixedWidth(30)
        colon_btn.clicked.connect(lambda: self.stop_text_input.setText('colon'))
        stop_btn_layout.addWidget(colon_btn)

        stop_layout.addLayout(stop_btn_layout)
        stop_layout.addStretch()
        self.params_layout.addLayout(stop_layout)

        # Include stop phrase
        self.include_stop_check = QCheckBox("Include stop phrase in result")
        self.include_stop_check.toggled.connect(self._on_params_changed)
        self.params_layout.addWidget(self.include_stop_check)

        # Skip stop phrase occurrences
        skip_stop_layout = QHBoxLayout()
        skip_stop_layout.addWidget(QLabel("Skip stop phrase:"))
        self.skip_stop_spin = QSpinBox()
        self.skip_stop_spin.setRange(0, 100)
        self.skip_stop_spin.setValue(0)
        self.skip_stop_spin.valueChanged.connect(self._on_params_changed)
        skip_stop_layout.addWidget(self.skip_stop_spin)
        skip_stop_layout.addWidget(QLabel("times"))
        skip_stop_layout.addStretch()
        self.params_layout.addLayout(skip_stop_layout)

        # Loop-specific params (hidden by default)
        self.loop_params_widget = QWidget()
        loop_layout = QVBoxLayout(self.loop_params_widget)
        loop_layout.setContentsMargins(0, 0, 0, 0)

        # Item separator for multiple items
        sep_layout = QHBoxLayout()
        sep_layout.addWidget(QLabel("Item Separator:"))
        self.separator_input = QLineEdit()
        self.separator_input.setPlaceholderText("e.g., newline, comma, period")
        self.separator_input.textChanged.connect(self._on_params_changed)
        sep_layout.addWidget(self.separator_input)
        sep_layout.addStretch()
        loop_layout.addLayout(sep_layout)

        # Skip leading separators
        skip_sep_layout = QHBoxLayout()
        skip_sep_layout.addWidget(QLabel("Skip leading separators:"))
        self.skip_separator_spin = QSpinBox()
        self.skip_separator_spin.setRange(0, 100)
        self.skip_separator_spin.setValue(0)
        self.skip_separator_spin.valueChanged.connect(self._on_params_changed)
        skip_sep_layout.addWidget(self.skip_separator_spin)
        skip_sep_layout.addWidget(QLabel("times"))
        skip_sep_layout.addStretch()
        loop_layout.addLayout(skip_sep_layout)

        self.loop_params_widget.setVisible(False)
        self.params_layout.addWidget(self.loop_params_widget)

    def _on_step_type_changed(self, step_type: str):
        """Update param visibility based on step type."""
        # Show/hide relevant controls
        is_loop = step_type == "Loop"
        self.loop_params_widget.setVisible(is_loop)

        # Update placeholder texts
        if step_type == "Find Text":
            self.search_text_input.setPlaceholderText("e.g., PROVEN HEADLINE")
            self.stop_text_input.setPlaceholderText("e.g., \":\", \"\\n\", \"\\t\"")
        elif step_type == "Skip Text":
            self.search_text_input.setPlaceholderText("e.g., from Dale Carnegie")
            self.stop_text_input.setPlaceholderText("e.g., \":\", \"\\n\"")
        elif step_type == "Select From/To":
            self.search_text_input.setPlaceholderText("Start phrase (e.g., \"\"\")")
            self.stop_text_input.setPlaceholderText("End phrase (e.g., \"\"\")")
        elif step_type == "Skip Count":
            self.search_text_input.setPlaceholderText("(ignored)")
            self.stop_text_input.setPlaceholderText("(ignored)")
        elif step_type == "Loop":
            self.search_text_input.setPlaceholderText("Loop start phrase")
            self.stop_text_input.setPlaceholderText("Loop end phrase")

    def _get_current_params(self) -> Dict:
        """Get all current parameters from UI."""
        return {
            'search_text': self.search_text_input.text(),
            'direction': self.direction_combo.currentText().lower(),
            'case_sensitive': self.case_check.isChecked(),
            'skip_count': self.skip_count_spin.value(),
            'skip_unit': self.skip_unit_combo.currentText().lower(),
            'stop_text': self.stop_text_input.text(),
            'include_stop': self.include_stop_check.isChecked(),
            'skip_stop_occurrences': self.skip_stop_spin.value(),
            'separator': self.separator_input.text(),
            'skip_separators': self.skip_separator_spin.value(),
        }

    def _add_step(self):
        """Add a new step."""
        step = RuleStep("Find Text", {})
        self.steps.append(step)
        self._update_step_list()
        self.step_list.setCurrentRow(len(self.steps) - 1)
        self._on_step_selected(self.step_list.currentItem())

    def _remove_step(self):
        """Remove the current step."""
        current = self.step_list.currentRow()
        if current >= 0:
            self.steps.pop(current)
            self._update_step_list()
            if self.steps:
                self.step_list.setCurrentRow(min(current, len(self.steps) - 1))
            self.rule_changed.emit(self.get_rule())

    def _move_step_up(self):
        """Move current step up."""
        current = self.step_list.currentRow()
        if current > 0:
            self.steps[current], self.steps[current - 1] = self.steps[current - 1], self.steps[current]
            self._update_step_list()
            self.step_list.setCurrentRow(current - 1)
            self.rule_changed.emit(self.get_rule())

    def _move_step_down(self):
        """Move current step down."""
        current = self.step_list.currentRow()
        if current < len(self.steps) - 1:
            self.steps[current], self.steps[current + 1] = self.steps[current + 1], self.steps[current]
            self._update_step_list()
            self.step_list.setCurrentRow(current + 1)
            self.rule_changed.emit(self.get_rule())

    def _on_step_selected(self, item):
        """Load step into editor without losing focus."""
        if not item:
            return

        index = self.step_list.row(item)
        if index < 0 or index >= len(self.steps):
            return

        self._current_editing_index = index
        self._updating = True

        try:
            step = self.steps[index]
            params = step.params

            # Block signals during update
            self.search_text_input.blockSignals(True)
            self.stop_text_input.blockSignals(True)
            self.skip_count_spin.blockSignals(True)
            self.skip_unit_combo.blockSignals(True)
            self.include_stop_check.blockSignals(True)
            self.skip_stop_spin.blockSignals(True)

            # Update UI
            self.step_type_combo.setCurrentText(step.step_type)
            self.search_text_input.setText(params.get('search_text', ''))
            self.direction_combo.setCurrentText(params.get('direction', 'forward').title())
            self.case_check.setChecked(params.get('case_sensitive', False))
            self.skip_count_spin.setValue(params.get('skip_count', 0))
            self.skip_unit_combo.setCurrentText(params.get('skip_unit', 'characters').title())
            self.stop_text_input.setText(params.get('stop_text', ''))
            self.include_stop_check.setChecked(params.get('include_stop', False))
            self.skip_stop_spin.setValue(params.get('skip_stop_occurrences', 0))

            # Unblock signals
            self.search_text_input.blockSignals(False)
            self.stop_text_input.blockSignals(False)
            self.skip_count_spin.blockSignals(False)
            self.skip_unit_combo.blockSignals(False)
            self.include_stop_check.blockSignals(False)
            self.skip_stop_spin.blockSignals(False)

            # Update step type visibility
            self._on_step_type_changed(step.step_type)
        finally:
            self._updating = False

    def _on_params_changed(self):
        """Update the current step with new parameters."""
        if self._updating:
            return

        if self._current_editing_index < 0 or self._current_editing_index >= len(self.steps):
            return

        params = self._get_current_params()
        step_type = self.step_type_combo.currentText()

        # Update the step
        self.steps[self._current_editing_index] = RuleStep(step_type, params)
        self._update_step_display()

        # Keep the selection
        self.step_list.setCurrentRow(self._current_editing_index)

        self.rule_changed.emit(self.get_rule())

    def _update_step_list(self):
        """Update the step list widget."""
        self.step_list.clear()
        for i, step in enumerate(self.steps):
            display = f"{i + 1}. {step.step_type}"
            if step.params.get('search_text'):
                display += f": {step.params['search_text'][:20]}"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, i)
            self.step_list.addItem(item)

    def _update_step_display(self):
        """Update the display of the current step."""
        self._update_step_list()

    def _on_mode_changed(self, mode: str):
        """Handle mode change."""
        self.mode = "multiple" if "Multiple" in mode else "singular"
        # Add loop step for multiple items if not present
        if self.mode == "multiple":
            has_loop = any(s.step_type == "Loop" for s in self.steps)
            if not has_loop:
                self._add_step()
                # Set the new step to Loop
                self.step_type_combo.setCurrentText("Loop")
        self.rule_changed.emit(self.get_rule())

    def get_rule(self) -> Dict:
        """Get the complete rule as a dictionary."""
        return {
            'mode': self.mode,
            'steps': [step.to_dict() for step in self.steps]
        }

    def _test_rule(self):
        """Test the rule on sample text."""
        # This would open a dialog to input sample text and show results
        QMessageBox.information(
            self,
            "Test Rule",
            "This would test the rule on sample text.\n\n"
            "The extracted items would be displayed here."
        )

    def get_regex_pattern(self) -> Optional[str]:
        """Convert the rule to a regex pattern for the extraction pipeline."""
        if not self.steps:
            return None

        # Find the first "Find Text" step
        search_text = None
        stop_text = None
        skip_count = 0
        skip_unit = 'characters'
        include_stop = False
        skip_stop = 0
        direction = 'forward'

        for step in self.steps:
            if step.step_type == "Find Text":
                params = step.params
                search_text = params.get('search_text', '')
                stop_text = params.get('stop_text', '')
                skip_count = params.get('skip_count', 0)
                skip_unit = params.get('skip_unit', 'characters')
                include_stop = params.get('include_stop', False)
                skip_stop = params.get('skip_stop_occurrences', 0)
                direction = params.get('direction', 'forward')
                break

        if not search_text:
            return None

        print(f"🔧 Building regex with: search='{search_text}', stop='{stop_text}', skip={skip_count} {skip_unit}")

        # Build the pattern
        pattern_parts = []

        # 1. Escape the search text
        pattern_parts.append(re.escape(search_text))

        # 2. Handle skip count (skip BEFORE capturing)
        if skip_count > 0:
            if skip_unit == 'characters':
                pattern_parts.append(r'.{' + str(skip_count) + r'}')
            elif skip_unit == 'words':
                pattern_parts.append(r'(?:\s*\S+\s*){' + str(skip_count) + r'}')
            elif skip_unit == 'lines':
                pattern_parts.append(r'(?:[^\n]*\n){' + str(skip_count) + r'}')

        # 3. Handle stop text
        if stop_text:
            # Map common stop text to regex
            stop_map = {
                'newline': r'\n',
                'tab': r'\t',
                'quote': r'"',  # This is the default
                'comma': r',',
                'period': r'\.',
                'space': r'\s',
                'colon': r':',
                'semicolon': r';',
            }

            # Special handling for quotes - match both straight and curly
            if stop_text.lower() == 'quote':
                # Match until we hit a quote (straight or curly)
                # This handles: " (straight), “ (left curly), ” (right curly)
                if include_stop:
                    # Include the quote in the match
                    pattern_parts.append(r'([^"\u201c\u201d]*?["\u201c\u201d])')
                else:
                    # Exclude the quote from the match
                    pattern_parts.append(r'([^"\u201c\u201d]*?)')
            else:
                stop_pattern = stop_map.get(stop_text.lower(), re.escape(stop_text))
                if include_stop:
                    pattern_parts.append(f'([^{stop_pattern}]*{stop_pattern})')
                else:
                    pattern_parts.append(f'([^{stop_pattern}]*?)')

            # 4. Skip stop occurrences after the capture
            if skip_stop > 0:
                if stop_text.lower() == 'quote':
                    pattern_parts.append(r'["\u201c\u201d]' + f'{{{skip_stop}}}')
                else:
                    stop_pattern = stop_map.get(stop_text.lower(), re.escape(stop_text))
                    pattern_parts.append(f'(?:{stop_pattern}){{{skip_stop}}}')

        else:
            # No stop text - capture everything until newline or end
            pattern_parts.append(r'([^\n]*?)')

        full_pattern = ''.join(pattern_parts)
        print(f"🔧 Full regex: {full_pattern}")
        return full_pattern

class PatternTestDialog(QDialog):
    """Dialog for testing pattern rules."""

    def __init__(self, rule: Dict, parent=None):
        super().__init__(parent)
        self.rule = rule
        self.setWindowTitle("🧪 Test Pattern Rule")
        self.setMinimumSize(600, 400)

        layout = QVBoxLayout(self)

        # Sample text input
        layout.addWidget(QLabel("Sample Text:"))
        self.sample_input = QTextEdit()
        self.sample_input.setPlaceholderText("Paste your sample text here...")
        layout.addWidget(self.sample_input)

        # Results
        layout.addWidget(QLabel("Extracted Items:"))
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(2)
        self.results_table.setHorizontalHeaderLabels(["#", "Extracted Text"])
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.results_table)

        # Buttons
        btn_layout = QHBoxLayout()
        self.test_btn = QPushButton("🔍 Test")
        self.test_btn.clicked.connect(self._test)
        btn_layout.addWidget(self.test_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

    def _test(self):
        """Run the test."""
        sample = self.sample_input.toPlainText()
        if not sample:
            return

        # Extract using the rule
        # This would use the compiled rule to extract items
        items = []
        # Simple extraction for demo
        lines = sample.split('\n')
        for i, line in enumerate(lines):
            if line.strip():
                items.append(line.strip())

        self.results_table.setRowCount(len(items))
        for i, item in enumerate(items):
            self.results_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.results_table.setItem(i, 1, QTableWidgetItem(item[:100]))