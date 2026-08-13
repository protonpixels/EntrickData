import os
import sys
import sqlite3
import json
import hashlib
import time
from typing import List, Dict, Optional
from datetime import datetime
from collections import OrderedDict

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QComboBox, QCheckBox,
    QTextEdit, QListWidget, QListWidgetItem, QSplitter,
    QTabWidget, QScrollArea, QFrame, QMessageBox,
    QFileDialog, QDialog, QSpinBox, QDoubleSpinBox,
    QTextBrowser, QSizePolicy, QGroupBox, QProgressDialog
)
from PySide6.QtGui import (
    QClipboard, QGuiApplication, QFont, QColor,
    QKeyEvent, QTextCursor, QTextCharFormat,
    QFontDatabase, QPixmap, QTextDocument
)

import requests
import json as json_lib
import subprocess
import platform

# At the top of data_chat_view.py
from utils.mullama_backend import MullamaManager

class ChatThread(QThread):
    """Thread for handling AI chat requests using Mullama"""
    response_received = Signal(str)
    error_occurred = Signal(str)
    thinking_started = Signal()
    thinking_finished = Signal()

    def __init__(self, prompt: str, context: str, model: str, backend_manager, use_cache: bool = True):
        super().__init__()
        self.prompt = prompt
        self.context = context
        self.model = model
        self.backend_manager = backend_manager
        self.use_cache = use_cache
        self.cache = {}

    def run(self):
        try:
            self.thinking_started.emit()

            # Check cache
            cache_key = self._get_cache_key()
            if self.use_cache and cache_key in self.cache:
                self.response_received.emit(self.cache[cache_key])
                self.thinking_finished.emit()
                return

            # Query the backend
            response = self.backend_manager.query(self.prompt, self.context, self.model)

            # Cache the response
            if self.use_cache:
                self.cache[cache_key] = response

            self.response_received.emit(response)
            self.thinking_finished.emit()

        except Exception as e:
            self.error_occurred.emit(str(e))
            self.thinking_finished.emit()

    def _get_cache_key(self) -> str:
        """Generate a cache key from the prompt and context"""
        combined = f"{self.prompt}_{self.context}_{self.model}"
        return hashlib.md5(combined.encode()).hexdigest()

