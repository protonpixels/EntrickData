import csv
import io
import json
import os
import re
import hashlib
from datetime import datetime
from collections import OrderedDict
from typing import List, Dict, Tuple, Optional, Set
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QComboBox, QCheckBox,
    QTextEdit, QListWidget, QListWidgetItem, QSplitter,
    QTabWidget, QScrollArea, QFrame, QMessageBox,
    QFileDialog, QDialog, QSpinBox, QDoubleSpinBox,
    QTextBrowser, QSizePolicy, QGroupBox, QProgressDialog,
    QCheckBox, QProgressBar, QMenu, QInputDialog,
    QDialogButtonBox
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

from views.synthesizer_view.table_generation_thread import TableGenerationThread
from views.synthesizer_view.table_generator import ColumnDefinition, ResponseType
from views.synthesizer_view.table_results_dialog import TableResultsDialog
from views.synthesizer_view.table_setup_dialog import ColumnSetupDialog

# Get the base directory path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE_DIR, "ai_model", "models")
DEFAULT_MODEL_PATH = os.path.join(MODEL_DIR, "qwen2.5-1.5b-instruct.gguf")
VECTOR_STORE_PATH = os.path.join(BASE_DIR, "vector_store.pkl")


class MLRelevanceScorer:
    """
    Score chunks by relevance to a query using TF-IDF and cosine similarity.
    Precomputes scores for all chunks in the corpus.
    """

    def __init__(self, chunks: List[str], query: str, max_features: int = 1000):
        self.chunks = chunks
        self.query = query
        self.vectorizer = TfidfVectorizer(
            stop_words='english',
            max_features=max_features,
            ngram_range=(1, 2)
        )
        self.vectors = self.vectorizer.fit_transform(chunks)
        self.query_vector = self.vectorizer.transform([query])
        self.scores = cosine_similarity(self.query_vector, self.vectors).flatten()
        self.score_dict = {chunk: score for chunk, score in zip(chunks, self.scores)}

    def score_chunk(self, chunk: str) -> float:
        return self.score_dict.get(chunk, 0.0)


