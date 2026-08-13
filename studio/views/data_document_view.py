import os
import sys
import sqlite3
import json
import re
import webbrowser
from collections import Counter
from typing import List, Dict
from urllib.parse import urljoin

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QComboBox, QCheckBox,
    QTextEdit, QListWidget, QListWidgetItem, QSplitter,
    QTabWidget, QScrollArea, QFrame, QMessageBox,
    QFileDialog, QDialog, QSpinBox, QDoubleSpinBox,
    QTextBrowser, QSizePolicy, QGroupBox, QCompleter, QRadioButton, QProgressDialog, QInputDialog
)
from PySide6.QtGui import (
    QClipboard, QGuiApplication, QFont, QColor,
    QKeyEvent, QTextCursor, QTextCharFormat,
    QFontDatabase, QSyntaxHighlighter, QPixmap, QTextDocument
)

from bs4 import BeautifulSoup
import hashlib

# Import studio utilities
from utils.file_handlers import FileHandler
from models.data_types import ColumnType

# Document processing libraries

try:
    import pymupdf  # PyMuPDF

    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    from docx import Document as DocxDocument

    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False


class DocumentProcessor(QThread):
    """Thread for processing documents into pages"""
    finished = Signal(list)  # Emits list of page data
    error = Signal(str)
    progress = Signal(int, int)  # current, total

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

                # Save to database as we go
                for page in pages:
                    self.save_page_to_database(page)

            self.progress.emit(total_files, total_files)
            self.finished.emit(all_pages)

        except Exception as e:
            self.error.emit(str(e))

    def process_txt(self, file_path):
        """Process a text file into pages"""
        pages = []
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # Split by paragraphs (2+ newlines) or by newlines if no paragraphs
        if '\n\n' in content:
            chunks = [c.strip() for c in content.split('\n\n') if c.strip()]
        else:
            chunks = [c.strip() for c in content.split('\n') if c.strip()]

        # If no chunks, treat as single page
        if not chunks:
            chunks = [content.strip()]

        filename = os.path.basename(file_path)

        for i, chunk in enumerate(chunks):
            # Split large chunks into smaller pages if needed
            if len(chunk) > 5000:  # Approximate page size
                # Split by sentences for large chunks
                sentences = re.split(r'(?<=[.!?])\s+', chunk)
                for j in range(0, len(sentences), 20):  # ~20 sentences per page
                    page_text = ' '.join(sentences[j:j + 20])
                    pages.append({
                        'title': f"{filename} - Page {i + 1}.{j // 20 + 1}",
                        'content': page_text,
                        'url': file_path,
                        'page_number': f"{i + 1}.{j // 20 + 1}",
                        'document': filename
                    })
            else:
                pages.append({
                    'title': f"{filename} - Page {i + 1}",
                    'content': chunk,
                    'url': file_path,
                    'page_number': str(i + 1),
                    'document': filename
                })

        return pages

    def process_pdf(self, file_path):
        """Process a PDF file into pages"""
        pages = []
        filename = os.path.basename(file_path)

        if HAS_FITZ:
            # Use PyMuPDF for better extraction
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
        else:
            # Fallback to PyPDF2 (simpler but less formatting)
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
                raise ImportError("Please install PyMuPDF (pymupdf) or PyPDF2 for PDF support.")

        return pages

    def process_docx(self, file_path):
        """Process a DOCX file into pages"""
        pages = []
        filename = os.path.basename(file_path)

        if HAS_DOCX:
            doc = DocxDocument(file_path)

            # Process paragraphs
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

            if not paragraphs:
                return pages

            # Group paragraphs into pages (~10-15 paragraphs per page)
            page_size = 12
            for i in range(0, len(paragraphs), page_size):
                page_paragraphs = paragraphs[i:i + page_size]
                page_text = '\n\n'.join(page_paragraphs)
                page_num = i // page_size + 1
                pages.append({
                    'title': f"{filename} - Page {page_num}",
                    'content': page_text,
                    'url': file_path,
                    'page_number': str(page_num),
                    'document': filename
                })
        else:
            raise ImportError("Please install python-docx for DOCX support.")

        return pages

    def save_page_to_database(self, page_data):
        """Save a page to the database"""
        if not os.path.exists(self.data_path):
            return

        conn = sqlite3.connect(self.data_path)
        cursor = conn.cursor()

        # Calculate hash for deduplication
        content_hash = hashlib.md5(page_data['content'].encode()).hexdigest()

        # Check if page already exists
        cursor.execute("SELECT id FROM pages WHERE content_hash = ?", (content_hash,))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return

        # Insert page
        cursor.execute('''
            INSERT INTO pages (
                url, title, main_text, main_html, metadata, raw_html, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            page_data.get('url', ''),
            page_data.get('title', ''),
            page_data.get('content', ''),
            '',  # main_html - empty for documents
            json.dumps({
                'document': page_data.get('document', ''),
                'page_number': page_data.get('page_number', ''),
                'type': 'document'
            }),
            page_data.get('content', ''),  # raw_html stores the text content
            content_hash
        ))

        conn.commit()
        conn.close()


class DataDocumentView(QWidget):
    """Data Document project view - for processing and viewing documents"""

    def __init__(self, parent=None, db=None, project_data=None):
        super().__init__(parent)
        self.parent_app = parent
        self.db = db
        self.project_data = project_data
        self.project_id = project_data.get('id')
        self.data_path = project_data.get('data_path')
        self.project_name = project_data.get('name', 'Document Project')

        # Data stores
        self.pages = []
        self.current_page_id = None
        self.current_page_index = -1
        self.elements = []
        self.links = []
        self.media_items = []
        self.base_url = ""

        # Data Table integration
        self.selected_table_project_id = None
        self.selected_column_name = None
        self.table_projects = []

        # Display settings
        self.current_font_family = "Georgia"
        self.current_font_size = 12
        self.current_line_height = 1.6
        self.current_matches = []
        self.current_match_index = -1

        self.setup_ui()
        self.load_table_projects()
        self.load_pages()
        self.update_status("Ready")

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)

        # Top bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)
        top_bar.setContentsMargins(5, 0, 5, 0)

        back_btn = QPushButton("← Back")
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
        back_btn.clicked.connect(self.go_back)
        top_bar.addWidget(back_btn)

        name_label = QLabel(f"📄 {self.project_name}")
        name_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #1c242e;")
        top_bar.addWidget(name_label)

        # Document info label
        self.doc_info_label = QLabel("")
        self.doc_info_label.setStyleSheet("color: #666; font-size: 12px;")
        top_bar.addWidget(self.doc_info_label)

        top_bar.addStretch()

        # Import Documents button
        import_btn = QPushButton("📂 Add Document(s)")
        import_btn.setStyleSheet("""
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
        import_btn.clicked.connect(self.import_documents)
        top_bar.addWidget(import_btn)

        # Rename Page button
        rename_page_btn = QPushButton("✏️ Rename Page")
        rename_page_btn.setStyleSheet("""
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
        rename_page_btn.clicked.connect(self.rename_page)
        top_bar.addWidget(rename_page_btn)

        # Delete Page button
        delete_page_btn = QPushButton("🗑️ Delete Page")
        delete_page_btn.setStyleSheet("""
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
        delete_page_btn.clicked.connect(self.delete_current_page)
        top_bar.addWidget(delete_page_btn)

        # Page count
        self.page_count_label = QLabel("Pages: 0")
        self.page_count_label.setStyleSheet("color: #666; font-size: 12px;")
        top_bar.addWidget(self.page_count_label)

        layout.addLayout(top_bar)

        # URL input and search for pages
        search_pages_layout = QHBoxLayout()
        search_pages_layout.setSpacing(5)
        search_pages_layout.setContentsMargins(5, 0, 5, 0)

        self.page_search = QLineEdit()
        self.page_search.setPlaceholderText("🔍 Search in pages...")
        self.page_search.setStyleSheet("font-size: 13px; padding: 6px; border-radius: 4px;")
        self.page_search.textChanged.connect(self.on_page_search_changed)
        search_pages_layout.addWidget(self.page_search, 1)

        layout.addLayout(search_pages_layout)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Left panel: Pages list + Data Table Integration
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Data Table Integration section
        table_section = QFrame()
        table_section.setStyleSheet("""
            QFrame {
                background-color: #f0f4f8;
                border: 1px solid #d0d7de;
                border-radius: 4px;
                margin: 4px;
                padding: 4px;
            }
        """)
        table_layout = QVBoxLayout(table_section)
        table_layout.setSpacing(4)

        table_label = QLabel("📊 Insert into Data Table")
        table_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #1c242e;")
        table_layout.addWidget(table_label)

        # Project dropdown
        project_layout = QHBoxLayout()
        project_layout.addWidget(QLabel("Project:"))
        self.project_combo = QComboBox()
        self.project_combo.setEditable(True)
        self.project_combo.setInsertPolicy(QComboBox.NoInsert)
        self.project_combo.setStyleSheet("font-size: 11px; padding: 3px;")
        self.project_combo.currentIndexChanged.connect(self.on_project_combo_changed)

        completer = QCompleter()
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.project_combo.setCompleter(completer)

        project_layout.addWidget(self.project_combo, 1)
        table_layout.addLayout(project_layout)

        # Column dropdown
        column_layout = QHBoxLayout()
        column_layout.addWidget(QLabel("Column:"))
        self.column_combo = QComboBox()
        self.column_combo.setStyleSheet("font-size: 11px; padding: 3px;")
        self.column_combo.addItem("Select a column...", None)
        column_layout.addWidget(self.column_combo, 1)
        table_layout.addLayout(column_layout)

        # Insert button
        self.insert_btn = QPushButton("📥 Insert Selected Text")
        self.insert_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.insert_btn.setEnabled(False)
        self.insert_btn.clicked.connect(self.insert_selected_text)
        table_layout.addWidget(self.insert_btn)

        left_layout.addWidget(table_section)

        # Pages label
        pages_label = QLabel("📄 Pages")
        pages_label.setStyleSheet("font-weight: bold; padding: 5px; background-color: #f0f0f0;")
        left_layout.addWidget(pages_label)

        # Page list
        self.page_list = QListWidget()
        self.page_list.setFocusPolicy(Qt.StrongFocus)
        self.page_list.itemClicked.connect(self.on_page_selected)
        self.page_list.setStyleSheet("""
            QListWidget::item:hover { background-color: #e0f0ff; }
            QListWidget::item:selected { background-color: #4CAF50; color: white; }
        """)
        left_layout.addWidget(self.page_list)

        splitter.addWidget(left_widget)

        # Right panel: Content display
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #d0d0d0;
                border-radius: 4px;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #4CAF50;
                color: white;
            }
        """)
        self.tabs.currentChanged.connect(self.on_tab_changed)

        # Text Content tab
        self.text_content_view = QTextBrowser()
        self.text_content_view.selectionChanged.connect(self.on_selection_changed)
        self.text_content_view.setFont(QFont("Georgia", 12))
        self.text_content_view.setStyleSheet("padding: 30px; background-color: #fcfcfc; border: none;")
        self.text_content_view.anchorClicked.connect(self.on_link_clicked)
        self.tabs.addTab(self.text_content_view, "📝 Text Content")

        # Links tab
        self.links_view = QTextEdit()
        self.links_view.setReadOnly(True)
        self.links_view.setFont(QFont("Segoe UI", 11))
        self.links_view.setStyleSheet("padding: 20px; background-color: #fcfcfc; border: none;")
        self.tabs.addTab(self.links_view, "🔗 Links")

        # Media tab
        self.media_tab = QWidget()
        self.media_layout = QVBoxLayout(self.media_tab)
        self.media_layout.setAlignment(Qt.AlignTop)
        self.media_scroll = QScrollArea()
        self.media_scroll.setWidgetResizable(True)
        self.media_scroll.setWidget(self.media_tab)
        self.tabs.addTab(self.media_scroll, "🎬 Media")

        # Raw Text tab
        self.raw_text_view = QTextEdit()
        self.raw_text_view.setReadOnly(True)
        self.raw_text_view.setFont(QFont("Courier New", 10))
        self.raw_text_view.setStyleSheet("""
            padding: 20px;
            background-color: #f8f8f8;
            border: none;
        """)
        self.tabs.addTab(self.raw_text_view, "📄 Raw Text")

        # Formatting controls
        formatting_widget = QWidget()
        formatting_layout = QHBoxLayout(formatting_widget)
        formatting_layout.setSpacing(10)

        # Copy Text button
        self.copy_btn = QPushButton("📋 Copy Text")
        self.copy_btn.clicked.connect(self.copy_current_view)
        self.copy_btn.setMaximumWidth(120)
        self.copy_btn.setStyleSheet("""
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
        formatting_layout.addWidget(self.copy_btn)

        # Separator
        line0 = QFrame()
        line0.setFrameShape(QFrame.VLine)
        line0.setFrameShadow(QFrame.Sunken)
        formatting_layout.addWidget(line0)

        # Text Display Options
        formatting_layout.addWidget(QLabel("Display:"))
        self.text_display_combo = QComboBox()
        self.text_display_combo.setMaximumWidth(180)
        self.text_display_combo.addItems([
            "Text Organized",
            "Text Jumble",
            "Text Elements",
            "Text Headers",
            "Text Paragraphs",
            "Text Sentences",
            "Text Unique Words",
            "Text Repeated Words",
            "Text Questions"
        ])
        self.text_display_combo.setCurrentIndex(0)
        self.text_display_combo.currentTextChanged.connect(self.update_text_display)
        formatting_layout.addWidget(self.text_display_combo)

        # Separator
        line1 = QFrame()
        line1.setFrameShape(QFrame.VLine)
        line1.setFrameShadow(QFrame.Sunken)
        formatting_layout.addWidget(line1)

        # Font controls
        formatting_layout.addWidget(QLabel("Font:"))
        self.font_combo = QComboBox()
        self.font_combo.setMaximumWidth(120)
        available_fonts = ["Georgia", "Times New Roman", "Arial", "Verdana", "Tahoma", "Courier New", "Palatino",
                           "Garamond"]
        for font in available_fonts:
            self.font_combo.addItem(font)
        self.font_combo.setCurrentText("Georgia")
        self.font_combo.currentTextChanged.connect(self.update_formatting)
        formatting_layout.addWidget(self.font_combo)

        formatting_layout.addWidget(QLabel("Size:"))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(12)
        self.font_size_spin.setMaximumWidth(50)
        self.font_size_spin.valueChanged.connect(self.update_formatting)
        formatting_layout.addWidget(self.font_size_spin)

        formatting_layout.addWidget(QLabel("Line Ht:"))
        self.line_height_spin = QDoubleSpinBox()
        self.line_height_spin.setRange(1.0, 3.0)
        self.line_height_spin.setSingleStep(0.1)
        self.line_height_spin.setValue(1.6)
        self.line_height_spin.setMaximumWidth(50)
        self.line_height_spin.valueChanged.connect(self.update_formatting)
        formatting_layout.addWidget(self.line_height_spin)

        # Separator
        line2 = QFrame()
        line2.setFrameShape(QFrame.VLine)
        line2.setFrameShadow(QFrame.Sunken)
        formatting_layout.addWidget(line2)

        # Full Text Search
        formatting_layout.addWidget(QLabel("🔍 Find:"))
        self.full_text_search = QLineEdit()
        self.full_text_search.setMaximumWidth(200)
        self.full_text_search.setPlaceholderText("Search in current tab...")
        self.full_text_search.textChanged.connect(self.search_full_text)
        self.full_text_search.returnPressed.connect(self.find_next_full_text)
        formatting_layout.addWidget(self.full_text_search)

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
        self.find_next_btn.clicked.connect(self.find_next_full_text)
        formatting_layout.addWidget(self.find_next_btn)

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
        self.find_prev_btn.clicked.connect(self.find_prev_full_text)
        formatting_layout.addWidget(self.find_prev_btn)

        self.match_count_label = QLabel("")
        self.match_count_label.setMaximumWidth(80)
        self.match_count_label.setStyleSheet("color: gray; font-size: 10px;")
        formatting_layout.addWidget(self.match_count_label)

        formatting_layout.addStretch()

        right_layout.addWidget(self.tabs)
        right_layout.addWidget(formatting_widget)

        splitter.addWidget(right_widget)
        splitter.setSizes([300, 900])

        layout.addWidget(splitter)
        self.setLayout(layout)

    def go_back(self):
        """Go back to home"""
        if self.parent_app and hasattr(self.parent_app, 'show_home_tab'):
            self.parent_app.show_home_tab()

    def update_status(self, message):
        """Update status message"""
        if self.parent_app and hasattr(self.parent_app, 'update_status'):
            self.parent_app.update_status(message)

    def load_pages(self):
        """Load pages from database"""
        self.pages = self.db.get_research_pages(self.data_path)
        self.page_list.clear()

        for page in self.pages:
            title = page.get('title', 'Untitled')
            display = f"{title[:60]}{'...' if len(title) > 60 else ''}"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, page['id'])
            self.page_list.addItem(item)

        self.page_count_label.setText(f"Pages: {len(self.pages)}")

        if self.pages:
            if self.page_list.currentRow() == -1:
                self.page_list.setCurrentRow(0)
                self.display_page(0)
        else:
            self.clear_display()

    def display_page(self, index):
        """Display a page's content"""
        if index < 0 or index >= len(self.pages):
            self.clear_display()
            return

        page = self.pages[index]
        self.current_page_id = page['id']
        self.current_page_index = index
        self.base_url = page.get('url', '')

        # Update document info
        metadata = page.get('metadata', {})
        doc_name = metadata.get('document', 'Unknown')
        page_num = metadata.get('page_number', '')
        self.doc_info_label.setText(f"📄 {doc_name} - Page {page_num}")

        # Get content
        content = page.get('main_text', '') or page.get('raw_html', '')

        # Display formatted text
        self.display_formatted_text(content)

        # Display raw text
        self.raw_text_view.setPlainText(content)

        # Extract links and media from content
        self.links = self.extract_links(content)
        self.media_items = self.extract_media(content)

        # Display links
        self.display_links()

        # Display media
        self.display_media()

        # Reset search
        self.full_text_search.clear()
        self.match_count_label.setText("")
        self.current_matches = []
        self.current_match_index = -1
        self.clear_full_text_highlights()

    def clear_display(self):
        """Clear all display areas"""
        self.text_content_view.clear()
        self.links_view.clear()
        self.raw_text_view.clear()
        self.clear_media_display()
        self.links = []
        self.media_items = []
        self.current_matches = []
        self.current_match_index = -1
        self.match_count_label.setText("")
        self.doc_info_label.setText("")

    def clear_media_display(self):
        """Clear media tab"""
        for i in reversed(range(self.media_layout.count())):
            widget = self.media_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

    def on_page_selected(self, item):
        """Handle page selection from list"""
        page_id = item.data(Qt.UserRole)
        for i, page in enumerate(self.pages):
            if page['id'] == page_id:
                self.display_page(i)
                break

    def on_page_search_changed(self, text):
        """Search through pages"""
        if not text:
            self.load_pages()
            return

        query = text.lower()
        self.page_list.clear()

        for page in self.pages:
            title = page.get('title', '').lower()
            content = page.get('main_text', '').lower()
            if query in title or query in content:
                display = f"🔍 {page.get('title', 'Untitled')[:60]}{'...' if len(page.get('title', '')) > 60 else ''}"
                item = QListWidgetItem(display)
                item.setData(Qt.UserRole, page['id'])
                self.page_list.addItem(item)

        if self.page_list.count() > 0:
            self.page_list.setCurrentRow(0)
            self.display_page(0)
        else:
            self.clear_display()
            self.doc_info_label.setText("No matching pages found")

    def extract_links(self, content):
        """Extract links from text content"""
        links = []
        if not content:
            return links

        # Find URLs in text
        url_pattern = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
        urls = url_pattern.findall(content)

        for url in urls:
            # Try to find context around the URL
            idx = content.find(url)
            start = max(0, idx - 50)
            end = min(len(content), idx + len(url) + 50)
            context = content[start:end].replace('\n', ' ').strip()

            links.append({
                'text': context[:100] if context else url[:50],
                'url': url,
                'html': f'<a href="{url}">{url}</a>'
            })

        return links

    def extract_media(self, content):
        """Extract media from content"""
        media = []
        if not content:
            return media

        # For documents, we'll look for image references in the text
        # This is a simple implementation - can be extended

        # Look for image references in text
        img_pattern = re.compile(r'\[Image: ([^\]]+)\]', re.IGNORECASE)
        images = img_pattern.findall(content)

        for i, img in enumerate(images):
            media.append({
                'type': 'image',
                'src': img,
                'alt': img,
                'html': f'[Image: {img}]',
                'page': self.current_page_index + 1
            })

        return media

    def display_links(self):
        """Display links in the Links tab"""
        if not self.links:
            self.links_view.setText("No links found on this page.")
            return

        html_parts = []
        html_parts.append('<style>')
        html_parts.append('''
            body { 
                font-family: 'Segoe UI', Arial, sans-serif;
                padding: 20px;
                line-height: 1.6;
                color: #2c3e50;
            }
            .link-container {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 12px 16px;
                margin-bottom: 10px;
                background-color: #fafafa;
            }
            .link-container:hover {
                background-color: #f0f4f8;
                border-color: #4CAF50;
            }
            .link-number {
                font-weight: bold;
                color: #4CAF50;
                font-size: 14px;
                margin-right: 8px;
            }
            .link-text {
                font-weight: 600;
                color: #1a1a2e;
                font-size: 13px;
            }
            .link-url {
                display: block;
                color: #2980b9;
                font-size: 12px;
                font-family: 'Consolas', monospace;
                word-break: break-all;
                margin-top: 4px;
                padding: 4px 8px;
                background-color: #f0f8ff;
                border-radius: 4px;
                border-left: 3px solid #2980b9;
            }
            .link-url a {
                color: #2980b9;
                text-decoration: none;
            }
            .link-url a:hover {
                text-decoration: underline;
            }
        ''')
        html_parts.append('</style>')
        html_parts.append(
            '<h2 style="border-bottom: 2px solid #4CAF50; padding-bottom: 8px; margin-bottom: 16px;">🔗 Links Found</h2>')

        for i, link in enumerate(self.links, 1):
            html_parts.append(f'<div class="link-container">')
            html_parts.append(f'<span class="link-number">#{i}</span>')
            html_parts.append(
                f'<span class="link-text">{link["text"][:80]}{"..." if len(link["text"]) > 80 else ""}</span>')
            html_parts.append(
                f'<div class="link-url">🔗 <a href="{link["url"]}" target="_blank">{link["url"]}</a></div>')
            html_parts.append('</div>')

        self.links_view.setHtml('\n'.join(html_parts))

    def display_media(self):
        """Display media in the Media tab"""
        self.clear_media_display()

        if not self.media_items:
            label = QLabel("No media found in this document.")
            label.setStyleSheet("padding: 20px; color: #666;")
            self.media_layout.addWidget(label)
            return

        for i, media in enumerate(self.media_items):
            frame = QFrame()
            frame.setStyleSheet("""
                QFrame {
                    border: 1px solid #ddd;
                    border-radius: 6px;
                    padding: 12px;
                    margin: 6px;
                    background-color: #fafafa;
                }
                QFrame:hover {
                    background-color: #f0f0f0;
                    border-color: #bbb;
                }
            """)
            layout = QVBoxLayout(frame)

            # Media info
            info_label = QLabel(f"[{i + 1}] {media['type'].upper()} - Page {media.get('page', 'Unknown')}")
            info_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #333;")
            layout.addWidget(info_label)

            src_label = QLabel(f"Source: {media['src'][:80]}{'...' if len(media['src']) > 80 else ''}")
            src_label.setStyleSheet("font-size: 10px; color: #666; word-wrap: break-word;")
            src_label.setWordWrap(True)
            layout.addWidget(src_label)

            if media.get('alt'):
                alt_label = QLabel(f"Alt: {media['alt'][:60]}{'...' if len(media['alt']) > 60 else ''}")
                alt_label.setStyleSheet("font-size: 10px; color: #888;")
                layout.addWidget(alt_label)

            # Copy button
            copy_btn = QPushButton("📋 Copy Text")
            copy_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border: none;
                    padding: 4px 12px;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #1976D2; }
            """)
            copy_btn.clicked.connect(lambda checked, m=media: QGuiApplication.clipboard().setText(m['src']))
            layout.addWidget(copy_btn)

            self.media_layout.addWidget(frame)

    def display_formatted_text(self, content):
        """Display text content with formatting"""
        if not content:
            self.text_content_view.clear()
            return

        # Convert text to HTML with basic formatting
        lines = content.split('\n')
        html_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                html_lines.append('<br>')
                continue

            # Check if it's a heading (starts with # or is all caps)
            if line.startswith('#') or (line.isupper() and len(line) > 10):
                level = min(line.count('#') + 1, 6)
                text = line.lstrip('#').strip()
                html_lines.append(f'<h{level}>{text}</h{level}>')
            else:
                # Check for URLs and make them clickable
                line = re.sub(
                    r'(https?://[^\s<>"{}|\\^`\[\]]+)',
                    r'<a href="\1" target="_blank">\1</a>',
                    line
                )
                html_lines.append(f'<p>{line}</p>')

        html_content = '\n'.join(html_lines)
        self._display_html_content(html_content)

    # ============ DATA TABLE INTEGRATION ============

    def load_table_projects(self):
        """Load all data table projects for the dropdown"""
        self.table_projects = self.db.get_all_data_table_projects()
        self.project_combo.blockSignals(True)
        self.project_combo.clear()

        self.project_combo.addItem("Select a Data Table Project...", None)
        for project in self.table_projects:
            self.project_combo.addItem(f"📊 {project['name']}", project['id'])

        self.project_combo.blockSignals(False)
        self.column_combo.clear()
        self.column_combo.addItem("Select a column...", None)

    def on_project_combo_changed(self, index):
        """Handle project selection change"""
        project_id = self.project_combo.currentData()
        if project_id:
            self.load_table_columns(project_id)
        else:
            self.column_combo.clear()
            self.column_combo.addItem("Select a column...", None)
            self.insert_btn.setEnabled(False)
        self.on_selection_changed()

    def load_table_columns(self, project_id):
        """Load columns for the selected data table project"""
        self.column_combo.blockSignals(True)
        self.column_combo.clear()
        self.column_combo.addItem("Select a column...", None)

        if project_id:
            project = next((p for p in self.table_projects if p['id'] == project_id), None)
            if project:
                columns = self.db.get_table_column_names(project['data_path'])
                for col in columns:
                    self.column_combo.addItem(col, col)

        self.column_combo.blockSignals(False)
        self.on_selection_changed()

    def insert_selected_text(self):
        """Insert selected text into the data table"""
        current_tab = self.tabs.currentWidget()
        if not current_tab:
            QMessageBox.warning(self, "No Selection", "No text selected to insert.")
            return

        # Get selected text
        selected_text = ""
        if hasattr(current_tab, 'textCursor'):
            cursor = current_tab.textCursor()
            if cursor.hasSelection():
                selected_text = cursor.selectedText()
            else:
                selected_text = current_tab.toPlainText()
        else:
            selected_text = current_tab.toPlainText()

        if not selected_text or not selected_text.strip():
            QMessageBox.warning(self, "No Content", "No text to insert.")
            return

        # Get project and column
        project_id = self.project_combo.currentData()
        column_name = self.column_combo.currentData()

        if not project_id or not column_name:
            QMessageBox.warning(self, "Incomplete", "Please select both a project and a column.")
            return

        project = next((p for p in self.table_projects if p['id'] == project_id), None)
        if not project:
            QMessageBox.warning(self, "Error", "Selected project not found.")
            return

        # Get column config
        column_config = project.get('metadata', {}).get('column_config', [])
        col_config = next((c for c in column_config if c['name'] == column_name), None)
        if not col_config:
            QMessageBox.warning(self, "Error", f"Column '{column_name}' not found in project.")
            return

        # Check if unique
        if col_config.get('unique', False):
            conn = sqlite3.connect(project['data_path'])
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM data WHERE \"{column_name}\" = ?", (selected_text,))
            count = cursor.fetchone()[0]
            conn.close()

            if count > 0:
                QMessageBox.warning(
                    self,
                    "Duplicate Value",
                    f"The value '{selected_text[:50]}...' already exists in column '{column_name}'.\n\n"
                    "This column requires unique values."
                )
                return

        # Get database column order
        conn = sqlite3.connect(project['data_path'])
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(data)")
        db_columns = cursor.fetchall()
        conn.close()

        db_column_names = []
        for col in db_columns:
            col_name = col[1]
            if col_name not in ['id', '_row_created_at', '_row_updated_at']:
                db_column_names.append(col_name)

        # Build row data
        col_to_value = {}
        for col_name in db_column_names:
            if col_name == column_name:
                col_to_value[col_name] = selected_text
            else:
                col_cfg = next((c for c in column_config if c['name'] == col_name), None)
                if col_cfg:
                    col_type = col_cfg.get('type', 'text')
                    if col_type == 'integer':
                        col_to_value[col_name] = 0
                    elif col_type == 'float':
                        col_to_value[col_name] = 0.0
                    elif col_type == 'boolean':
                        col_to_value[col_name] = 0
                    else:
                        col_to_value[col_name] = 'must-be-updated'
                else:
                    col_to_value[col_name] = 'must-be-updated'

        row_data = [col_to_value.get(col_name, 'must-be-updated') for col_name in db_column_names]

        # Add the row
        try:
            self.db.add_table_row(project['data_path'], row_data)
            self.update_status(f"Inserted '{selected_text[:50]}...' into {project['name']}.{column_name}")
            QMessageBox.information(
                self,
                "Success",
                f"Successfully inserted text into:\n\n"
                f"Project: {project['name']}\n"
                f"Column: {column_name}\n"
                f"Text: {selected_text[:100]}{'...' if len(selected_text) > 100 else ''}"
            )
            if hasattr(self.parent_app, 'refresh_table_view'):
                self.parent_app.refresh_table_view(project_id)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to insert row:\n{str(e)}")

    # ============ PAGE MANAGEMENT ============

    def rename_page(self):
        """Rename the current page"""
        if self.current_page_index < 0 or self.current_page_index >= len(self.pages):
            QMessageBox.warning(self, "Error", "No page selected.")
            return

        page = self.pages[self.current_page_index]
        current_title = page.get('title', 'Untitled')

        new_title, ok = QInputDialog.getText(
            self,
            "Edit Page Name",
            "Enter new page name:",
            text=current_title
        )

        if ok and new_title:
            conn = sqlite3.connect(self.data_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE pages SET title = ? WHERE id = ?", (new_title, page['id']))
            conn.commit()
            conn.close()

            self.pages[self.current_page_index]['title'] = new_title
            self.load_pages()

            for i, p in enumerate(self.pages):
                if p['id'] == page['id']:
                    self.page_list.setCurrentRow(i)
                    self.display_page(i)
                    break

            self.update_status(f"✅ Page renamed to: {new_title}")

    def delete_current_page(self):
        """Delete the current page"""
        if self.current_page_index < 0 or not self.pages:
            QMessageBox.warning(self, "Error", "No page selected.")
            return

        page = self.pages[self.current_page_index]
        title = page.get('title', 'Untitled')

        reply = QMessageBox.question(
            self,
            "Delete Page",
            f"Are you sure you want to delete page:\n\n'{title}'\n\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            conn = sqlite3.connect(self.data_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pages WHERE id = ?", (page['id'],))
            conn.commit()
            conn.close()

            self.load_pages()

            if not self.pages:
                self.clear_display()
            else:
                self.page_list.setCurrentRow(0)
                self.display_page(0)

            self.update_status(f"🗑️ Deleted page: {title}")

    def import_documents(self):
        """Import documents into the project"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Documents",
            "",
            "Documents (*.txt *.pdf *.docx *.doc);;Text Files (*.txt);;PDF Files (*.pdf);;Word Documents (*.docx *.doc)"
        )

        if not file_paths:
            return

        # Show progress dialog
        progress = QProgressDialog("Processing documents...", "Cancel", 0, len(file_paths), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        # Process documents in thread
        self.processor = DocumentProcessor(file_paths, self.data_path)
        self.processor.progress.connect(lambda current, total: progress.setValue(current + 1))
        self.processor.finished.connect(lambda pages: self.on_documents_processed(pages, progress))
        self.processor.error.connect(lambda error: self.on_document_error(error, progress))
        self.processor.start()

    def on_documents_processed(self, pages, progress):
        """Handle documents processed"""
        progress.setValue(progress.maximum())
        progress.close()

        self.load_pages()

        if pages:
            self.page_list.setCurrentRow(0)
            self.display_page(0)
            QMessageBox.information(self, "Success",
                                    f"Successfully processed {len(pages)} pages from {len(set(p.get('document', '') for p in pages))} documents.")
        else:
            QMessageBox.warning(self, "Warning", "No content extracted from the documents.")

    def on_document_error(self, error, progress):
        """Handle document processing error"""
        progress.close()
        QMessageBox.critical(self, "Error", f"Failed to process documents:\n{error}")

    # ============ TEXT PROCESSING ============

    def update_text_display(self, display_type):
        """Update text content based on selected display type"""
        if self.current_page_index < 0 or self.current_page_index >= len(self.pages):
            return

        page = self.pages[self.current_page_index]
        content = page.get('main_text', '') or page.get('raw_html', '')

        if not content:
            self.text_content_view.clear()
            return

        if display_type == "Text Organized":
            self.display_formatted_text(content)
            return

        # Process content for other display types
        self._display_transformed_content(content, display_type)

    def _display_transformed_content(self, content, display_type):
        """Display transformed content based on display type"""
        if not content:
            self.text_content_view.clear()
            return

        # Clean up text
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        all_text = ' '.join(lines)

        if display_type == "Text Jumble":
            text = ' '.join(all_text.split())
            self.text_content_view.setPlainText(text)

        elif display_type == "Text Elements":
            # Treat each paragraph as an element
            elements = []
            for i, line in enumerate(lines, 1):
                if len(line) > 5:
                    elements.append(f"[PARAGRAPH {i}] {line}")
            text = "\n\n".join(elements)
            self.text_content_view.setPlainText(text)

        elif display_type == "Text Headers":
            # Look for lines that look like headers
            headers = [line for line in lines if line.isupper() and len(line) > 5 or line.startswith('#')]
            text = "\n\n".join(headers)
            self.text_content_view.setPlainText(text)

        elif display_type == "Text Paragraphs":
            text = "\n\n".join(lines)
            self.text_content_view.setPlainText(text)

        elif display_type == "Text Sentences":
            sentences = re.split(r'(?<=[.!?])\s+', all_text)
            sentences = [s.strip() for s in sentences if s.strip() and len(s) > 5]
            text = "\n\n".join(sentences)
            self.text_content_view.setPlainText(text)

        elif display_type == "Text Unique Words":
            words = re.findall(r'\b[a-z]+\b', all_text.lower())
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'without',
                          'by'}
            words = [w for w in words if w not in stop_words and len(w) > 2]
            unique_words = list(dict.fromkeys(words))
            text = "\n".join(unique_words)
            self.text_content_view.setPlainText(text)

        elif display_type == "Text Repeated Words":
            words = re.findall(r'\b[a-z]+\b', all_text.lower())
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'without',
                          'by'}
            words = [w for w in words if w not in stop_words and len(w) > 2]
            word_counts = Counter(words)
            repeated = [(word, count) for word, count in word_counts.items() if count > 1]
            repeated.sort(key=lambda x: x[1], reverse=True)
            text = "\n".join([f"{word}: {count}" for word, count in repeated[:50]])
            self.text_content_view.setPlainText(text)

        elif display_type == "Text Questions":
            questions = re.findall(r'[^.!?]*\?', all_text)
            questions = [q.strip() for q in questions if q.strip() and len(q) > 5]
            text = "\n".join(questions)
            self.text_content_view.setPlainText(text)

        else:
            self.text_content_view.setPlainText(all_text)

    def _display_html_content(self, html_content):
        """Display HTML content"""
        if not html_content:
            self.text_content_view.clear()
            return

        font_family = self.font_combo.currentText()
        font_size = self.font_size_spin.value()
        line_height = self.line_height_spin.value()
        word_spacing = 2.0

        doc = self.text_content_view.document()
        doc.setDefaultStyleSheet(f"""
            body {{
                font-family: "{font_family}";
                font-size: {font_size}pt;
                line-height: {line_height};
                word-spacing: {word_spacing}px;
                padding: 30px 40px;
                max-width: 900px;
                margin: 0 auto;
                color: #2c3e50;
                background-color: #ffffff;
            }}
            h1 {{
                font-size: {font_size + 12}pt;
                font-weight: bold;
                margin-top: 28px;
                margin-bottom: 14px;
                color: #1a1a2e;
                border-bottom: 3px solid #3498db;
                padding-bottom: 10px;
            }}
            h2 {{
                font-size: {font_size + 8}pt;
                font-weight: bold;
                margin-top: 24px;
                margin-bottom: 12px;
                color: #2c3e50;
                border-bottom: 2px solid #ecf0f1;
                padding-bottom: 8px;
            }}
            h3 {{
                font-size: {font_size + 4}pt;
                font-weight: bold;
                margin-top: 20px;
                margin-bottom: 10px;
                color: #34495e;
            }}
            h4 {{
                font-size: {font_size + 2}pt;
                font-weight: bold;
                margin-top: 16px;
                margin-bottom: 8px;
                color: #445566;
            }}
            h5, h6 {{
                font-size: {font_size}pt;
                font-weight: bold;
                margin-top: 14px;
                margin-bottom: 6px;
                color: #556677;
            }}
            p {{
                margin-top: 12px;
                margin-bottom: 12px;
                line-height: {line_height};
                text-align: justify;
            }}
            a {{
                color: #2980b9;
                text-decoration: underline;
                cursor: pointer;
                font-weight: 500;
            }}
            a:hover {{ color: #1a5276; }}
            ul, ol {{
                margin-top: 10px;
                margin-bottom: 10px;
                padding-left: 30px;
            }}
            li {{
                margin-top: 4px;
                margin-bottom: 4px;
                line-height: {line_height};
            }}
            blockquote {{
                margin: 14px 20px;
                padding: 12px 20px;
                border-left: 4px solid #3498db;
                background-color: #f8f9fa;
                font-style: italic;
            }}
            code {{
                background-color: #f4f4f4;
                padding: 2px 6px;
                border-radius: 4px;
                font-family: "Consolas", monospace;
                font-size: 0.9em;
                color: #c0392b;
            }}
            pre {{
                background-color: #f4f4f4;
                padding: 12px 16px;
                border-radius: 4px;
                overflow-x: auto;
                font-family: "Consolas", monospace;
                font-size: 0.9em;
                margin: 12px 0;
            }}
        """)

        styled_html = f"""
        <div style="font-family: '{font_family}'; font-size: {font_size}pt; line-height: {line_height}; word-spacing: {word_spacing}px; padding: 10px;">
            {html_content}
        </div>
        """

        self.text_content_view.setHtml(styled_html)

    def update_formatting(self):
        """Update formatting when controls change"""
        if self.current_page_index >= 0 and self.current_page_index < len(self.pages):
            page = self.pages[self.current_page_index]
            content = page.get('main_text', '') or page.get('raw_html', '')
            self.display_formatted_text(content)

    # ============ COPY FUNCTION ============

    def copy_current_view(self):
        """Copy content from current tab"""
        current_tab = self.tabs.currentWidget()
        if current_tab:
            if isinstance(current_tab, QTextBrowser):
                text = current_tab.toPlainText()
            else:
                text = current_tab.toPlainText()

            if text:
                QGuiApplication.clipboard().setText(text)
                tab_name = self.tabs.tabText(self.tabs.currentIndex())
                self.update_status(f"Copied {tab_name} content to clipboard")
            else:
                QMessageBox.information(self, "Copy", "No content to copy.")

    # ============ LINK HANDLING ============

    def on_link_clicked(self, url):
        """Handle link clicks in text content view"""
        url_str = url.toString()
        webbrowser.open(url_str)
        self.update_status(f"Opened in browser: {url_str}")

    # ============ SEARCH ============

    def search_full_text(self, text):
        """Search for text in the current tab's content"""
        if not text:
            self.match_count_label.setText("")
            self.clear_full_text_highlights()
            self.current_matches = []
            self.current_match_index = -1
            return

        current_tab = self.tabs.currentWidget()
        if not current_tab or not hasattr(current_tab, 'document'):
            return

        doc = current_tab.document()
        self.clear_full_text_highlights()

        cursor = doc.find(text)
        matches = []

        while not cursor.isNull():
            matches.append(cursor)
            cursor = doc.find(text, cursor)

        if matches:
            self.match_count_label.setText(f"{len(matches)} matches")
            self.highlight_full_text_match(matches[0])
            self.current_matches = matches
            self.current_match_index = 0
            if hasattr(current_tab, 'setTextCursor'):
                current_tab.setTextCursor(matches[0])
                current_tab.ensureCursorVisible()
        else:
            self.match_count_label.setText("No matches")
            self.current_matches = []
            self.current_match_index = -1

    def clear_full_text_highlights(self):
        """Clear all highlights from the current tab"""
        current_tab = self.tabs.currentWidget()
        if not current_tab or not hasattr(current_tab, 'document'):
            return

        doc = current_tab.document()
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.Document)
        cursor.setCharFormat(QTextCharFormat())

    def highlight_full_text_match(self, cursor):
        """Highlight a specific match"""
        format = QTextCharFormat()
        format.setBackground(QColor(255, 255, 0))
        cursor.mergeCharFormat(format)

    def find_next_full_text(self):
        """Find the next match in the current tab"""
        if not hasattr(self, 'current_matches') or not self.current_matches:
            return

        current_tab = self.tabs.currentWidget()
        if not current_tab:
            return

        if self.current_match_index < len(self.current_matches) - 1:
            self.current_match_index += 1
            self.highlight_full_text_match(self.current_matches[self.current_match_index])
            if hasattr(current_tab, 'setTextCursor'):
                current_tab.setTextCursor(self.current_matches[self.current_match_index])
                current_tab.ensureCursorVisible()
            self.match_count_label.setText(f"{self.current_match_index + 1} of {len(self.current_matches)}")
        else:
            self.current_match_index = 0
            self.highlight_full_text_match(self.current_matches[0])
            if hasattr(current_tab, 'setTextCursor'):
                current_tab.setTextCursor(self.current_matches[0])
                current_tab.ensureCursorVisible()
            self.match_count_label.setText(f"1 of {len(self.current_matches)}")

    def find_prev_full_text(self):
        """Find the previous match in the current tab"""
        if not hasattr(self, 'current_matches') or not self.current_matches:
            return

        current_tab = self.tabs.currentWidget()
        if not current_tab:
            return

        if self.current_match_index > 0:
            self.current_match_index -= 1
            self.highlight_full_text_match(self.current_matches[self.current_match_index])
            if hasattr(current_tab, 'setTextCursor'):
                current_tab.setTextCursor(self.current_matches[self.current_match_index])
                current_tab.ensureCursorVisible()
            self.match_count_label.setText(f"{self.current_match_index + 1} of {len(self.current_matches)}")
        else:
            self.current_match_index = len(self.current_matches) - 1
            self.highlight_full_text_match(self.current_matches[self.current_match_index])
            if hasattr(current_tab, 'setTextCursor'):
                current_tab.setTextCursor(self.current_matches[self.current_match_index])
                current_tab.ensureCursorVisible()
            self.match_count_label.setText(f"{len(self.current_matches)} of {len(self.current_matches)}")

    # ============ SELECTION ============

    def on_selection_changed(self):
        """Handle selection changes in any tab"""
        current_tab = self.tabs.currentWidget()
        if not current_tab:
            self.insert_btn.setEnabled(False)
            return

        has_selection = False
        if hasattr(current_tab, 'textCursor'):
            cursor = current_tab.textCursor()
            has_selection = cursor.hasSelection()

        project_selected = self.project_combo.currentData() is not None
        column_selected = self.column_combo.currentData() is not None

        self.insert_btn.setEnabled(has_selection and project_selected and column_selected)

    def on_tab_changed(self, index):
        """Handle tab changes"""
        self.on_selection_changed()

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard shortcuts"""
        if (self.page_list.hasFocus() or not self.focusWidget()) and (
                event.key() == Qt.Key_Up or event.key() == Qt.Key_Down):
            current_row = self.page_list.currentRow()
            if event.key() == Qt.Key_Up:
                new_row = max(0, current_row - 1)
            else:
                new_row = min(self.page_list.count() - 1, current_row + 1)

            if new_row != current_row:
                self.page_list.setCurrentRow(new_row)
                item = self.page_list.item(new_row)
                if item:
                    page_id = item.data(Qt.UserRole)
                    for i, page in enumerate(self.pages):
                        if page['id'] == page_id:
                            self.display_page(i)
                            break
            return

        if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
            if self.insert_btn.isEnabled():
                self.insert_selected_text()
            return

        super().keyPressEvent(event)