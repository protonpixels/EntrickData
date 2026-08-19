from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QListWidget, QListWidgetItem,
    QSlider, QGroupBox, QCheckBox, QSpinBox, QDoubleSpinBox,
    QComboBox, QProgressBar, QSplitter, QTabWidget,
    QMessageBox, QFileDialog, QDialog, QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor, QBrush
import re
from typing import List, Dict, Optional

from studio.core.extraction_pipeline import ExtractionPipeline
from studio.core.database import StudioDatabase
from .pattern_rule_builder import PatternRuleBuilder, PatternTestDialog


class MLTrainingThread(QThread):
    """Thread for training ML model in background."""
    progress = Signal(int, str)
    complete = Signal(dict)
    error = Signal(str)

    def __init__(self, pipeline, seed_items, full_text):
        super().__init__()
        self.pipeline = pipeline
        self.seed_items = seed_items
        self.full_text = full_text

    def run(self):
        try:
            self.progress.emit(30, "Training ML model...")
            success, result = self.pipeline.train_ml_model(self.seed_items, self.full_text)
            if success:
                self.progress.emit(100, "Training complete!")
                self.complete.emit(result)
            else:
                self.error.emit(result.get("error", "Unknown training error"))
        except Exception as e:
            self.error.emit(str(e))