class SettingsDialog(QDialog):
    def __init__(self, parent=None, current_settings=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Processing Settings")
        self.setMinimumSize(550, 500)

        layout = QVBoxLayout(self)

        # Processing Mode
        layout.addWidget(QLabel("Processing Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "Relevancy",
            "Hierarchical",
            "Sentence Clustering"
        ])
        if current_settings and 'mode' in current_settings:
            idx = self.mode_combo.findText(current_settings['mode'])
            if idx >= 0:
                self.mode_combo.setCurrentIndex(idx)
        self.mode_combo.currentTextChanged.connect(self._update_visibility)
        layout.addWidget(self.mode_combo)

        # Relevancy settings
        self.relevancy_group = QGroupBox("Relevancy Settings")
        relevancy_layout = QVBoxLayout(self.relevancy_group)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Top K per Project:"))
        self.top_k_spinner = QSpinBox()
        self.top_k_spinner.setRange(1, 1000)
        self.top_k_spinner.setValue(20)
        if current_settings and 'top_k' in current_settings:
            self.top_k_spinner.setValue(current_settings['top_k'])
        h1.addWidget(self.top_k_spinner)
        h1.addStretch()
        relevancy_layout.addLayout(h1)

        self.process_all_check = QCheckBox("Process all chunks (ignore Top K)")
        self.process_all_check.setChecked(False)
        if current_settings and 'process_all' in current_settings:
            self.process_all_check.setChecked(current_settings['process_all'])
        relevancy_layout.addWidget(self.process_all_check)

        layout.addWidget(self.relevancy_group)

        # Hierarchical settings
        self.hierarchical_group = QGroupBox("Hierarchical Settings")
        hierarchical_layout = QVBoxLayout(self.hierarchical_group)
        hierarchical_layout.addWidget(QLabel("Uses the same settings as Relevancy mode."))
        layout.addWidget(self.hierarchical_group)

        # Sentence Clustering settings
        self.cluster_group = QGroupBox("Sentence Clustering Settings")
        cluster_layout = QVBoxLayout(self.cluster_group)

        h_sent_thresh = QHBoxLayout()
        h_sent_thresh.addWidget(QLabel("Sentence Relevancy Threshold:"))
        self.sentence_thresh_spin = QDoubleSpinBox()
        self.sentence_thresh_spin.setRange(0.0, 1.0)
        self.sentence_thresh_spin.setSingleStep(0.05)
        self.sentence_thresh_spin.setValue(0.5)
        if current_settings and 'sentence_threshold' in current_settings:
            self.sentence_thresh_spin.setValue(current_settings['sentence_threshold'])
        h_sent_thresh.addWidget(self.sentence_thresh_spin)
        cluster_layout.addLayout(h_sent_thresh)

        h_levels = QHBoxLayout()
        h_levels.addWidget(QLabel("Further Clustering Levels:"))
        self.levels_spin = QSpinBox()
        self.levels_spin.setRange(0, 5)
        self.levels_spin.setValue(0)
        if current_settings and 'clustering_levels' in current_settings:
            self.levels_spin.setValue(current_settings['clustering_levels'])
        h_levels.addWidget(self.levels_spin)
        cluster_layout.addLayout(h_levels)

        h_topk = QHBoxLayout()
        h_topk.addWidget(QLabel("Top K Clusters for Answer:"))
        self.topk_clusters_spin = QSpinBox()
        self.topk_clusters_spin.setRange(1, 50)
        self.topk_clusters_spin.setValue(5)
        if current_settings and 'top_k_clusters' in current_settings:
            self.topk_clusters_spin.setValue(current_settings['top_k_clusters'])
        h_topk.addWidget(self.topk_clusters_spin)
        cluster_layout.addLayout(h_topk)

        layout.addWidget(self.cluster_group)

        # Synthesis Settings
        self.synthesis_group = QGroupBox("Synthesis Settings")
        synthesis_layout = QVBoxLayout(self.synthesis_group)

        h_synth = QHBoxLayout()
        h_synth.addWidget(QLabel("Max Tokens:"))
        self.max_tokens_spinner = QSpinBox()
        self.max_tokens_spinner.setRange(100, 4096)
        self.max_tokens_spinner.setValue(400)
        if current_settings and 'max_tokens' in current_settings:
            self.max_tokens_spinner.setValue(current_settings['max_tokens'])
        h_synth.addWidget(self.max_tokens_spinner)
        h_synth.addStretch()
        synthesis_layout.addLayout(h_synth)

        h_temp = QHBoxLayout()
        h_temp.addWidget(QLabel("Temperature:"))
        self.temperature_spinner = QDoubleSpinBox()
        self.temperature_spinner.setRange(0.0, 2.0)
        self.temperature_spinner.setSingleStep(0.1)
        self.temperature_spinner.setValue(0.7)
        if current_settings and 'temperature' in current_settings:
            self.temperature_spinner.setValue(current_settings['temperature'])
        h_temp.addWidget(self.temperature_spinner)
        h_temp.addStretch()
        synthesis_layout.addLayout(h_temp)

        h_topp = QHBoxLayout()
        h_topp.addWidget(QLabel("Top P:"))
        self.top_p_spinner = QDoubleSpinBox()
        self.top_p_spinner.setRange(0.0, 1.0)
        self.top_p_spinner.setSingleStep(0.05)
        self.top_p_spinner.setValue(0.9)
        if current_settings and 'top_p' in current_settings:
            self.top_p_spinner.setValue(current_settings['top_p'])
        h_topp.addWidget(self.top_p_spinner)
        h_topp.addStretch()
        synthesis_layout.addLayout(h_topp)

        layout.addWidget(self.synthesis_group)

        # Common settings
        common_group = QGroupBox("Common Settings")
        common_layout = QVBoxLayout(common_group)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Batch Size:"))
        self.batch_size_spinner = QSpinBox()
        self.batch_size_spinner.setRange(1, 20)
        self.batch_size_spinner.setValue(5)
        if current_settings and 'batch_size' in current_settings:
            self.batch_size_spinner.setValue(current_settings['batch_size'])
        h2.addWidget(self.batch_size_spinner)
        h2.addStretch()
        common_layout.addLayout(h2)

        layout.addWidget(common_group)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self._update_visibility(self.mode_combo.currentText())

    def _update_visibility(self, mode: str):
        self.relevancy_group.setVisible(mode == "Relevancy")
        self.hierarchical_group.setVisible(mode == "Hierarchical")
        self.cluster_group.setVisible(mode == "Sentence Clustering")

    def get_settings(self) -> dict:
        settings = {
            'mode': self.mode_combo.currentText(),
            'top_k': self.top_k_spinner.value(),
            'process_all': self.process_all_check.isChecked(),
            'batch_size': self.batch_size_spinner.value(),
            'sentence_threshold': self.sentence_thresh_spin.value() if hasattr(self, 'sentence_thresh_spin') else 0.5,
            'clustering_levels': self.levels_spin.value() if hasattr(self, 'levels_spin') else 0,
            'top_k_clusters': self.topk_clusters_spin.value() if hasattr(self, 'topk_clusters_spin') else 5,
            'max_tokens': self.max_tokens_spinner.value(),
            'temperature': self.temperature_spinner.value(),
            'top_p': self.top_p_spinner.value(),
        }
        return settings


class VectorStore:
    """Vector store for RAG (Retrieval-Augmented Generation)."""

    def __init__(self):
        self.chunks = []
        self.embeddings = []
        self.vectorizer = None
        self.pca = None
        self.is_initialized = False
        self.chunk_project_map = {}
        self.project_names = []

    def build_index(self, chunks: List[str], project_names: List[str] = None):
        print(f"📊 Building vector index with {len(chunks)} chunks...")
        self.chunks = chunks

        if project_names:
            self.chunk_project_map = {i: project_names[i] for i in range(len(chunks))}
            self.project_names = list(set(project_names))
        else:
            self.chunk_project_map = {i: "Unknown" for i in range(len(chunks))}
            self.project_names = ["Unknown"]

        print("   Creating TF-IDF vectors...")
        self.vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words='english',
            ngram_range=(1, 2)
        )
        vectors = self.vectorizer.fit_transform(chunks)

        print("   Reducing dimensionality with PCA...")
        n_samples = vectors.shape[0]
        n_features = vectors.shape[1]
        max_components = min(n_samples, n_features, 100)

        if max_components < 2:
            print(f"   ⚠️ Too few samples ({n_samples}) for PCA, using raw TF-IDF")
            self.embeddings = vectors.toarray()
            self.pca = None
        else:
            self.pca = PCA(n_components=max_components)
            self.embeddings = self.pca.fit_transform(vectors.toarray())
            print(f"   Using {max_components} PCA components")

        self.is_initialized = True
        print(f"✅ Vector index built: {self.embeddings.shape[0]} chunks, {self.embeddings.shape[1]} dimensions")
        return self

    def search_by_project(self, query: str, project_name: str, top_k: int = 10) -> List[Tuple[str, float, int]]:
        if not self.is_initialized or len(self.chunks) == 0:
            return []

        project_indices = [i for i, p in self.chunk_project_map.items() if p == project_name]
        if not project_indices:
            return []

        query_vector = self.vectorizer.transform([query])

        if self.pca is not None:
            query_embedding = self.pca.transform(query_vector.toarray())
            chunk_embeddings = self.embeddings[project_indices]
        else:
            query_embedding = query_vector.toarray()
            chunk_embeddings = self.vectorizer.transform([self.chunks[i] for i in project_indices]).toarray()

        similarities = cosine_similarity(query_embedding, chunk_embeddings)[0]
        sorted_indices = np.argsort(similarities)[::-1][:top_k]
        results = []
        for idx in sorted_indices:
            actual_idx = project_indices[idx]
            results.append((self.chunks[actual_idx], similarities[idx], actual_idx))
        return results

    def get_all_chunks_by_project(self, project_name: str) -> List[str]:
        project_indices = [i for i, p in self.chunk_project_map.items() if p == project_name]
        return [self.chunks[i] for i in project_indices]

    def get_project_names(self) -> List[str]:
        return self.project_names

    def save(self, filepath: str):
        data = {
            'chunks': self.chunks,
            'embeddings': self.embeddings,
            'vectorizer': self.vectorizer,
            'pca': self.pca,
            'is_initialized': self.is_initialized,
            'chunk_project_map': self.chunk_project_map,
            'project_names': self.project_names
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
        self.chunk_project_map = data.get('chunk_project_map', {})
        self.project_names = data.get('project_names', [])
        print(f"📂 Vector store loaded: {len(self.chunks)} chunks")
        return self


class SemanticChunker:
    def __init__(self, similarity_threshold: float = 0.6):
        self.threshold = similarity_threshold
        self.vectorizer = TfidfVectorizer(max_features=100)

    def chunk_text(self, text: str) -> List[str]:
        sentences = self._split_sentences(text)
        if len(sentences) <= 1:
            return sentences

        try:
            vectors = self.vectorizer.fit_transform(sentences)
            similarities = cosine_similarity(vectors)

            chunks = []
            current_chunk = [sentences[0]]

            for i in range(1, len(sentences)):
                sim = similarities[i - 1][i]
                if sim > self.threshold:
                    current_chunk.append(sentences[i])
                else:
                    chunks.append(' '.join(current_chunk))
                    current_chunk = [sentences[i]]

            if current_chunk:
                chunks.append(' '.join(current_chunk))

            return chunks if chunks else [text]
        except:
            return self._fallback_chunking(sentences)

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

    def _fallback_chunking(self, sentences: List[str]) -> List[str]:
        chunks = []
        current_chunk = []
        current_length = 0

        for sentence in sentences:
            if current_length + len(sentence) > 800 and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = []
                current_length = 0
            current_chunk.append(sentence)
            current_length += len(sentence)

        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks if chunks else [' '.join(sentences)]


class WebExtractor:
    def __init__(self):
        pass

    def extract_content(self, html: str) -> str:
        import re
        from html import unescape

        if not html:
            return ""

        html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL)
        html = re.sub(r'<nav.*?>.*?</nav>', '', html, flags=re.DOTALL)
        html = re.sub(r'<header.*?>.*?</header>', '', html, flags=re.DOTALL)
        html = re.sub(r'<footer.*?>.*?</footer>', '', html, flags=re.DOTALL)

        content_patterns = [
            r'<main.*?>(.*?)</main>',
            r'<article.*?>(.*?)</article>',
            r'<div[^>]*class="[^"]*content[^"]*".*?>(.*?)</div>',
            r'<div[^>]*id="[^"]*content[^"]*".*?>(.*?)</div>',
            r'<body.*?>(.*?)</body>'
        ]

        extracted_text = ""
        for pattern in content_patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                extracted_text = match.group(1)
                break

        if not extracted_text:
            extracted_text = html

        extracted_text = re.sub(r'<[^>]+>', ' ', extracted_text)
        extracted_text = unescape(extracted_text)
        extracted_text = re.sub(r'\s+', ' ', extracted_text)

        return extracted_text.strip()

    def clean_html(self, html: str) -> str:
        import re
        from html import unescape

        html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL)
        html = re.sub(r'<[^>]+>', ' ', html)
        html = unescape(html)
        html = re.sub(r'\s+', ' ', html)
        return html.strip()


