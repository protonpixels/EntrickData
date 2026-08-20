import os
import sqlite3
import json
import re
import hashlib
from typing import List, Dict

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QComboBox, QTextEdit,
    QListWidget, QListWidgetItem, QSplitter,
    QFrame, QMessageBox, QFileDialog, QProgressDialog, QInputDialog,
    QSizePolicy, QSpinBox, QDoubleSpinBox
)
from PySide6.QtGui import QClipboard, QGuiApplication, QFont, QKeyEvent, QTextCursor, QTextCharFormat, QColor


class DocumentProcessor(QThread):
    finished = Signal(list)
    error = Signal(str)
    progress = Signal(int, int)

    def __init__(self, file_paths, data_path):
        super().__init__()
        self.file_paths = file_paths if isinstance(file_paths, list) else [file_paths]
        self.data_path = data_path

    def run(self):
        try:
            all_pages = []
            total_files = len(self.file_paths)

            for file_idx, file_path in enumerate(self.file_paths):
                self.progress.emit(file_idx, total_files)
                if not os.path.exists(file_path):
                    continue

                ext = os.path.splitext(file_path)[1].lower()
                if ext == '.txt':
                    pages = self.process_txt(file_path)
                elif ext == '.pdf':
                    pages = self.process_pdf(file_path)
                elif ext in ['.docx', '.doc']:
                    pages = self.process_docx(file_path)
                else:
                    continue

                all_pages.extend(pages)
                for page in pages:
                    self.save_page_to_database(page)

            self.progress.emit(total_files, total_files)
            self.finished.emit(all_pages)

        except Exception as e:
            self.error.emit(str(e))

    def process_txt(self, file_path):
        pages = []
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        filename = os.path.basename(file_path)
        chunks = [c.strip() for c in content.split('\n\n') if c.strip()] or [content.strip()]
        for i, chunk in enumerate(chunks):
            pages.append({
                'title': f"{filename} - Page {i + 1}",
                'content': chunk,
                'url': file_path,
                'page_number': str(i + 1),
                'document': filename
            })
        return pages

    def process_pdf(self, file_path):
        pages = []
        filename = os.path.basename(file_path)
        try:
            import pymupdf
            doc = pymupdf.open(file_path)
            for page_num, page in enumerate(doc.pages()):
                text = page.get_text()
                if text.strip():
                    pages.append({
                        'title': f"{filename} - Page {page_num + 1}",
                        'content': text,
                        'url': file_path,
                        'page_number': str(page_num + 1),
                        'document': filename
                    })
            doc.close()
        except ImportError:
            try:
                import PyPDF2
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    for page_num, page in enumerate(reader.pages):
                        text = page.extract_text()
                        if text.strip():
                            pages.append({
                                'title': f"{filename} - Page {page_num + 1}",
                                'content': text,
                                'url': file_path,
                                'page_number': str(page_num + 1),
                                'document': filename
                            })
            except ImportError:
                pass
        return pages

    def process_docx(self, file_path):
        pages = []
        filename = os.path.basename(file_path)
        try:
            from docx import Document as DocxDocument
            doc = DocxDocument(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            page_size = 12
            for i in range(0, len(paragraphs), page_size):
                page_text = '\n\n'.join(paragraphs[i:i + page_size])
                pages.append({
                    'title': f"{filename} - Page {i // page_size + 1}",
                    'content': page_text,
                    'url': file_path,
                    'page_number': str(i // page_size + 1),
                    'document': filename
                })
        except ImportError:
            pass
        return pages

    def save_page_to_database(self, page_data):
        if not os.path.exists(self.data_path):
            return
        try:
            conn = sqlite3.connect(self.data_path)
            cursor = conn.cursor()
            content_hash = hashlib.md5(page_data['content'].encode()).hexdigest()
            cursor.execute("SELECT id FROM pages WHERE content_hash = ?", (content_hash,))
            if cursor.fetchone():
                conn.close()
                return

            # Always insert without rich_text column (plain text only)
            cursor.execute('''
                INSERT INTO pages (
                    url, title, main_text, main_html, metadata, raw_html, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                page_data.get('url', ''),
                page_data.get('title', ''),
                page_data.get('content', ''),
                '',
                json.dumps({
                    'document': page_data.get('document', ''),
                    'page_number': page_data.get('page_number', ''),
                    'type': 'document'
                }),
                page_data.get('content', ''),
                content_hash
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error saving page: {e}")


class DataDocumentView(QWidget):
    """Data Document project view - with plain text editor and styling"""

    def __init__(self, parent=None, db=None, project_data=None):
        super().__init__(parent)
        self.parent_app = parent
        self.db = db
        self.project_data = project_data
        self.project_id = project_data.get('id')
        self.data_path = project_data.get('data_path')
        self.project_name = project_data.get('name', 'Document Project')

        self.pages = []
        self.current_page_id = None
        self.current_page_index = -1
        self.is_edit_mode = False
        self._loading = False

        # Display settings
        self.font_family = "Georgia"
        self.font_size = 12
        self.line_height = 1.6
        self.word_spacing = 1.0
        self.letter_spacing = 0.0

        # Search
        self.search_matches = []
        self.search_match_index = -1

        self.setup_ui()
        QTimer.singleShot(300, self._load_pages_safe)

    def _load_pages_safe(self):
        try:
            if self._loading:
                return
            self._loading = True
            self.load_pages()
        except Exception as e:
            print(f"Error loading pages: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._loading = False

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Top toolbar
        top_bar = self._create_top_toolbar()
        layout.addLayout(top_bar)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Left panel
        left_widget = self._create_left_panel()
        splitter.addWidget(left_widget)

        # Right panel
        right_widget = self._create_right_panel()
        splitter.addWidget(right_widget)

        splitter.setSizes([300, 900])
        layout.addWidget(splitter)

        # Bottom toolbar with formatting controls and search
        bottom_bar = self._create_bottom_toolbar()
        layout.addLayout(bottom_bar)

        self.setLayout(layout)

    def _create_top_toolbar(self):
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        back_btn = QPushButton("← Back")
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #666;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #555; }
        """)
        back_btn.clicked.connect(self.go_back)
        toolbar.addWidget(back_btn)

        name_label = QLabel(f"📄 {self.project_name}")
        name_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #1c242e;")
        toolbar.addWidget(name_label)

        toolbar.addStretch()

        # Edit Mode toggle
        self.edit_mode_btn = QPushButton("✏️ Edit")
        self.edit_mode_btn.setCheckable(True)
        self.edit_mode_btn.setChecked(False)
        self.edit_mode_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #666;
                font-weight: bold;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:checked {
                background-color: #FF9800;
                color: white;
            }
            QPushButton:checked:hover { background-color: #F57C00; }
        """)
        self.edit_mode_btn.clicked.connect(self.toggle_edit_mode)
        toolbar.addWidget(self.edit_mode_btn)

        # Save button (only appears in edit mode)
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.setStyleSheet("""
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
        self.save_btn.setVisible(False)
        self.save_btn.clicked.connect(self.save_page_content)
        toolbar.addWidget(self.save_btn)

        import_btn = QPushButton("📂 Add")
        import_btn.setStyleSheet("""
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
        import_btn.clicked.connect(self.import_documents)
        toolbar.addWidget(import_btn)

        add_page_btn = QPushButton("➕ Page")
        add_page_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        add_page_btn.clicked.connect(self.add_empty_page)
        toolbar.addWidget(add_page_btn)

        rename_btn = QPushButton("✏️ Rename")
        rename_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #F57C00; }
        """)
        rename_btn.clicked.connect(self.rename_page)
        toolbar.addWidget(rename_btn)

        delete_btn = QPushButton("🗑️ Delete")
        delete_btn.setStyleSheet("""
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
        delete_btn.clicked.connect(self.delete_current_page)
        toolbar.addWidget(delete_btn)

        self.page_count_label = QLabel("Pages: 0")
        self.page_count_label.setStyleSheet("color: #666; font-size: 12px;")
        toolbar.addWidget(self.page_count_label)

        return toolbar

    def _create_left_panel(self):
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.page_search = QLineEdit()
        self.page_search.setPlaceholderText("🔍 Search pages...")
        self.page_search.setStyleSheet("font-size: 12px; padding: 4px; border-radius: 4px;")
        self.page_search.textChanged.connect(self.on_page_search_changed)
        left_layout.addWidget(self.page_search)

        pages_label = QLabel("📄 Pages")
        pages_label.setStyleSheet("font-weight: bold; padding: 4px 8px; background-color: #f0f0f0;")
        left_layout.addWidget(pages_label)

        self.page_list = QListWidget()
        self.page_list.itemClicked.connect(self.on_page_selected)
        left_layout.addWidget(self.page_list)

        return left_widget

    def _create_right_panel(self):
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Document info
        self.doc_info_label = QLabel("")
        self.doc_info_label.setStyleSheet("color: #666; font-size: 12px; padding: 2px 8px;")
        right_layout.addWidget(self.doc_info_label)

        # Text editor
        self.text_editor = QTextEdit()
        self.text_editor.setReadOnly(True)
        self.text_editor.setFont(QFont("Georgia", 12))
        self.text_editor.setStyleSheet("""
            QTextEdit {
                padding: 20px;
                background-color: #fcfcfc;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
        """)
        self.text_editor.textChanged.connect(self.on_text_changed)
        right_layout.addWidget(self.text_editor)

        return right_widget

    def _create_bottom_toolbar(self):
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        # Font controls
        toolbar.addWidget(QLabel("Font:"))
        self.font_combo = QComboBox()
        self.font_combo.setMaximumWidth(120)
        available_fonts = ["Georgia", "Times New Roman", "Arial", "Verdana", "Tahoma", "Courier New", "Palatino",
                           "Garamond"]
        for font in available_fonts:
            self.font_combo.addItem(font)
        self.font_combo.setCurrentText("Georgia")
        self.font_combo.currentTextChanged.connect(self.update_display_style)
        toolbar.addWidget(self.font_combo)

        toolbar.addWidget(QLabel("Size:"))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(12)
        self.font_size_spin.setMaximumWidth(50)
        self.font_size_spin.valueChanged.connect(self.update_display_style)
        toolbar.addWidget(self.font_size_spin)

        toolbar.addWidget(QLabel("Line Ht:"))
        self.line_height_spin = QDoubleSpinBox()
        self.line_height_spin.setRange(1.0, 3.0)
        self.line_height_spin.setSingleStep(0.1)
        self.line_height_spin.setValue(1.6)
        self.line_height_spin.setMaximumWidth(50)
        self.line_height_spin.valueChanged.connect(self.update_display_style)
        toolbar.addWidget(self.line_height_spin)

        toolbar.addWidget(QLabel("Word Sp:"))
        self.word_spacing_spin = QDoubleSpinBox()
        self.word_spacing_spin.setRange(0.0, 5.0)
        self.word_spacing_spin.setSingleStep(0.1)
        self.word_spacing_spin.setValue(1.0)
        self.word_spacing_spin.setMaximumWidth(50)
        self.word_spacing_spin.valueChanged.connect(self.update_display_style)
        toolbar.addWidget(self.word_spacing_spin)

        toolbar.addWidget(QLabel("Letter Sp:"))
        self.letter_spacing_spin = QDoubleSpinBox()
        self.letter_spacing_spin.setRange(0.0, 2.0)
        self.letter_spacing_spin.setSingleStep(0.05)
        self.letter_spacing_spin.setValue(0.0)
        self.letter_spacing_spin.setMaximumWidth(50)
        self.letter_spacing_spin.valueChanged.connect(self.update_display_style)
        toolbar.addWidget(self.letter_spacing_spin)


        # Copy button
        copy_btn = QPushButton("📋 Copy")
        copy_btn.clicked.connect(self.copy_text)
        copy_btn.setStyleSheet("""
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
        toolbar.addWidget(copy_btn)


        # Search in current page
        toolbar.addWidget(QLabel("🔍 Find:"))
        self.search_input = QLineEdit()
        self.search_input.setMaximumWidth(200)
        self.search_input.setPlaceholderText("Search in page...")
        self.search_input.textChanged.connect(self.search_in_page)
        self.search_input.returnPressed.connect(self.find_next)
        toolbar.addWidget(self.search_input)

        self.find_next_btn = QPushButton("Next")
        self.find_next_btn.setMaximumWidth(60)
        self.find_next_btn.setStyleSheet("""
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
        self.find_next_btn.clicked.connect(self.find_next)
        toolbar.addWidget(self.find_next_btn)

        self.find_prev_btn = QPushButton("Prev")
        self.find_prev_btn.setMaximumWidth(60)
        self.find_prev_btn.setStyleSheet("""
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
        self.find_prev_btn.clicked.connect(self.find_prev)
        toolbar.addWidget(self.find_prev_btn)

        self.match_count_label = QLabel("")
        self.match_count_label.setMaximumWidth(80)
        self.match_count_label.setStyleSheet("color: #666; font-size: 10px;")
        toolbar.addWidget(self.match_count_label)

        toolbar.addStretch()

        self.selection_status = QLabel("")
        self.selection_status.setStyleSheet("color: #666; font-size: 11px;")
        toolbar.addWidget(self.selection_status)

        return toolbar

    # ============ DISPLAY STYLING ============

    def update_display_style(self):
        """Update the text display with current font settings."""
        self.font_family = self.font_combo.currentText()
        self.font_size = self.font_size_spin.value()
        self.line_height = self.line_height_spin.value()
        self.word_spacing = self.word_spacing_spin.value()
        self.letter_spacing = self.letter_spacing_spin.value()

        # Apply to editor
        font = QFont(self.font_family, self.font_size)
        self.text_editor.setFont(font)

        # Set line height via CSS
        self.text_editor.setStyleSheet(f"""
            QTextEdit {{
                padding: 20px;
                background-color: #fcfcfc;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                font-family: "{self.font_family}";
                font-size: {self.font_size}pt;
                line-height: {self.line_height};
                word-spacing: {self.word_spacing}px;
                letter-spacing: {self.letter_spacing}px;
            }}
        """)

    # ============ EDIT MODE ============

    def toggle_edit_mode(self):
        self.is_edit_mode = self.edit_mode_btn.isChecked()
        self.text_editor.setReadOnly(not self.is_edit_mode)
        self.save_btn.setVisible(self.is_edit_mode)

        if self.is_edit_mode:
            self.edit_mode_btn.setText("✏️ Edit ON")
            self.text_editor.setStyleSheet("""
                QTextEdit {
                    padding: 20px;
                    background-color: #fff8e1;
                    border: 2px solid #FF9800;
                    border-radius: 4px;
                    font-family: "Georgia";
                    font-size: 12pt;
                    line-height: 1.6;
                }
            """)
            self.update_status("✏️ Edit mode ON")
        else:
            self.save_page_content()
            self.edit_mode_btn.setText("✏️ Edit")
            self.update_display_style()
            self.update_status("📖 View mode")

    def on_text_changed(self):
        """Handle text changes in edit mode."""
        if self.is_edit_mode:
            # Auto-save indicator (could add a dirty flag)
            pass

    def save_page_content(self):
        """Save the current page content."""
        if self.current_page_id is None or self.current_page_index < 0:
            return

        plain_text = self.text_editor.toPlainText()

        try:
            conn = sqlite3.connect(self.data_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE pages SET main_text = ?, raw_html = ? WHERE id = ?",
                (plain_text, plain_text, self.current_page_id)
            )
            conn.commit()
            conn.close()

            self.pages[self.current_page_index]['main_text'] = plain_text
            self.pages[self.current_page_index]['raw_html'] = plain_text
            self.update_status(f"✅ Page saved: {len(plain_text)} characters")
        except Exception as e:
            print(f"Error saving page: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    # ============ PAGE LOADING ============

    def load_pages(self):
        """Load pages from database."""
        try:
            if not self.db:
                return

            if hasattr(self.db, 'get_document_pages'):
                self.pages = self.db.get_document_pages(self.data_path)
            else:
                self.pages = self.db.get_research_pages(self.data_path)

            self._refresh_page_list()

            if self.pages and self.page_list.count() > 0:
                self.page_list.setCurrentRow(0)
                self.display_page(0)
        except Exception as e:
            print(f"Error loading pages: {e}")
            self.page_count_label.setText("Pages: 0")

    def display_page(self, index):
        try:
            if index < 0 or index >= len(self.pages):
                return

            page = self.pages[index]
            self.current_page_id = page.get('id')
            self.current_page_index = index

            metadata = page.get('metadata', {})
            doc_name = metadata.get('document', 'Unknown')
            page_num = metadata.get('page_number', '')
            self.doc_info_label.setText(f"📄 {doc_name} - Page {page_num}")

            content = page.get('main_text', '') or page.get('raw_html', '')
            self.text_editor.setPlainText(content)

            # Clear search
            self.search_input.clear()
            self.search_matches = []
            self.search_match_index = -1
            self.match_count_label.setText("")
            self.clear_highlights()

        except Exception as e:
            print(f"Error displaying page: {e}")

    def on_page_selected(self, item):
        page_id = item.data(Qt.UserRole)
        for i, page in enumerate(self.pages):
            if page.get('id') == page_id:
                self.display_page(i)
                break

    def on_page_search_changed(self, text):
        if not text:
            self.load_pages()
            return
        query = text.lower()
        self.page_list.clear()
        for page in self.pages:
            title = page.get('title', '').lower()
            content = page.get('main_text', '').lower()
            if query in title or query in content:
                display = f"🔍 {page.get('title', 'Untitled')[:60]}"
                item = QListWidgetItem(display)
                item.setData(Qt.UserRole, page.get('id'))
                self.page_list.addItem(item)
        if self.page_list.count() > 0:
            self.page_list.setCurrentRow(0)
            self.display_page(0)

    # ============ SEARCH IN PAGE ============

    def search_in_page(self, text):
        """Search for text in the current page."""
        if not text:
            self.clear_highlights()
            self.search_matches = []
            self.search_match_index = -1
            self.match_count_label.setText("")
            return

        doc = self.text_editor.document()
        self.clear_highlights()

        cursor = doc.find(text)
        matches = []
        while not cursor.isNull():
            matches.append(cursor)
            cursor = doc.find(text, cursor)

        if matches:
            self.search_matches = matches
            self.search_match_index = 0
            self.match_count_label.setText(f"{len(matches)} matches")
            self.highlight_match(matches[0])
            self.text_editor.setTextCursor(matches[0])
            self.text_editor.ensureCursorVisible()
        else:
            self.search_matches = []
            self.search_match_index = -1
            self.match_count_label.setText("No matches")

    def clear_highlights(self):
        """Clear all search highlights."""
        doc = self.text_editor.document()
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.Document)
        cursor.setCharFormat(QTextCharFormat())

    def highlight_match(self, cursor):
        """Highlight a specific match."""
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(255, 255, 0))
        cursor.mergeCharFormat(fmt)

    def find_next(self):
        """Find the next match."""
        if not self.search_matches:
            return

        self.clear_highlights()

        if self.search_match_index < len(self.search_matches) - 1:
            self.search_match_index += 1
        else:
            self.search_match_index = 0

        match = self.search_matches[self.search_match_index]
        self.highlight_match(match)
        self.text_editor.setTextCursor(match)
        self.text_editor.ensureCursorVisible()
        self.match_count_label.setText(f"{self.search_match_index + 1} of {len(self.search_matches)}")

    def find_prev(self):
        """Find the previous match."""
        if not self.search_matches:
            return

        self.clear_highlights()

        if self.search_match_index > 0:
            self.search_match_index -= 1
        else:
            self.search_match_index = len(self.search_matches) - 1

        match = self.search_matches[self.search_match_index]
        self.highlight_match(match)
        self.text_editor.setTextCursor(match)
        self.text_editor.ensureCursorVisible()
        self.match_count_label.setText(f"{self.search_match_index + 1} of {len(self.search_matches)}")

    # ============ PAGE MANAGEMENT ============

    def add_empty_page(self):
        """Add a new empty page."""
        title, ok = QInputDialog.getText(
            self,
            "Add Page",
            "Page title:",
            text=f"Page {len(self.pages) + 1}"
        )
        if not ok or not title.strip():
            return

        try:
            conn = sqlite3.connect(self.data_path)
            cursor = conn.cursor()
            content_hash = hashlib.md5(''.encode()).hexdigest()

            cursor.execute('''
                INSERT INTO pages (
                    url, title, main_text, main_html, metadata, raw_html, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                '',
                title.strip(),
                '',
                '',
                json.dumps({
                    'document': 'Empty',
                    'page_number': str(len(self.pages) + 1),
                    'type': 'document'
                }),
                '',
                content_hash
            ))

            page_id = cursor.lastrowid
            conn.commit()
            conn.close()

            # Add to local cache
            new_page = {
                'id': page_id,
                'title': title.strip(),
                'main_text': '',
                'raw_html': '',
                'metadata': {'document': 'Empty', 'page_number': str(len(self.pages) + 1)}
            }
            self.pages.append(new_page)

            # Clear cache in database
            if hasattr(self.db, 'clear_cache'):
                self.db.clear_cache()

            self._refresh_page_list()

            # Select the new page
            self.page_list.setCurrentRow(len(self.pages) - 1)
            self.display_page(len(self.pages) - 1)

            self.update_status(f"✅ Added page: {title.strip()}")
        except Exception as e:
            print(f"Error adding page: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to add page: {e}")

    def rename_page(self):
        """Rename the current page."""
        if self.current_page_index < 0 or self.current_page_index >= len(self.pages):
            QMessageBox.warning(self, "No Page", "No page selected to rename.")
            return

        page = self.pages[self.current_page_index]
        current_title = page.get('title', 'Untitled')

        new_title, ok = QInputDialog.getText(
            self,
            "Rename Page",
            "Enter new page name:",
            text=current_title
        )

        if ok and new_title.strip():
            try:
                conn = sqlite3.connect(self.data_path)
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE pages SET title = ? WHERE id = ?",
                    (new_title.strip(), page.get('id'))
                )
                conn.commit()
                conn.close()

                # Update local cache
                page['title'] = new_title.strip()

                # Refresh the list while preserving selection
                self._refresh_page_list()

                # Find and select the renamed page
                for i, p in enumerate(self.pages):
                    if p.get('id') == page.get('id'):
                        self.page_list.setCurrentRow(i)
                        break

                self.update_status(f"✅ Page renamed to: {new_title.strip()}")

            except Exception as e:
                print(f"Error renaming page: {e}")
                QMessageBox.critical(self, "Error", f"Failed to rename page: {e}")

    def delete_current_page(self):
        """Delete the current page."""
        if self.current_page_index < 0 or self.current_page_index >= len(self.pages):
            QMessageBox.warning(self, "No Page", "No page selected to delete.")
            return

        page = self.pages[self.current_page_index]
        title = page.get('title', 'Untitled')

        reply = QMessageBox.question(
            self,
            "Delete Page",
            f"Are you sure you want to delete page:\n\n'{title}'\n\nThis action cannot be undone!",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                conn = sqlite3.connect(self.data_path)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM pages WHERE id = ?", (page.get('id'),))
                conn.commit()
                conn.close()

                # Remove from local cache
                self.pages.pop(self.current_page_index)

                # Clear cache in database
                if hasattr(self.db, 'clear_cache'):
                    self.db.clear_cache()

                # Refresh the list
                self._refresh_page_list()

                # Select a new page
                if self.pages:
                    # Select the page at the same index, or the last one if we deleted the last
                    new_index = min(self.current_page_index, len(self.pages) - 1)
                    self.page_list.setCurrentRow(new_index)
                    self.display_page(new_index)
                else:
                    # No pages left
                    self.clear_display()
                    self.page_count_label.setText("Pages: 0")

                self.update_status(f"🗑️ Deleted page: {title}")

            except Exception as e:
                print(f"Error deleting page: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete page: {e}")

    def clear_display(self):
        """Clear the display when no pages are available."""
        self.text_editor.clear()
        self.doc_info_label.setText("No pages")
        self.current_page_id = None
        self.current_page_index = -1

    # ============ COPY ============

    def copy_text(self):
        cursor = self.text_editor.textCursor()
        if cursor.hasSelection():
            text = cursor.selectedText()
        else:
            text = self.text_editor.toPlainText()
        if text:
            QGuiApplication.clipboard().setText(text)
            self.update_status(f"📋 Copied {len(text)} characters")
        else:
            QMessageBox.information(self, "Copy", "No content to copy.")

    # ============ IMPORT ============

    def import_documents(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select Documents", "",
                                                     "Documents (*.txt *.pdf *.docx *.doc)")
        if not file_paths:
            return
        progress = QProgressDialog("Processing...", "Cancel", 0, len(file_paths), self)
        progress.setWindowModality(Qt.WindowModal)
        self.processor = DocumentProcessor(file_paths, self.data_path)
        self.processor.progress.connect(lambda c, t: progress.setValue(c + 1))
        self.processor.finished.connect(lambda p: self._on_documents_done(p, progress))
        self.processor.error.connect(lambda e: self._on_documents_error(e, progress))
        self.processor.start()

    def _on_documents_done(self, pages, progress):
        progress.close()
        self.load_pages()
        if pages:
            QMessageBox.information(self, "Success", f"Processed {len(pages)} pages.")

    def _on_documents_error(self, error, progress):
        progress.close()
        QMessageBox.critical(self, "Error", f"Processing error: {error}")

    # ============ UTILITY ============

    def go_back(self):
        if self.parent_app and hasattr(self.parent_app, 'show_home_tab'):
            self.parent_app.show_home_tab()

    def update_status(self, message):
        if self.parent_app and hasattr(self.parent_app, 'update_status'):
            self.parent_app.update_status(message)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard shortcuts."""
        if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
            if self.is_edit_mode:
                self.save_page_content()
            return
        super().keyPressEvent(event)

    def _refresh_page_list(self):
        """Refresh the page list widget without reloading from database."""
        self.page_list.clear()

        for i, page in enumerate(self.pages):
            title = page.get('title', 'Untitled')
            display = title[:60] + ('...' if len(title) > 60 else '')
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, page.get('id'))
            self.page_list.addItem(item)

        self.page_count_label.setText(f"Pages: {len(self.pages)}")