class DataChatView(QWidget):
    """AI-powered chat interface for querying data across projects using Ollama"""

    def __init__(self, parent=None, db=None, project_data=None):
        super().__init__(parent)
        self.parent_app = parent
        self.db = db
        self.project_data = project_data
        self.project_id = project_data.get('id')
        self.project_name = project_data.get('name', 'Chat Project')
        self.data_path = project_data.get('data_path')

        # Chat sessions
        self.chat_sessions = {}
        self.current_session_id = None
        self.chat_messages = {}
        self.session_names = {}
        self.next_session_id = 1

        # Cache for responses
        self.response_cache = OrderedDict(maxsize=100)

        # AI settings - Using Ollama
        self.ai_enabled = False
        self.current_model = "qwen2.5:1.5b"
        self.available_models = ["qwen2.5:1.5b", "gemma:2b", "phi:mini", "tinyllama:1.1b", "mistral:7b"]
        self.model_available = False
        self.ollama_running = False

        # Initialize Mullama backend instead of Ollama
        self.ai_backend = MullamaManager()
        self.ai_enabled = False
        self.model_available = self.ai_backend.get_active_backend() is not None

        # Selected projects for context
        self.selected_projects = []

        # Setup UI
        self.setup_ui()

        # Load projects for selection
        self.load_projects()

        self.load_chat_sessions()

        # Check Ollama status
        self.check_ollama_status()

        self.update_status("Ready")

    def setup_ui(self):
        """Setup the chat interface"""
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

        name_label = QLabel(f"💬 {self.project_name}")
        name_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #1c242e;")
        top_bar.addWidget(name_label)

        top_bar.addStretch()

        # AI Enable button
        self.ai_toggle = QPushButton("🤖 Enable AI")
        self.ai_toggle.setCheckable(True)
        self.ai_toggle.setChecked(False)
        self.ai_toggle.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #666;
                font-weight: bold;
                padding: 4px 14px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:checked {
                background-color: #4CAF50;
                color: white;
            }
            QPushButton:checked:hover { background-color: #45a049; }
        """)
        self.ai_toggle.clicked.connect(self.toggle_ai)
        top_bar.addWidget(self.ai_toggle)

        # AI Status label
        self.ai_status_label = QLabel("⚪ AI Disabled")
        self.ai_status_label.setStyleSheet("color: #666; font-size: 11px;")
        top_bar.addWidget(self.ai_status_label)

        # Model dropdown
        self.model_combo = QComboBox()
        self.model_combo.setMaximumWidth(150)
        self.model_combo.addItems(self.available_models)
        self.model_combo.setCurrentText("qwen2.5:1.5b")
        self.model_combo.setEnabled(True)
        self.model_combo.currentTextChanged.connect(self.change_model)
        top_bar.addWidget(self.model_combo)

        # Refresh button
        refresh_btn = QPushButton("🔄")
        refresh_btn.setFixedSize(30, 30)
        refresh_btn.setToolTip("Check Ollama status")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #e0e0e0; }
        """)
        refresh_btn.clicked.connect(self.refresh_ollama)
        top_bar.addWidget(refresh_btn)

        # Pull model button
        pull_btn = QPushButton("📥 Pull Model")
        pull_btn.setMaximumWidth(100)
        pull_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #F57C00; }
        """)
        pull_btn.clicked.connect(self.pull_model)
        top_bar.addWidget(pull_btn)

        # Privacy badge
        privacy_badge = QLabel("🔒 100% OFFLINE - Your data stays on your computer")
        privacy_badge.setStyleSheet("""
            QLabel {
                background-color: #e8f5e9;
                color: #2e7d32;
                padding: 4px 12px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        top_bar.addWidget(privacy_badge)

        layout.addLayout(top_bar)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left panel: Sessions and project selector
        left_widget = self.create_left_panel()
        splitter.addWidget(left_widget)

        # Right panel: Chat and Notes
        right_widget = self.create_right_panel()
        splitter.addWidget(right_widget)

        splitter.setSizes([300, 900])
        layout.addWidget(splitter)

        self.setLayout(layout)

    def create_left_panel(self):
        """Create the left panel with sessions and project selector"""
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Sessions section
        sessions_label = QLabel("💬 Chat Sessions")
        sessions_label.setStyleSheet("font-weight: bold; padding: 5px; background-color: #f0f0f0;")
        left_layout.addWidget(sessions_label)

        self.session_list = QListWidget()
        self.session_list.itemClicked.connect(self.load_session)
        self.session_list.setStyleSheet("""
            QListWidget::item:hover { background-color: #e0f0ff; }
            QListWidget::item:selected { background-color: #4CAF50; color: white; }
        """)
        left_layout.addWidget(self.session_list)

        session_btns = QHBoxLayout()
        new_session_btn = QPushButton("+ New Session")
        new_session_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        new_session_btn.clicked.connect(self.create_new_session)
        session_btns.addWidget(new_session_btn)

        delete_session_btn = QPushButton("🗑️ Delete")
        delete_session_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        delete_session_btn.clicked.connect(self.delete_current_session)
        session_btns.addWidget(delete_session_btn)

        left_layout.addLayout(session_btns)

        # Project selection section
        projects_label = QLabel("📊 Projects to Query")
        projects_label.setStyleSheet("font-weight: bold; padding: 5px; background-color: #f0f0f0; margin-top: 8px;")
        left_layout.addWidget(projects_label)

        # Add Select All / Deselect All buttons
        project_btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 2px 8px;
                border-radius: 3px;
                font-size: 10px;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        select_all_btn.clicked.connect(self.select_all_projects)
        project_btn_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 2px 8px;
                border-radius: 3px;
                font-size: 10px;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        deselect_all_btn.clicked.connect(self.deselect_all_projects)
        project_btn_layout.addWidget(deselect_all_btn)
        project_btn_layout.addStretch()
        left_layout.addLayout(project_btn_layout)

        # Project selection with checkboxes
        self.project_list = QListWidget()
        self.project_list.setSelectionMode(QListWidget.MultiSelection)
        self.project_list.setStyleSheet("""
            QListWidget::item:hover { background-color: #e0f0ff; }
            QListWidget::item:selected { background-color: #4CAF50; color: white; }
        """)
        self.project_list.itemSelectionChanged.connect(self.update_selected_projects)
        left_layout.addWidget(self.project_list)

        # Selected projects count
        self.project_count_label = QLabel("Selected: 0 projects")
        self.project_count_label.setStyleSheet("color: #666; font-size: 11px; padding: 4px;")
        left_layout.addWidget(self.project_count_label)

        # Cache controls
        cache_label = QLabel("💾 Response Cache")
        cache_label.setStyleSheet("font-weight: bold; padding: 5px; background-color: #f0f0f0; margin-top: 8px;")
        left_layout.addWidget(cache_label)

        cache_btns = QHBoxLayout()
        clear_cache_btn = QPushButton("Clear Cache")
        clear_cache_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #F57C00; }
        """)
        clear_cache_btn.clicked.connect(self.clear_cache)
        cache_btns.addWidget(clear_cache_btn)

        self.cache_count_label = QLabel("0 responses cached")
        self.cache_count_label.setStyleSheet("color: #888; font-size: 10px; padding: 4px;")
        cache_btns.addWidget(self.cache_count_label)

        left_layout.addLayout(cache_btns)

        left_layout.addStretch()
        left_widget.setLayout(left_layout)
        return left_widget

    def create_right_panel(self):
        """Create the right panel with chat and notes tabs"""
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

        # Chat tab
        chat_widget = self.create_chat_tab()
        self.tabs.addTab(chat_widget, "💬 Chat")

        # Notes tab
        notes_widget = self.create_notes_tab()
        self.tabs.addTab(notes_widget, "📝 Notes")

        right_layout.addWidget(self.tabs)
        right_widget.setLayout(right_layout)
        return right_widget

    def create_chat_tab(self):
        """Create the chat tab with message display and input"""
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setSpacing(5)

        # Chat display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #fcfcfc;
                border: none;
                padding: 20px;
                font-size: 13px;
                line-height: 1.6;
            }
        """)
        chat_layout.addWidget(self.chat_display, 1)

        # Input area
        input_layout = QHBoxLayout()
        input_layout.setSpacing(5)

        self.chat_input = QTextEdit()
        self.chat_input.setPlaceholderText("Ask about your data... (Select projects on the left for context)")
        self.chat_input.setMaximumHeight(100)
        self.chat_input.setStyleSheet("""
            QTextEdit {
                border: 2px solid #ddd;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
                background-color: white;
            }
            QTextEdit:focus {
                border-color: #4CAF50;
            }
        """)
        self.chat_input.installEventFilter(self)

        send_btn = QPushButton("Send")
        send_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 6px;
                font-size: 14px;
                min-height: 40px;
            }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:disabled {
                background-color: #ccc;
                color: #888;
            }
        """)
        send_btn.clicked.connect(self.send_message)

        input_layout.addWidget(self.chat_input, 1)
        input_layout.addWidget(send_btn)

        chat_layout.addLayout(input_layout)

        return chat_widget

    def create_notes_tab(self):
        """Create the notes tab"""
        notes_widget = QWidget()
        notes_layout = QVBoxLayout(notes_widget)

        # Notes toolbar
        notes_toolbar = QHBoxLayout()
        notes_toolbar.addWidget(QLabel("Notes for this chat session"))

        # Copy notes button
        copy_notes_btn = QPushButton("📋 Copy Notes")
        copy_notes_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 4px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        copy_notes_btn.clicked.connect(self.copy_notes)
        notes_toolbar.addStretch()
        notes_toolbar.addWidget(copy_notes_btn)

        notes_layout.addLayout(notes_toolbar)

        # Notes editor
        self.notes_editor = QTextEdit()
        self.notes_editor.setPlaceholderText(
            "Take notes about your data analysis...\n\nThese notes are saved with this chat session.")
        self.notes_editor.setFont(QFont("Segoe UI", 12))
        self.notes_editor.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 12px;
                background-color: white;
            }
        """)
        self.notes_editor.textChanged.connect(self.save_notes)
        notes_layout.addWidget(self.notes_editor)

        notes_widget.setLayout(notes_layout)
        return notes_widget

    # ============ SESSION MANAGEMENT ============
    def load_chat_sessions(self):
        """Load chat sessions from database"""
        project_data = self.db.get_project(self.project_id)
        if project_data and 'chat_sessions' in project_data.get('metadata', {}):
            sessions_data = project_data['metadata']['chat_sessions']

            # Convert keys to integers
            sessions = {}
            for key, value in sessions_data.get('sessions', {}).items():
                sessions[int(key)] = value

            messages = {}
            for key, value in sessions_data.get('messages', {}).items():
                messages[int(key)] = value

            names = {}
            for key, value in sessions_data.get('names', {}).items():
                names[int(key)] = value

            self.chat_sessions = sessions
            self.chat_messages = messages
            self.session_names = names
            self.next_session_id = int(sessions_data.get('next_id', 1))

        self.update_session_list()

        if not self.chat_sessions:
            self.create_new_session()

    def save_chat_sessions(self):
        """Save chat sessions to database"""
        project_data = self.db.get_project(self.project_id)
        if project_data:
            metadata = project_data.get('metadata', {})
            # Convert keys to strings for JSON serialization
            sessions = {str(k): v for k, v in self.chat_sessions.items()}
            messages = {str(k): v for k, v in self.chat_messages.items()}
            names = {str(k): v for k, v in self.session_names.items()}

            metadata['chat_sessions'] = {
                'sessions': sessions,
                'messages': messages,
                'names': names,
                'next_id': self.next_session_id
            }
            self.db.update_project(self.project_id, metadata=metadata)

    def create_new_session(self):
        """Create a new chat session"""
        # Ensure session_id is an integer
        session_id = int(self.next_session_id)
        self.next_session_id += 1

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        name = f"Session {session_id} - {timestamp}"

        self.chat_sessions[session_id] = {
            'created': timestamp,
            'updated': timestamp,
            'message_count': 0,
            'notes': ''
        }
        self.chat_messages[session_id] = []
        self.session_names[session_id] = name

        self.current_session_id = session_id
        self.update_session_list()
        self.load_session_by_id(session_id)
        self.save_chat_sessions()

        self.update_status(f"Created new session: {name}")
        return session_id

    def update_session_list(self):
        """Update the session list display"""
        self.session_list.clear()

        # Convert all keys to int for sorting
        session_ids = []
        for sid in self.chat_sessions.keys():
            try:
                session_ids.append(int(sid))
            except (ValueError, TypeError):
                session_ids.append(sid)

        # Sort properly
        try:
            sorted_ids = sorted(session_ids, reverse=True)
        except TypeError:
            # Fallback: sort as strings if mixed types
            sorted_ids = sorted([str(sid) for sid in session_ids], reverse=True)
            # Convert back to original types
            sorted_ids = [int(sid) if sid.isdigit() else sid for sid in sorted_ids]

        for session_id in sorted_ids:
            name = self.session_names.get(session_id, f"Session {session_id}")
            count = self.chat_sessions[session_id].get('message_count', 0)
            display = f"{name} ({count} messages)"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, session_id)

            if session_id == self.current_session_id:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setBackground(QColor(0, 220, 0, 30))

            self.session_list.addItem(item)

    def load_session(self, item):
        """Load a session by list item"""
        session_id = item.data(Qt.UserRole)
        self.load_session_by_id(session_id)

    def load_session_by_id(self, session_id):
        """Load a session by ID"""
        if session_id not in self.chat_sessions:
            return

        self.current_session_id = session_id

        notes = self.chat_sessions[session_id].get('notes', '')
        self.notes_editor.blockSignals(True)
        self.notes_editor.setPlainText(notes)
        self.notes_editor.blockSignals(False)

        messages = self.chat_messages.get(session_id, [])
        self.chat_display.clear()

        if not messages:
            self.chat_display.append("💬 Welcome to your chat session!")
            self.chat_display.append("")
            self.chat_display.append("Select projects on the left to include their data as context.")
            self.chat_display.append("Enable AI to start asking questions about your data.")
            self.chat_display.append("")
            self.chat_display.append("_" * 50)
            self.chat_display.append("")

        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            timestamp = msg.get('timestamp', '')

            if role == 'user':
                self.chat_display.append(f"🧑 **You:** {content}")
            else:
                self.chat_display.append(f"🤖 **AI:** {content}")

            if timestamp:
                self.chat_display.append(f"*{timestamp}*")
            self.chat_display.append("")

        self.chat_display.moveCursor(QTextCursor.End)
        self.update_session_list()

    def delete_current_session(self):
        """Delete the current session"""
        if self.current_session_id is None:
            return

        session_id = self.current_session_id
        name = self.session_names.get(session_id, f"Session {session_id}")

        reply = QMessageBox.question(
            self,
            "Delete Session",
            f"Delete session '{name}'?\n\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            del self.chat_sessions[session_id]
            del self.chat_messages[session_id]
            del self.session_names[session_id]

            self.current_session_id = None
            self.chat_display.clear()
            self.notes_editor.clear()

            self.update_session_list()
            self.save_chat_sessions()

            if not self.chat_sessions:
                self.create_new_session()

            self.update_status(f"Deleted session: {name}")

    # ============ PROJECT SELECTION ============

    def load_projects(self):
        """Load projects for selection"""
        self.project_list.clear()

        all_projects = self.db.get_all_projects()
        for project in all_projects:
            if project['id'] == self.project_id:
                continue

            icon = {
                'data_table': '📊',
                'data_research': '🌐',
                'data_document': '📄'
            }.get(project['project_type'], '📁')

            display = f"{icon} {project['name']} ({project['project_type'].replace('_', ' ').title()})"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, project['id'])

            if project['id'] in self.selected_projects:
                item.setSelected(True)

            self.project_list.addItem(item)

        self.update_project_count()

    def update_selected_projects(self):
        """Update selected projects list"""
        self.selected_projects = []
        for item in self.project_list.selectedItems():
            project_id = item.data(Qt.UserRole)
            self.selected_projects.append(project_id)

        self.update_project_count()

    def update_project_count(self):
        """Update the project count label"""
        count = len(self.selected_projects)
        self.project_count_label.setText(f"Selected: {count} projects")

    def select_all_projects(self):
        """Select all projects in the list"""
        for i in range(self.project_list.count()):
            item = self.project_list.item(i)
            item.setSelected(True)
        self.update_selected_projects()

    def deselect_all_projects(self):
        """Deselect all projects in the list"""
        for i in range(self.project_list.count()):
            item = self.project_list.item(i)
            item.setSelected(False)
        self.update_selected_projects()

    def get_selected_project_data(self) -> List[Dict]:
        """Get data from selected projects for context"""
        context = []

        for project_id in self.selected_projects:
            project_data = self.db.get_project(project_id)
            if not project_data:
                continue

            project_name = project_data.get('name', 'Unknown')
            project_type = project_data.get('project_type', '')
            data_path = project_data.get('data_path', '')

            if project_type == 'data_table':
                try:
                    columns = self.db.get_table_column_names(data_path)
                    data = self.db.get_table_data(data_path)
                    sample = data[:5] if data else []

                    context.append({
                        'name': project_name,
                        'type': 'Data Table',
                        'columns': columns,
                        'row_count': len(data),
                        'sample': sample
                    })
                except Exception as e:
                    context.append({
                        'name': project_name,
                        'type': 'Data Table',
                        'error': str(e)
                    })

            else:
                try:
                    pages = self.db.get_research_pages(data_path)
                    total_pages = len(pages)

                    sample_texts = []
                    for page in pages[:3]:
                        text = page.get('main_text', '') or page.get('raw_html', '')
                        if text:
                            sample_texts.append(text[:300])

                    context.append({
                        'name': project_name,
                        'type': 'Research' if project_type == 'data_research' else 'Document',
                        'page_count': total_pages,
                        'sample_content': sample_texts
                    })
                except Exception as e:
                    context.append({
                        'name': project_name,
                        'type': 'Research' if project_type == 'data_research' else 'Document',
                        'error': str(e)
                    })

        return context

    def build_context_string(self) -> str:
        """Build a context string from selected projects"""
        projects_data = self.get_selected_project_data()

        if not projects_data:
            return "No projects selected for context."

        context_parts = []
        context_parts.append("=== PROJECT DATA CONTEXT ===\n")

        for project in projects_data:
            context_parts.append(f"\n--- {project['name']} ({project['type']}) ---")

            if 'error' in project:
                context_parts.append(f"⚠️ Error: {project['error']}")
                continue

            if project['type'] == 'Data Table':
                context_parts.append(f"Columns: {', '.join(project.get('columns', []))}")
                context_parts.append(f"Total rows: {project.get('row_count', 0)}")

                if project.get('sample'):
                    context_parts.append("\nSample data:")
                    for row in project['sample'][:5]:
                        context_parts.append(f"  {row}")

                    if project.get('row_count', 0) > 5:
                        context_parts.append(f"  ... and {project['row_count'] - 5} more rows")

            else:
                context_parts.append(f"Total pages: {project.get('page_count', 0)}")

                if project.get('sample_content'):
                    context_parts.append("\nSample content:")
                    for i, text in enumerate(project['sample_content'][:3], 1):
                        context_parts.append(f"  Page {i}: {text[:300]}...")

                if project.get('page_count', 0) > 3:
                    context_parts.append(f"  ... and {project['page_count'] - 3} more pages")

            context_parts.append("")

        total_projects = len(projects_data)
        total_rows = sum(p.get('row_count', 0) for p in projects_data if p['type'] == 'Data Table')
        total_pages = sum(p.get('page_count', 0) for p in projects_data if p['type'] != 'Data Table')

        context_parts.append("\n=== SUMMARY ===")
        context_parts.append(f"Total projects: {total_projects}")
        if total_rows > 0:
            context_parts.append(f"Total data rows: {total_rows}")
        if total_pages > 0:
            context_parts.append(f"Total pages: {total_pages}")

        return "\n".join(context_parts)

    # ============ OLLAMA STATUS ============

    def check_ollama_status(self):
        """Check if Ollama is running and model is available"""
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            if response.status_code == 200:
                self.ollama_running = True
                models = response.json().get('models', [])
                model_names = [m.get('name', '') for m in models]

                if self.current_model in model_names:
                    self.model_available = True
                    self.ai_status_label.setText("✅ Model Ready")
                    self.ai_status_label.setStyleSheet("color: #4CAF50; font-size: 11px;")
                    self.ai_status_label.setToolTip(f"Model {self.current_model} is ready")
                    return True
                else:
                    self.model_available = False
                    self.ai_status_label.setText(f"⚠️ Pull '{self.current_model}'")
                    self.ai_status_label.setStyleSheet("color: #FF9800; font-size: 11px;")
                    self.ai_status_label.setToolTip(f"Run: ollama pull {self.current_model}")
                    return False
            else:
                self.ollama_running = False
                self.model_available = False
                self.ai_status_label.setText("⚠️ Ollama Error")
                self.ai_status_label.setStyleSheet("color: #f44336; font-size: 11px;")
                return False
        except requests.exceptions.ConnectionError:
            self.ollama_running = False
            self.model_available = False
            self.ai_status_label.setText("⚠️ Ollama Not Running")
            self.ai_status_label.setStyleSheet("color: #f44336; font-size: 11px;")
            self.ai_status_label.setToolTip("Start Ollama with: ollama serve")
            return False
        except Exception as e:
            self.ollama_running = False
            self.model_available = False
            self.ai_status_label.setText("⚠️ Connection Error")
            self.ai_status_label.setStyleSheet("color: #f44336; font-size: 11px;")
            return False

    def refresh_ollama(self):
        """Refresh Ollama connection"""
        self.check_ollama_status()
        if self.ollama_running and self.model_available:
            self.update_status("✅ Ollama is ready")
        else:
            self.update_status("⚠️ Ollama not ready")

    def pull_model(self):
        """Pull the selected model"""
        model = self.model_combo.currentText()

        reply = QMessageBox.question(
            self,
            "Pull Model",
            f"This will download the {model} model (~1 GB).\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.No:
            return

        self.update_status(f"⏳ Pulling {model}... This may take a few minutes.")

        # Run in thread
        self.pull_thread = QThread()
        self.pull_thread.run = lambda: self._do_pull(model)
        self.pull_thread.finished.connect(self._on_pull_finished)
        self.pull_thread.start()

    def _do_pull(self, model):
        """Pull the model using Ollama"""
        try:
            # Check if ollama is available
            result = subprocess.run(["ollama", "--version"], capture_output=True, text=True)
            if result.returncode != 0:
                self._pull_error = "Ollama not found. Please install Ollama."
                return

            # Pull the model
            subprocess.run(["ollama", "pull", model], capture_output=True, text=True, timeout=600)
            self._pull_success = True
        except subprocess.TimeoutExpired:
            self._pull_error = "Pull timed out. Please try again."
        except Exception as e:
            self._pull_error = f"Error: {str(e)}"

    def _on_pull_finished(self):
        """Handle pull completion"""
        if hasattr(self, '_pull_success') and self._pull_success:
            self.update_status("✅ Model pulled successfully!")
            self.check_ollama_status()
            QMessageBox.information(self, "Success", f"Model {self.model_combo.currentText()} downloaded successfully!")
        else:
            error = getattr(self, '_pull_error', 'Unknown error')
            self.update_status(f"❌ Failed to pull model")
            QMessageBox.critical(self, "Error", f"Failed to pull model:\n\n{error}")

    # ============ AI FUNCTIONALITY ============
    def toggle_ai(self, checked):
        """Toggle AI on/off using Mullama"""
        if checked:
            # Check if backend is available
            backend = self.ai_backend.get_active_backend()

            if not backend:
                reply = QMessageBox.question(
                    self,
                    "Model Not Found",
                    "🔒 Qwen model not found or Mullama not installed.\n\n"
                    "Please ensure:\n"
                    "1. Mullama is installed: pip install mullama\n"
                    "2. Model is downloaded using download_ai_model.py\n\n"
                    "Would you like to see installation instructions?",
                    QMessageBox.Yes | QMessageBox.No
                )
                
                self.ai_toggle.setChecked(False)
                return

            # Model is ready
            self.ai_enabled = True
            self.ai_toggle.setText("🔒 AI Enabled (Mullama)")
            self.ai_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    font-weight: bold;
                    padding: 4px 14px;
                    border-radius: 4px;
                    font-size: 12px;
                }
                QPushButton:hover { background-color: #45a049; }
            """)
            self.update_status("🔒 AI Enabled - Using Mullama (100% Offline)")
            self.ai_status_label.setText("✅ Mullama Ready")
            self.ai_status_label.setStyleSheet("color: #4CAF50; font-size: 11px;")

        else:
            self.ai_enabled = False
            self.ai_toggle.setText("🤖 Enable AI")
            self.ai_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #e0e0e0;
                    color: #666;
                    font-weight: bold;
                    padding: 4px 14px;
                    border-radius: 4px;
                    font-size: 12px;
                }
                QPushButton:hover { background-color: #d0d0d0; }
            """)
            self.update_status("AI Disabled")
            self.ai_status_label.setText("⚪ AI Disabled")
            self.ai_status_label.setStyleSheet("color: #666; font-size: 11px;")

    def change_model(self, model):
        """Change the AI model"""
        self.current_model = model
        self.check_ollama_status()
        self.update_status(f"Model changed to: {model}")

    def send_message(self):
        """Send a message to the AI using Mullama"""
        prompt = self.chat_input.toPlainText().strip()
        if not prompt:
            return

        # Ensure we have a current session
        if self.current_session_id is None:
            self.create_new_session()
            self.load_session_by_id(self.current_session_id)

        if not self.ai_enabled:
            QMessageBox.warning(self, "AI Disabled", "Please enable AI first using the toggle button.")
            return

        if not self.selected_projects:
            QMessageBox.warning(
                self,
                "No Projects Selected",
                "Please select at least one project on the left to query."
            )
            return

        # Disable input during processing
        self.chat_input.setEnabled(False)
        self.chat_input.clear()

        # Add user message to chat
        timestamp = datetime.now().strftime("%H:%M")
        self.add_message_to_chat('user', prompt, timestamp)

        # Show thinking indicator
        self.update_status("🤔 Thinking with Mullama...")

        # Build context
        context = self.build_context_string()

        # Create and start thread
        self.chat_thread = ChatThread(prompt, context, self.current_model, self.ai_backend)
        self.chat_thread.response_received.connect(self.on_response_received)
        self.chat_thread.error_occurred.connect(self.on_error_occurred)
        self.chat_thread.thinking_started.connect(lambda: self.update_status("🤔 Thinking..."))
        self.chat_thread.thinking_finished.connect(lambda: self.update_status("Ready"))
        self.chat_thread.start()

    def on_response_received(self, response):
        """Handle AI response"""
        timestamp = datetime.now().strftime("%H:%M")
        self.add_message_to_chat('assistant', response, timestamp)

        self.update_status("Ready")
        self.chat_input.setEnabled(True)
        self.update_cache_info()

    def on_error_occurred(self, error):
        """Handle AI error"""
        self.add_message_to_chat('assistant', f"⚠️ {error}", datetime.now().strftime("%H:%M"))

        self.update_status(f"❌ Error")
        self.chat_input.setEnabled(True)

    def add_message_to_chat(self, role, content, timestamp):
        """Add a message to the chat display and storage"""
        if self.current_session_id is None:
            self.create_new_session()

        if role == 'user':
            self.chat_display.append(f"🧑 **You:** {content}")
        else:
            self.chat_display.append(f"🤖 **AI:** {content}")

        if timestamp:
            self.chat_display.append(f"*{timestamp}*")
        self.chat_display.append("")

        self.chat_display.moveCursor(QTextCursor.End)

        if self.current_session_id not in self.chat_messages:
            self.chat_messages[self.current_session_id] = []

        self.chat_messages[self.current_session_id].append({
            'role': role,
            'content': content,
            'timestamp': timestamp
        })

        self.chat_sessions[self.current_session_id]['updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.chat_sessions[self.current_session_id]['message_count'] = len(
            self.chat_messages[self.current_session_id])

        self.save_chat_sessions()
        self.update_session_list()

    # ============ NOTES ============

    def save_notes(self):
        """Save notes for the current session"""
        if self.current_session_id is None:
            return

        notes = self.notes_editor.toPlainText()
        self.chat_sessions[self.current_session_id]['notes'] = notes
        self.save_chat_sessions()

    def copy_notes(self):
        """Copy notes to clipboard"""
        notes = self.notes_editor.toPlainText()
        if notes:
            QGuiApplication.clipboard().setText(notes)
            self.update_status("Notes copied to clipboard")
        else:
            QMessageBox.information(self, "No Notes", "No notes to copy.")

    # ============ CACHE ============

    def clear_cache(self):
        """Clear the response cache"""
        reply = QMessageBox.question(
            self,
            "Clear Cache",
            "Clear all cached AI responses?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.response_cache.clear()
            self.update_cache_info()
            self.update_status("Cache cleared")

    def update_cache_info(self):
        """Update cache info display"""
        cache_count = len(self.response_cache)
        self.cache_count_label.setText(f"{cache_count} responses cached")

    # ============ UTILITY ============

    def update_status(self, message):
        """Update the status bar"""
        if self.parent_app and hasattr(self.parent_app, 'update_status'):
            self.parent_app.update_status(message)

    def go_back(self):
        """Go back to home"""
        if self.parent_app and hasattr(self.parent_app, 'show_home_tab'):
            self.parent_app.show_home_tab()

    def eventFilter(self, obj, event):
        """Handle Enter key in chat input"""
        if obj == self.chat_input and event.type() == event.type().KeyPress:
            if event.key() == Qt.Key_Return and not event.modifiers():
                self.send_message()
                return True
            elif event.key() == Qt.Key_Return and event.modifiers() == Qt.ShiftModifier:
                return False
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard shortcuts"""
        if event.key() == Qt.Key_C and event.modifiers() == Qt.ControlModifier:
            if self.chat_display.hasFocus():
                cursor = self.chat_display.textCursor()
                if cursor.hasSelection():
                    QGuiApplication.clipboard().setText(cursor.selectedText())
                    self.update_status("Copied selected text")
                return

        super().keyPressEvent(event)