class SentenceClusterProcessor:
    def __init__(self, query: str, chunks: List[str], project_names: List[str],
                 llm, settings: dict, progress_callback=None):
        self.query = query
        self.chunks = chunks
        self.project_names = project_names
        self.llm = llm
        self.settings = settings
        self.progress_callback = progress_callback

        self.temperature = settings.get('temperature', 0.7)
        self.top_p = settings.get('top_p', 0.9)
        self.batch_size = settings.get('batch_size', 5)
        self.max_tokens = settings.get('max_tokens', 500)
        self.threshold = settings.get('sentence_threshold', 0.5)
        self.clustering_levels = settings.get('clustering_levels', 0)
        self.top_k_clusters = settings.get('top_k_clusters', 5)

        self.sentences = self._extract_sentences()
        self.clusters = self._build_clusters()

        if self.clustering_levels > 0:
            for _ in range(self.clustering_levels):
                self.clusters = self._further_cluster()

        self.selected_clusters = self._select_clusters()
        self.distilled_insights = self._distill_clusters()
        self.final_answer = self._generate_answer()

    def _extract_sentences(self) -> List[str]:
        full_text = '\n\n'.join(self.chunks)
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', full_text)
        sentences = [s.strip() for s in sentences if s.strip()]
        return sentences

    def _build_clusters(self) -> List[List[str]]:
        if not self.sentences:
            return []

        from sklearn.feature_extraction.text import TfidfVectorizer
        vectorizer = TfidfVectorizer(max_features=100, stop_words='english')
        sentence_vectors = vectorizer.fit_transform(self.sentences)

        clusters = []
        current_cluster = [self.sentences[0]]

        for i in range(1, len(self.sentences)):
            if len(current_cluster) >= 2:
                sims = []
                for s in current_cluster[-2:]:
                    sim = cosine_similarity(sentence_vectors[i], sentence_vectors[self.sentences.index(s)])[0][0]
                    sims.append(sim)
                sim_last2 = np.mean(sims)
            else:
                sim_last2 = cosine_similarity(sentence_vectors[i], sentence_vectors[self.sentences.index(current_cluster[-1])])[0][0]

            if len(current_cluster) >= 2:
                sims = []
                for s in current_cluster[:2]:
                    sim = cosine_similarity(sentence_vectors[i], sentence_vectors[self.sentences.index(s)])[0][0]
                    sims.append(sim)
                sim_first2 = np.mean(sims)
            else:
                sim_first2 = sim_last2

            sims = []
            for s in current_cluster:
                sim = cosine_similarity(sentence_vectors[i], sentence_vectors[self.sentences.index(s)])[0][0]
                sims.append(sim)
            sim_cluster = np.mean(sims)

            combined = 0.5 * sim_last2 + 0.3 * sim_first2 + 0.2 * sim_cluster

            if combined < self.threshold:
                clusters.append(current_cluster)
                current_cluster = [self.sentences[i]]
            else:
                current_cluster.append(self.sentences[i])

        if current_cluster:
            clusters.append(current_cluster)

        return clusters

    def _further_cluster(self) -> List[List[str]]:
        if len(self.clusters) <= 1:
            return self.clusters

        from sklearn.feature_extraction.text import TfidfVectorizer
        all_sentences = [s for cluster in self.clusters for s in cluster]
        vectorizer = TfidfVectorizer(max_features=100, stop_words='english')
        all_vectors = vectorizer.fit_transform(all_sentences)

        cluster_vectors = []
        start = 0
        for cluster in self.clusters:
            end = start + len(cluster)
            cluster_vec = np.asarray(np.mean(all_vectors[start:end], axis=0))
            if cluster_vec.ndim == 1:
                cluster_vec = cluster_vec.reshape(1, -1)
            cluster_vectors.append(cluster_vec)
            start = end

        new_clusters = []
        used = [False] * len(self.clusters)

        for i in range(len(self.clusters)):
            if used[i]:
                continue
            best_match = -1
            best_score = -1
            for j in range(i + 1, len(self.clusters)):
                if used[j]:
                    continue
                sim = cosine_similarity(cluster_vectors[i], cluster_vectors[j])[0][0]
                if sim > best_score:
                    best_score = sim
                    best_match = j
            if best_match != -1:
                combined = self.clusters[i] + self.clusters[best_match]
                new_clusters.append(combined)
                used[i] = True
                used[best_match] = True
            else:
                new_clusters.append(self.clusters[i])
                used[i] = True

        for i, used_flag in enumerate(used):
            if not used_flag:
                new_clusters.append(self.clusters[i])

        return new_clusters

    def _select_clusters(self) -> List[List[str]]:
        if not self.clusters:
            return []

        scorer = MLRelevanceScorer(self.sentences, self.query)
        cluster_scores = []
        for cluster in self.clusters:
            scores = [scorer.score_chunk(s) for s in cluster]
            avg_score = sum(scores) / len(scores) if scores else 0
            cluster_scores.append((cluster, avg_score))

        cluster_scores.sort(key=lambda x: x[1], reverse=True)
        selected = [cluster for cluster, _ in cluster_scores[:self.top_k_clusters]]
        return selected

    def _distill_clusters(self) -> List[str]:
        distilled = []
        for cluster in self.selected_clusters:
            cluster_text = ' '.join(cluster)
            if self._count_tokens(cluster_text) > self.max_tokens:
                chunks = self._chunk_text(cluster_text, self.max_tokens)
                summary = self._distill_chunk(chunks[0])
                for chunk in chunks[1:]:
                    summary = self._merge_summaries(summary, self._distill_chunk(chunk))
                distilled.append(summary)
            else:
                summary = self._distill_chunk(cluster_text)
                distilled.append(summary)
        return distilled

    def _chunk_text(self, text: str, max_tokens: int) -> List[str]:
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        chunks = []
        current_chunk = []
        current_tokens = 0
        for sent in sentences:
            sent_tokens = self._count_tokens(sent)
            if current_tokens + sent_tokens > max_tokens and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = []
                current_tokens = 0
            current_chunk.append(sent)
            current_tokens += sent_tokens
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        return chunks

    def _count_tokens(self, text: str) -> int:
        return len(text) // 4

    def _distill_chunk(self, text: str) -> str:
        prompt = f"""Distill the key insights from the following text into a concise summary (3-5 sentences):

{text}

Summary:"""
        return self._call_llm(prompt, max_tokens=100)

    def _merge_summaries(self, summary_a: str, summary_b: str) -> str:
        prompt = f"""Merge the following two summaries into one, keeping all information from the first and only adding new information from the second that is not already covered.

Summary A:
{summary_a}

Summary B:
{summary_b}

Merged Summary:"""
        return self._call_llm(prompt, max_tokens=150)

    def _call_llm(self, prompt: str, max_tokens: int) -> str:
        try:
            response = self.llm(
                prompt,
                max_tokens=max_tokens,
                temperature=self.temperature,
                top_p=self.top_p,
                stop=["###", "---", "```"]
            )
            content = response['choices'][0]['text'].strip()
            return content if content else ""
        except Exception as e:
            print(f"⚠️ LLM call error: {e}")
            return ""

    def _extract_claims(self, distilled_insights: List[str]) -> List[str]:
        claims = []
        for insight in distilled_insights:
            sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', insight)
            claims.extend([s.strip() for s in sentences if s.strip()])
        return claims

    def _build_context(self, claims: List[str]) -> str:
        if not claims:
            return ""

        scorer = MLRelevanceScorer(claims, self.query)
        scored = [(claim, scorer.score_chunk(claim)) for claim in claims]
        scored.sort(key=lambda x: x[1], reverse=True)

        anchor = scored[0][0]
        context_parts = [anchor]
        used = {anchor}
        total_tokens = self._count_tokens(anchor)

        anchor_scorer = MLRelevanceScorer(claims, anchor)
        remaining = [c for c, _ in scored[1:]]
        remaining.sort(key=lambda c: anchor_scorer.score_chunk(c), reverse=True)

        for claim in remaining:
            if claim in used:
                continue
            claim_tokens = self._count_tokens(claim)
            if total_tokens + claim_tokens <= self.max_tokens:
                context_parts.append(claim)
                used.add(claim)
                total_tokens += claim_tokens
            else:
                break

        return '\n\n'.join(context_parts)

    def _generate_answer(self) -> str:
        if not self.distilled_insights:
            return "No insights could be distilled."

        claims = self._extract_claims(self.distilled_insights)
        if not claims:
            return "No claims extracted."

        context = self._build_context(claims)
        if not context:
            return "No context could be built."

        prompt = f"""Answer the following query based solely on the provided context.

QUERY: {self.query}

CONTEXT:
{context}

ANSWER:"""
        return self._call_llm(prompt, max_tokens=400)


