# studio/views/table_generator.py
import re
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class ResponseType(Enum):
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    ARTICLE = "article"


class ChunkStrategy(Enum):
    EXACT_MATCH = "exact_match"
    SEMANTIC_MATCH = "semantic_match"
    MAX_SEMANTIC = "max_semantic"


class SourceType(Enum):
    PROJECT = "project"
    PREVIOUS_COLUMN_DATA = "previous_column_data"
    PREVIOUS_COLUMN_CHUNKS = "previous_column_chunks"


@dataclass
class ColumnDefinition:
    """Definition for a single column in the table."""
    name: str
    response_type: ResponseType
    request: str
    creativity: float = 0.5
    chunk_strategy: ChunkStrategy = ChunkStrategy.EXACT_MATCH
    lookup_params: Dict[str, Any] = field(default_factory=lambda: {
        'top_k': 10,
        'previous_sentences': 1,
        'following_sentences': 1,
        'order': 'relevancy'
    })
    source_type: SourceType = SourceType.PROJECT
    source_column: Optional[int] = None
    response_size: Dict[str, Any] = field(default_factory=lambda: {
        'words': (2, 6)
    })


class ChunkExtractor:
    """Extract chunks from text using different strategies."""

    def __init__(self, text: str):
        self.text = text
        self.sentences = self._split_sentences(text)

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        return sentences

    def exact_match(self, query: str, previous: int = 1, following: int = 1,
                    top_k: int = 10, order: str = 'relevancy') -> List[str]:
        """Find exact matches and return surrounding sentences."""
        results = []
        query_lower = query.lower()

        for i, sentence in enumerate(self.sentences):
            if query_lower in sentence.lower():
                start = max(0, i - previous)
                end = min(len(self.sentences), i + following + 1)
                chunk = ' '.join(self.sentences[start:end])
                # Score by number of matches
                score = sentence.lower().count(query_lower)
                results.append((chunk, score, i))

        # Sort by score
        if order == 'relevancy':
            results.sort(key=lambda x: x[1], reverse=True)
        elif order == 'A-Z':
            results.sort(key=lambda x: x[0])
        elif order == 'Z-A':
            results.sort(key=lambda x: x[0], reverse=True)

        # Return top K chunks
        return [r[0] for r in results[:top_k]]

    def semantic_match(self, query: str, previous: int = 1, following: int = 1,
                       top_k: int = 10, order: str = 'relevancy') -> List[str]:
        """Find semantically similar sentences using TF-IDF."""
        if not self.sentences:
            return []

        # Build TF-IDF vectors
        vectorizer = TfidfVectorizer(stop_words='english', max_features=500)
        sentence_vectors = vectorizer.fit_transform(self.sentences)
        query_vector = vectorizer.transform([query])

        # Compute similarities
        similarities = cosine_similarity(query_vector, sentence_vectors).flatten()

        # Get top indices
        indices = np.argsort(similarities)[::-1]

        results = []
        for idx in indices:
            if similarities[idx] > 0.05:  # Minimum threshold
                start = max(0, idx - previous)
                end = min(len(self.sentences), idx + following + 1)
                chunk = ' '.join(self.sentences[start:end])
                results.append((chunk, similarities[idx], idx))

        # Sort by score
        if order == 'relevancy':
            results.sort(key=lambda x: x[1], reverse=True)
        elif order == 'A-Z':
            results.sort(key=lambda x: x[0])
        elif order == 'Z-A':
            results.sort(key=lambda x: x[0], reverse=True)

        return [r[0] for r in results[:top_k]]

    def max_semantic(self, max_tokens: int = 500) -> List[str]:
        """Split text into chunks of maximum token size."""
        chunks = []
        current_chunk = []
        current_tokens = 0

        for sentence in self.sentences:
            sentence_tokens = len(sentence) // 4  # Rough token estimate
            if current_tokens + sentence_tokens > max_tokens and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = []
                current_tokens = 0
            current_chunk.append(sentence)
            current_tokens += sentence_tokens

        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks


