import os
import re
import hashlib
import json
import pickle
from datetime import datetime
from collections import OrderedDict
from typing import List, Dict, Tuple, Optional, Set

import numpy as np

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QComboBox, QCheckBox,
    QTextEdit, QListWidget, QListWidgetItem, QSplitter,
    QTabWidget, QScrollArea, QFrame, QMessageBox,
    QFileDialog, QDialog, QSpinBox, QDoubleSpinBox,
    QTextBrowser, QSizePolicy, QGroupBox, QProgressDialog,
    QCheckBox, QProgressBar, QMenu, QInputDialog
)
from PySide6.QtGui import (
    QClipboard, QGuiApplication, QFont, QColor,
    QKeyEvent, QTextCursor, QTextCharFormat,
    QFontDatabase, QPixmap, QTextDocument, QAction,
    QTextOption
)
from PySide6.QtCore import QTimer

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import PCA
import pickle

from llama_cpp import Llama

# Get the base directory path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE_DIR, "ai_model", "models")
DEFAULT_MODEL_PATH = os.path.join(MODEL_DIR, "qwen2.5-1.5b-instruct.gguf")
VECTOR_STORE_PATH = os.path.join(BASE_DIR, "vector_store.pkl")


class VectorStore:
    """Vector store for RAG (Retrieval-Augmented Generation)."""

    def __init__(self):
        self.chunks = []
        self.embeddings = []
        self.vectorizer = None
        self.pca = None
        self.is_initialized = False

    def build_index(self, chunks: List[str]):
        print(f"📊 Building vector index with {len(chunks)} chunks...")
        self.chunks = chunks
        print("   Creating TF-IDF vectors...")
        self.vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words='english',
            ngram_range=(1, 2)
        )
        vectors = self.vectorizer.fit_transform(chunks)
        print("   Reducing dimensionality with PCA...")
        self.pca = PCA(n_components=100)
        self.embeddings = self.pca.fit_transform(vectors.toarray())
        self.is_initialized = True
        print(f"✅ Vector index built: {self.embeddings.shape[0]} chunks, {self.embeddings.shape[1]} dimensions")
        return self

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        if not self.is_initialized or len(self.chunks) == 0:
            return []
        query_vector = self.vectorizer.transform([query])
        query_embedding = self.pca.transform(query_vector.toarray())
        similarities = cosine_similarity(query_embedding, self.embeddings)[0]
        top_indices = np.argsort(similarities)[::-1][:top_k]
        return [(self.chunks[idx], similarities[idx]) for idx in top_indices]

    def save(self, filepath: str):
        data = {
            'chunks': self.chunks,
            'embeddings': self.embeddings,
            'vectorizer': self.vectorizer,
            'pca': self.pca,
            'is_initialized': self.is_initialized
        }
        with open(filepath, 'wb') as f:
            pickle.dump(data, f)
        print(f"💾 Vector store saved to {filepath}")

    def load(self, filepath: str):
        with open(filepath, 'rb') as f:
            data = pickle.load(f)
        self.chunks = data['chunks']
        self.embeddings = data['embeddings']
        self.vectorizer = data['vectorizer']
        self.pca = data['pca']
        self.is_initialized = data['is_initialized']
        print(f"📂 Vector store loaded: {len(self.chunks)} chunks")
        return self


class ProgressiveRAGEngine:
    """Progressive RAG engine that processes chunks in batches."""

    def __init__(self, vector_store: VectorStore, llm):
        self.vector_store = vector_store
        self.llm = llm
        self.batch_size = 5
        self.progress_callback = None

    def query(self, query: str, top_k: int = 100) -> str:
        print(f"🔍 Progressive RAG Query: {query}")
        retrieved = self.vector_store.search(query, top_k=top_k)
        print(f"   Retrieved {len(retrieved)} chunks")
        if not retrieved:
            return "No relevant information found in the data."
        reranked = self._rerank_chunks(retrieved, query)
        batch_responses = []
        total_batches = (len(reranked) + self.batch_size - 1) // self.batch_size
        for batch_num in range(total_batches):
            start_idx = batch_num * self.batch_size
            end_idx = min(start_idx + self.batch_size, len(reranked))
            batch = reranked[start_idx:end_idx]
            print(f"   Processing batch {batch_num + 1}/{total_batches} ({len(batch)} chunks)")
            if self.progress_callback:
                self.progress_callback(batch_num + 1, total_batches, len(batch))
            brief_answer = self._process_batch(query, batch, batch_num + 1, total_batches)
            if brief_answer:
                batch_responses.append(brief_answer)
        final_answer = self._synthesize_answers(query, batch_responses)
        return final_answer

    def _rerank_chunks(self, chunks: List[Tuple[str, float]], query: str) -> List[Tuple[str, float]]:
        query_words = set(re.findall(r'\w+', query.lower()))
        reranked = []
        seen_keywords = set()
        for chunk, score in chunks:
            chunk_words = set(re.findall(r'\w+', chunk.lower()))
            overlap = chunk_words.intersection(seen_keywords)
            diversity_penalty = len(overlap) / max(len(chunk_words), 1) * 0.3
            new_keywords = chunk_words - seen_keywords
            diversity_boost = len(new_keywords) / max(len(query_words), 1) * 0.2
            final_score = score + diversity_boost - diversity_penalty
            reranked.append((chunk, final_score))
            seen_keywords.update(chunk_words)
        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked

    def _process_batch(self, query: str, batch: List[Tuple[str, float]], batch_num: int, total_batches: int) -> str:
        context_parts = []
        for chunk, score in batch:
            chunk_text = chunk[:300] + "..." if len(chunk) > 300 else chunk
            context_parts.append(f"[Score: {score:.2f}] {chunk_text}")
        context = '\n\n'.join(context_parts)
        prompt = f"""Based on these {len(batch)} text snippets, give a BRIEF answer (3-8 sentences) to the query.

QUERY: {query}

SNIPPETS:
{context}

BRIEF ANSWER:"""
        try:
            response = self.llm(prompt, max_tokens=60, temperature=0.6, top_p=0.9, stop=["###", "---", "```"])
            content = response['choices'][0]['text'].strip()
            if not content:
                content = f"[Batch {batch_num}] No clear answer found."
        except Exception as e:
            print(f"   ⚠️ Batch {batch_num} error: {e}")
            content = f"[Batch {batch_num}] Could not process this batch."
        return content

    def _synthesize_answers(self, query: str, batch_responses: List[str]) -> str:
        if not batch_responses:
            return "No answers could be generated from the data."
        combined = '\n\n'.join([f"{i + 1}. {resp}" for i, resp in enumerate(batch_responses)])
        prompt = f"""You are a research synthesizer. Combine these brief answers into a polished, comprehensive response.

QUERY: {query}

BRIEF ANSWERS FROM DIFFERENT DATA BATCHES:
{combined}

Create a well-structured final answer that:
1. Starts with a clear summary
2. Organizes the key points logically
3. Provides specific details from the data
4. Is comprehensive but concise

FINAL ANSWER:"""
        try:
            response = self.llm(prompt, max_tokens=400, temperature=0.7, top_p=0.9, stop=["###", "---", "```"])
            content = response['choices'][0]['text'].strip()
            if not content:
                content = "No final answer could be synthesized."
        except Exception as e:
            print(f"❌ Synthesis error: {e}")
            content = f"Error synthesizing answers: {str(e)}"
        content += f"\n\n---\n📚 Analyzed {len(batch_responses)} batches of data."
        return content


