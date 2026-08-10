import os
import sys
import sqlite3
import json
import re
import webbrowser
import time
import random
from collections import Counter
from urllib.parse import urljoin

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QComboBox, QCheckBox,
    QTextEdit, QListWidget, QListWidgetItem, QSplitter,
    QTabWidget, QScrollArea, QFrame, QMessageBox,
    QFileDialog, QDialog, QSpinBox, QDoubleSpinBox,
    QTextBrowser, QSizePolicy, QGroupBox, QCompleter, QRadioButton
)
from PySide6.QtGui import (
    QClipboard, QGuiApplication, QFont, QColor,
    QKeyEvent, QTextCursor, QTextCharFormat,
    QFontDatabase, QSyntaxHighlighter, QPixmap, QTextDocument
)
from PySide6.QtWebEngineWidgets import QWebEngineView

from bs4 import BeautifulSoup
from readability import Document
from fake_useragent import UserAgent
import requests
import hashlib

# Import studio utilities
from utils.web_extractors import WebExtractor
from utils.file_handlers import FileHandler
from models.data_types import ColumnType


class FetchThread(QThread):
    """Thread for fetching and extracting web pages"""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, url, data_path):
        super().__init__()
        self.url = url
        self.data_path = data_path

    def run(self):
        try:
            extractor = WebExtractor()
            data = extractor.extract_page(self.url)

            # Save to database
            page_id = self.save_to_database(self.data_path, data)
            data['id'] = page_id

            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))

    def save_to_database(self, data_path, extracted_data):
        """Save extracted data to the project database"""
        if not os.path.exists(data_path):
            return -1

        conn = sqlite3.connect(data_path)
        cursor = conn.cursor()

        # Calculate hash for deduplication
        main_text = extracted_data.get('main_text', '')
        if main_text:
            content_hash = hashlib.md5(main_text.encode()).hexdigest()
        else:
            # If no main_text, use URL + title for hash
            url = extracted_data.get('url', '')
            title = extracted_data.get('title', '')
            content_hash = hashlib.md5(f"{url}_{title}".encode()).hexdigest()

        print(f"Content hash: {content_hash}")
        print(f"Title: {extracted_data.get('title', 'No title')}")

        # Check if page already exists
        cursor.execute("SELECT id FROM pages WHERE content_hash = ?", (content_hash,))
        existing = cursor.fetchone()
        if existing:
            page_id = existing[0]
            print(f"Page already exists with ID: {page_id}")
            conn.close()
            return page_id

        # Insert page
        cursor.execute('''
            INSERT INTO pages (url, title, main_text, main_html, metadata, raw_html, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            extracted_data.get('url', ''),
            extracted_data.get('title', ''),
            main_text,
            extracted_data.get('main_html', ''),
            json.dumps(extracted_data.get('metadata', {})),
            extracted_data.get('raw_html', ''),
            content_hash
        ))
        page_id = cursor.lastrowid

        # Insert elements
        for i, elem in enumerate(extracted_data.get('elements', [])):
            cursor.execute('''
                INSERT INTO elements (page_id, element_type, position, content, html_fragment, attributes)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                page_id,
                elem.get('type', 'text'),
                i,
                elem.get('content', ''),
                elem.get('html', ''),
                json.dumps(elem.get('attributes', {}))
            ))

        conn.commit()
        conn.close()

        print(f"Saved new page with ID: {page_id}")

        return page_id

class HTMLHighlighter(QSyntaxHighlighter):
    """HTML syntax highlighter with VSCode-like colors"""

    def __init__(self, parent):
        super().__init__(parent)
        self.highlighting_rules = []

        # Tags (blue)
        tag_format = QTextCharFormat()
        tag_format.setForeground(QColor(86, 156, 214))
        tag_format.setFontWeight(QFont.Bold)
        self.highlighting_rules.append((re.compile(r'&lt;[\/]?[a-zA-Z][a-zA-Z0-9]*'), tag_format))

        # Attributes (red)
        attr_format = QTextCharFormat()
        attr_format.setForeground(QColor(220, 120, 120))
        self.highlighting_rules.append((re.compile(r'\b[a-zA-Z\-]+(?==)'), attr_format))

        # Attribute values (orange)
        value_format = QTextCharFormat()
        value_format.setForeground(QColor(206, 145, 120))
        self.highlighting_rules.append((re.compile(r'"[^"]*"'), value_format))
        self.highlighting_rules.append((re.compile(r"'[^']*'"), value_format))

        # Comments (green)
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor(106, 153, 85))
        comment_format.setFontItalic(True)
        self.highlighting_rules.append((re.compile(r'&lt;!--.*?--&gt;'), comment_format))

        # DOCTYPE (gray)
        doctype_format = QTextCharFormat()
        doctype_format.setForeground(QColor(128, 128, 128))
        self.highlighting_rules.append((re.compile(r'&lt;!DOCTYPE[^&gt;]*&gt;'), doctype_format))

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)


class CSSHighlighter(QSyntaxHighlighter):
    """CSS syntax highlighter with VSCode-like colors"""

    def __init__(self, parent):
        super().__init__(parent)
        self.highlighting_rules = []

        # Selectors (yellow)
        selector_format = QTextCharFormat()
        selector_format.setForeground(QColor(220, 220, 170))
        self.highlighting_rules.append((re.compile(r'[a-zA-Z][a-zA-Z0-9\-]*(?=\s*\{)'), selector_format))

        # Properties (red)
        prop_format = QTextCharFormat()
        prop_format.setForeground(QColor(220, 120, 120))
        self.highlighting_rules.append((re.compile(r'[a-zA-Z\-]+(?=\s*:)'), prop_format))

        # Values (orange)
        value_format = QTextCharFormat()
        value_format.setForeground(QColor(206, 145, 120))
        self.highlighting_rules.append((re.compile(r':\s*[^;]+'), value_format))

        # Comments (green)
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor(106, 153, 85))
        comment_format.setFontItalic(True)
        self.highlighting_rules.append((re.compile(r'/\*.*?\*/'), comment_format))

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)


class JavaScriptHighlighter(QSyntaxHighlighter):
    """JavaScript syntax highlighter with VSCode-like colors"""

    def __init__(self, parent):
        super().__init__(parent)
        self.highlighting_rules = []

        # Keywords (blue)
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor(86, 156, 214))
        keyword_format.setFontWeight(QFont.Bold)
        keywords = ['function', 'var', 'let', 'const', 'if', 'else', 'for', 'while', 'return',
                    'class', 'new', 'this', 'try', 'catch', 'finally', 'throw', 'switch', 'case',
                    'break', 'continue', 'do', 'typeof', 'instanceof', 'void', 'delete', 'import',
                    'export', 'default', 'from', 'async', 'await', 'yield', 'super', 'extends']
        self.highlighting_rules.append((re.compile(r'\b(' + '|'.join(keywords) + r')\b'), keyword_format))

        # Strings (orange)
        string_format = QTextCharFormat()
        string_format.setForeground(QColor(206, 145, 120))
        self.highlighting_rules.append((re.compile(r'"[^"]*"'), string_format))
        self.highlighting_rules.append((re.compile(r"'[^']*'"), string_format))
        self.highlighting_rules.append((re.compile(r'`[^`]*`'), string_format))

        # Comments (green)
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor(106, 153, 85))
        comment_format.setFontItalic(True)
        self.highlighting_rules.append((re.compile(r'//.*'), comment_format))
        self.highlighting_rules.append((re.compile(r'/\*.*?\*/'), comment_format))

        # Numbers (cyan)
        number_format = QTextCharFormat()
        number_format.setForeground(QColor(181, 206, 168))
        self.highlighting_rules.append((re.compile(r'\b\d+\b'), number_format))

        # Booleans (blue)
        bool_format = QTextCharFormat()
        bool_format.setForeground(QColor(86, 156, 214))
        bool_format.setFontWeight(QFont.Bold)
        self.highlighting_rules.append((re.compile(r'\b(true|false|null|undefined)\b'), bool_format))

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)