class TableGenerator:
    """Generates a multi-column table from project data."""

    def __init__(self, db, llm, selected_projects: List[int],
                 progress_callback=None, item_progress_callback=None):
        self.db = db
        self.llm = llm
        self.selected_projects = selected_projects
        self.progress_callback = progress_callback
        self.item_progress_callback = item_progress_callback  # NEW
        self.column_definitions: List[ColumnDefinition] = []
        self.results: List[List[Dict]] = []
        self.chunk_cache = {}
        self.source_texts = None
        self.total_items = 0
        self.processed_items = 0

    def add_column(self, definition: ColumnDefinition):
        """Add a column definition to the table."""
        self.column_definitions.append(definition)

    def get_project_texts(self) -> List[str]:
        """Extract text from all selected projects."""
        if self.source_texts is not None:
            return self.source_texts

        texts = []
        for project_id in self.selected_projects:
            project_data = self.db.get_project(project_id)
            if not project_data:
                continue

            data_path = project_data.get('data_path')
            project_type = project_data.get('project_type')

            if project_type in ['data_research', 'data_document']:
                pages = self.db.get_research_pages(data_path)
                for page in pages:
                    if page.get('main_text'):
                        texts.append(page['main_text'])
            elif project_type == 'data_table':
                rows = self.db.get_table_data(data_path)
                columns = self.db.get_table_column_names(data_path)
                for row in rows:
                    if columns:
                        row_dict = dict(zip(columns, row))
                        texts.append(str(row_dict))
                    else:
                        texts.append(' '.join([str(cell) for cell in row if cell]))

        self.source_texts = texts
        return texts

    def get_all_text(self) -> str:
        """Get all text as a single string."""
        return '\n\n'.join(self.get_project_texts())

    def _get_source_data(self, definition: ColumnDefinition, col_idx: int) -> str:
        """Get source data based on the column's source type."""
        if definition.source_type == SourceType.PROJECT:
            return self.get_all_text()
        elif definition.source_type == SourceType.PREVIOUS_COLUMN_DATA:
            if definition.source_column is not None and definition.source_column < len(self.results):
                items = []
                for row in self.results[definition.source_column]:
                    if row.get('item'):
                        items.append(row['item'])
                return '\n\n'.join(items)
        elif definition.source_type == SourceType.PREVIOUS_COLUMN_CHUNKS:
            if definition.source_column is not None and definition.source_column < len(self.results):
                chunks = []
                for row in self.results[definition.source_column]:
                    if row.get('chunks'):
                        chunks.extend(row['chunks'])
                return '\n\n'.join(chunks)
        return ""

    def _extract_chunks(self, definition: ColumnDefinition, source_text: str) -> List[str]:
        """Extract chunks using the specified strategy."""
        if not source_text:
            return []

        extractor = ChunkExtractor(source_text)
        params = definition.lookup_params

        if definition.chunk_strategy == ChunkStrategy.EXACT_MATCH:
            return extractor.exact_match(
                query=definition.request,
                previous=params.get('previous_sentences', 1),
                following=params.get('following_sentences', 1),
                top_k=params.get('top_k', 10),
                order=params.get('order', 'relevancy')
            )
        elif definition.chunk_strategy == ChunkStrategy.SEMANTIC_MATCH:
            return extractor.semantic_match(
                query=definition.request,
                previous=params.get('previous_sentences', 1),
                following=params.get('following_sentences', 1),
                top_k=params.get('top_k', 10),
                order=params.get('order', 'relevancy')
            )
        elif definition.chunk_strategy == ChunkStrategy.MAX_SEMANTIC:
            max_tokens = params.get('max_tokens', 500)
            # For max semantic, return the chunks, then we'll score them
            chunks = extractor.max_semantic(max_tokens)
            # Score chunks by relevance to query
            vectorizer = TfidfVectorizer(stop_words='english', max_features=500)
            chunk_vectors = vectorizer.fit_transform(chunks)
            query_vector = vectorizer.transform([definition.request])
            similarities = cosine_similarity(query_vector, chunk_vectors).flatten()

            # Sort by relevance
            scored = [(chunks[i], similarities[i]) for i in range(len(chunks))]
            scored.sort(key=lambda x: x[1], reverse=True)

            top_k = params.get('top_k', 10)
            return [chunk for chunk, _ in scored[:top_k]]

        return []

    def _generate_item(self, definition: ColumnDefinition, chunks: List[str]) -> Dict:
        """Generate a single item using LLM with error handling."""
        if not chunks:
            return {'item': '', 'chunks': []}

        # Build context from chunks
        context = '\n\n'.join(chunks[:5])

        # Determine response format
        if definition.response_type == ResponseType.SENTENCE:
            min_words, max_words = definition.response_size.get('words', (2, 6))
            format_instruction = f"Provide a response in 1 sentence ({min_words}-{max_words} words)."
        elif definition.response_type == ResponseType.PARAGRAPH:
            min_sentences, max_sentences = definition.response_size.get('sentences', (3, 6))
            format_instruction = f"Provide a response in 1 paragraph ({min_sentences}-{max_sentences} sentences)."
        else:  # ARTICLE
            min_paragraphs, max_paragraphs = definition.response_size.get('paragraphs', (2, 4))
            format_instruction = f"Provide a response as an article ({min_paragraphs}-{max_paragraphs} paragraphs)."

        # Build prompt
        creativity = definition.creativity
        if creativity < 0.3:
            style = "Extract the information directly and literally."
        elif creativity < 0.7:
            style = "Summarize the information clearly and concisely."
        else:
            style = "Write in a creative, engaging, and expressive style."

        prompt = f"""Based on the following context, {definition.request}:

CONTEXT:
{context}

{format_instruction}
{style}

RESPONSE:"""

        try:
            # Calculate max tokens based on response type
            if definition.response_type == ResponseType.SENTENCE:
                max_tokens = 60
            elif definition.response_type == ResponseType.PARAGRAPH:
                max_tokens = 200
            else:
                max_tokens = 400

            response = self.llm(
                prompt,
                max_tokens=max_tokens,
                temperature=creativity,
                top_p=0.9,
                stop=["###", "---", "```"]
            )
            content = response['choices'][0]['text'].strip()

            return {
                'item': content,
                'chunks': chunks,
                'context': context[:500] + '...' if len(context) > 500 else context
            }
        except Exception as e:
            print(f"⚠️ Generation error: {e}")
            return {'item': f"[Error: {str(e)}]", 'chunks': chunks}

    def generate(self) -> List[List[Dict]]:
        """Generate all columns in order with item progress tracking."""
        self.results = []
        self.processed_items = 0

        # Count total items to process
        self.total_items = self._count_total_items()

        for col_idx, definition in enumerate(self.column_definitions):
            print(f"📊 Generating column {col_idx + 1}: {definition.name}")

            if self.progress_callback:
                self.progress_callback(f"Generating column: {definition.name}", col_idx, len(self.column_definitions))

            # Get source data
            source_text = self._get_source_data(definition, col_idx)

            if not source_text:
                print(f"⚠️ No source data for column {definition.name}")
                self.results.append([])
                continue

            # Extract chunks
            chunks = self._extract_chunks(definition, source_text)

            if not chunks:
                print(f"⚠️ No chunks extracted for column {definition.name}")
                self.results.append([])
                continue

            # Generate items for each chunk with progress tracking
            column_items = []
            for chunk_idx, chunk in enumerate(chunks):
                item = self._generate_item(definition, [chunk])
                if item['item']:
                    column_items.append(item)

                # Track progress
                self.processed_items += 1
                if self.item_progress_callback:
                    self.item_progress_callback(self.processed_items, self.total_items)

            self.results.append(column_items)

        return self.results

    def _count_total_items(self) -> int:
        """Estimate total number of items to generate."""
        total = 0
        for definition in self.column_definitions:
            # Get source data
            source_text = self._get_source_data(definition, len(self.results))
            if source_text:
                # Estimate chunks based on strategy
                if definition.chunk_strategy == ChunkStrategy.EXACT_MATCH:
                    # Rough estimate: count occurrences of request in text
                    total += source_text.lower().count(definition.request.lower()) or 5
                elif definition.chunk_strategy == ChunkStrategy.SEMANTIC_MATCH:
                    total += definition.lookup_params.get('top_k', 10)
                else:  # MAX_SEMANTIC
                    total += len(source_text) // 500  # Rough chunk count
            else:
                total += 5  # Default estimate

        return max(total, 1)  # At least 1 item