class DataProcessor:
    def __init__(self, db, project_ids: List[int], mode: str = "Relevancy",
                 max_tokens: int = 500, target_chunks: int = 10):
        self.db = db
        self.project_ids = project_ids
        self.extractor = WebExtractor()
        self.chunk_project_names = []
        self.mode = mode
        self.max_tokens = max_tokens
        self.target_chunks = target_chunks if target_chunks else 10
        self.chunker = TokenAwareChunker(max_tokens_per_chunk=max_tokens)

    def process_all_data(self) -> List[str]:
        print(f"📊 Processing {len(self.project_ids)} projects in {self.mode} mode...")
        all_chunks = []
        self.chunk_project_names = []

        for project_id in self.project_ids:
            project_data = self.db.get_project(project_id)
            if not project_data:
                continue

            project_type = project_data.get('project_type', '')
            data_path = project_data.get('data_path', '')
            project_name = project_data.get('name', 'Unknown')

            print(f"\n   📖 Reading: {project_name} ({project_type})")
            print(f"   {'=' * 40}")

            if project_type == 'data_table':
                text = self._process_table(data_path)
            elif project_type == 'data_chat':
                text = self._process_chat_project(project_data)
            else:
                text = self._process_research_pages(data_path)

            if text:
                self.chunker.max_tokens = self.max_tokens
                chunks = self.chunker.chunk_text(text)
                print(f"   📄 Created {len(chunks)} chunks from {project_name}")

                for chunk in chunks:
                    all_chunks.append(chunk)
                    self.chunk_project_names.append(project_name)
            else:
                print(f"   ⚠️ No content found in {project_name}")

        print(f"\n📝 Total: {len(all_chunks)} chunks from {len(self.project_ids)} projects")
        return all_chunks

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

    def _process_chat_project(self, project_data: dict) -> str:
        metadata = project_data.get('metadata', {})
        sessions_data = metadata.get('chat_sessions', {})
        messages_data = sessions_data.get('messages', {})

        all_text = []
        for session_id, messages in messages_data.items():
            session_parts = []
            for msg in messages:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                if content:
                    session_parts.append(f"[{role.upper()}]: {content}")
            if session_parts:
                all_text.append('\n'.join(session_parts))

        return '\n\n--- SESSION BREAK ---\n\n'.join(all_text)

    def _process_research_pages(self, data_path: str) -> str:
        try:
            pages = self.db.get_research_pages(data_path)
            if not pages:
                return ""

            print(f"      📄 Reading {len(pages)} pages...")

            all_text = []
            for i, page in enumerate(pages):
                if (i + 1) % 50 == 0:
                    print(f"      📄 Progress: {i + 1}/{len(pages)} pages")

                text = page.get('main_text', '')
                if not text:
                    raw_html = page.get('raw_html', '')
                    if raw_html:
                        try:
                            text = self.extractor.extract_content(raw_html)
                        except:
                            text = self.extractor.clean_html(raw_html)

                if text:
                    all_text.append(text)

            if not all_text:
                return ""

            return '\n\n--- PAGE BREAK ---\n\n'.join(all_text)
        except Exception as e:
            print(f"   ⚠️ Error processing pages: {e}")
            return ""


class ProgressiveRAGEngine:
    def __init__(self, vector_store: VectorStore, llm,
                 temperature: float = 0.7, top_p: float = 0.9,
                 mode: str = "Relevancy", top_k: int = 20,
                 process_all: bool = False, batch_size: int = 5,
                 max_tokens: int = 400,
                 sentence_threshold: float = 0.5,
                 clustering_levels: int = 0,
                 top_k_clusters: int = 5,
                 progress_callback=None, batch_complete_callback=None):
        self.vector_store = vector_store
        self.llm = llm
        self.temperature = temperature
        self.top_p = top_p
        self.mode = mode
        self.top_k = top_k
        self.process_all = process_all
        self.batch_size = batch_size
        self.max_tokens = max_tokens
        self.sentence_threshold = sentence_threshold
        self.clustering_levels = clustering_levels
        self.top_k_clusters = top_k_clusters
        self.progress_callback = progress_callback
        self.batch_complete_callback = batch_complete_callback
        self.current_project = ""
        self.order = "Most Relevant First"
        self.synthesis = "Contextual Linking"
        self.cluster_count = 3
        self.drop_threshold = 0.3

    def _process_project_batches(self, query: str, chunks: List[str], project_name: str) -> str:
        batch_responses = []
        total_batches = (len(chunks) + self.batch_size - 1) // self.batch_size

        for batch_num in range(total_batches):
            start = batch_num * self.batch_size
            end = min(start + self.batch_size, len(chunks))
            batch = chunks[start:end]

            print(f"\n   📦 Batch {batch_num + 1}/{total_batches} ({len(batch)} chunks)")

            brief_answer = self._process_batch(query, batch, project_name, batch_num + 1)
            if brief_answer:
                batch_responses.append(brief_answer)
                print(f"      ✅ Batch {batch_num + 1} processed")
                if self.progress_callback:
                    self.progress_callback('batch', batch_num + 1, total_batches, brief_answer, project_name)

                if hasattr(self, 'batch_complete_callback') and self.batch_complete_callback:
                    self.batch_complete_callback(batch_num + 1, total_batches)

        if not batch_responses:
            return ""

        if self.mode == "Hierarchical":
            project_summary = self._hierarchical_merge(batch_responses, query)
        else:
            project_summary = self._synthesize_project(query, batch_responses, project_name)

        print(f"\n   📝 {project_name} summary generated")
        print(f"      {project_summary[:200]}...")
        if self.progress_callback:
            self.progress_callback('project', 0, 0, project_summary, project_name)
        return project_summary

    def _process_batch(self, query: str, batch: List[str], project_name: str, batch_num: int) -> str:
        context = '\n\n'.join([chunk[:300] + "..." if len(chunk) > 300 else chunk for chunk in batch])

        max_tokens = max(40, min(100, len(batch) * 15))
        temperature = self.temperature
        top_p = self.top_p

        prompt = f"""Based on the data provided, give a BRIEF answer (3-5 sentences) to the query.

QUERY: {query}

DATA (from {project_name}):
{context}

BRIEF ANSWER:"""

        try:
            response = self.llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=["###", "---", "```"]
            )
            content = response['choices'][0]['text'].strip()
            return content if content else f"[Batch {batch_num}] No clear answer found."
        except Exception as e:
            print(f"      ⚠️ Batch {batch_num} error: {e}")
            return f"[Batch {batch_num}] Could not process this batch."

    def _synthesize_project(self, query: str, batch_responses: List[str], project_name: str) -> str:
        combined = '\n\n'.join([f"{i + 1}. {resp}" for i, resp in enumerate(batch_responses)])

        prompt = f"""Summarize the insights from this project.

QUERY: {query}

PROJECT: {project_name}

INSIGHTS FROM PROJECT:
{combined}

Create a brief summary (3-4 sentences) of what this project reveals about the query.
Project Summary:"""
        try:
            response = self.llm(
                prompt,
                max_tokens=100,
                temperature=self.temperature,
                top_p=self.top_p,
                stop=["###", "---", "```"]
            )
            content = response['choices'][0]['text'].strip()
            return f"📖 {project_name}: {content}" if content else ""
        except:
            return f"📖 {project_name}: Insights could not be synthesized."

    def _direct_synthesis(self, query: str, project_summaries: List[str]) -> str:
        combined = '\n\n'.join(project_summaries)
        prompt = f"""Create a comprehensive final answer synthesizing insights from multiple projects.

QUERY: {query}

INSIGHTS FROM EACH PROJECT:
{combined}

Create a well-structured final answer that:
1. Starts with a clear summary
2. Organizes findings by project
3. Highlights key patterns across projects
4. Provides practical takeaways

FINAL ANSWER:"""
        try:
            response = self.llm(
                prompt,
                max_tokens=600,
                temperature=self.temperature,
                top_p=self.top_p,
                stop=["###", "---", "```"]
            )
            content = response['choices'][0]['text'].strip()
            return content if content else "No final answer could be synthesized."
        except Exception as e:
            print(f"❌ Synthesis error: {e}")
            return f"Error synthesizing answers: {str(e)}"

    def query(self, query: str) -> str:
        print("\n" + "=" * 60)
        print(f"🔍 QUERY: {query}")
        print(f"📋 MODE: {self.mode}")
        print("=" * 60 + "\n")

        project_names = self.vector_store.get_project_names()
        if not project_names:
            return "No projects available in the index."

        print(f"📚 Found {len(project_names)} projects: {', '.join(project_names)}")

        if self.mode == "Sentence Clustering":
            all_chunks = []
            all_project_names = []
            for project in project_names:
                chunks = self.vector_store.get_all_chunks_by_project(project)
                if chunks:
                    all_chunks.extend(chunks)
                    all_project_names.extend([project] * len(chunks))

            if not all_chunks:
                return "No chunks found in any project."

            print(f"📚 Processing {len(all_chunks)} chunks across {len(project_names)} projects")

            processor = SentenceClusterProcessor(
                query, all_chunks, all_project_names, self.llm,
                settings={
                    'temperature': self.temperature,
                    'top_p': self.top_p,
                    'batch_size': self.batch_size,
                    'max_tokens': self.max_tokens,
                    'sentence_threshold': getattr(self, 'sentence_threshold', 0.5),
                    'clustering_levels': getattr(self, 'clustering_levels', 0),
                    'top_k_clusters': getattr(self, 'top_k_clusters', 5)
                },
                progress_callback=self.progress_callback
            )
            return processor.final_answer

        all_project_summaries = []
        total_projects = len(project_names)

        for idx, project_name in enumerate(project_names):
            self.current_project = project_name
            print(f"\n{'─' * 50}")
            print(f"📖 PROJECT {idx + 1}/{total_projects}: {project_name}")
            print(f"{'─' * 50}")

            if self.process_all:
                all_chunks = self.vector_store.get_all_chunks_by_project(project_name)
                if not all_chunks:
                    print(f"   ⚠️ No chunks found in {project_name}")
                    continue
                scorer = MLRelevanceScorer(all_chunks, query)
                scored = [(chunk, scorer.score_chunk(chunk)) for chunk in all_chunks]
                scored.sort(key=lambda x: x[1], reverse=True)
                chunks = [chunk for chunk, _ in scored]
                print(f"   Processing all {len(chunks)} chunks sorted by relevance")
            else:
                results = self.vector_store.search_by_project(query, project_name, self.top_k)
                chunks = [item[0] for item in results]
                print(f"   Found {len(chunks)} relevant chunks in {project_name}")
                if not chunks:
                    print(f"   ⚠️ No relevant chunks found in {project_name}")
                    continue

            for i, chunk in enumerate(chunks[:3]):
                preview = chunk[:150] + "..." if len(chunk) > 150 else chunk
                print(f"   Chunk {i + 1}: {preview}")

            project_summary = self._process_project_batches(query, chunks, project_name)

            if project_summary:
                all_project_summaries.append(project_summary)

        if not all_project_summaries:
            return "No relevant information found in any project."

        print(f"\n{'=' * 60}")
        print(f"🔄 FINAL SYNTHESIS")
        print(f"{'=' * 60}\n")

        if self.mode == "Hierarchical":
            final_answer = self._hierarchical_synthesis(all_project_summaries, query)
        else:
            final_answer = self._direct_synthesis(query, all_project_summaries)

        project_list = ', '.join(self.vector_store.get_project_names())
        final_answer += f"\n\n---\n📚 Projects analyzed: {project_list}"
        final_answer += f"\n📋 Mode: {self.mode}"
        return final_answer

    def _hierarchical_merge(self, summaries: List[str], query: str) -> str:
        if not summaries:
            return ""
        merged = summaries[0]
        for i in range(1, len(summaries)):
            merged = self._merge_two_summaries(merged, summaries[i], query)
        return merged

    def _merge_two_summaries(self, summary_a: str, summary_b: str, query: str) -> str:
        prompt = f"""You are merging two summaries about the query: "{query}".

Summary A (existing knowledge):
{summary_a}

Summary B (new information):
{summary_b}

Merge them into a single concise summary that captures ALL unique information from both.
- Keep everything from Summary A.
- Add any NEW information from Summary B that is not already covered in Summary A.
- Avoid repetition.
- Keep the merged summary concise and focused.

Merged Summary:"""
        try:
            response = self.llm(
                prompt,
                max_tokens=200,
                temperature=self.temperature,
                top_p=self.top_p,
                stop=["###", "---", "```"]
            )
            content = response['choices'][0]['text'].strip()
            return content if content else summary_a
        except Exception as e:
            print(f"⚠️ Merge error: {e}")
            return summary_a

    def _hierarchical_synthesis(self, summaries: List[str], query: str) -> str:
        if not summaries:
            return "No summaries to merge."
        if len(summaries) == 1:
            return summaries[0]
        merged = summaries[0]
        for i in range(1, len(summaries)):
            merged = self._merge_two_summaries(merged, summaries[i], query)
        return merged