class ProgressiveRAGChatThread(QThread):
    response_received = Signal(str)
    error_occurred = Signal(str)
    thinking_started = Signal()
    thinking_finished = Signal()
    progress_update = Signal(int, int, int)
    status_update = Signal(str)
    batch_complete = Signal(int, int)
    all_complete = Signal()

    def __init__(self, prompt: str, vector_store: VectorStore, model_path: str,
                 top_k: int = 100, batch_size: int = 5, use_cache: bool = True):
        super().__init__()
        self.prompt = prompt
        self.vector_store = vector_store
        self.model_path = model_path
        self.top_k = min(top_k, 200)
        self.batch_size = batch_size
        self.use_cache = use_cache
        self.cache = {}
        self.llm = None
        self.is_running = True

    def run(self):
        try:
            self.thinking_started.emit()
            cache_key = self._get_cache_key()
            if self.use_cache and cache_key in self.cache:
                self.response_received.emit(self.cache[cache_key])
                self.thinking_finished.emit()
                return
            self._get_llm()
            self.status_update.emit("🔍 Retrieving relevant information...")
            rag = ProgressiveRAGEngine(self.vector_store, self.llm)
            rag.batch_size = self.batch_size
            rag.progress_callback = self._on_progress
            self.status_update.emit(f"📝 Processing {self.top_k} chunks in batches of {self.batch_size}...")
            response = rag.query(self.prompt, top_k=self.top_k)
            self.status_update.emit("✅ Complete!")
            self.all_complete.emit()
            if self.use_cache:
                self.cache[cache_key] = response
            self.response_received.emit(response)
            self.thinking_finished.emit()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(str(e))
            self.thinking_finished.emit()

    def _on_progress(self, current_batch: int, total_batches: int, chunks_in_batch: int):
        self.progress_update.emit(current_batch, total_batches, chunks_in_batch)
        self.batch_complete.emit(current_batch, total_batches)

    def _get_llm(self):
        if self.llm is None:
            print(f"Loading model from: {self.model_path}")
            try:
                self.llm = Llama(
                    model_path=self.model_path,
                    n_gpu_layers=0,
                    n_ctx=2048,
                    n_threads=4,
                    verbose=False
                )
                print("✅ Model loaded successfully!")
            except Exception as e:
                print(f"❌ Model load failed: {e}")
                self.llm = Llama(
                    model_path=self.model_path,
                    n_gpu_layers=-1,
                    n_ctx=2048,
                    verbose=False
                )
                print("✅ Model loaded with default settings!")
        return self.llm

    def _get_cache_key(self) -> str:
        combined = f"{self.prompt}_{self.top_k}_{self.batch_size}"
        return hashlib.md5(combined.encode()).hexdigest()

    def stop(self):
        self.is_running = False