class GradualExtractionTab(QWidget):
    """Tab for gradual extraction with Pattern → ML → AI pipeline."""

    settings_changed = Signal(dict)  # Emit when settings change

    def __init__(self, db: StudioDatabase, project_id: int, parent=None):
        super().__init__(parent)
        self.db = db
        self.project_id = project_id
        self.pipeline = ExtractionPipeline(db, project_id, "temp_column")
        self.seed_items = []
        self.candidates = []
        self.ml_model_id = None
        self.ml_trained = False
        self.column_def = None
        self.full_text = ""
        self.current_rule = {}

        self.setup_ui()

    def setup_ui(self):
        """Build the UI with collapsible sections."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # --- Extraction Method Selection ---
        method_group = QGroupBox("Extraction Method")
        method_group.setObjectName("method_group")
        method_layout = QHBoxLayout(method_group)

        self.method_combo = QComboBox()
        self.method_combo.addItems(["Pattern/Rule Only", "ML-Assisted", "AI Generation", "Hybrid"])
        self.method_combo.setToolTip("Select the primary extraction method")
        self.method_combo.currentTextChanged.connect(self._on_method_changed)
        method_layout.addWidget(QLabel("Method:"))
        method_layout.addWidget(self.method_combo)
        method_layout.addStretch()

        layout.addWidget(method_group)

        # --- STAGE 1: Seed Extraction ---
        seed_group = QGroupBox("🌱 Stage 1: Seed Extraction (Pattern/Rule)")
        seed_group.setObjectName("seed_group")
        seed_layout = QVBoxLayout(seed_group)

        # Rule Builder (replaces pattern input)
        self.rule_builder = PatternRuleBuilder()
        self.rule_builder.rule_changed.connect(self._on_rule_changed)
        seed_layout.addWidget(self.rule_builder)

        # Seed controls
        seed_controls = QHBoxLayout()
        self.extract_seed_btn = QPushButton("🔍 Extract Seeds")
        self.extract_seed_btn.clicked.connect(self._extract_seeds)
        seed_controls.addWidget(self.extract_seed_btn)

        self.test_rule_btn = QPushButton("🧪 Test Rule")
        self.test_rule_btn.clicked.connect(self._test_rule)
        seed_controls.addWidget(self.test_rule_btn)

        seed_controls.addStretch()
        seed_layout.addLayout(seed_controls)

        # Seed preview
        self.seed_preview_list = QListWidget()
        self.seed_preview_list.setMaximumHeight(150)
        self.seed_preview_list.setSelectionMode(QListWidget.MultiSelection)
        seed_layout.addWidget(QLabel("Found Seeds:"))
        seed_layout.addWidget(self.seed_preview_list)

        # Seed count and controls
        seed_info_layout = QHBoxLayout()
        self.seed_count_label = QLabel("0 seeds found")
        seed_info_layout.addWidget(self.seed_count_label)
        seed_info_layout.addStretch()

        self.use_seeds_check = QCheckBox("Use seeds for ML training")
        self.use_seeds_check.setChecked(True)
        seed_info_layout.addWidget(self.use_seeds_check)

        self.clear_seeds_btn = QPushButton("Clear Seeds")
        self.clear_seeds_btn.clicked.connect(self._clear_seeds)
        seed_info_layout.addWidget(self.clear_seeds_btn)

        seed_layout.addLayout(seed_info_layout)
        layout.addWidget(seed_group)

        # --- STAGE 2: ML Training ---
        ml_group = QGroupBox("🧠 Stage 2: ML-Assisted Detection")
        ml_group.setObjectName("ml_group")
        ml_layout = QVBoxLayout(ml_group)

        # Training controls
        train_layout = QHBoxLayout()
        self.train_ml_btn = QPushButton("🎯 Train ML Model")
        self.train_ml_btn.clicked.connect(self._train_ml)
        self.train_ml_btn.setEnabled(False)
        train_layout.addWidget(self.train_ml_btn)

        self.ml_status_label = QLabel("Not trained")
        self.ml_status_label.setStyleSheet("color: #888;")
        train_layout.addWidget(self.ml_status_label)

        train_layout.addStretch()

        self.ml_accuracy_label = QLabel("")
        train_layout.addWidget(self.ml_accuracy_label)

        ml_layout.addLayout(train_layout)

        # Training progress
        self.ml_progress = QProgressBar()
        self.ml_progress.setMaximumHeight(16)
        self.ml_progress.setVisible(False)
        ml_layout.addWidget(self.ml_progress)

        # Confidence threshold
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("Confidence Threshold:"))
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(50, 100)
        self.threshold_slider.setValue(85)
        self.threshold_slider.setTickInterval(10)
        self.threshold_slider.setTickPosition(QSlider.TicksBelow)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        threshold_layout.addWidget(self.threshold_slider)

        self.threshold_label = QLabel("0.85")
        self.threshold_label.setMinimumWidth(40)
        threshold_layout.addWidget(self.threshold_label)

        ml_layout.addLayout(threshold_layout)

        # Scan button
        scan_layout = QHBoxLayout()
        self.scan_ml_btn = QPushButton("🔎 Scan with ML")
        self.scan_ml_btn.clicked.connect(self._scan_with_ml)
        self.scan_ml_btn.setEnabled(False)
        scan_layout.addWidget(self.scan_ml_btn)

        self.candidate_count_label = QLabel("Candidates: 0")
        scan_layout.addWidget(self.candidate_count_label)
        scan_layout.addStretch()

        ml_layout.addLayout(scan_layout)

        # Candidate preview
        self.candidate_list = QListWidget()
        self.candidate_list.setMaximumHeight(150)
        self.candidate_list.setSelectionMode(QListWidget.MultiSelection)
        self.candidate_list.itemChanged.connect(self._on_candidate_toggled)
        ml_layout.addWidget(QLabel("ML Candidates:"))
        ml_layout.addWidget(self.candidate_list)

        # Candidate controls
        candidate_controls = QHBoxLayout()
        self.select_all_candidates_btn = QPushButton("Select All")
        self.select_all_candidates_btn.clicked.connect(lambda: self._toggle_candidates(True))
        candidate_controls.addWidget(self.select_all_candidates_btn)

        self.deselect_all_candidates_btn = QPushButton("Deselect All")
        self.deselect_all_candidates_btn.clicked.connect(lambda: self._toggle_candidates(False))
        candidate_controls.addWidget(self.deselect_all_candidates_btn)

        candidate_controls.addStretch()

        self.add_candidates_btn = QPushButton("✅ Add Selected to Column")
        self.add_candidates_btn.clicked.connect(self._add_selected_candidates)
        self.add_candidates_btn.setEnabled(False)
        candidate_controls.addWidget(self.add_candidates_btn)

        ml_layout.addLayout(candidate_controls)
        layout.addWidget(ml_group)

        # --- STAGE 3: AI Enrichment ---
        ai_group = QGroupBox("✨ Stage 3: AI Enrichment (Optional)")
        ai_group.setObjectName("ai_group")
        ai_layout = QVBoxLayout(ai_group)

        # AI Settings
        ai_settings_layout = QHBoxLayout()

        # Prompt template
        prompt_layout = QVBoxLayout()
        prompt_layout.addWidget(QLabel("Prompt Template:"))
        self.ai_prompt_input = QTextEdit()
        self.ai_prompt_input.setPlaceholderText("Summarize {{item}} in one sentence...")
        self.ai_prompt_input.setMaximumHeight(60)
        prompt_layout.addWidget(self.ai_prompt_input)

        # AI Parameters
        params_layout = QHBoxLayout()

        # Temperature
        temp_layout = QVBoxLayout()
        temp_layout.addWidget(QLabel("Temperature:"))
        self.ai_temp_spin = QDoubleSpinBox()
        self.ai_temp_spin.setRange(0.0, 1.0)
        self.ai_temp_spin.setSingleStep(0.1)
        self.ai_temp_spin.setValue(0.7)
        temp_layout.addWidget(self.ai_temp_spin)
        params_layout.addLayout(temp_layout)

        # Top P
        topp_layout = QVBoxLayout()
        topp_layout.addWidget(QLabel("Top P:"))
        self.ai_topp_spin = QDoubleSpinBox()
        self.ai_topp_spin.setRange(0.0, 1.0)
        self.ai_topp_spin.setSingleStep(0.05)
        self.ai_topp_spin.setValue(0.9)
        topp_layout.addWidget(self.ai_topp_spin)
        params_layout.addLayout(topp_layout)

        # Max Tokens
        tokens_layout = QVBoxLayout()
        tokens_layout.addWidget(QLabel("Max Tokens:"))
        self.ai_tokens_spin = QSpinBox()
        self.ai_tokens_spin.setRange(50, 2000)
        self.ai_tokens_spin.setValue(200)
        tokens_layout.addWidget(self.ai_tokens_spin)
        params_layout.addLayout(tokens_layout)

        # Response Format
        format_layout = QVBoxLayout()
        format_layout.addWidget(QLabel("Response Format:"))
        self.ai_format_combo = QComboBox()
        self.ai_format_combo.addItems(["Sentence", "Paragraph", "Article"])
        format_layout.addWidget(self.ai_format_combo)
        params_layout.addLayout(format_layout)

        ai_settings_layout.addLayout(prompt_layout)
        ai_settings_layout.addLayout(params_layout)

        ai_layout.addLayout(ai_settings_layout)

        self.ai_enrich_btn = QPushButton("🚀 Run AI Enrichment")
        self.ai_enrich_btn.clicked.connect(self._run_ai_enrichment)
        self.ai_enrich_btn.setEnabled(False)
        ai_layout.addWidget(self.ai_enrich_btn)

        layout.addWidget(ai_group)

        # Initialize visibility
        self._on_method_changed(self.method_combo.currentText())

    def _on_rule_changed(self, rule: dict):
        """Handle rule changes from the rule builder."""
        self.current_rule = rule
        # Emit settings changed
        self.settings_changed.emit(self.get_settings())

    def _test_rule(self):
        """Test the current rule on sample text."""
        rule = self.rule_builder.get_rule() if hasattr(self.rule_builder, 'get_rule') else {}
        dialog = PatternTestDialog(rule, self)
        dialog.exec_()

    def _on_method_changed(self, method: str):
        """Update UI based on selected method."""
        is_pattern = method in ["Pattern/Rule Only", "Hybrid"]
        is_ml = method in ["ML-Assisted", "Hybrid"]
        is_ai = method in ["AI Generation", "Hybrid"]

        # Find group boxes by object name
        seed_group = self.findChild(QGroupBox, "seed_group")
        ml_group = self.findChild(QGroupBox, "ml_group")
        ai_group = self.findChild(QGroupBox, "ai_group")

        if seed_group:
            seed_group.setVisible(is_pattern)
        if ml_group:
            ml_group.setVisible(is_ml)
        if ai_group:
            ai_group.setVisible(is_ai)

    def set_column_definition(self, column_def):
        """Set the column definition and load settings."""
        self.column_def = column_def
        if column_def:
            # Load settings into rule builder if needed
            if column_def.seed_pattern and hasattr(self.rule_builder, 'set_pattern'):
                self.rule_builder.set_pattern(column_def.seed_pattern)
            self.threshold_slider.setValue(int(column_def.confidence_threshold * 100))
            self.use_seeds_check.setChecked(column_def.use_ml_assist)
            if column_def.extracted_seed_items:
                self._display_seeds(column_def.extracted_seed_items)

    def get_settings(self) -> dict:
        """Get current settings for the column definition."""
        return {
            'seed_pattern': self.rule_builder.get_regex_pattern() if hasattr(self.rule_builder,
                                                                             'get_regex_pattern') else None,
            'rule': self.current_rule,
            'extraction_method': self.method_combo.currentText(),
            'confidence_threshold': self.threshold_slider.value() / 100.0,
            'use_ml_assist': self.use_seeds_check.isChecked(),
            'extracted_seed_items': self.seed_items,
            'ml_model_id': self.ml_model_id,
            'ml_trained': self.ml_trained,
            'ai_prompt': self.ai_prompt_input.toPlainText(),
            'ai_temperature': self.ai_temp_spin.value(),
            'ai_top_p': self.ai_topp_spin.value(),
            'ai_max_tokens': self.ai_tokens_spin.value(),
            'ai_format': self.ai_format_combo.currentText(),
        }

    def _get_selected_projects_text(self) -> str:
        """Get text from all selected projects using proper extraction."""
        print("\n" + "=" * 60)
        print("📚 FETCHING PROJECT TEXT")
        print("=" * 60)

        if not self.db:
            print("❌ No database connection")
            return ""

        # Try to get selected projects from various possible parent objects
        selected_projects = []

        # Method 1: Check if parent is DataChatView
        parent = self.parent()
        while parent:
            if hasattr(parent, 'selected_projects'):
                selected_projects = parent.selected_projects
                print(f"✅ Found selected_projects in parent: {len(selected_projects)} projects")
                break
            parent = parent.parent()

        # Method 2: Check if parent_app exists
        if not selected_projects and hasattr(self, 'parent_app'):
            if hasattr(self.parent_app, 'selected_projects'):
                selected_projects = self.parent_app.selected_projects
                print(f"✅ Found selected_projects in parent_app: {len(selected_projects)} projects")

        # Method 3: Try main window
        if not selected_projects:
            main_window = self._find_main_window()
            if main_window and hasattr(main_window, 'selected_projects'):
                selected_projects = main_window.selected_projects
                print(f"✅ Found selected_projects in main_window: {len(selected_projects)} projects")

        if not selected_projects:
            print("⚠️ No selected projects found, using current project")
            text = self.db.get_project_text_pool(self.project_id)
            print(f"📄 Current project text: {len(text)} characters")
            return text

        all_text = []
        for project_id in selected_projects:
            print(f"📖 Fetching project {project_id}...")
            text = self.db.get_project_text_pool(project_id)
            if text:
                print(f"   ✅ Got {len(text)} characters")
                all_text.append(text)
            else:
                print(f"   ⚠️ No text found")

        combined = '\n\n'.join(all_text)
        print(f"📄 Combined text: {len(combined)} characters")
        return combined

    def _find_main_window(self):
        """Find the main window by traversing parent hierarchy."""
        parent = self.parent()
        while parent:
            # Check if this is the main window (has tab_widget or is MainWindow)
            if hasattr(parent, 'tab_widget') or parent.__class__.__name__ == 'MainWindow':
                return parent
            parent = parent.parent()
        return None

    def _extract_seeds(self):
        """Extract seed items using the pattern rule."""
        print("\n" + "=" * 60)
        print("🔍 EXTRACTING SEEDS")
        print("=" * 60)

        # Get the regex pattern from the rule builder
        if not hasattr(self.rule_builder, 'get_regex_pattern'):
            QMessageBox.warning(self, "Error", "Rule builder not properly initialized.")
            return

        pattern = self.rule_builder.get_regex_pattern()
        print(f"📝 Pattern: {pattern}")

        if not pattern:
            QMessageBox.warning(self, "Missing Pattern", "Please build a rule first.")
            return

        # Get project text from ALL selected projects
        self.full_text = self._get_selected_projects_text()
        print(f"📄 Text length: {len(self.full_text)} characters")
        print(f"📄 First 500 chars: {self.full_text[:500]}...")

        if not self.full_text:
            QMessageBox.warning(
                self,
                "No Text",
                "No text content found in selected projects. Please ensure you have selected projects and they contain text data."
            )
            return

        # Extract seeds
        self.pipeline.column_name = self.column_def.name if self.column_def else "temp"
        self.seed_items = self.pipeline.extract_seed_items(self.full_text, pattern)

        print(f"✅ Found {len(self.seed_items)} seeds")
        if self.seed_items:
            print(f"   First 3: {self.seed_items[:3]}")

        if not self.seed_items:
            QMessageBox.information(self, "No Matches", "No seeds found with this pattern.")
            self.seed_preview_list.clear()
            self.seed_count_label.setText("0 seeds found")
            self.train_ml_btn.setEnabled(False)
            return

        self._display_seeds(self.seed_items)
        self.train_ml_btn.setEnabled(True)
        self.scan_ml_btn.setEnabled(False)

        QMessageBox.information(
            self,
            "Seeds Extracted",
            f"Found {len(self.seed_items)} seed items."
        )
    def _display_seeds(self, seeds: List[str]):
        """Display seed items in the list."""
        self.seed_preview_list.clear()
        for seed in seeds:
            item = QListWidgetItem(seed)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.seed_preview_list.addItem(item)
        self.seed_count_label.setText(f"{len(seeds)} seeds found")

    def _clear_seeds(self):
        """Clear all seed items."""
        self.seed_preview_list.clear()
        self.seed_items = []
        self.seed_count_label.setText("0 seeds found")
        self.train_ml_btn.setEnabled(False)

    def _train_ml(self):
        """Train ML model on seed items."""
        if not self.seed_items:
            QMessageBox.warning(self, "No Seeds", "Extract seeds first.")
            return

        if len(self.seed_items) < 5:
            reply = QMessageBox.question(
                self,
                "Few Seeds",
                f"Only {len(self.seed_items)} seeds found. Training with few examples may not work well. Continue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        # Show progress
        self.ml_progress.setVisible(True)
        self.ml_progress.setValue(0)
        self.ml_status_label.setText("Training...")
        self.ml_status_label.setStyleSheet("color: #FF9800;")
        self.train_ml_btn.setEnabled(False)

        # Run training in thread
        self.ml_thread = MLTrainingThread(self.pipeline, self.seed_items, self.full_text)
        self.ml_thread.progress.connect(self._on_ml_progress)
        self.ml_thread.complete.connect(self._on_ml_complete)
        self.ml_thread.error.connect(self._on_ml_error)
        self.ml_thread.start()

    def _on_ml_progress(self, value: int, message: str):
        """Update ML training progress."""
        self.ml_progress.setValue(value)
        self.ml_status_label.setText(message)

    def _on_ml_complete(self, result: dict):
        """Handle ML training complete."""
        self.ml_trained = True
        self.ml_model_id = result.get('model_id')
        self.ml_progress.setValue(100)
        self.ml_status_label.setText(f"Trained on {result['training_samples']} examples")
        self.ml_status_label.setStyleSheet("color: #4CAF50;")
        self.ml_accuracy_label.setText(f"Accuracy: {result['accuracy']:.2%}")
        self.scan_ml_btn.setEnabled(True)
        self.train_ml_btn.setEnabled(True)

        QMessageBox.information(
            self,
            "ML Training Complete",
            f"Model trained on {result['training_samples']} samples.\n"
            f"Accuracy: {result['accuracy']:.2%}"
        )

        # Emit settings changed
        self.settings_changed.emit(self.get_settings())

    def _on_ml_error(self, error: str):
        """Handle ML training error."""
        self.ml_status_label.setText(f"Error: {error}")
        self.ml_status_label.setStyleSheet("color: #f44336;")
        self.train_ml_btn.setEnabled(True)
        QMessageBox.critical(self, "Training Error", f"Failed to train ML model:\n{error}")

    def _on_threshold_changed(self):
        """Update threshold label."""
        value = self.threshold_slider.value() / 100.0
        self.threshold_label.setText(f"{value:.2f}")

    def _scan_with_ml(self):
        """Scan project with trained ML model."""
        if not self.ml_trained:
            QMessageBox.warning(self, "Not Trained", "Train the ML model first.")
            return

        if not self.ml_model_id:
            QMessageBox.warning(self, "No Model", "No ML model found.")
            return

        # Load model
        success = self.pipeline.load_ml_model(self.ml_model_id)
        if not success:
            QMessageBox.critical(self, "Error", "Failed to load ML model.")
            return

        # Run scan
        threshold = self.threshold_slider.value() / 100.0
        self.candidates = self.pipeline.scan_with_ml(threshold)

        if not self.candidates:
            QMessageBox.information(self, "No Candidates", "No candidates found above threshold.")
            self.candidate_list.clear()
            self.candidate_count_label.setText("Candidates: 0")
            return

        # Display candidates with confidence
        self.candidate_list.clear()
        for candidate in self.candidates:
            text = candidate['text']
            conf = candidate['confidence']
            display = f"[{conf:.2f}] {text[:80]}..." if len(text) > 80 else f"[{conf:.2f}] {text}"

            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, candidate)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)

            # Color by confidence
            if conf >= 0.9:
                item.setBackground(QBrush(QColor(200, 255, 200)))  # Green
            elif conf >= 0.7:
                item.setBackground(QBrush(QColor(255, 255, 200)))  # Yellow
            else:
                item.setBackground(QBrush(QColor(255, 200, 200)))  # Red

            self.candidate_list.addItem(item)

        self.candidate_count_label.setText(f"Candidates: {len(self.candidates)}")
        self.add_candidates_btn.setEnabled(True)

    def _on_candidate_toggled(self, item):
        """Update add button based on selected candidates."""
        checked = 0
        for i in range(self.candidate_list.count()):
            if self.candidate_list.item(i).checkState() == Qt.Checked:
                checked += 1
        self.add_candidates_btn.setEnabled(checked > 0)

    def _toggle_candidates(self, checked: bool):
        """Select or deselect all candidates."""
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.candidate_list.count()):
            self.candidate_list.item(i).setCheckState(state)

    def _add_selected_candidates(self):
        """Add selected candidates to the column."""
        selected = []
        for i in range(self.candidate_list.count()):
            item = self.candidate_list.item(i)
            if item.checkState() == Qt.Checked:
                candidate = item.data(Qt.UserRole)
                selected.append(candidate)

        if not selected:
            return

        # Add to seeds list (for further processing)
        for candidate in selected:
            if candidate['text'] not in self.seed_items:
                self.seed_items.append(candidate['text'])

        # Emit settings changed
        self.settings_changed.emit(self.get_settings())

        QMessageBox.information(
            self,
            "Candidates Added",
            f"Added {len(selected)} candidates to the column."
        )

        # Clear candidates
        self.candidate_list.clear()
        self.candidate_count_label.setText("Candidates: 0")
        self.add_candidates_btn.setEnabled(False)

    def _run_ai_enrichment(self):
        """Run AI enrichment on the column items."""
        if not self.seed_items:
            QMessageBox.warning(self, "No Items", "Extract seeds or add candidates first.")
            return

        prompt_template = self.ai_prompt_input.toPlainText().strip()
        if not prompt_template:
            QMessageBox.warning(self, "Missing Prompt", "Enter a prompt template.")
            return

        # This will be handled by the main TableGenerator
        QMessageBox.information(
            self,
            "AI Enrichment",
            f"Will run AI enrichment on {len(self.seed_items)} items.\n\n"
            f"Prompt: {prompt_template[:100]}..."
        )

        # Emit settings changed with AI config
        self.settings_changed.emit(self.get_settings())

    def _extract_seeds_fallback(self, search_text: str) -> List[str]:
        """Fallback: Find text using simple string search."""
        print(f"🔍 Fallback: Searching for '{search_text}'")
        results = []
        lines = self.full_text.split('\n')

        for i, line in enumerate(lines):
            if search_text.lower() in line.lower():
                # Check if there's a quote on this line or next line
                if '"' in line:
                    # Extract between quotes on same line
                    start = line.find('"') + 1
                    end = line.find('"', start)
                    if end > start:
                        results.append(line[start:end])
                elif i + 1 < len(lines) and '"' in lines[i + 1]:
                    # Quote on next line
                    next_line = lines[i + 1].strip()
                    if next_line.startswith('"') and next_line.endswith('"'):
                        results.append(next_line[1:-1])
                    elif next_line.startswith('“') and next_line.endswith('”'):
                        results.append(next_line[1:-1])

        return results