class TokenAwareChunker:
    def __init__(self, max_tokens_per_chunk: int = 500):
        self.max_tokens = max_tokens_per_chunk
        self._token_cache = {}

    def _count_tokens(self, text: str) -> int:
        return len(text) // 4

    def chunk_text(self, text: str, target_chunks: int = None) -> List[str]:
        if not text or not text.strip():
            return []

        sentences = self._split_sentences(text)
        if not sentences:
            return []

        sentences = [s for s in sentences if len(s.split()) > 3]
        if not sentences:
            return []

        total_tokens = self._count_tokens(' '.join(sentences))
        if target_chunks and target_chunks > 0:
            target_tokens_per_chunk = max(100, total_tokens // target_chunks)
            self.max_tokens = target_tokens_per_chunk

        chunks = []
        current_chunk = []
        current_token_count = 0

        for sentence in sentences:
            sentence_tokens = self._count_tokens(sentence)
            if sentence_tokens > self.max_tokens:
                if current_chunk:
                    chunks.append(' '.join(current_chunk))
                    current_chunk = []
                    current_token_count = 0
                sub_sentences = self._split_long_sentence(sentence)
                for sub in sub_sentences:
                    if self._count_tokens(sub) <= self.max_tokens:
                        chunks.append(sub)
                    else:
                        parts = self._split_by_punctuation(sub)
                        for part in parts:
                            if part:
                                chunks.append(part)
                continue

            if current_token_count + sentence_tokens > self.max_tokens and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = []
                current_token_count = 0

            current_chunk.append(sentence)
            current_token_count += sentence_tokens

        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return [chunk.strip() for chunk in chunks if chunk.strip()]

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

    def _split_long_sentence(self, sentence: str) -> List[str]:
        parts = re.split(r'(?<=[,;:])\s+|(?<=\s)(?:and|but|or|so|for|nor|yet)\s+', sentence)
        if len(parts) <= 1 or any(len(p) > 100 for p in parts):
            words = sentence.split()
            part_size = max(10, len(words) // 5)
            parts = [' '.join(words[i:i + part_size]) for i in range(0, len(words), part_size)]
        result = []
        for part in parts:
            part = part.strip()
            if part:
                if part[-1] not in '.!?':
                    part += '.'
                result.append(part)
        return result

    def _split_by_punctuation(self, text: str) -> List[str]:
        parts = re.split(r'(?<=[.!?,;:])\s+', text)
        result = []
        current = []
        current_tokens = 0
        for part in parts:
            part_tokens = self._count_tokens(part)
            if current_tokens + part_tokens > self.max_tokens and current:
                result.append(' '.join(current))
                current = []
                current_tokens = 0
            current.append(part)
            current_tokens += part_tokens
        if current:
            result.append(' '.join(current))
        return result


class ProgressiveRAGChatThread(QThread):
    response_received = Signal(str)
    error_occurred = Signal(str)
    thinking_started = Signal()
    thinking_finished = Signal()
    progress_update = Signal(int, int, int, str)
    status_update = Signal(str)
    batch_summary = Signal(str, str)
    project_summary = Signal(str, str)
    all_complete = Signal()
    final_answer_ready = Signal(str)
    batch_complete = Signal(int, int)

    def __init__(self, prompt: str, vector_store: VectorStore, model_path: str,
                 settings: dict, use_cache: bool = True):
        super().__init__()
        self.prompt = prompt
        self.vector_store = vector_store
        self.model_path = model_path
        self.settings = settings
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

            def progress_callback(typ, current, total, summary, project):
                if typ == 'batch':
                    self.batch_summary.emit(summary, project)
                elif typ == 'project':
                    self.project_summary.emit(summary, project)

            def batch_complete_callback(current_batch, total_batches):
                self.batch_complete.emit(current_batch, total_batches)

            rag = ProgressiveRAGEngine(
                self.vector_store, self.llm,
                temperature=self.settings.get('temperature', 0.7),
                top_p=self.settings.get('top_p', 0.9),
                mode=self.settings.get('mode', 'Relevancy'),
                top_k=self.settings.get('top_k', 20),
                process_all=self.settings.get('process_all', False),
                batch_size=self.settings.get('batch_size', 5),
                max_tokens=self.settings.get('max_tokens', 400),
                sentence_threshold=self.settings.get('sentence_threshold', 0.5),
                clustering_levels=self.settings.get('clustering_levels', 0),
                top_k_clusters=self.settings.get('top_k_clusters', 5),
                progress_callback=progress_callback,
                batch_complete_callback=batch_complete_callback
            )

            if 'order' in self.settings:
                rag.order = self.settings['order']
            if 'synthesis' in self.settings:
                rag.synthesis = self.settings['synthesis']
            if 'cluster_count' in self.settings:
                rag.cluster_count = self.settings['cluster_count']
            if 'drop_threshold' in self.settings:
                rag.drop_threshold = self.settings['drop_threshold']

            self.status_update.emit(f"📝 Processing with {rag.mode} mode...")
            response = rag.query(self.prompt)

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

    def _get_llm(self):
        if self.llm is None:
            print(f"Loading model from: {self.model_path}")
            try:
                self.llm = Llama(
                    model_path=self.model_path,
                    n_gpu_layers=0,
                    n_ctx=4096,
                    n_threads=4,
                    verbose=False
                )
                print("✅ Model loaded successfully!")
            except Exception as e:
                print(f"❌ Model load failed: {e}")
                self.llm = Llama(
                    model_path=self.model_path,
                    n_gpu_layers=-1,
                    n_ctx=4096,
                    verbose=False
                )
                print("✅ Model loaded with default settings!")
        return self.llm

    def _get_cache_key(self) -> str:
        combined = f"{self.prompt}_{self.settings}_{hashlib.md5(str(self.vector_store.chunks[:10]).encode()).hexdigest()}"
        return hashlib.md5(combined.encode()).hexdigest()

    def stop(self):
        self.is_running = False


class DataChatView(QWidget):
    """Data Chat project view - Q&A with RAG support."""

    def __init__(self, parent=None, db=None, project_data=None):
        super().__init__(parent)
        self.parent_app = parent
        self.db = db
        self.project_data = project_data
        self.project_id = project_data.get('id')
        self.project_name = project_data.get('name', 'Chat Project')
        self.data_path = project_data.get('data_path')

        self.chat_sessions = {}
        self.current_session_id = None
        self.chat_messages = {}
        self.session_names = {}
        self.next_session_id = 1
        self.vector_store_path = os.path.join(BASE_DIR, "vector_store.pkl")

        self.response_cache = OrderedDict(maxsize=100)

        self.ai_enabled = False
        self.model_path = DEFAULT_MODEL_PATH
        self.model_loaded = False
        self.llm = None

        self.selected_projects = []
        self.vector_store = VectorStore()
        self.is_vectorized = False
        self.text_direction = Qt.LayoutDirection.LeftToRight

        self.processing_settings = {
            'mode': 'Relevancy',
            'top_k': 20,
            'batch_size': 5,
            'max_tokens': 500,
            'target_chunks': 10,
            'temperature': 0.7,
            'top_p': 0.9,
            'order': 'Most Relevant First',
            'synthesis': 'Contextual Linking',
            'cluster_count': 3,
            'drop_threshold': 0.3,
            'process_all': False
        }

        self.setup_ui()
        self.load_projects()
        self.load_chat_sessions()
        self.check_model_status()
        self.update_status("Ready")

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(2)
        layout.setContentsMargins(0, 0, 0, 0)

        # Progress bar
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

        # Top bar
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

        # Controls
        controls_group = QGroupBox("Processing Controls")
        controls_group.setStyleSheet("QGroupBox { border: none; padding: 0px; margin: 0px; }")
        controls_layout = QHBoxLayout(controls_group)
        controls_layout.setSpacing(6)
        controls_layout.setContentsMargins(0, 0, 0, 0)

        controls_layout.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Relevancy", "Hierarchical", "Sentence Clustering"])
        self.mode_combo.setStyleSheet("font-size: 11px; padding: 1px 4px;")
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        controls_layout.addWidget(self.mode_combo)

        self.settings_btn = QPushButton("⚙️ Settings")
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #607D8B;
                color: white;
                font-weight: bold;
                padding: 3px 8px;
                border-radius: 4px;
                font-size: 10px;
            }
            QPushButton:hover { background-color: #455A64; }
        """)
        self.settings_btn.clicked.connect(self.show_settings)
        controls_layout.addWidget(self.settings_btn)

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
        model_info.setStyleSheet("color: #555; font-size: 9px; padding: 2px 6px; background-color: #f0f0f0; border-radius: 3px;")
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

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        left_widget = self.create_left_panel()
        splitter.addWidget(left_widget)
        right_widget = self.create_right_panel()
        splitter.addWidget(right_widget)
        splitter.setSizes([300, 900])
        layout.addWidget(splitter)

        self.setLayout(layout)

    def _on_mode_changed(self, mode: str):
        self.processing_settings['mode'] = mode
        self.update_status(f"📋 Mode: {mode}")

    def show_settings(self):
        dialog = SettingsDialog(self, self.processing_settings)
        if dialog.exec_() == QDialog.DialogCode.Accepted:
            self.processing_settings = dialog.get_settings()
            self.update_status(f"⚙️ Settings updated: {self.processing_settings['mode']}")

    def create_left_panel(self):
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

        session_search_label = QLabel("🔍 Search sessions:")
        session_search_label.setStyleSheet("font-size: 10px; color: #666; padding: 2px 4px;")
        left_layout.addWidget(session_search_label)

        self.session_search = QLineEdit()
        self.session_search.setPlaceholderText("Search session content...")
        self.session_search.setStyleSheet("font-size: 11px; padding: 3px 6px; border: 1px solid #ddd; border-radius: 3px;")
        self.session_search.textChanged.connect(self._filter_sessions_by_content)
        left_layout.addWidget(self.session_search)

        # Projects
        projects_label = QLabel("📊 Sources to Query")
        projects_label.setStyleSheet("font-weight: bold; padding: 4px 8px; background-color: #f0f0f0; font-size: 12px; margin-top: 4px;")
        left_layout.addWidget(projects_label)

        self.project_list = QListWidget()
        self.project_list.setSelectionMode(QListWidget.MultiSelection)
        self.project_list.setStyleSheet("font-size: 12px;")
        self.project_list.itemSelectionChanged.connect(self.update_selected_projects)
        left_layout.addWidget(self.project_list)

        self.project_count_label = QLabel("Selected: 0 sources")
        self.project_count_label.setStyleSheet("color: #666; font-size: 10px; padding: 2px 4px;")
        left_layout.addWidget(self.project_count_label)

        self.index_status_label = QLabel("📊 No vector index")
        self.index_status_label.setStyleSheet("color: #888; font-size: 10px; padding: 2px 4px;")
        left_layout.addWidget(self.index_status_label)

        left_layout.addStretch()
        return left_widget

    def _filter_sessions_by_content(self, text: str):
        text = text.lower().strip()
        if not text:
            for i in range(self.session_list.count()):
                self.session_list.item(i).setHidden(False)
            return

        for i in range(self.session_list.count()):
            item = self.session_list.item(i)
            session_id = item.data(Qt.UserRole)
            messages = self.chat_messages.get(session_id, [])
            found = False
            for msg in messages:
                content = msg.get('content', '').lower()
                if text in content:
                    found = True
                    break
            item.setHidden(not found)

    def _show_session_context_menu(self, position):
        menu = QMenu()
        rename_action = QAction("✏️ Rename Session", self)
        rename_action.triggered.connect(self._rename_selected_session)
        menu.addAction(rename_action)
        menu.exec_(self.session_list.mapToGlobal(position))

    def _rename_selected_session(self):
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

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setAcceptRichText(True)
        self.chat_display.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
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

        self.chat_search = QLineEdit()
        self.chat_search.setPlaceholderText("🔍 Search in chat...")
        self.chat_search.setStyleSheet("font-size: 11px; padding: 2px 6px; border: 1px solid #ddd; border-radius: 3px;")
        self.chat_search.returnPressed.connect(self._search_chat)
        toolbar.addWidget(self.chat_search)

        toolbar.addStretch()

        toolbar.addWidget(QLabel("Font:"))
        self.font_combo = QComboBox()
        self.font_combo.addItems(["Segoe UI", "Arial", "Times New Roman", "Courier New", "Georgia", "Verdana"])
        self.font_combo.setStyleSheet("font-size: 11px; padding: 1px 4px;")
        self.font_combo.currentTextChanged.connect(self._update_chat_style)
        toolbar.addWidget(self.font_combo)

        toolbar.addWidget(QLabel("Size:"))
        self.font_size_spinner = QSpinBox()
        self.font_size_spinner.setRange(8, 24)
        self.font_size_spinner.setValue(13)
        self.font_size_spinner.setFixedWidth(40)
        self.font_size_spinner.setStyleSheet("font-size: 11px;")
        self.font_size_spinner.valueChanged.connect(self._update_chat_style)
        toolbar.addWidget(self.font_size_spinner)

        toolbar.addWidget(QLabel("Line Ht:"))
        self.line_height_spinner = QDoubleSpinBox()
        self.line_height_spinner.setRange(1.0, 3.0)
        self.line_height_spinner.setValue(1.6)
        self.line_height_spinner.setSingleStep(0.1)
        self.line_height_spinner.setFixedWidth(45)
        self.line_height_spinner.setStyleSheet("font-size: 11px;")
        self.line_height_spinner.valueChanged.connect(self._update_chat_style)
        toolbar.addWidget(self.line_height_spinner)

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
        if self.text_direction == Qt.LayoutDirection.LeftToRight:
            self.text_direction = Qt.LayoutDirection.RightToLeft
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
            self.text_direction = Qt.LayoutDirection.LeftToRight
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

        self.chat_display.setLayoutDirection(self.text_direction)
        self.chat_display.setAlignment(
            Qt.AlignLeft if self.text_direction == Qt.LayoutDirection.LeftToRight else Qt.AlignRight)
        self.chat_input.setLayoutDirection(self.text_direction)
        self.chat_input.setAlignment(
            Qt.AlignLeft if self.text_direction == Qt.LayoutDirection.LeftToRight else Qt.AlignRight)

    def _search_chat(self):
        text = self.chat_search.text().strip()
        if not text:
            cursor = self.chat_display.textCursor()
            cursor.clearSelection()
            self.chat_display.setTextCursor(cursor)
            return

        highlight_format = QTextCharFormat()
        highlight_format.setBackground(QColor(255, 255, 0))
        highlight_format.setForeground(QColor(0, 0, 0))

        cursor = self.chat_display.textCursor()
        if not cursor.hasSelection():
            cursor.movePosition(QTextCursor.Start)
        cursor.clearSelection()

        found = self.chat_display.find(text)
        if not found:
            cursor.movePosition(QTextCursor.Start)
            self.chat_display.setTextCursor(cursor)
            found = self.chat_display.find(text)

        if found:
            cursor = self.chat_display.textCursor()
            cursor.mergeCharFormat(highlight_format)
            self.chat_display.setTextCursor(cursor)

    def _update_chat_style(self):
        font_family = self.font_combo.currentText()
        font_size = self.font_size_spinner.value()
        line_height = self.line_height_spinner.value()

        font = QFont(font_family, font_size)
        self.chat_display.setFont(font)
        self.chat_input.setFont(font)

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
        self.project_list.clear()
        all_projects = self.db.get_all_projects()

        for project in all_projects:
            if project['id'] == self.project_id:
                continue

            project_type = project.get('project_type', '')
            project_name = project.get('name', 'Unknown')

            if project_type == 'data_chat':
                icon = '💬'
                label = 'Chat'
            elif project_type == 'data_table':
                icon = '📊'
                label = 'Table'
            elif project_type == 'data_research':
                icon = '🌐'
                label = 'Research'
            elif project_type == 'data_document':
                icon = '📄'
                label = 'Document'
            else:
                icon = '📁'
                label = project_type.replace('_', ' ').title()

            display = f"{icon} {project_name} ({label})"
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
        self.project_count_label.setText(f"Selected: {count} sources")

    def build_vector_index(self):
        if not self.selected_projects:
            QMessageBox.warning(self, "No Sources", "Please select sources first.")
            return

        print("\n" + "=" * 60)
        print("📊 BUILDING VECTOR INDEX")
        print(f"📋 Mode: {self.processing_settings.get('mode', 'Relevancy')}")
        print("=" * 60 + "\n")

        self.update_status("⏳ Building vector index...")
        self.index_status_label.setText("⏳ Building index...")
        self.progress_bar.setValue(10)
        self.progress_label.setText("Processing data...")

        # Get settings with fallbacks
        mode = self.processing_settings.get('mode', 'Relevancy')
        max_tokens = self.processing_settings.get('max_tokens', 500)
        target_chunks = self.processing_settings.get('target_chunks', 10)  # Fallback to 10

        processor = DataProcessor(
            self.db, self.selected_projects,
            mode=mode,
            max_tokens=max_tokens,
            target_chunks=target_chunks
        )
        chunks = processor.process_all_data()

        if not chunks:
            QMessageBox.warning(self, "No Data", "No data found in selected sources.")
            return

        self.progress_bar.setValue(40)
        self.progress_label.setText("Building vector index...")

        self.vector_store.build_index(chunks, processor.chunk_project_names)
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

        print("\n✅ INDEX BUILD COMPLETE")
        print(f"   {len(chunks)} chunks indexed from {len(self.selected_projects)} projects")
        print(f"   Projects: {', '.join(self.vector_store.get_project_names())}")

        self.update_status(f"✅ Vector index built with {len(chunks)} chunks")

        QMessageBox.information(
            self,
            "Index Built",
            f"Successfully built vector index with {len(chunks)} chunks.\n\n"
            "You can now ask questions using RAG (Retrieval-Augmented Generation)."
        )

    def send_message(self):
        """Send a message with the current processing settings."""
        prompt = self.chat_input.toPlainText().strip()
        if not prompt:
            return

        if not self.selected_projects:
            QMessageBox.warning(self, "No Sources", "Please select sources first.")
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

        print("\n" + "=" * 60)
        print(f"🔍 QUERY: {prompt}")
        print(f"📋 Mode: {self.processing_settings.get('mode', 'Relevancy')}")
        print(f"📋 List Output: {self.processing_settings.get('list_output', False)}")
        print("=" * 60 + "\n")

        self.progress_bar.setValue(0)
        self.progress_label.setText("🔍 Starting...")

        self._create_response_placeholder()

        # Get all settings with defaults
        settings = {
            'mode': self.processing_settings.get('mode', 'Relevancy'),
            'top_k': self.processing_settings.get('top_k', 20),
            'process_all': self.processing_settings.get('process_all', False),
            'batch_size': self.processing_settings.get('batch_size', 5),
            'max_tokens': self.processing_settings.get('max_tokens', 400),
            'temperature': self.processing_settings.get('temperature', 0.7),
            'top_p': self.processing_settings.get('top_p', 0.9),
            'list_output': self.processing_settings.get('list_output', False),
            'list_tokens': self.processing_settings.get('list_tokens', 150),
            'list_sentences': self.processing_settings.get('list_sentences', 3),
            'list_temp': self.processing_settings.get('list_temp', 0.6),
            'list_topp': self.processing_settings.get('list_topp', 0.9),
            'sentence_threshold': self.processing_settings.get('sentence_threshold', 0.5),
            'clustering_levels': self.processing_settings.get('clustering_levels', 0),
            'top_k_clusters': self.processing_settings.get('top_k_clusters', 5),
            'order': self.processing_settings.get('order', 'Most Relevant First'),
            'synthesis': self.processing_settings.get('synthesis', 'Contextual Linking'),
            'cluster_count': self.processing_settings.get('cluster_count', 3),
            'drop_threshold': self.processing_settings.get('drop_threshold', 0.3)
        }

        # Create and start thread
        self.chat_thread = ProgressiveRAGChatThread(
            prompt, self.vector_store, self.model_path,
            settings=settings,
            use_cache=True
        )

        # Connect signals
        self.chat_thread.progress_update.connect(self.update_batch_progress)
        self.chat_thread.batch_complete.connect(self.on_batch_complete)
        self.chat_thread.all_complete.connect(self.on_all_complete)
        self.chat_thread.response_received.connect(self.on_response_received)
        self.chat_thread.error_occurred.connect(self.on_error_occurred)
        self.chat_thread.status_update.connect(self.update_status)
        self.chat_thread.batch_summary.connect(self.append_batch_summary)
        self.chat_thread.project_summary.connect(self.append_project_summary)

        self.chat_thread.start()

    def update_batch_progress(self, current_batch: int, total_batches: int, chunks_in_batch: int,
                              project_name: str = ""):
        """Update the progress bar with batch information."""
        if total_batches > 0:
            progress = int((current_batch / total_batches) * 100)
            self.progress_bar.setValue(progress)

            if project_name:
                self.progress_label.setText(
                    f"📖 {project_name} | Batch {current_batch}/{total_batches} ({chunks_in_batch} chunks)")
            else:
                self.progress_label.setText(f"📦 Batch {current_batch}/{total_batches} ({chunks_in_batch} chunks)")
        else:
            self.progress_bar.setValue(0)
            self.progress_label.setText("Processing...")
        self.chat_display.repaint()

    def append_batch_summary(self, summary: str, project: str):
        """Append a batch summary to the chat display."""
        html = f"""
        <div style="
            background: #f0f8ff;
            border-radius: 6px;
            padding: 8px 12px;
            margin: 4px 0;
            border-left: 3px solid #2196F3;
            font-size: 13px;
            color: #2d3748;
        ">
            <div style="color: #666; font-size: 11px; font-weight: 600;">📦 Batch Summary - {project}</div>
            <div style="margin-top: 4px;">{summary.replace(chr(10), '<br>')}</div>
        </div>
        """
        self.chat_display.append(html)
        self.chat_display.moveCursor(QTextCursor.End)
        self.chat_display.repaint()


    def append_project_summary(self, summary: str, project: str):
        """Append a project summary to the chat display."""
        html = f"""
        <div style="
            background: #e8f5e9;
            border-radius: 6px;
            padding: 10px 16px;
            margin: 6px 0;
            border-left: 4px solid #4CAF50;
            font-size: 14px;
            color: #1b5e20;
        ">
            <div style="color: #2e7d32; font-size: 12px; font-weight: 600;">📖 Project Summary - {project}</div>
            <div style="margin-top: 4px;">{summary.replace(chr(10), '<br>')}</div>
        </div>
        """
        self.chat_display.append(html)
        self.chat_display.moveCursor(QTextCursor.End)
        self.chat_display.repaint()

    def on_batch_complete(self, current_batch: int, total_batches: int):
        pass

    def _create_response_placeholder(self):
        """Create a placeholder for the response."""
        timestamp = datetime.now().strftime("%H:%M")
        placeholder = "🔄 Processing projects..."

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
        self.chat_display.repaint()

    def on_all_complete(self):
        """Called when all processing is complete."""
        self.chat_input.setEnabled(True)
        self.update_status("Ready")
        self.progress_label.setText("✅ Done")
        QTimer.singleShot(1500, lambda: self.progress_bar.setValue(0))
        QTimer.singleShot(1500, lambda: self.progress_label.setText("Ready"))

        if self.current_session_id is not None:
            self.load_session_by_id(self.current_session_id)

        print("\n✅ RESPONSE COMPLETE")
        print("─" * 60)

    def on_response_received(self, response):
        """Handle the final response."""
        paragraphs = response.split('\n')
        formatted_paragraphs = []
        for p in paragraphs:
            p = p.strip()
            if p:
                formatted_paragraphs.append(p)
        formatted_text = '<br><br>'.join(formatted_paragraphs)

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

        html = self.chat_display.toHtml()
        import re
        pattern = r'<div style="background: #f8f9fa; border-radius: 8px; padding: 16px 20px; margin: 4px 0; border-left: 4px solid #9C27B0;.*?</div>'
        match = re.search(pattern, html, re.DOTALL)

        if match:
            new_html = html.replace(match.group(0), styled)
            self.chat_display.setHtml(new_html)
            self.chat_display.moveCursor(QTextCursor.End)
        else:
            self.chat_display.append(f"🤖 **AI:** {styled}")
            self.chat_display.append("")
            self.chat_display.moveCursor(QTextCursor.End)

        timestamp = datetime.now().strftime("%H:%M")
        self.add_message_to_chat('assistant', response, timestamp)
        self.chat_display.repaint()

    def on_error_occurred(self, error):
        """Handle errors."""
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
        self.chat_display.repaint()
        print(f"\n❌ ERROR: {error}")

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
                Select sources, build index, then enable AI to start asking questions.
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
                    html += f"<div style='color: #999; font-size: 11px; text-align: left; margin-top: 2px;'>{timestamp}</div>"
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

    def show_table_generator(self):
        """Open the table generator dialog."""
        if not self.selected_projects:
            QMessageBox.warning(self, "No Sources", "Please select sources first.")
            return

        if not self.model_loaded:
            QMessageBox.warning(self, "Model Not Loaded", "Please load the model first.")
            return

        # Show column setup dialog - pass self as parent with db access
        dialog = ColumnSetupDialog(self)  # self has db, project_id, etc.
        dialog.parent_app = self  # Give dialog access to parent

        if dialog.exec_() == QDialog.DialogCode.Accepted:
            columns = dialog.get_columns()
            if not columns:
                QMessageBox.warning(self, "No Columns", "Please add at least one column.")
                return

            # Create progress dialog
            self.progress_dialog = QProgressDialog("Generating table...", "Cancel", 0, len(columns), self)
            self.progress_dialog.setWindowTitle("Processing")
            self.progress_dialog.setModal(True)
            self.progress_dialog.show()

            # Generate the table
            self._generate_table(columns)

    def _generate_table(self, columns: List[ColumnDefinition]):
        """Generate the table in a thread."""
        self.table_thread = TableGenerationThread(
            self.db, self.llm, self.selected_projects, columns
        )
        self.table_thread.progress_update.connect(self._on_table_progress)
        self.table_thread.column_complete.connect(self._on_column_complete)
        self.table_thread.generation_complete.connect(self._on_table_complete)
        self.table_thread.error_occurred.connect(self._on_table_error)
        self.table_thread.item_progress.connect(self._on_item_progress)  # NEW
        self.table_thread.start()

    def _on_item_progress(self, current: int, total: int):
        """Update item-level progress."""
        if self.progress_dialog:
            self.progress_dialog.setValue(int((current / total) * 100))
            self.progress_dialog.setLabelText(f"Generating item {current} of {total}...")

    def _on_table_progress(self, message: str, current: int, total: int):
        """Update progress dialog."""
        if self.progress_dialog:
            self.progress_dialog.setLabelText(message)
            self.progress_dialog.setValue(current)

    def _on_column_complete(self, col_index: int, results: List[Dict]):
        """Handle column completion."""
        print(f"✅ Column {col_index + 1} complete: {len(results)} items")

    def _on_table_complete(self, results: List[List[Dict]]):
        """Handle table generation complete."""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        # Show the table results dialog
        self._show_table_results(results)

    def _on_table_error(self, error: str):
        """Handle table generation error."""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        QMessageBox.critical(self, "Error", f"Table generation failed:\n{error}")


    def _show_table_results(self, results: List[List[Dict]]):
        """Display the table results in a popup."""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        # Get column definitions from the thread
        columns = self.table_thread.columns if self.table_thread else []

        # Show results dialog
        dialog = TableResultsDialog(results, columns, self)
        dialog.exec_()

    def _generate_item_batch(self, definition: ColumnDefinition, chunks: List[str]) -> List[Dict]:
        """Generate multiple items in a single LLM call for efficiency."""
        if not chunks:
            return []

        # Build batch prompt
        items_text = []
        for i, chunk in enumerate(chunks[:5]):  # Limit to 5 items per batch
            items_text.append(f"ITEM {i + 1}:\n{chunk[:300]}...")

        context = '\n\n'.join(items_text)

        # Determine response format
        if definition.response_type == ResponseType.SENTENCE:
            min_words, max_words = definition.response_size.get('words', (2, 6))
            format_instruction = f"For each item, provide a response in 1 sentence ({min_words}-{max_words} words)."
        elif definition.response_type == ResponseType.PARAGRAPH:
            min_sentences, max_sentences = definition.response_size.get('sentences', (3, 6))
            format_instruction = f"For each item, provide a response in 1 paragraph ({min_sentences}-{max_sentences} sentences)."
        else:
            min_paragraphs, max_paragraphs = definition.response_size.get('paragraphs', (2, 4))
            format_instruction = f"For each item, provide a response as an article ({min_paragraphs}-{max_paragraphs} paragraphs)."

        # Build prompt
        creativity = definition.creativity
        if creativity < 0.3:
            style = "Extract the information directly and literally."
        elif creativity < 0.7:
            style = "Summarize the information clearly and concisely."
        else:
            style = "Write in a creative, engaging, and expressive style."

        prompt = f"""Based on the following items, {definition.request}:

    {context}

    {format_instruction}
    {style}

    For each item, provide the response on a new line starting with "ITEM X:".

    RESPONSES:"""

        try:
            response = self.llm(
                prompt,
                max_tokens=len(chunks) * 200,  # Dynamic token limit
                temperature=creativity,
                top_p=0.9,
                stop=["###", "---", "```"]
            )
            content = response['choices'][0]['text'].strip()

            # Parse responses
            results = []
            import re
            item_matches = re.findall(r'ITEM\s*(\d+):\s*(.+?)(?=ITEM\s*\d+:|$)', content, re.DOTALL)

            for match in item_matches:
                idx = int(match[0]) - 1
                if idx < len(chunks):
                    results.append({
                        'item': match[1].strip(),
                        'chunks': [chunks[idx]],
                        'context': chunks[idx][:500] + '...' if len(chunks[idx]) > 500 else chunks[idx]
                    })

            return results
        except Exception as e:
            print(f"⚠️ Batch generation error: {e}")
            return []