class MediaViewerDialog(QDialog):
    """Dialog for viewing media content with download option"""

    def __init__(self, media_item, base_url="", parent=None):
        super().__init__(parent)
        self.media_item = media_item
        self.base_url = base_url

        file_ext = self.get_file_extension(media_item.get('src', ''))
        ext_display = f" ({file_ext.upper()})" if file_ext else ""

        self.setWindowTitle(f"Media Viewer - {media_item.get('type', 'UNKNOWN').upper()}{ext_display}")
        self.resize(700, 600)
        self.setup_ui()
        self.load_media()

    def get_file_extension(self, url):
        if not url:
            return None
        if url.startswith('data:'):
            match = re.match(r'data:image/(\w+);', url)
            if match:
                return match.group(1)
            return 'base64'
        url_path = url.split('?')[0]
        filename = url_path.split('/')[-1]
        if '.' in filename:
            ext = filename.split('.')[-1].lower()
            if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico',
                       'mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv', 'pdf', 'doc', 'docx']:
                return ext
        return None

    def is_base64_data(self, url):
        return url.startswith('data:')

    def is_video_platform(self, url):
        if not url:
            return False
        url_lower = url.lower()
        return ('youtube.com' in url_lower or 'youtu.be' in url_lower or
                'vimeo.com' in url_lower or 'dailymotion.com' in url_lower or
                'twitch.tv' in url_lower or 'youtube-nocookie.com' in url_lower)

    def get_embed_url(self, url):
        if not url:
            return None
        if 'youtube.com/embed/' in url:
            return url
        elif 'youtube.com/watch?v=' in url or 'youtu.be/' in url:
            if 'youtube.com/watch?v=' in url:
                video_id = url.split('v=')[1].split('&')[0]
            else:
                video_id = url.split('/')[-1].split('?')[0]
            return f"https://www.youtube.com/embed/{video_id}"
        elif 'youtube.com/shorts/' in url:
            video_id = url.split('/')[-1].split('?')[0]
            return f"https://www.youtube.com/embed/{video_id}"
        elif 'vimeo.com/' in url:
            video_id = url.split('/')[-1].split('?')[0]
            return f"https://player.vimeo.com/video/{video_id}"
        elif 'dailymotion.com/video/' in url:
            video_id = url.split('/')[-1].split('_')[0]
            return f"https://www.dailymotion.com/embed/video/{video_id}"
        elif 'embed' in url or 'player' in url:
            return url
        return None

    def setup_ui(self):
        layout = QVBoxLayout(self)

        src_display = self.media_item.get('src', '')[:100]
        info_label = QLabel(f"Type: {self.media_item.get('type', 'UNKNOWN').upper()}\nSource: {src_display}")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("padding: 8px; background-color: #f5f5f5; border-radius: 4px;")
        layout.addWidget(info_label)

        self.display_area = QWidget()
        self.display_layout = QVBoxLayout(self.display_area)
        self.display_layout.setAlignment(Qt.AlignCenter)

        scroll = QScrollArea()
        scroll.setWidget(self.display_area)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: 1px solid #ddd; border-radius: 4px; background-color: #f0f0f0;")
        layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        download_btn = QPushButton("💾 Download")
        download_btn.clicked.connect(self.download_media)
        download_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #218838; }
        """)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #5a6268; }
        """)
        btn_layout.addWidget(download_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def load_media(self):
        src = self.media_item.get('src', '')
        media_type = self.media_item.get('type', '')

        self.clear_display()

        if self.is_base64_data(src):
            self.load_base64_media(src, media_type)
            return

        if self.is_video_platform(src):
            self.load_video_platform(src)
            return

        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/') and self.base_url:
            src = urljoin(self.base_url, src)

        try:
            if media_type == 'image':
                response = requests.get(src, timeout=10)
                pixmap = QPixmap()
                pixmap.loadFromData(response.content)
                if not pixmap.isNull():
                    scaled = pixmap.scaled(500, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    label = QLabel()
                    label.setPixmap(scaled)
                    label.setAlignment(Qt.AlignCenter)
                    self.display_layout.addWidget(label)
                else:
                    self.show_error("Failed to load image")
            else:
                self.show_info(f"{media_type.upper()} content:\n\n{src}\n\n(Click download to save)")
        except Exception as e:
            self.show_error(f"Error loading media:\n{str(e)}")

    def clear_display(self):
        for i in reversed(range(self.display_layout.count())):
            widget = self.display_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

    def load_base64_media(self, src, media_type):
        try:
            if media_type == 'image':
                import base64
                match = re.match(r'data:image/(\w+);base64,(.+)', src)
                if match:
                    image_format = match.group(1)
                    base64_data = match.group(2)
                    image_data = base64.b64decode(base64_data)
                    pixmap = QPixmap()
                    pixmap.loadFromData(image_data)
                    if not pixmap.isNull():
                        scaled = pixmap.scaled(500, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        label = QLabel()
                        label.setPixmap(scaled)
                        label.setAlignment(Qt.AlignCenter)
                        self.display_layout.addWidget(label)
                        info = QLabel(f"Base64 Image (Format: {image_format.upper()})")
                        info.setStyleSheet("color: #666; font-size: 10px; margin-top: 8px;")
                        info.setAlignment(Qt.AlignCenter)
                        self.display_layout.addWidget(info)
                    else:
                        self.show_error("Failed to decode base64 image")
                else:
                    self.show_error("Invalid base64 data format")
            else:
                self.show_info("Base64 content (non-image):\n\nDownload to view")
        except Exception as e:
            self.show_error(f"Error loading base64 media:\n{str(e)}")

    def load_video_platform(self, src):
        embed_url = self.get_embed_url(src)
        if not embed_url:
            self.show_error(f"Could not generate embed URL for this platform.\n\nURL: {src}")
            return

        try:
            web_view = QWebEngineView()
            web_view.setUrl(QUrl(embed_url))
            web_view.setMinimumHeight(400)

            platform = "Video"
            if 'youtube' in embed_url.lower():
                platform = "YouTube"
            elif 'vimeo' in embed_url.lower():
                platform = "Vimeo"
            elif 'dailymotion' in embed_url.lower():
                platform = "Dailymotion"

            info = QLabel(f"🎬 {platform} Embedded Video")
            info.setStyleSheet("padding: 8px; background-color: #f8f8f8; border-radius: 4px; font-weight: bold;")
            info.setWordWrap(True)
            self.display_layout.addWidget(info)
            self.display_layout.addWidget(web_view)
        except ImportError:
            self.show_info(f"Video from platform:\n\n{src}\n\nEmbed URL: {embed_url}\n\nDownload to save")
        except Exception as e:
            self.show_error(f"Error loading video:\n{str(e)}\n\nEmbed URL: {embed_url}")

    def show_error(self, message):
        label = QLabel(f"❌ {message}")
        label.setStyleSheet("color: #d9534f; font-size: 14px; padding: 20px;")
        label.setAlignment(Qt.AlignCenter)
        self.display_layout.addWidget(label)

    def show_info(self, message):
        label = QLabel(f"ℹ️ {message}")
        label.setStyleSheet("color: #666; font-size: 14px; padding: 20px;")
        label.setAlignment(Qt.AlignCenter)
        self.display_layout.addWidget(label)

    def download_media(self):
        src = self.media_item.get('src', '')

        if self.is_base64_data(src):
            self.download_base64_media(src)
            return

        if self.media_item.get('type') == 'iframe':
            reply = QMessageBox.question(
                self, "Download Video",
                "This is an embedded video. The video itself may not be directly downloadable.\n\n"
                "Do you want to open it in your browser instead?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                webbrowser.open(src)
            return

        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/') and self.base_url:
            src = urljoin(self.base_url, src)

        filename = src.split('/')[-1].split('?')[0]
        if not filename:
            filename = f"{self.media_item.get('type', 'media')}_download"

        file_path, _ = QFileDialog.getSaveFileName(self, "Save Media", filename, "All Files (*.*)")

        if file_path:
            try:
                time.sleep(random.uniform(0.5, 1.5))
                response = requests.get(src, timeout=30)
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                QMessageBox.information(self, "Success", f"Media saved to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to download:\n{str(e)}")

    def download_base64_media(self, src):
        try:
            import base64
            match = re.match(r'data:image/(\w+);base64,(.+)', src)
            if match:
                image_format = match.group(1)
                base64_data = match.group(2)
                image_data = base64.b64decode(base64_data)
                filename = f"base64_image.{image_format}"
                file_path, _ = QFileDialog.getSaveFileName(self, "Save Base64 Image", filename, f"*.{image_format}")
                if file_path:
                    with open(file_path, 'wb') as f:
                        f.write(image_data)
                    QMessageBox.information(self, "Success", f"Image saved to:\n{file_path}")
            else:
                file_path, _ = QFileDialog.getSaveFileName(self, "Save Base64 Content", "base64_content.bin",
                                                           "All Files (*.*)")
                if file_path:
                    base64_data = src.split(',')[-1]
                    import base64
                    data = base64.b64decode(base64_data)
                    with open(file_path, 'wb') as f:
                        f.write(data)
                    QMessageBox.information(self, "Success", f"File saved to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to download base64 media:\n{str(e)}")

class DataResearchView(QWidget):
    """Data Research project view - for web data extraction"""

    def __init__(self, parent=None, db=None, project_data=None):
        super().__init__(parent)
        self.parent_app = parent
        self.db = db
        self.project_data = project_data
        self.project_id = project_data.get('id')
        self.data_path = project_data.get('data_path')
        self.project_name = project_data.get('name', 'Research Project')

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

        # Setup UI with data table integration
        self.setup_ui()

        if hasattr(self, 'editor_toolbar'):
            self.editor_toolbar.setVisible(False)

        # Load data table projects
        self.load_table_projects()

        self.load_pages()

        # Load editor content
        self.load_editor_content()

        self.update_status("Ready")

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop)

        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)

        # Top bar with back button and project info
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

        name_label = QLabel(f"🌐 {self.project_name}")
        name_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #1c242e;")
        top_bar.addWidget(name_label)

        top_bar.addStretch()

        # Page count label
        self.page_count_label = QLabel("Pages: 0")
        self.page_count_label.setStyleSheet("color: #666; font-size: 12px;")
        top_bar.addWidget(self.page_count_label)

        layout.addLayout(top_bar)

        # URL input and fetch button
        fetch_layout = QHBoxLayout()
        fetch_layout.setSpacing(5)
        fetch_layout.setContentsMargins(5, 0, 5, 0)

        self.url_entry = QLineEdit()
        self.url_entry.setPlaceholderText("Enter URL to fetch...")
        self.url_entry.setStyleSheet("font-size: 13px; padding: 6px; border-radius: 4px;")
        self.url_entry.returnPressed.connect(self.fetch_page)
        fetch_layout.addWidget(self.url_entry, 1)

        self.fetch_btn = QPushButton("Fetch & Extract")
        self.fetch_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        self.fetch_btn.clicked.connect(self.fetch_page)
        fetch_layout.addWidget(self.fetch_btn)

        layout.addLayout(fetch_layout)

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

        # Project dropdown with filter
        project_layout = QHBoxLayout()
        project_layout.addWidget(QLabel("Project:"))
        self.project_combo = QComboBox()
        self.project_combo.setEditable(True)
        self.project_combo.setInsertPolicy(QComboBox.NoInsert)
        self.project_combo.setStyleSheet("font-size: 11px; padding: 3px;")
        self.project_combo.currentIndexChanged.connect(self.on_project_combo_changed)

        # Add completer for filtering
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

        self.tabs.currentChanged.connect(self.on_tab_changed)


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

        # Text Content tab
        self.text_content_view = QTextBrowser()
        self.text_content_view.selectionChanged.connect(self.on_selection_changed)

        self.text_content_view.setFont(QFont("Georgia", 12))
        self.text_content_view.setStyleSheet("padding: 30px; background-color: #fcfcfc; border: none;")
        self.text_content_view.anchorClicked.connect(self.on_link_clicked)
        self.tabs.addTab(self.text_content_view, "📝 Text Content")

        # Links tab
        self.links_view = QTextEdit()
        self.links_view.selectionChanged.connect(self.on_selection_changed)
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

        # HTML tab
        self.html_content_view = QTextEdit()

        self.html_content_view.selectionChanged.connect(self.on_selection_changed)

        self.html_content_view.setReadOnly(True)
        self.html_content_view.setFont(QFont("Consolas", 10))
        self.html_content_view.setStyleSheet("""
            padding: 20px;
            background-color: #1e1e1e;
            border: none;
            color: #d4d4d4;
        """)
        self.tabs.addTab(self.html_content_view, "💻 HTML")

        # CSS tab
        self.css_content_view = QTextEdit()
        self.css_content_view.selectionChanged.connect(self.on_selection_changed)
        self.css_content_view.setReadOnly(True)
        self.css_content_view.setFont(QFont("Consolas", 10))
        self.css_content_view.setStyleSheet("""
            padding: 20px;
            background-color: #1e1e1e;
            border: none;
            color: #d4d4d4;
        """)
        self.tabs.addTab(self.css_content_view, "🎨 CSS")

        # JavaScript tab
        self.js_content_view = QTextEdit()
        self.js_content_view.selectionChanged.connect(self.on_selection_changed)
        self.js_content_view.setReadOnly(True)
        self.js_content_view.setFont(QFont("Consolas", 10))
        self.js_content_view.setStyleSheet("""
            padding: 20px;
            background-color: #1e1e1e;
            border: none;
            color: #d4d4d4;
        """)
        self.tabs.addTab(self.js_content_view, "📜 JavaScript")

        self.editor_view = QTextEdit()
        self.editor_view.setFont(QFont("Courier New", 12))
        self.editor_view.setStyleSheet("""
            QTextEdit {
                padding: 20px;
                background-color: #ffffff;
                border: none;
                font-family: 'Courier New', monospace;
                font-size: 13px;
                line-height: 1.6;
            }
        """)
        # REMOVE: self.editor_view.textChanged.connect(self.autosave_editor_content)
        self.tabs.addTab(self.editor_view, "✏️ Editor")

        # Create Editor toolbar
        editor_toolbar = QWidget()
        editor_toolbar.setVisible(False)  # Hide by default
        editor_toolbar_layout = QHBoxLayout(editor_toolbar)
        editor_toolbar_layout.setSpacing(5)
        editor_toolbar_layout.setContentsMargins(5, 0, 5, 0)

        # Save button
        save_btn = QPushButton("💾 Save Editor Content")
        save_btn.setStyleSheet("""
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
        save_btn.clicked.connect(self.save_editor_content)
        editor_toolbar_layout.addWidget(save_btn)

        # Bulk Import button
        bulk_import_btn = QPushButton("📥 Bulk Import to Table")
        bulk_import_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #F57C00; }
        """)
        bulk_import_btn.clicked.connect(self.bulk_import_to_table)
        editor_toolbar_layout.addWidget(bulk_import_btn)

        # Replace/Find button
        replace_btn = QPushButton("🔍 Replace/Find")
        replace_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        replace_btn.clicked.connect(self.show_replace_dialog)
        editor_toolbar_layout.addWidget(replace_btn)

        # Clean Text button
        clean_btn = QPushButton("🧹 Clean Text")
        clean_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #7B1FA2; }
        """)
        clean_btn.clicked.connect(self.clean_editor_text)
        editor_toolbar_layout.addWidget(clean_btn)

        # Optional: Clear button
        clear_btn = QPushButton("🗑️ Clear")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        editor_toolbar_layout.addWidget(clear_btn)

        editor_toolbar_layout.addStretch()

        # Store reference to editor toolbar for visibility control
        self.editor_toolbar = editor_toolbar

        editor_toolbar_layout.addStretch()
        # Text Content Formatting Controls
        formatting_widget = QWidget()
        formatting_layout = QHBoxLayout(formatting_widget)
        formatting_layout.setSpacing(10)

        right_layout.addWidget(self.tabs)
        right_layout.addWidget(formatting_widget)


        # Apply syntax highlighters
        self.html_highlighter = HTMLHighlighter(self.html_content_view.document())
        self.css_highlighter = CSSHighlighter(self.css_content_view.document())
        self.js_highlighter = JavaScriptHighlighter(self.js_content_view.document())



        # Copy Text button (moved to leftmost)
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

        # Text Display Options Dropdown
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
        self.text_display_combo.setCurrentIndex(5)
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

        # Full Text Search Bar (moved to rightmost)
        formatting_layout.addWidget(QLabel("🔍 Find:"))
        self.full_text_search = QLineEdit()
        self.full_text_search.setMaximumWidth(200)
        self.full_text_search.setPlaceholderText("Search in current tab...")
        self.full_text_search.textChanged.connect(self.search_full_text)
        self.full_text_search.returnPressed.connect(self.find_next_full_text)
        formatting_layout.addWidget(self.full_text_search)

        # Find Next button
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

        # Find Previous button
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

        # Match count label
        self.match_count_label = QLabel("")
        self.match_count_label.setMaximumWidth(80)
        self.match_count_label.setStyleSheet("color: #000; font-family: serif; font-size: 10px;")
        formatting_layout.addWidget(self.match_count_label)

        formatting_layout.addStretch()

        right_layout.addWidget(self.tabs)
        right_layout.addWidget(formatting_widget)
        right_layout.addWidget(editor_toolbar)  # Add editor toolbar

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

    # ============ PAGE MANAGEMENT ============
    def load_pages(self):
        """Load pages from database"""
        self.pages = self.db.get_research_pages(self.data_path)
        self.page_list.clear()

        for page in self.pages:
            title = page.get('title', 'Untitled')
            display = f"{title[:50]}{'...' if len(title) > 50 else ''}"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, page['id'])
            self.page_list.addItem(item)

        self.page_count_label.setText(f"Pages: {len(self.pages)}")

        # Debug print
        print(f"Loaded {len(self.pages)} pages")

        if self.pages:
            # Only select the first page if we don't have a current selection
            if self.page_list.currentRow() == -1:
                self.page_list.setCurrentRow(0)
                self.display_page(0)
        else:
            self.clear_display()

    def clear_display(self):
        """Clear all display areas"""
        self.text_content_view.clear()
        self.links_view.clear()
        self.html_content_view.clear()
        self.css_content_view.clear()
        self.js_content_view.clear()
        self.clear_media_display()
        self.elements = []
        self.links = []
        self.media_items = []
        self.current_matches = []
        self.current_match_index = -1
        self.match_count_label.setText("")

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

    def display_page(self, index):
        """Display a page's content"""
        if index < 0 or index >= len(self.pages):
            self.clear_display()
            return

        page = self.pages[index]
        self.current_page_id = page['id']
        self.current_page_index = index
        self.base_url = page.get('url', '')

        # Get elements for this page
        all_elements = self.db.get_elements_for_page(self.data_path, page['id'])
        self.elements = [e for e in all_elements if e.get('type') != 'section']

        # Extract links and media
        raw_html = page.get('raw_html', '')
        main_html = page.get('main_html', '')

        self.links = self.extract_links(raw_html)
        self.media_items = self.extract_media(raw_html)

        # Display formatted text
        self.display_formatted_text(main_html)

        # Display links
        self.display_links()

        # Display media
        self.display_media()

        # Display code tabs
        self.display_code_tabs(raw_html)

        # Reset search
        self.full_text_search.clear()
        self.match_count_label.setText("")
        self.current_matches = []
        self.current_match_index = -1
        self.clear_full_text_highlights()

    def display_links(self):
        """Display links in the Links tab"""
        if not self.links:
            self.links_view.setText("No links found on this page.")
            return

        text = "=== LINKS ===\n\n"
        for i, link in enumerate(self.links, 1):
            text += f"[{i}] Text: {link['text']}\n"
            text += f"    URL: {link['url']}\n"
            text += f"    HTML: {link['html'][:100]}...\n\n"

        self.links_view.setText(text)

    def display_media(self):
        """Display media in the Media tab"""
        self.clear_media_display()

        if not self.media_items:
            label = QLabel("No media found on this page.")
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

            src = media.get('src', '')
            file_ext = self.get_file_extension(src)
            media_type_display = media.get('type', 'unknown').upper()
            type_badge = f"[{media_type_display}]"
            if file_ext:
                type_badge += f" {file_ext.upper()}"

            info_label = QLabel(f"{type_badge} - Item {i + 1}")
            info_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #333;")
            layout.addWidget(info_label)

            src_display = src[:80] + ('...' if len(src) > 80 else '')
            src_label = QLabel(f"Source: {src_display}")
            src_label.setStyleSheet("font-size: 10px; color: #666; word-wrap: break-word;")
            src_label.setWordWrap(True)
            layout.addWidget(src_label)

            if media.get('type') == 'image' and media.get('alt'):
                alt_label = QLabel(f"Alt: {media['alt'][:60]}{'...' if len(media['alt']) > 60 else ''}")
                alt_label.setStyleSheet("font-size: 10px; color: #888;")
                layout.addWidget(alt_label)

            view_btn = QPushButton("👁️ View Media Item")
            view_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0078d4;
                    color: white;
                    border: none;
                    padding: 6px 12px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #0066b3; }
                QPushButton:pressed { background-color: #005a9e; }
            """)
            view_btn.clicked.connect(lambda checked, m=media: self.view_media(m))
            layout.addWidget(view_btn)

            self.media_layout.addWidget(frame)

    def view_media(self, media_item):
        """Open media viewer dialog"""
        dialog = MediaViewerDialog(media_item, self.base_url, self)
        dialog.exec()

    def get_file_extension(self, url):
        """Extract file extension from URL"""
        if not url:
            return None
        url_path = url.split('?')[0]
        filename = url_path.split('/')[-1]
        if '.' in filename:
            ext = filename.split('.')[-1].lower()
            if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico',
                       'mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv', 'pdf', 'doc', 'docx']:
                return ext
        return None

    def extract_links(self, html_content):
        """Extract all links from HTML content"""
        links = []
        if not html_content:
            return links
        soup = BeautifulSoup(html_content, 'html.parser')
        for a in soup.find_all('a', href=True):
            text = a.get_text(strip=True)
            href = a.get('href')
            if href:
                links.append({
                    'text': text or '[No Text]',
                    'url': href,
                    'html': str(a)
                })
        return links

    def extract_media(self, html_content):
        """Extract all media from HTML content"""
        media = []
        if not html_content:
            return media

        soup = BeautifulSoup(html_content, 'html.parser')

        for img in soup.find_all('img'):
            src = img.get('src')
            if not src or src.startswith('data:image/svg') or 'placeholder' in src:
                src = img.get('data-src')
            if not src:
                srcset = img.get('data-srcset')
                if srcset:
                    src = srcset.split(',')[0].split()[0]
            if src:
                media.append({
                    'type': 'image',
                    'src': src,
                    'alt': img.get('alt', ''),
                    'html': str(img)
                })

        for video in soup.find_all('video', src=True):
            media.append({
                'type': 'video',
                'src': video.get('src'),
                'html': str(video)
            })

        for iframe in soup.find_all('iframe', src=True):
            src = iframe.get('src')
            if src:
                media.append({
                    'type': 'iframe',
                    'src': src,
                    'html': str(iframe)
                })

        return media

    def display_code_tabs(self, html_content):
        """Extract and display HTML, CSS, and JavaScript in separate tabs"""
        if not html_content:
            self.html_content_view.setPlainText("No HTML content available.")
            self.css_content_view.setPlainText("No CSS content available.")
            self.js_content_view.setPlainText("No JavaScript content available.")
            return

        # HTML - remove script and style tags
        soup = BeautifulSoup(html_content, 'html.parser')
        for tag in soup.find_all(['style', 'script']):
            tag.decompose()
        body = soup.find('body')
        body_html = str(body) if body else str(soup)
        self.html_content_view.setPlainText(body_html)

        # CSS
        css_content = ""
        css_pattern = re.compile(r'<style[^>]*>(.*?)</style>', re.DOTALL | re.IGNORECASE)
        css_matches = css_pattern.findall(html_content)
        if css_matches:
            css_content = "\n\n".join(css_matches)
        inline_css_pattern = re.compile(r'style\s*=\s*"([^"]*)"', re.IGNORECASE)
        inline_css = inline_css_pattern.findall(html_content)
        if inline_css:
            css_content += "\n\n/* Inline Styles */\n"
            for i, style in enumerate(inline_css, 1):
                css_content += f"/* Style {i} */\n{style}\n"
        self.css_content_view.setPlainText(css_content if css_content else "No CSS content found.")

        # JavaScript
        js_content = ""
        js_pattern = re.compile(r'<script[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)
        js_matches = js_pattern.findall(html_content)
        for i, script in enumerate(js_matches, 1):
            script = script.strip()
            if script:
                if len(js_matches) > 1:
                    js_content += f"// ===== SCRIPT {i} =====\n\n"
                js_content += script + "\n\n"
        inline_js_pattern = re.compile(r'on[a-z]+\s*=\s*"([^"]*)"', re.IGNORECASE)
        inline_js = inline_js_pattern.findall(html_content)
        if inline_js:
            js_content += "\n// ===== INLINE EVENT HANDLERS =====\n\n"
            for i, handler in enumerate(inline_js, 1):
                js_content += f"// Handler {i}\n{handler}\n"
        if js_content:
            js_content = re.sub(r';', ';\n', js_content)
            js_content = re.sub(r'\{', '{\n', js_content)
            js_content = re.sub(r'\}', '}\n', js_content)
            js_content = re.sub(r'\n\s*\n', '\n', js_content)
        self.js_content_view.setPlainText(js_content if js_content else "No JavaScript content found.")

    # ============ TEXT PROCESSING ============

    def get_all_text(self):
        return [elem.get('content', '') for elem in self.elements if elem.get('content')]

    def get_text_jumble(self):
        return " ".join(self.get_all_text())

    def get_text_organized(self):
        return "\n\n".join(self.get_all_text())

    def get_text_elements(self):
        parts = []
        for i, elem in enumerate(self.elements, 1):
            content = elem.get('content', '').strip()
            if content:
                parts.append(f"[{i}] {elem.get('type', 'unknown').upper()}\n{content}")
        return "\n\n".join(parts)

    def get_text_headers(self):
        headers = [elem.get('content', '') for elem in self.elements
                   if elem.get('type') == 'heading' and elem.get('content')]
        return "\n\n".join(headers)

    def get_text_paragraphs(self):
        paragraphs = [elem.get('content', '') for elem in self.elements
                      if elem.get('type') == 'paragraph' and elem.get('content')]
        return "\n\n".join(paragraphs)

    def get_text_sentences(self):
        all_text = " ".join(self.get_all_text())
        sentences = re.split(r'(?<=[.!?])\s+', all_text)
        return "\n\n".join([s.strip() for s in sentences if s.strip()])

    def get_text_unique_words(self):
        all_text = " ".join(self.get_all_text()).lower()
        words = re.findall(r'\b[a-z]+\b', all_text)
        unique_words = []
        seen = set()
        for word in words:
            if word not in seen:
                unique_words.append(word)
                seen.add(word)
        return "\n".join(unique_words)

    def get_text_repeated_words(self):
        all_text = " ".join(self.get_all_text()).lower()
        words = re.findall(r'\b[a-z]+\b', all_text)
        word_counts = Counter(words)
        repeated = [(word, count) for word, count in word_counts.items() if count > 1]
        repeated.sort(key=lambda x: x[1], reverse=True)
        return "\n".join([f"{word}: {count}" for word, count in repeated])

    def get_text_questions(self):
        all_text = " ".join(self.get_all_text())
        questions = re.findall(r'[^.!?]*\?', all_text)
        return "\n".join([q.strip() for q in questions if q.strip()])

    def update_text_display(self, display_type):
        """Update text content based on selected display type"""
        if self.current_page_index < 0 or self.current_page_index >= len(self.pages):
            return

        # For "Text Organized", display formatted HTML instead of plain text
        if display_type == "Text Organized":
            page = self.pages[self.current_page_index]
            html_content = page.get('main_html', '')
            if html_content:
                self._display_html_content(html_content)
            return

        text_map = {
            "Text Jumble": self.get_text_jumble,
            "Text Elements": self.get_text_elements,
            "Text Headers": self.get_text_headers,
            "Text Paragraphs": self.get_text_paragraphs,
            "Text Sentences": self.get_text_sentences,
            "Text Unique Words": self.get_text_unique_words,
            "Text Repeated Words": self.get_text_repeated_words,
            "Text Questions": self.get_text_questions
        }

        if display_type in text_map:
            text = text_map[display_type]()
            self.text_content_view.setPlainText(text)

    def _display_html_content(self, html_content):
        """Internal method to display HTML content without triggering recursion"""
        if not html_content:
            self.text_content_view.clear()
            return

        # Store current selection if any
        cursor = self.text_content_view.textCursor()
        has_selection = cursor.hasSelection()
        selected_text = cursor.selectedText() if has_selection else ""
        # Store the selection start and end positions
        selection_start = cursor.selectionStart() if has_selection else -1
        selection_end = cursor.selectionEnd() if has_selection else -1

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
                max-width: 850px;
                margin: 0 auto;
                color: #2c3e50;
                background-color: #ffffff;
            }}
            h1 {{
                font-size: {font_size + 10}pt;
                font-weight: bold;
                margin-top: 30px;
                margin-bottom: 14px;
                color: #1a1a2e;
                border-bottom: 3px solid #3498db;
                padding-bottom: 10px;
            }}
            h2 {{
                font-size: {font_size + 6}pt;
                font-weight: bold;
                margin-top: 24px;
                margin-bottom: 10px;
                color: #2c3e50;
                border-bottom: 2px solid #ecf0f1;
                padding-bottom: 8px;
            }}
            h3 {{
                font-size: {font_size + 3}pt;
                font-weight: bold;
                margin-top: 20px;
                margin-bottom: 8px;
                color: #34495e;
            }}
            h4, h5, h6 {{
                font-size: {font_size + 1}pt;
                font-weight: bold;
                margin-top: 16px;
                margin-bottom: 6px;
                color: #445566;
            }}
            p {{
                margin-top: 14px;
                margin-bottom: 14px;
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
                margin-top: 12px;
                margin-bottom: 12px;
                padding-left: 35px;
            }}
            li {{
                margin-top: 6px;
                margin-bottom: 6px;
                line-height: {line_height};
            }}
            blockquote {{
                margin: 18px 25px;
                padding: 14px 24px;
                border-left: 5px solid #3498db;
                background-color: #f8f9fa;
                font-style: italic;
                border-radius: 0 6px 6px 0;
                color: #34495e;
            }}
            table {{
                border-collapse: collapse;
                margin: 18px 0;
                width: 100%;
                border-radius: 6px;
                overflow: hidden;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            th, td {{
                border: 1px solid #dee2e6;
                padding: 10px 16px;
                text-align: left;
            }}
            th {{
                background-color: #e9ecef;
                font-weight: 600;
                color: #1a1a2e;
            }}
            tr:nth-child(even) {{ background-color: #f8f9fa; }}
            tr:hover {{ background-color: #e8f0fe; }}
            code {{
                background-color: #f4f4f4;
                padding: 2px 8px;
                border-radius: 4px;
                font-family: "Consolas", monospace;
                font-size: 0.9em;
                color: #c0392b;
            }}
            pre {{
                background-color: #f4f4f4;
                padding: 14px 18px;
                border-radius: 6px;
                overflow-x: auto;
                font-family: "Consolas", monospace;
                font-size: 0.9em;
                margin: 14px 0;
                border: 1px solid #e9ecef;
            }}
        """)

        styled_html = f"""
        <div style="font-family: '{font_family}'; font-size: {font_size}pt; line-height: {line_height}; word-spacing: {word_spacing}px; padding: 10px;">
            {html_content}
        </div>
        """

        self.text_content_view.setHtml(styled_html)

        # Restore selection if there was one
        if has_selection and selected_text and selection_start >= 0:
            # Try to find the text
            doc = self.text_content_view.document()
            cursor = doc.find(selected_text)
            if not cursor.isNull():
                self.text_content_view.setTextCursor(cursor)
                # After restoring, trigger selection changed
                self.on_selection_changed()


    def display_formatted_text(self, html_content):
        """Display HTML content with article styling"""
        if not html_content:
            self.text_content_view.clear()
            return

        self._display_html_content(html_content)

        # Update text display based on current selection
        current_display = self.text_display_combo.currentText()
        if current_display != "Text Organized":
            self.update_text_display(current_display)

    def update_formatting(self):
        """Update formatting when controls change"""
        if self.current_page_index >= 0 and self.current_page_index < len(self.pages):
            page = self.pages[self.current_page_index]
            self.display_formatted_text(page.get('main_html', ''))

    # ============ FULL TEXT SEARCH ============

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

        # Escape special regex characters but keep quotes
        # We want to search for the exact text, including quotes
        search_text = text

        doc = current_tab.document()
        self.clear_full_text_highlights()

        cursor = doc.find(search_text)
        matches = []

        while not cursor.isNull():
            matches.append(cursor)
            cursor = doc.find(search_text, cursor)

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

    # ============ FETCHING ============
    def on_fetch_error(self, error):
        """Handle fetch error"""
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Fetch & Extract")
        self.update_status("Error fetching page")
        QMessageBox.critical(self, "Error", f"Failed to fetch:\n{error}")

    def fetch_page(self):
        url = self.url_entry.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a URL.")
            return

        # Check if page already exists
        for page in self.pages:
            if page.get('url') == url:
                # Select it in the list
                for i, p in enumerate(self.pages):
                    if p['id'] == page['id']:
                        self.page_list.setCurrentRow(i)
                        self.display_page(i)
                        return

        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("Fetching...")
        self.update_status("Fetching page...")

        self.thread = FetchThread(url, self.data_path)
        self.thread.finished.connect(self.on_fetch_finished)
        self.thread.error.connect(self.on_fetch_error)
        self.thread.start()

    def on_fetch_finished(self, data):
        """Handle fetch completion"""
        # Reload pages from database
        self.load_pages()

        # Find and select the new page
        new_page_id = data.get('id')
        found = False

        for i, page in enumerate(self.pages):
            if page['id'] == new_page_id:
                self.page_list.setCurrentRow(i)
                self.display_page(i)
                found = True
                break

        if not found:
            # If the page wasn't found, just select the first page
            if self.pages:
                self.page_list.setCurrentRow(0)
                self.display_page(0)
            else:
                self.clear_display()

        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Fetch & Extract")
        self.url_entry.clear()
        self.update_status(f"Fetched: {data.get('title', 'Untitled')}")

        QMessageBox.information(self, "Success", f"Fetched: {data.get('title', 'Untitled')}")

    # ============ LINK HANDLING ============

    def on_link_clicked(self, url):
        """Handle link clicks in text content view"""
        url_str = url.toString()

        reply = QMessageBox.question(
            self, "Open Link",
            f"Do you want to scrape this page?\n\n{url_str}",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
        )

        if reply == QMessageBox.Yes:
            self.url_entry.setText(url_str)
            self.fetch_page()
        elif reply == QMessageBox.No:
            webbrowser.open(url_str)
            self.update_status(f"Opened in browser: {url_str}")

        # Restore content
        if self.current_page_index >= 0 and self.current_page_index < len(self.pages):
            page = self.pages[self.current_page_index]
            self.display_formatted_text(page.get('main_html', ''))

    # ============ COPY ============

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

    def load_table_projects(self):
        """Load all data table projects for the dropdown"""
        self.table_projects = self.db.get_all_data_table_projects()
        self.project_combo.blockSignals(True)
        self.project_combo.clear()

        # Add empty option
        self.project_combo.addItem("Select a Data Table Project...", None)

        for project in self.table_projects:
            self.project_combo.addItem(f"📊 {project['name']}", project['id'])

        self.project_combo.blockSignals(False)

        # Clear column combo
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

        # Re-check selection state
        self.on_selection_changed()

    def load_table_columns(self, project_id):
        """Load columns for the selected data table project"""
        self.column_combo.blockSignals(True)
        self.column_combo.clear()
        self.column_combo.addItem("Select a column...", None)

        if project_id:
            # Find the project
            project = next((p for p in self.table_projects if p['id'] == project_id), None)
            if project:
                columns = self.db.get_table_column_names(project['data_path'])
                for col in columns:
                    self.column_combo.addItem(col, col)
                self.selected_table_project_id = project_id

        self.column_combo.blockSignals(False)

        # Re-check selection state
        self.on_selection_changed()

    def insert_selected_text(self):
        """Insert selected text into the data table"""
        # Get selected text from current tab
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
                # If no selection, get the entire content
                selected_text = current_tab.toPlainText()
        else:
            selected_text = current_tab.toPlainText()

        if not selected_text or not selected_text.strip():
            QMessageBox.warning(self, "No Content", "No text to insert.")
            return

        # Get the selected project and column
        project_id = self.project_combo.currentData()
        column_name = self.column_combo.currentData()

        if not project_id or not column_name:
            QMessageBox.warning(self, "Incomplete", "Please select both a project and a column.")
            return

        # Find the project
        project = next((p for p in self.table_projects if p['id'] == project_id), None)
        if not project:
            QMessageBox.warning(self, "Error", "Selected project not found.")
            return

        # Get column config from project metadata
        column_config = project.get('metadata', {}).get('column_config', [])

        # Find the column config
        col_config = next((c for c in column_config if c['name'] == column_name), None)
        if not col_config:
            QMessageBox.warning(self, "Error", f"Column '{column_name}' not found in project.")
            return

        # Check if column is unique
        if col_config.get('unique', False):
            # Check if value already exists in the column
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

        # Get the database column order
        conn = sqlite3.connect(project['data_path'])
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(data)")
        db_columns = cursor.fetchall()
        conn.close()

        # Get all column names from the database in order (excluding internal columns)
        db_column_names = []
        for col in db_columns:
            col_name = col[1]
            if col_name not in ['id', '_row_created_at', '_row_updated_at']:
                db_column_names.append(col_name)

        # Build a dictionary of column_name -> value
        # Start with all columns having 'must-be-updated' as default
        col_to_value = {}
        for col_name in db_column_names:
            if col_name == column_name:
                col_to_value[col_name] = selected_text
            else:
                # Find column config for default value
                col_cfg = next((c for c in column_config if c['name'] == col_name), None)
                if col_cfg:
                    col_type = col_cfg.get('type', 'text')
                    if col_type == 'integer':
                        col_to_value[col_name] = 0
                    elif col_type == 'float':
                        col_to_value[col_name] = 0.0
                    elif col_type == 'boolean':
                        col_to_value[col_name] = 0  # False as integer
                    else:
                        col_to_value[col_name] = 'must-be-updated'
                else:
                    col_to_value[col_name] = 'must-be-updated'

        # Create row data in database column order
        row_data = []
        for col_name in db_column_names:
            row_data.append(col_to_value.get(col_name, 'must-be-updated'))

        # Debug output
        print(f"Database column order: {db_column_names}")
        print(f"Row data in database order: {row_data}")

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
            # If the table view is open, refresh it
            if hasattr(self.parent_app, 'refresh_table_view'):
                self.parent_app.refresh_table_view(project_id)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to insert row:\n{str(e)}")

    def refresh_table_data(self):
        """Refresh the table data from the database"""
        self.update_status("Table refreshed")

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard shortcuts"""
        if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
            # Ctrl+Enter - insert selected text
            # Check if we have a selection and the button is enabled
            if self.insert_btn.isEnabled():
                self.insert_selected_text()
            else:
                # If button is disabled, show a message explaining why
                project_selected = self.project_combo.currentData() is not None
                column_selected = self.column_combo.currentData() is not None

                if not project_selected or not column_selected:
                    QMessageBox.warning(self, "Incomplete", "Please select both a project and a column first.")
                else:
                    # Check if there's a selection
                    current_tab = self.tabs.currentWidget()
                    if hasattr(current_tab, 'textCursor'):
                        cursor = current_tab.textCursor()
                        if not cursor.hasSelection():
                            QMessageBox.warning(self, "No Selection", "Please select some text first.")
            return

        super().keyPressEvent(event)



    def on_selection_changed(self):
        """Handle selection changes in any tab"""
        current_tab = self.tabs.currentWidget()
        if not current_tab:
            self.insert_btn.setEnabled(False)
            return

        # Check if the current tab has a selection
        has_selection = False
        if hasattr(current_tab, 'textCursor'):
            cursor = current_tab.textCursor()
            has_selection = cursor.hasSelection()

        # Also check if a project and column are selected
        project_selected = self.project_combo.currentData() is not None
        column_selected = self.column_combo.currentData() is not None

        # Enable the button only if there's a selection AND both project and column are selected
        self.insert_btn.setEnabled(has_selection and project_selected and column_selected)

    def on_tab_changed(self, index):
        """Handle tab changes"""
        # Re-check selection state when switching tabs
        self.on_selection_changed()

        # Show/hide editor toolbar based on selected tab
        if hasattr(self, 'editor_toolbar'):
            # Get the tab text to identify which tab is selected
            tab_text = self.tabs.tabText(index)
            if tab_text == "✏️ Editor":
                self.editor_toolbar.setVisible(True)
            else:
                self.editor_toolbar.setVisible(False)

    def load_data(self):
        """Load data from the project database"""
        if self.data_path and os.path.exists(self.data_path):
            conn = sqlite3.connect(self.data_path)
            cursor = conn.cursor()

            try:
                cursor.execute('SELECT * FROM data ORDER BY id')
                rows_with_ids = cursor.fetchall()
                conn.close()

                # Get column order from database (excluding internal columns)
                conn2 = sqlite3.connect(self.data_path)
                cursor2 = conn2.cursor()
                cursor2.execute("PRAGMA table_info(data)")
                db_columns = cursor2.fetchall()
                conn2.close()

                # Get the column names in order (excluding internal)
                db_column_names = []
                for col in db_columns:
                    col_name = col[1]
                    if col_name not in ['id', '_row_created_at', '_row_updated_at']:
                        db_column_names.append(col_name)

                self.row_ids = []
                self.rows = []
                for row in rows_with_ids:
                    self.row_ids.append(row[0])
                    # Extract only the non-internal columns in the correct order
                    row_data = []
                    # Skip the first 3 columns (id, _row_created_at, _row_updated_at)
                    # and take the rest in order
                    for i in range(3, len(row)):
                        row_data.append(row[i])
                    self.rows.append(row_data)
            except sqlite3.OperationalError:
                conn.close()
                self.rows = []
                self.row_ids = []
        else:
            self.rows = []
            self.row_ids = []
        self.refresh_table()

    def load_editor_content(self):
        """Load editor content from project data"""
        if not self.data_path or not self.project_id:
            return

        # Check if editor_content exists in project metadata
        project_data = self.db.get_project(self.project_id)
        if project_data and 'editor_content' in project_data.get('metadata', {}):
            content = project_data['metadata']['editor_content']
            self.editor_view.setPlainText(content)

        # Show/hide toolbar based on current tab
        if hasattr(self, 'editor_toolbar'):
            current_tab_text = self.tabs.tabText(self.tabs.currentIndex())
            if current_tab_text == "✏️ Editor":
                self.editor_toolbar.setVisible(True)
            else:
                self.editor_toolbar.setVisible(False)

    def save_editor_content(self):
        """Save editor content manually"""
        if not self.data_path or not self.project_id:
            QMessageBox.warning(self, "Error", "No project loaded.")
            return

        content = self.editor_view.toPlainText()

        # Update project metadata
        project_data = self.db.get_project(self.project_id)
        if project_data:
            metadata = project_data.get('metadata', {})
            metadata['editor_content'] = content
            self.db.update_project(self.project_id, metadata=metadata)

            self.update_status("Editor content saved")
            QMessageBox.information(self, "Saved", "Editor content saved successfully!")

    def bulk_import_to_table(self):
        """Bulk import editor content to a data table column with advanced options"""
        # Get the current editor content
        text = self.editor_view.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "No Content", "Editor is empty. Please add content first.")
            return

        # Get the selected project and column
        project_id = self.project_combo.currentData()
        column_name = self.column_combo.currentData()

        if not project_id or not column_name:
            QMessageBox.warning(self, "Incomplete", "Please select both a project and a column.")
            return

        # Find the project
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

        # Split text into entries based on user selection
        entries = self.split_entries_with_options(text)

        if not entries:
            QMessageBox.warning(self, "No Entries", "No valid entries found.")
            return

        # Get existing values for duplicate checking
        conn = sqlite3.connect(project['data_path'])
        cursor = conn.cursor()
        cursor.execute(f"SELECT \"{column_name}\" FROM data")
        existing_values = [row[0] for row in cursor.fetchall() if row[0]]
        conn.close()

        # Show import options dialog
        import_config = self.show_import_options_dialog(entries, existing_values, col_config)

        if import_config is None:  # User cancelled
            return

        # Process entries based on configuration
        entries_to_add = self.process_entries_with_options(entries, import_config, existing_values, col_config)

        if not entries_to_add:
            QMessageBox.information(self, "No Entries", "No entries to add based on your selections.")
            return

        # Add the entries
        success_count = 0
        error_count = 0

        for entry in entries_to_add:
            try:
                # Get the database column order
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
                        col_to_value[col_name] = entry
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
                self.db.add_table_row(project['data_path'], row_data)
                success_count += 1

            except Exception as e:
                error_count += 1
                print(f"Error adding entry: {entry[:50]}... - {str(e)}")

        # Show success message
        msg = f"Bulk Import Complete!\n\n"
        msg += f"Successfully added: {success_count} entries\n"
        if error_count > 0:
            msg += f"Failed to add: {error_count} entries\n"

        QMessageBox.information(self, "Import Complete", msg)

        # Refresh the table view if it's open
        if hasattr(self.parent_app, 'refresh_table_view'):
            self.parent_app.refresh_table_view(project_id)

    def split_entries_with_options(self, text):
        """Split text into entries with user-selected options"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Import Options - Split Settings")
        dialog.setModal(True)
        dialog.setMinimumWidth(450)

        layout = QVBoxLayout()

        # Info label
        info_label = QLabel("How would you like to split the text into entries?")
        info_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(info_label)

        # Split method selection
        split_group = QGroupBox("Split Method")
        split_layout = QVBoxLayout()

        # Option 1: Single row (all text as one entry)
        single_row_radio = QRadioButton("Single Row - Add all text as ONE entry")
        single_row_radio.setChecked(False)
        split_layout.addWidget(single_row_radio)

        # Option 2: Split by newlines (1 or more newlines)
        newline_radio = QRadioButton("Split by newlines (one or more)")
        newline_radio.setChecked(True)
        split_layout.addWidget(newline_radio)

        # Option 3: Split by paragraph (2 or more newlines)
        paragraph_radio = QRadioButton("Split by paragraphs (two or more newlines)")
        split_layout.addWidget(paragraph_radio)

        # Option 4: Custom separator
        custom_layout = QHBoxLayout()
        custom_radio = QRadioButton("Custom separator:")
        custom_layout.addWidget(custom_radio)
        custom_separator = QLineEdit()
        custom_separator.setPlaceholderText("e.g., , or ; or |")
        custom_separator.setMaximumWidth(150)
        custom_layout.addWidget(custom_separator)
        split_layout.addLayout(custom_layout)

        split_group.setLayout(split_layout)
        layout.addWidget(split_group)

        # Skip pattern
        skip_group = QGroupBox("Skip Pattern (optional)")
        skip_layout = QVBoxLayout()

        skip_info = QLabel("Skip entries based on pattern (e.g., add 1st, skip 1st, add 3rd, skip 1st...)")
        skip_info.setWordWrap(True)
        skip_info.setStyleSheet("font-size: 11px; color: #666;")
        skip_layout.addWidget(skip_info)

        skip_layout_2 = QHBoxLayout()
        skip_layout_2.addWidget(QLabel("Skip every:"))
        skip_spin = QSpinBox()
        skip_spin.setRange(0, 100)
        skip_spin.setValue(0)
        skip_spin.setToolTip("0 = no skipping")
        skip_layout_2.addWidget(skip_spin)
        skip_layout_2.addWidget(QLabel("entry(ies)"))
        skip_layout_2.addStretch()
        skip_layout.addLayout(skip_layout_2)

        skip_group.setLayout(skip_layout)
        layout.addWidget(skip_group)

        # Preview section
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout()

        preview_label = QLabel("Entries will be:")
        preview_label.setStyleSheet("font-weight: bold;")
        preview_layout.addWidget(preview_label)

        preview_text = QTextEdit()
        preview_text.setReadOnly(True)
        preview_text.setMaximumHeight(100)
        preview_text.setStyleSheet("font-size: 11px; background-color: #f5f5f5;")
        preview_layout.addWidget(preview_text)

        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        # Buttons
        btn_layout = QHBoxLayout()

        # Update preview button
        preview_btn = QPushButton("Preview")
        preview_btn.clicked.connect(lambda: self.update_preview(
            preview_text, text, single_row_radio, newline_radio,
            paragraph_radio, custom_radio, custom_separator, skip_spin
        ))
        btn_layout.addWidget(preview_btn)

        btn_layout.addStretch()

        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        ok_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)
        dialog.setLayout(layout)

        # Show initial preview
        self.update_preview(preview_text, text, single_row_radio, newline_radio,
                            paragraph_radio, custom_radio, custom_separator, skip_spin)

        if dialog.exec() != QDialog.Accepted:
            return None

        # Gather results
        if single_row_radio.isChecked():
            return [text.strip()]
        elif newline_radio.isChecked():
            entries = [e.strip() for e in text.split('\n') if e.strip()]
        elif paragraph_radio.isChecked():
            entries = [e.strip() for e in re.split(r'\n\s*\n+', text) if e.strip()]
        elif custom_radio.isChecked() and custom_separator.text():
            sep = custom_separator.text()
            entries = [e.strip() for e in text.split(sep) if e.strip()]
        else:
            entries = [e.strip() for e in text.split('\n') if e.strip()]

        skip_count = skip_spin.value()
        if skip_count > 0:
            filtered_entries = []
            for i, entry in enumerate(entries):
                if (i + 1) % (skip_count + 1) != 0:  # Add if not a skip position
                    filtered_entries.append(entry)
            entries = filtered_entries

        return entries

    def update_preview(self, preview_text, original_text, single_row_radio, newline_radio,
                       paragraph_radio, custom_radio, custom_separator, skip_spin):
        """Update the preview text based on current settings"""
        if single_row_radio.isChecked():
            entries = [original_text.strip()]
        elif newline_radio.isChecked():
            entries = [e.strip() for e in original_text.split('\n') if e.strip()]
        elif paragraph_radio.isChecked():
            entries = [e.strip() for e in re.split(r'\n\s*\n+', original_text) if e.strip()]
        elif custom_radio.isChecked() and custom_separator.text():
            sep = custom_separator.text()
            entries = [e.strip() for e in original_text.split(sep) if e.strip()]
        else:
            entries = [e.strip() for e in original_text.split('\n') if e.strip()]

        skip_count = skip_spin.value()
        if skip_count > 0:
            filtered_entries = []
            for i, entry in enumerate(entries):
                if (i + 1) % (skip_count + 1) != 0:
                    filtered_entries.append(entry)
            entries = filtered_entries

        # Show preview (limit to 10 entries for readability)
        preview_text.clear()
        if not entries:
            preview_text.setPlainText("No entries found.")
            return

        preview_text.setPlainText(f"Total entries: {len(entries)}\n\n")
        for i, entry in enumerate(entries[:10], 1):
            preview_text.append(f"{i}. {entry[:80]}{'...' if len(entry) > 80 else ''}")

        if len(entries) > 10:
            preview_text.append(f"\n... and {len(entries) - 10} more entries")

    def show_import_options_dialog(self, entries, existing_values, col_config):
        """Show the import options dialog with duplicate handling"""
        # Check for duplicates
        duplicate_entries = []
        new_entries = []

        for entry in entries:
            if entry in existing_values:
                duplicate_entries.append(entry)
            else:
                new_entries.append(entry)

        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Bulk Import Options")
        dialog.setModal(True)
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout()

        # Summary
        summary = f"📊 Import Summary\n\n"
        summary += f"Total entries: {len(entries)}\n"
        summary += f"New entries: {len(new_entries)}\n"
        summary += f"Duplicate entries: {len(duplicate_entries)}\n\n"

        if col_config.get('unique', False):
            summary += "⚠️ Column is set to UNIQUE\n"
            summary += "Duplicate entries will be skipped automatically."

        summary_label = QLabel(summary)
        summary_label.setWordWrap(True)
        summary_label.setStyleSheet("font-size: 12px; padding: 10px; background-color: #f5f5f5; border-radius: 4px;")
        layout.addWidget(summary_label)

        # Duplicate handling option (only if column is not unique)
        if not col_config.get('unique', False) and duplicate_entries:
            dup_group = QGroupBox("Duplicate Handling")
            dup_layout = QVBoxLayout()

            dup_info = QLabel(f"Found {len(duplicate_entries)} duplicate entries.")
            dup_info.setStyleSheet("font-weight: bold;")
            dup_layout.addWidget(dup_info)

            # Show some duplicates
            dup_list = QListWidget()
            dup_list.setMaximumHeight(80)
            for dup in duplicate_entries[:5]:
                dup_list.addItem(dup[:80] + ('...' if len(dup) > 80 else ''))
            if len(duplicate_entries) > 5:
                dup_list.addItem(f"... and {len(duplicate_entries) - 5} more")
            dup_layout.addWidget(dup_list)

            duplicate_options = QHBoxLayout()
            skip_duplicates = QRadioButton("Skip duplicates (add only new)")
            skip_duplicates.setChecked(True)
            duplicate_options.addWidget(skip_duplicates)

            include_duplicates = QRadioButton("Include duplicates (add all)")
            duplicate_options.addWidget(include_duplicates)
            dup_layout.addLayout(duplicate_options)

            dup_group.setLayout(dup_layout)
            layout.addWidget(dup_group)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        import_btn = QPushButton("Import")
        import_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        import_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(import_btn)

        layout.addLayout(btn_layout)
        dialog.setLayout(layout)

        if dialog.exec() != QDialog.Accepted:
            return None

        # Process results
        config = {
            'entries': entries,
            'new_entries': new_entries,
            'duplicate_entries': duplicate_entries,
            'include_duplicates': False
        }

        if not col_config.get('unique', False) and duplicate_entries:
            if include_duplicates.isChecked():
                config['include_duplicates'] = True

        return config

    def process_entries_with_options(self, entries, config, existing_values, col_config):
        """Process entries based on configuration"""
        if col_config.get('unique', False):
            # For unique columns, only add new entries
            return config['new_entries']
        else:
            # For non-unique columns
            if config.get('include_duplicates', False):
                return config['entries']
            else:
                return config['new_entries']

    def show_replace_dialog(self):
        """Show the replace/find dialog"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Find and Replace")
        dialog.setModal(True)
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout()

        # Find section
        layout.addWidget(QLabel("Find:"))
        find_input = QLineEdit()
        find_input.setPlaceholderText("Text to find...")
        find_input.setStyleSheet("font-size: 13px; padding: 6px;")
        layout.addWidget(find_input)

        # Replace section
        layout.addWidget(QLabel("Replace with:"))
        replace_input = QLineEdit()
        replace_input.setPlaceholderText("Replacement text...")
        replace_input.setStyleSheet("font-size: 13px; padding: 6px;")
        layout.addWidget(replace_input)

        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout()

        case_sensitive = QCheckBox("Case sensitive")
        options_layout.addWidget(case_sensitive)

        whole_word = QCheckBox("Whole word only")
        options_layout.addWidget(whole_word)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Buttons
        btn_layout = QHBoxLayout()

        find_btn = QPushButton("🔍 Find Next")
        find_btn.clicked.connect(
            lambda: self.find_in_editor(find_input.text(), case_sensitive.isChecked(), whole_word.isChecked()))
        btn_layout.addWidget(find_btn)

        replace_btn = QPushButton("🔄 Replace")
        replace_btn.clicked.connect(
            lambda: self.replace_in_editor(find_input.text(), replace_input.text(), case_sensitive.isChecked(),
                                           whole_word.isChecked()))
        btn_layout.addWidget(replace_btn)

        replace_all_btn = QPushButton("🔄 Replace All")
        replace_all_btn.clicked.connect(
            lambda: self.replace_all_in_editor(find_input.text(), replace_input.text(), case_sensitive.isChecked(),
                                               whole_word.isChecked()))
        btn_layout.addWidget(replace_all_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        dialog.setLayout(layout)
        dialog.exec()

    def find_in_editor(self, find_text, case_sensitive=False, whole_word=False):
        """Find text in the editor"""
        if not find_text:
            return

        cursor = self.editor_view.textCursor()

        # Build search flags
        flags = QTextDocument.FindFlag(0)
        if case_sensitive:
            flags |= QTextDocument.FindCaseSensitively
        if whole_word:
            flags |= QTextDocument.FindWholeWords

        # Search forward from current cursor position
        found = self.editor_view.find(find_text, flags)

        if not found:
            # If not found forward, search from beginning
            cursor.movePosition(QTextCursor.Start)
            self.editor_view.setTextCursor(cursor)
            found = self.editor_view.find(find_text, flags)

            if not found:
                QMessageBox.information(self, "Not Found", f"'{find_text}' not found in the document.")

    def replace_in_editor(self, find_text, replace_text, case_sensitive=False, whole_word=False):
        """Replace text in the editor"""
        if not find_text:
            return

        # Check if there's a selection that matches
        cursor = self.editor_view.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == find_text:
            cursor.insertText(replace_text)
            self.editor_view.setTextCursor(cursor)
        else:
            # Find and replace the next occurrence
            self.find_in_editor(find_text, case_sensitive, whole_word)
            # If found, replace the selection
            cursor = self.editor_view.textCursor()
            if cursor.hasSelection() and cursor.selectedText() == find_text:
                cursor.insertText(replace_text)
                self.editor_view.setTextCursor(cursor)

    def replace_all_in_editor(self, find_text, replace_text, case_sensitive=False, whole_word=False):
        """Replace all occurrences in the editor"""
        if not find_text:
            return

        # Get the current text
        text = self.editor_view.toPlainText()

        # Build regex flags
        flags = 0
        if not case_sensitive:
            flags |= re.IGNORECASE

        if whole_word:
            pattern = r'\b' + re.escape(find_text) + r'\b'
        else:
            pattern = re.escape(find_text)

        # Replace all occurrences
        new_text = re.sub(pattern, replace_text, text, flags=flags)

        # Count replacements
        count = text.count(find_text) if not whole_word else len(re.findall(pattern, text, flags=flags))

        if count == 0:
            QMessageBox.information(self, "No Matches", f"'{find_text}' not found in the document.")
            return

        # Ask for confirmation
        reply = QMessageBox.question(
            self,
            "Confirm Replace All",
            f"Replace {count} occurrence(s) of '{find_text}' with '{replace_text}'?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.editor_view.setPlainText(new_text)
            QMessageBox.information(self, "Complete", f"Replaced {count} occurrence(s).")

    def clean_editor_text(self):
        """Clean the editor text by normalizing whitespace and fixing common issues"""
        text = self.editor_view.toPlainText()

        if not text.strip():
            QMessageBox.information(self, "No Content", "Editor is empty.")
            return

        # Apply cleaning operations
        cleaned_text = text

        # 1. Replace tabs with single space
        cleaned_text = cleaned_text.replace('\t', ' ')

        # 2. Replace multiple spaces with single space (but preserve newlines)
        lines = cleaned_text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Remove multiple spaces within the line
            cleaned_line = re.sub(r' +', ' ', line.strip())
            cleaned_lines.append(cleaned_line)

        cleaned_text = '\n'.join(cleaned_lines)

        # 3. Remove empty lines at start and end
        cleaned_text = cleaned_text.strip()

        # Show preview and ask for confirmation
        preview = cleaned_text[:500] + ("..." if len(cleaned_text) > 500 else "")

        reply = QMessageBox.question(
            self,
            "Clean Text",
            f"Preview of cleaned text:\n\n{preview}\n\nApply cleaning?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.editor_view.setPlainText(cleaned_text)
            QMessageBox.information(self, "Cleaned", "Text has been cleaned.")