class SentenceChunker:
    def __init__(self, min_sentences: int = 2, max_sentences: int = 5):
        self.min_sentences = min_sentences
        self.max_sentences = max_sentences

    def chunk_text(self, text: str) -> List[str]:
        if not text or not text.strip():
            return []
        sentences = self._split_sentences(text)
        sentences = [s for s in sentences if len(s.split()) > 3]
        if not sentences:
            return []
        chunks = []
        i = 0
        total = len(sentences)
        while i < total:
            remaining = total - i
            if remaining <= self.max_sentences:
                chunk_size = remaining
            elif remaining <= self.max_sentences + 2:
                chunk_size = remaining // 2
            else:
                chunk_size = min(self.max_sentences, max(self.min_sentences, remaining // 3))
                chunk_size = max(self.min_sentences, min(self.max_sentences, chunk_size))
            chunk_sentences = sentences[i:i + chunk_size]
            chunk = ' '.join(chunk_sentences).strip()
            if chunk and chunk[-1] not in '.!?':
                chunk += '.'
            chunks.append(chunk)
            i += chunk_size
        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        text = text.replace('\n', ' ').replace('\r', ' ')
        text = re.sub(r'\s+', ' ', text)
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
        if len(sentences) <= 1:
            sentences = re.split(r'(?<=[.!?])\s+', text)
        cleaned = []
        for s in sentences:
            s = s.strip()
            if s:
                if s[-1] not in '.!?':
                    s += '.'
                cleaned.append(s)
        return cleaned


class DataProcessor:
    def __init__(self, db, project_ids: List[int]):
        self.db = db
        self.project_ids = project_ids
        self.chunker = SentenceChunker(min_sentences=2, max_sentences=5)

    def process_all_data(self) -> List[str]:
        print(f"📊 Processing {len(self.project_ids)} projects...")
        all_text = []
        for project_id in self.project_ids:
            project_data = self.db.get_project(project_id)
            if not project_data:
                continue
            project_type = project_data.get('project_type', '')
            data_path = project_data.get('data_path', '')
            project_name = project_data.get('name', 'Unknown')
            print(f"   📄 Processing: {project_name} ({project_type})")
            if project_type == 'data_table':
                text = self._process_table(data_path)
                if text:
                    all_text.append(text)
            else:
                text = self._process_research_pages(data_path)
                if text:
                    all_text.append(text)
        combined = '\n\n'.join(all_text)
        print(f"📝 Total text length: {len(combined)} characters")
        chunks = self.chunker.chunk_text(combined)
        print(f"📄 Created {len(chunks)} chunks")
        return chunks

    def _process_table(self, data_path: str) -> str:
        try:
            columns = self.db.get_table_column_names(data_path)
            data = self.db.get_table_data(data_path)
            if not data:
                return ""
            lines = []
            lines.append(f"Columns: {', '.join(columns)}")
            lines.append(f"Total rows: {len(data)}")
            lines.append("")
            lines.append("Data:")
            for row in data[:20]:
                lines.append(str(row))
            if len(data) > 20:
                lines.append(f"... and {len(data) - 20} more rows")
            return '\n'.join(lines)
        except Exception as e:
            print(f"   ⚠️ Error processing table: {e}")
            return ""

    def _process_research_pages(self, data_path: str) -> str:
        try:
            pages = self.db.get_research_pages(data_path)
            if not pages:
                return ""
            print(f"      📄 Found {len(pages)} pages")
            all_text = []
            for page in pages:
                text = page.get('main_text', '') or page.get('raw_html', '')
                if text:
                    all_text.append(text)
            if not all_text:
                return ""
            return '\n\n--- PAGE BREAK ---\n\n'.join(all_text)
        except Exception as e:
            print(f"   ⚠️ Error processing pages: {e}")
            return ""


class DataChatView(QWidget):
    """Main chat view with RAG support and progress bar."""

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
        self.vector_store_path = os.path.join(BASE_DIR, "vector_store.pkl")

        # Cache
        self.response_cache = OrderedDict(maxsize=100)

        # AI settings
        self.ai_enabled = False
        self.model_path = DEFAULT_MODEL_PATH
        self.model_loaded = False
        self.llm = None

        # Selected projects
        self.selected_projects = []

        # Vector store for RAG
        self.vector_store = VectorStore()
        self.is_vectorized = False

        # Text direction
        self.text_direction = Qt.LeftToRight

        # Setup UI
        self.setup_ui()
        self.load_projects()
        self.load_chat_sessions()
        self.check_model_status()
        self.update_status("Ready")

    def setup_ui(self):
        """Setup the chat interface with progress bar at top."""
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(2)
        layout.setContentsMargins(0, 0, 0, 0)

        # === PROGRESS BAR ===
        progress_container = QWidget()
        progress_container.setStyleSheet("background-color: #f0f0f0; border: none; padding: 0px; margin: 0px;")
        progress_container.setFixedHeight(22)
        progress_layout = QHBoxLayout(progress_container)
        progress_layout.setContentsMargins(5, 0, 5, 0)
        progress_layout.setSpacing(5)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #e0e0e0;
                border-radius: 3px;
                text-align: center;
                font-size: 10px;
                font-weight: bold;
                color: #333;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #4CAF50,
                    stop: 0.5 #8BC34A,
                    stop: 1 #4CAF50
                );
                border-radius: 3px;
            }
        """)
        progress_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("Ready")
        self.progress_label.setStyleSheet("font-size: 10px; color: #666; padding: 0px 4px; min-width: 180px;")
        progress_layout.addWidget(self.progress_label)

        layout.addWidget(progress_container)

        # === TOP BAR ===
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)
        top_bar.setContentsMargins(5, 2, 5, 2)

        back_btn = QPushButton("← Back")
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #666;
                color: white;
                font-weight: bold;
                padding: 4px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #555; }
        """)
        back_btn.clicked.connect(self.go_back)
        top_bar.addWidget(back_btn)

        name_label = QLabel(f"💬 {self.project_name}")
        name_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #1c242e;")
        top_bar.addWidget(name_label)
        top_bar.addStretch()

        # RAG Controls
        controls_group = QGroupBox("RAG Controls")
        controls_group.setStyleSheet("QGroupBox { border: none; padding: 0px; margin: 0px; }")
        controls_layout = QHBoxLayout(controls_group)
        controls_layout.setSpacing(6)
        controls_layout.setContentsMargins(0, 0, 0, 0)

        controls_layout.addWidget(QLabel("Top K:"))
        self.top_k_spinner = QSpinBox()
        self.top_k_spinner.setRange(20, 200)
        self.top_k_spinner.setValue(100)
        self.top_k_spinner.setFixedWidth(50)
        self.top_k_spinner.setStyleSheet("font-size: 11px;")
        controls_layout.addWidget(self.top_k_spinner)

        controls_layout.addWidget(QLabel("Batch:"))
        self.batch_size_spinner = QSpinBox()
        self.batch_size_spinner.setRange(3, 15)
        self.batch_size_spinner.setValue(5)
        self.batch_size_spinner.setFixedWidth(40)
        self.batch_size_spinner.setStyleSheet("font-size: 11px;")
        controls_layout.addWidget(self.batch_size_spinner)

        self.build_index_btn = QPushButton("📊 Build Index")
        self.build_index_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                font-weight: bold;
                padding: 3px 10px;
                border-radius: 4px;
                font-size: 10px;
            }
            QPushButton:hover { background-color: #7B1FA2; }
        """)
        self.build_index_btn.clicked.connect(self.build_vector_index)
        controls_layout.addWidget(self.build_index_btn)

        top_bar.addWidget(controls_group)

        # AI toggle
        self.ai_toggle = QPushButton("🤖 Enable AI")
        self.ai_toggle.setCheckable(True)
        self.ai_toggle.setChecked(False)
        self.ai_toggle.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #666;
                font-weight: bold;
                padding: 3px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:checked {
                background-color: #4CAF50;
                color: white;
            }
            QPushButton:checked:hover { background-color: #45a049; }
        """)
        self.ai_toggle.clicked.connect(self.toggle_ai)
        top_bar.addWidget(self.ai_toggle)

        self.ai_status_label = QLabel("⚪ AI Disabled")
        self.ai_status_label.setStyleSheet("color: #666; font-size: 10px;")
        top_bar.addWidget(self.ai_status_label)

        model_info = QLabel("🧠 Qwen2.5-1.5B")
        model_info.setStyleSheet(
            "color: #555; font-size: 9px; padding: 2px 6px; background-color: #f0f0f0; border-radius: 3px;")
        top_bar.addWidget(model_info)

        load_btn = QPushButton("📥 Load")
        load_btn.setMaximumWidth(55)
        load_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                padding: 3px 6px;
                border-radius: 4px;
                font-size: 10px;
            }
            QPushButton:hover { background-color: #F57C00; }
        """)
        load_btn.clicked.connect(self.load_model)
        top_bar.addWidget(load_btn)

        privacy_badge = QLabel("🔒 OFFLINE")
        privacy_badge.setStyleSheet("""
            QLabel {
                background-color: #e8f5e9;
                color: #2e7d32;
                padding: 2px 8px;
                border-radius: 3px;
                font-size: 9px;
                font-weight: bold;
            }
        """)
        top_bar.addWidget(privacy_badge)

        layout.addLayout(top_bar)

        # === MAIN SPLITTER ===
        splitter = QSplitter(Qt.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        left_widget = self.create_left_panel()
        splitter.addWidget(left_widget)
        right_widget = self.create_right_panel()
        splitter.addWidget(right_widget)
        splitter.setSizes([300, 900])
        layout.addWidget(splitter)

        self.setLayout(layout)

    def create_left_panel(self):
        """Create the left panel with sessions and project selector."""
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)

        # Sessions
        sessions_label = QLabel("💬 Chat Sessions")
        sessions_label.setStyleSheet("font-weight: bold; padding: 4px 8px; background-color: #f0f0f0; font-size: 12px;")
        left_layout.addWidget(sessions_label)

        self.session_list = QListWidget()
        self.session_list.setStyleSheet("font-size: 12px;")
        self.session_list.itemClicked.connect(self.load_session)
        self.session_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.session_list.customContextMenuRequested.connect(self._show_session_context_menu)
        left_layout.addWidget(self.session_list)

        session_btns = QHBoxLayout()
        new_btn = QPushButton("+ New")
        new_btn.setStyleSheet("font-size: 10px; padding: 2px 8px;")
        new_btn.clicked.connect(self.create_new_session)
        session_btns.addWidget(new_btn)
        delete_btn = QPushButton("🗑️")
        delete_btn.setStyleSheet("font-size: 10px; padding: 2px 8px;")
        delete_btn.clicked.connect(self.delete_selected_sessions)
        session_btns.addWidget(delete_btn)
        session_btns.addStretch()
        left_layout.addLayout(session_btns)

        # Search within sessions (by content)
        session_search_label = QLabel("🔍 Search sessions:")
        session_search_label.setStyleSheet("font-size: 10px; color: #666; padding: 2px 4px;")
        left_layout.addWidget(session_search_label)

        self.session_search = QLineEdit()
        self.session_search.setPlaceholderText("Search session content...")
        self.session_search.setStyleSheet(
            "font-size: 11px; padding: 3px 6px; border: 1px solid #ddd; border-radius: 3px;")
        self.session_search.textChanged.connect(self._filter_sessions_by_content)
        left_layout.addWidget(self.session_search)

        # Projects
        projects_label = QLabel("📊 Projects to Query")
        projects_label.setStyleSheet(
            "font-weight: bold; padding: 4px 8px; background-color: #f0f0f0; font-size: 12px; margin-top: 4px;")
        left_layout.addWidget(projects_label)

        self.project_list = QListWidget()
        self.project_list.setSelectionMode(QListWidget.MultiSelection)
        self.project_list.setStyleSheet("font-size: 12px;")
        self.project_list.itemSelectionChanged.connect(self.update_selected_projects)
        left_layout.addWidget(self.project_list)

        self.project_count_label = QLabel("Selected: 0 projects")
        self.project_count_label.setStyleSheet("color: #666; font-size: 10px; padding: 2px 4px;")
        left_layout.addWidget(self.project_count_label)

        self.index_status_label = QLabel("📊 No vector index")
        self.index_status_label.setStyleSheet("color: #888; font-size: 10px; padding: 2px 4px;")
        left_layout.addWidget(self.index_status_label)

        left_layout.addStretch()
        return left_widget

    def _filter_sessions_by_content(self, text: str):
        """Filter sessions by searching through their content."""
        text = text.lower().strip()
        if not text:
            # Show all sessions
            for i in range(self.session_list.count()):
                self.session_list.item(i).setHidden(False)
            return

        for i in range(self.session_list.count()):
            item = self.session_list.item(i)
            session_id = item.data(Qt.UserRole)
            messages = self.chat_messages.get(session_id, [])

            # Search through all messages in this session
            found = False
            for msg in messages:
                content = msg.get('content', '').lower()
                if text in content:
                    found = True
                    break

            item.setHidden(not found)

    def _show_session_context_menu(self, position):
        """Show context menu for session list."""
        menu = QMenu()
        rename_action = QAction("✏️ Rename Session", self)
        rename_action.triggered.connect(self._rename_selected_session)
        menu.addAction(rename_action)
        menu.exec_(self.session_list.mapToGlobal(position))

    def _rename_selected_session(self):
        """Rename the selected session."""
        item = self.session_list.currentItem()
        if not item:
            return
        session_id = item.data(Qt.UserRole)
        current_name = self.session_names.get(session_id, f"Session {session_id}")
        new_name, ok = QInputDialog.getText(
            self, "Rename Session", "Enter new session name:",
            QLineEdit.Normal, current_name
        )
        if ok and new_name.strip():
            self.session_names[session_id] = new_name.strip()
            self.save_chat_sessions()
            self.update_session_list()

    def create_right_panel(self):
        """Create the right panel."""
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabBar::tab { font-size: 12px; padding: 4px 12px; }")

        # Chat tab
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setSpacing(4)
        chat_layout.setContentsMargins(4, 4, 4, 4)

        # Chat display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setAcceptRichText(True)
        # Set initial direction
        self.chat_display.setLayoutDirection(Qt.LeftToRight)
        # Use a text option to ensure proper alignment
        self.chat_display.setAlignment(Qt.AlignLeft)
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #fcfcfc;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 12px;
                font-size: 13px;
                line-height: 1.6;
            }
        """)
        chat_layout.addWidget(self.chat_display, 1)

        # Input area
        input_layout = QHBoxLayout()
        input_layout.setSpacing(4)
        self.chat_input = QTextEdit()
        self.chat_input.setPlaceholderText("Ask about your data... (Build index first)")
        self.chat_input.setMaximumHeight(80)
        self.chat_input.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 6px;
                font-size: 13px;
            }
            QTextEdit:focus { border-color: #4CAF50; }
        """)
        self.chat_input.installEventFilter(self)
        input_layout.addWidget(self.chat_input, 1)

        send_btn = QPushButton("Send")
        send_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 13px;
                min-height: 32px;
            }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:disabled { background-color: #ccc; color: #888; }
        """)
        send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(send_btn)

        chat_layout.addLayout(input_layout)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        toolbar.setContentsMargins(4, 2, 4, 2)

        # Search within current session
        self.chat_search = QLineEdit()
        self.chat_search.setPlaceholderText("🔍 Search in chat...")
        self.chat_search.setStyleSheet("font-size: 11px; padding: 2px 6px; border: 1px solid #ddd; border-radius: 3px;")
        self.chat_search.returnPressed.connect(self._search_chat)
        toolbar.addWidget(self.chat_search)

        toolbar.addStretch()

        # Font family
        toolbar.addWidget(QLabel("Font:"))
        self.font_combo = QComboBox()
        self.font_combo.addItems(["Segoe UI", "Arial", "Times New Roman", "Courier New", "Georgia", "Verdana"])
        self.font_combo.setStyleSheet("font-size: 11px; padding: 1px 4px;")
        self.font_combo.currentTextChanged.connect(self._update_chat_style)
        toolbar.addWidget(self.font_combo)

        # Font size
        toolbar.addWidget(QLabel("Size:"))
        self.font_size_spinner = QSpinBox()
        self.font_size_spinner.setRange(8, 24)
        self.font_size_spinner.setValue(13)
        self.font_size_spinner.setFixedWidth(40)
        self.font_size_spinner.setStyleSheet("font-size: 11px;")
        self.font_size_spinner.valueChanged.connect(self._update_chat_style)
        toolbar.addWidget(self.font_size_spinner)

        # Line height
        toolbar.addWidget(QLabel("Line Ht:"))
        self.line_height_spinner = QDoubleSpinBox()
        self.line_height_spinner.setRange(1.0, 3.0)
        self.line_height_spinner.setValue(1.6)
        self.line_height_spinner.setSingleStep(0.1)
        self.line_height_spinner.setFixedWidth(45)
        self.line_height_spinner.setStyleSheet("font-size: 11px;")
        self.line_height_spinner.valueChanged.connect(self._update_chat_style)
        toolbar.addWidget(self.line_height_spinner)

        # Text direction toggle
        self.direction_btn = QPushButton("⇄ LTR")
        self.direction_btn.setFixedWidth(60)
        self.direction_btn.setStyleSheet("""
            QPushButton {
                background-color: #e0e0e0;
                color: #333;
                font-weight: bold;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 10px;
            }
            QPushButton:hover { background-color: #d0d0d0; }
        """)
        self.direction_btn.clicked.connect(self._toggle_text_direction)
        toolbar.addWidget(self.direction_btn)

        chat_layout.addLayout(toolbar)

        self.tabs.addTab(chat_widget, "💬 Chat")

        # Notes tab
        notes_widget = QWidget()
        notes_layout = QVBoxLayout(notes_widget)
        self.notes_editor = QTextEdit()
        self.notes_editor.setPlaceholderText("Take notes...")
        self.notes_editor.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
            }
        """)
        notes_layout.addWidget(self.notes_editor)
        self.tabs.addTab(notes_widget, "📝 Notes")

        right_layout.addWidget(self.tabs)
        return right_widget

    def _toggle_text_direction(self):
        """Toggle text direction between LTR and RTL."""
        if self.text_direction == Qt.LeftToRight:
            self.text_direction = Qt.RightToLeft
            self.direction_btn.setText("⇄ RTL")
            self.direction_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    font-weight: bold;
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-size: 10px;
                }
                QPushButton:hover { background-color: #1976D2; }
            """)
        else:
            self.text_direction = Qt.LeftToRight
            self.direction_btn.setText("⇄ LTR")
            self.direction_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e0e0e0;
                    color: #333;
                    font-weight: bold;
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-size: 10px;
                }
                QPushButton:hover { background-color: #d0d0d0; }
            """)

        # Update both the chat display and input field
        self.chat_display.setLayoutDirection(self.text_direction)
        self.chat_display.setAlignment(Qt.AlignLeft if self.text_direction == Qt.LeftToRight else Qt.AlignRight)
        self.chat_input.setLayoutDirection(self.text_direction)
        self.chat_input.setAlignment(Qt.AlignLeft if self.text_direction == Qt.LeftToRight else Qt.AlignRight)

    def _search_chat(self):
        """Search within the current chat display."""
        text = self.chat_search.text().strip()
        if not text:
            # Reset selection
            cursor = self.chat_display.textCursor()
            cursor.clearSelection()
            self.chat_display.setTextCursor(cursor)
            return

        # Create a format for highlighting
        highlight_format = QTextCharFormat()
        highlight_format.setBackground(QColor(255, 255, 0))  # Yellow highlight
        highlight_format.setForeground(QColor(0, 0, 0))  # Black text

        # Search from current position
        cursor = self.chat_display.textCursor()
        if not cursor.hasSelection():
            cursor.movePosition(QTextCursor.Start)

        # Clear existing selection
        cursor.clearSelection()

        # Search for the text
        found = self.chat_display.find(text)
        if not found:
            # Wrap around
            cursor.movePosition(QTextCursor.Start)
            self.chat_display.setTextCursor(cursor)
            found = self.chat_display.find(text)

        if found:
            # Apply highlighting to the found text
            cursor = self.chat_display.textCursor()
            cursor.mergeCharFormat(highlight_format)
            self.chat_display.setTextCursor(cursor)

    def _update_chat_style(self):
        """Update chat display styling with actual font changes."""
        font_family = self.font_combo.currentText()
        font_size = self.font_size_spinner.value()
        line_height = self.line_height_spinner.value()

        # Apply font directly to the widget
        font = QFont(font_family, font_size)
        self.chat_display.setFont(font)

        # Also set the font for the input field
        self.chat_input.setFont(font)

        # Set line height using style sheet
        self.chat_display.setStyleSheet(f"""
            QTextEdit {{
                background-color: #fcfcfc;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 12px;
                font-family: '{font_family}';
                font-size: {font_size}px;
                line-height: {line_height};
            }}
        """)

    def load_projects(self):
        """Load projects for selection."""
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
            display = f"{icon} {project['name']}"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, project['id'])
            self.project_list.addItem(item)
        self.update_project_count()

    def update_selected_projects(self):
        self.selected_projects = []
        for item in self.project_list.selectedItems():
            project_id = item.data(Qt.UserRole)
            self.selected_projects.append(project_id)
        self.update_project_count()

    def update_project_count(self):
        count = len(self.selected_projects)
        self.project_count_label.setText(f"Selected: {count} projects")

    def build_vector_index(self):
        if not self.selected_projects:
            QMessageBox.warning(self, "No Projects", "Please select projects first.")
            return

        self.update_status("⏳ Building vector index...")
        self.index_status_label.setText("⏳ Building index...")
        self.progress_bar.setValue(10)
        self.progress_label.setText("Processing data...")

        processor = DataProcessor(self.db, self.selected_projects)
        chunks = processor.process_all_data()

        if not chunks:
            QMessageBox.warning(self, "No Data", "No data found in selected projects.")
            return

        self.progress_bar.setValue(40)
        self.progress_label.setText("Building vector index...")

        self.vector_store.build_index(chunks)
        self.is_vectorized = True

        try:
            self.vector_store.save(VECTOR_STORE_PATH)
        except Exception as e:
            print(f"⚠️ Could not save vector store: {e}")

        self.index_status_label.setText(f"📊 {len(chunks)} chunks indexed")
        self.progress_bar.setValue(100)
        self.progress_label.setText("✅ Index ready!")
        QTimer.singleShot(1000, lambda: self.progress_bar.setValue(0))
        QTimer.singleShot(1000, lambda: self.progress_label.setText("Ready"))

        self.update_status(f"✅ Vector index built with {len(chunks)} chunks")

        QMessageBox.information(
            self,
            "Index Built",
            f"Successfully built vector index with {len(chunks)} chunks.\n\n"
            "You can now ask questions using RAG (Retrieval-Augmented Generation)."
        )

    def send_message(self):
        prompt = self.chat_input.toPlainText().strip()
        if not prompt:
            return

        if not self.selected_projects:
            QMessageBox.warning(self, "No Projects", "Please select projects first.")
            return

        if not self.is_vectorized:
            QMessageBox.warning(self, "No Index", "Please build the vector index first.")
            return

        if not self.ai_enabled:
            QMessageBox.warning(self, "AI Disabled", "Please enable AI first.")
            return

        if not self.model_loaded:
            QMessageBox.warning(self, "Model Not Loaded", "Please load the model first.")
            return

        if self.current_session_id is None:
            self.create_new_session()

        timestamp = datetime.now().strftime("%H:%M")
        self.add_message_to_chat('user', prompt, timestamp)
        self.chat_input.clear()
        self.chat_input.setEnabled(False)

        top_k = self.top_k_spinner.value()
        batch_size = self.batch_size_spinner.value()

        self.progress_bar.setValue(0)
        self.progress_label.setText("🔍 Starting...")

        self._create_response_placeholder()

        self.chat_thread = ProgressiveRAGChatThread(
            prompt, self.vector_store, self.model_path,
            top_k=top_k,
            batch_size=batch_size,
            use_cache=True
        )
        self.chat_thread.progress_update.connect(self.update_batch_progress)
        self.chat_thread.batch_complete.connect(self.on_batch_complete)
        self.chat_thread.all_complete.connect(self.on_all_complete)
        self.chat_thread.response_received.connect(self.on_response_received)
        self.chat_thread.error_occurred.connect(self.on_error_occurred)
        self.chat_thread.status_update.connect(self.update_status)
        self.chat_thread.start()

    def update_batch_progress(self, current_batch: int, total_batches: int, chunks_in_batch: int):
        progress = int((current_batch / total_batches) * 100)
        self.progress_bar.setValue(progress)
        self.progress_label.setText(f"📦 Batch {current_batch}/{total_batches} ({chunks_in_batch} chunks)")

    def on_batch_complete(self, current_batch: int, total_batches: int):
        pass

    def _create_response_placeholder(self):
        """Create a placeholder that gets rendered properly."""
        timestamp = datetime.now().strftime("%H:%M")

        # Create the placeholder text without HTML wrapper issues
        placeholder = "🔄 Processing batches of data..."

        # Use a simpler HTML structure that renders properly
        html = f"""
        <div style="
            background: #f8f9fa;
            border-radius: 8px;
            padding: 16px 20px;
            margin: 4px 0;
            border-left: 4px solid #9C27B0;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 14px;
            line-height: 1.8;
            color: #2d3748;
        ">
            <div style="color: #666; font-size: 12px; font-weight: 600; margin-bottom: 4px;">
                📝 Answer
            </div>
            {placeholder}
        </div>
        """
        self.chat_display.append(f"🤖 **AI:** {html}")
        self.chat_display.append(f"*{timestamp}*")
        self.chat_display.append("")
        self.chat_display.moveCursor(QTextCursor.End)

    def on_all_complete(self):
        self.chat_input.setEnabled(True)
        self.update_status("Ready")
        self.progress_label.setText("✅ Done")
        QTimer.singleShot(1500, lambda: self.progress_bar.setValue(0))
        QTimer.singleShot(1500, lambda: self.progress_label.setText("Ready"))

        # Auto-refresh the current session
        if self.current_session_id is not None:
            self.load_session_by_id(self.current_session_id)

    def on_response_received(self, response):
        """Handle the final response."""
        # Format the response with double line breaks between paragraphs
        # Split by single newlines and join with double
        paragraphs = response.split('\n')
        formatted_paragraphs = []
        for p in paragraphs:
            p = p.strip()
            if p:
                formatted_paragraphs.append(p)
        formatted_text = '<br><br>'.join(formatted_paragraphs)

        # Build the styled response
        styled = f"""
        <div style="
            background: #f8f9fa;
            border-radius: 8px;
            padding: 16px 20px;
            margin: 4px 0;
            border-left: 4px solid #4CAF50;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 14px;
            line-height: 1.8;
            color: #2d3748;
        ">
            <div style="color: #666; font-size: 12px; font-weight: 600; margin-bottom: 8px;">
                📝 Answer
            </div>
            {formatted_text}
        </div>
        """

        # Find and replace the placeholder
        html = self.chat_display.toHtml()

        # Find the last AI message and replace it
        import re
        # Look for the pattern with the placeholder
        pattern = r'<div style="background: #f8f9fa; border-radius: 8px; padding: 16px 20px; margin: 4px 0; border-left: 4px solid #9C27B0;.*?</div>'
        match = re.search(pattern, html, re.DOTALL)

        if match:
            # Replace the placeholder with the actual response
            new_html = html.replace(match.group(0), styled)
            self.chat_display.setHtml(new_html)
            self.chat_display.moveCursor(QTextCursor.End)
        else:
            # Fallback: just append
            self.chat_display.append(f"🤖 **AI:** {styled}")
            self.chat_display.append("")
            self.chat_display.moveCursor(QTextCursor.End)

        # Store in chat history
        timestamp = datetime.now().strftime("%H:%M")
        self.add_message_to_chat('assistant', response, timestamp)

    def on_error_occurred(self, error):
        self.update_status(f"❌ Error: {error}")
        self.chat_input.setEnabled(True)
        self.progress_label.setText("❌ Error")
        self.progress_bar.setStyleSheet("""
            QProgressBar::chunk {
                background-color: #f44336;
                border-radius: 3px;
            }
        """)
        QTimer.singleShot(2000, lambda: self.progress_bar.setStyleSheet("""
            QProgressBar::chunk {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #4CAF50,
                    stop: 0.5 #8BC34A,
                    stop: 1 #4CAF50
                );
                border-radius: 3px;
            }
        """))

    def load_chat_sessions(self):
        project_data = self.db.get_project(self.project_id)
        if project_data and 'chat_sessions' in project_data.get('metadata', {}):
            sessions_data = project_data['metadata']['chat_sessions']
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
        project_data = self.db.get_project(self.project_id)
        if project_data:
            metadata = project_data.get('metadata', {})
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
        session_id = int(self.next_session_id)
        self.next_session_id += 1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        # Use a generic name without emoji prefix
        name = f"Session {session_id}"

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
        return session_id

    def update_session_list(self):
        self.session_list.clear()
        session_ids = []
        for sid in self.chat_sessions.keys():
            try:
                session_ids.append(int(sid))
            except (ValueError, TypeError):
                session_ids.append(sid)

        try:
            sorted_ids = sorted(session_ids, reverse=True)
        except TypeError:
            sorted_ids = sorted([str(sid) for sid in session_ids], reverse=True)
            sorted_ids = [int(sid) if sid.isdigit() else sid for sid in sorted_ids]

        for session_id in sorted_ids:
            name = self.session_names.get(session_id, f"Session {session_id}")
            count = self.chat_sessions[session_id].get('message_count', 0)
            # Remove emoji from name if it starts with one
            clean_name = name
            if clean_name.startswith('💬'):
                clean_name = clean_name[2:].strip()
            elif clean_name.startswith('📝'):
                clean_name = clean_name[2:].strip()
            elif clean_name.startswith('💡'):
                clean_name = clean_name[2:].strip()
            display = f"💬 {clean_name} ({count})"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, session_id)
            if session_id == self.current_session_id:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setBackground(QColor(0, 220, 0, 30))
            self.session_list.addItem(item)

    def delete_selected_sessions(self):
        """Delete multiple selected sessions."""
        selected_items = self.session_list.selectedItems()
        if not selected_items:
            return

        reply = QMessageBox.question(
            self,
            "Delete Sessions",
            f"Delete {len(selected_items)} selected session(s)?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        for item in selected_items:
            session_id = item.data(Qt.UserRole)
            if session_id in self.chat_sessions:
                del self.chat_sessions[session_id]
                del self.chat_messages[session_id]
                del self.session_names[session_id]

        if self.current_session_id not in self.chat_sessions:
            self.current_session_id = None
            self.chat_display.clear()
            self.notes_editor.clear()
            if not self.chat_sessions:
                self.create_new_session()
            else:
                self.current_session_id = list(self.chat_sessions.keys())[0]
                self.load_session_by_id(self.current_session_id)

        self.update_session_list()
        self.save_chat_sessions()

    def load_session(self, item):
        session_id = item.data(Qt.UserRole)
        self.load_session_by_id(session_id)

    def load_session_by_id(self, session_id):
        if session_id not in self.chat_sessions:
            return
        self.current_session_id = session_id
        notes = self.chat_sessions[session_id].get('notes', '')
        self.notes_editor.setPlainText(notes)
        messages = self.chat_messages.get(session_id, [])
        self.chat_display.clear()
        if not messages:
            welcome = """
            <div style="
                background: #f0f8ff;
                border-radius: 8px;
                padding: 20px 24px;
                margin: 8px 0;
                border-left: 4px solid #4CAF50;
                font-size: 14px;
                line-height: 1.8;
                color: #2d3748;
            ">
                <b>💬 Welcome to your chat session!</b><br><br>
                Select projects, build index, then enable AI to start asking questions.
            </div>
            """
            self.chat_display.append(welcome)
        else:
            for msg in messages:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                timestamp = msg.get('timestamp', '')

                if role == 'user':
                    badge = "📝 Prompt"
                    color = "#2196F3"
                else:
                    badge = "📝 Answer"
                    color = "#4CAF50"

                # Replace newlines with double <br> for proper paragraph separation
                paragraphs = content.split('\n')
                formatted_content = '<br><br>'.join([p for p in paragraphs if p.strip()])

                html = f"""
                <div style="
                    background: #f8f9fa;
                    border-radius: 8px;
                    padding: 12px 16px;
                    margin: 4px 0;
                    border-left: 4px solid {color};
                    font-size: 14px;
                    line-height: 1.8;
                    color: #2d3748;
                ">
                    <div style="color: #666; font-size: 11px; font-weight: 600; margin-bottom: 4px;">
                        {badge}
                    </div>
                    {formatted_content}
                </div>
                """
                if timestamp:
                    html += f"<div style='color: #999; font-size: 11px; text-align: right; margin-top: 2px;'>{timestamp}</div>"
                self.chat_display.append(html)
        self.chat_display.moveCursor(QTextCursor.End)
        self.update_session_list()

    def delete_current_session(self):
        if self.current_session_id is None:
            return
        session_id = self.current_session_id
        name = self.session_names.get(session_id, f"Session {session_id}")
        reply = QMessageBox.question(
            self,
            "Delete Session",
            f"Delete session '{name}'?",
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
            else:
                self.current_session_id = list(self.chat_sessions.keys())[0]
                self.load_session_by_id(self.current_session_id)

    def add_message_to_chat(self, role, content, timestamp):
        if self.current_session_id is None:
            self.create_new_session()

        if not isinstance(content, str):
            content = str(content)

        if self.current_session_id not in self.chat_messages:
            self.chat_messages[self.current_session_id] = []

        self.chat_messages[self.current_session_id].append({
            'role': role,
            'content': content,
            'timestamp': timestamp
        })

        # Auto-rename session if it's the first message (without emoji prefix)
        if len(self.chat_messages[self.current_session_id]) == 1:
            prompt_preview = content[:30] + ("..." if len(content) > 30 else "")
            self.session_names[self.current_session_id] = prompt_preview
            self.update_session_list()

        self.chat_sessions[self.current_session_id]['updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.chat_sessions[self.current_session_id]['message_count'] = len(
            self.chat_messages[self.current_session_id])

        self.save_chat_sessions()
        self.update_session_list()

    def check_model_status(self):
        if os.path.exists(self.model_path):
            self.model_loaded = False
            self.ai_status_label.setText("📦 Model found")
            self.ai_status_label.setStyleSheet("color: #2196F3; font-size: 10px;")
            return True
        else:
            self.model_loaded = False
            self.ai_status_label.setText("⚠️ Model not found")
            self.ai_status_label.setStyleSheet("color: #f44336; font-size: 10px;")
            return False

    def load_model(self):
        if not os.path.exists(self.model_path):
            QMessageBox.critical(
                self,
                "Model Not Found",
                f"Model file not found at:\n{self.model_path}"
            )
            return

        reply = QMessageBox.question(
            self,
            "Load Model",
            "This will load the model. It may take a few seconds.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return

        self.update_status("⏳ Loading model...")
        self.progress_label.setText("⏳ Loading model...")
        self.progress_bar.setValue(30)

        self.load_thread = QThread()
        self.load_thread.run = self._do_load_model
        self.load_thread.finished.connect(self._on_load_finished)
        self.load_thread.start()

    def _do_load_model(self):
        try:
            self.llm = Llama(
                model_path=self.model_path,
                n_gpu_layers=0,
                n_ctx=4096,
                n_threads=4,
                verbose=False
            )
            self.model_loaded = True
        except Exception as e:
            self.model_loaded = False
            self._load_error = str(e)

    def _on_load_finished(self):
        if self.model_loaded:
            self.update_status("✅ Model loaded successfully!")
            self.ai_status_label.setText("✅ Model Ready")
            self.ai_status_label.setStyleSheet("color: #4CAF50; font-size: 10px;")
            self.progress_label.setText("✅ Model ready")
            self.progress_bar.setValue(100)
            QTimer.singleShot(1000, lambda: self.progress_bar.setValue(0))
            QTimer.singleShot(1000, lambda: self.progress_label.setText("Ready"))
            QMessageBox.information(self, "Success", "Model loaded successfully!")
        else:
            error = getattr(self, '_load_error', 'Unknown error')
            self.update_status("❌ Failed to load model")
            self.ai_status_label.setText("❌ Load Failed")
            self.ai_status_label.setStyleSheet("color: #f44336; font-size: 10px;")
            self.progress_label.setText("❌ Failed")
            QMessageBox.critical(self, "Error", f"Failed to load model:\n\n{error}")

    def toggle_ai(self, checked):
        if checked:
            if not self.model_loaded:
                reply = QMessageBox.question(
                    self,
                    "Model Not Loaded",
                    "Model is not loaded. Load it now?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self.load_model()
                self.ai_toggle.setChecked(False)
                return

            self.ai_enabled = True
            self.ai_toggle.setText("🤖 AI Enabled")
            self.ai_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    font-weight: bold;
                    padding: 3px 12px;
                    border-radius: 4px;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #45a049; }
            """)
            self.update_status("🤖 AI Enabled (RAG)")
            self.ai_status_label.setText("✅ AI Active")
            self.ai_status_label.setStyleSheet("color: #4CAF50; font-size: 10px;")
        else:
            self.ai_enabled = False
            self.ai_toggle.setText("🤖 Enable AI")
            self.ai_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #e0e0e0;
                    color: #666;
                    font-weight: bold;
                    padding: 3px 12px;
                    border-radius: 4px;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #d0d0d0; }
            """)
            self.update_status("AI Disabled")
            self.ai_status_label.setText("⚪ AI Disabled")
            self.ai_status_label.setStyleSheet("color: #666; font-size: 10px;")

    def update_status(self, message):
        if self.parent_app and hasattr(self.parent_app, 'update_status'):
            self.parent_app.update_status(message)

    def go_back(self):
        if self.parent_app and hasattr(self.parent_app, 'show_home_tab'):
            self.parent_app.show_home_tab()

    def eventFilter(self, obj, event):
        if obj == self.chat_input and event.type() == event.type().KeyPress:
            if event.key() == Qt.Key_Return and not event.modifiers():
                self.send_message()
                return True
        return super().eventFilter(obj, event)