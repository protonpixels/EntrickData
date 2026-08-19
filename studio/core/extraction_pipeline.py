import re
import pickle
import numpy as np
import random
from typing import List, Dict, Optional, Tuple
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from studio.core.database import StudioDatabase
from studio.models.ml_model import MLModel

# Common stopwords for feature extraction
STOPWORDS = {'the', 'a', 'an', 'of', 'for', 'on', 'at', 'to', 'in', 'with', 'without', 'by',
             'and', 'or', 'but', 'so', 'for', 'nor', 'yet', 'as', 'if', 'then', 'than', 'that',
             'this', 'these', 'those', 'which', 'who', 'whom', 'whose', 'will', 'would', 'could',
             'should', 'may', 'might', 'must', 'shall', 'can', 'does', 'did', 'has', 'have', 'had',
             'do', 'are', 'is', 'was', 'were', 'been', 'being'}


class ExtractionPipeline:
    def __init__(self, db: StudioDatabase, project_id: int, column_name: str):
        self.db = db
        self.project_id = project_id
        self.column_name = column_name
        self.model = None
        self.vectorizer = None
        self.feature_names = None
        self.ml_model_id = None
        self.ml_storage = MLModel(db.db_path)
        self.scaler = None  # For future use

    # ========== FEATURE ENGINEERING ==========

    def extract_features(self, text: str) -> Dict[str, float]:
        """
        Extract handcrafted features from text.
        These are calculated per item and stored with embeddings.
        """
        if not text:
            return {
                'word_count': 0,
                'char_count': 0,
                'sentence_count': 0,
                'question_count': 0,
                'digit_count': 0,
                'upper_ratio': 0,
                'title_case_ratio': 0,
                'stopword_ratio': 0,
                'avg_word_length': 0,
                'special_char_count': 0,
                'exclamation_count': 0,
                'colon_count': 0,
                'semicolon_count': 0,
                'comma_count': 0,
                'has_numbers': 0,
                'all_caps_ratio': 0,
                'unique_word_ratio': 0,
            }

        words = text.split()
        num_words = len(words)

        # Count sentence endings (. ! ?)
        sentence_endings = text.count('.') + text.count('!') + text.count('?')

        # Count specific punctuation
        question_count = text.count('?')
        exclamation_count = text.count('!')
        colon_count = text.count(':')
        semicolon_count = text.count(';')
        comma_count = text.count(',')
        special_chars = len(re.findall(r'[!?;:@#$%^&*()_+=\[\]{}|\\/~`<>]', text))

        # Count digits
        digits = len(re.findall(r'\d', text))
        has_numbers = 1 if digits > 0 else 0

        # Uppercase ratios
        upper_chars = sum(1 for c in text if c.isupper())
        upper_ratio = upper_chars / max(1, len(text))

        # All caps ratio (words that are all uppercase)
        all_caps_words = sum(1 for w in words if w.isupper() and len(w) > 1)
        all_caps_ratio = all_caps_words / max(1, num_words)

        # Title case ratio (words that start with capital letter)
        title_words = sum(1 for w in words if w and w[0].isupper() and not w.isupper())
        title_case_ratio = title_words / max(1, num_words)

        # Stopword ratio
        stopwords = sum(1 for w in words if w.lower() in STOPWORDS)
        stopword_ratio = stopwords / max(1, num_words)

        # Average word length
        avg_word_length = sum(len(w) for w in words) / max(1, num_words)

        # Unique word ratio (vocabulary diversity)
        unique_words = len(set(w.lower() for w in words))
        unique_word_ratio = unique_words / max(1, num_words)

        return {
            'word_count': num_words,
            'char_count': len(text),
            'sentence_count': sentence_endings,
            'question_count': question_count,
            'digit_count': digits,
            'upper_ratio': upper_ratio,
            'title_case_ratio': title_case_ratio,
            'stopword_ratio': stopword_ratio,
            'avg_word_length': avg_word_length,
            'special_char_count': special_chars,
            'exclamation_count': exclamation_count,
            'colon_count': colon_count,
            'semicolon_count': semicolon_count,
            'comma_count': comma_count,
            'has_numbers': has_numbers,
            'all_caps_ratio': all_caps_ratio,
            'unique_word_ratio': unique_word_ratio,
        }

    def get_feature_names(self) -> List[str]:
        """Get the names of all handcrafted features."""
        return list(self.extract_features("test").keys())

    def combine_features(self, texts: List[str]) -> np.ndarray:
        """
        Combine TF-IDF embeddings with handcrafted features.
        This creates a rich feature vector for each text.
        """
        if not texts:
            return np.array([])

        # 1. Get TF-IDF embeddings
        if self.vectorizer is None:
            self.vectorizer = TfidfVectorizer(
                max_features=300,  # Limit to 300 most important features
                stop_words='english',
                ngram_range=(1, 2),  # Unigrams and bigrams
                min_df=2,  # Ignore terms that appear in less than 2 documents
                max_df=0.9,  # Ignore terms that appear in more than 90% of documents
            )
            tfidf_features = self.vectorizer.fit_transform(texts)
        else:
            tfidf_features = self.vectorizer.transform(texts)

        # 2. Get handcrafted features
        handcrafted_features = []
        for text in texts:
            features = self.extract_features(text)
            handcrafted_features.append(list(features.values()))
        handcrafted = np.array(handcrafted_features)

        # 3. Combine features
        # Convert sparse matrix to dense
        tfidf_dense = tfidf_features.toarray()
        combined = np.hstack([tfidf_dense, handcrafted])

        # Store feature names for reference
        if self.feature_names is None:
            tfidf_names = self.vectorizer.get_feature_names_out().tolist()
            handcrafted_names = self.get_feature_names()
            self.feature_names = tfidf_names + handcrafted_names

        return combined

    # ========== EXTRACTION METHODS ==========

    def extract_seed_items(self, text_pool: str, pattern: str) -> List[str]:
        """Stage 1: Fast regex/pattern extraction with cleaning."""
        if not pattern:
            return []

        try:
            matches = re.findall(pattern, text_pool, re.IGNORECASE | re.DOTALL | re.MULTILINE)
            cleaned = []
            for m in matches:
                if isinstance(m, tuple):
                    item = ' '.join(str(part).strip() for part in m if part)
                else:
                    item = str(m).strip()

                # Clean
                item = re.sub(r'\s+', ' ', item)
                item = item.strip('"\'“”‘’')
                item = item.strip()

                if item and len(item) > 3:
                    cleaned.append(item)

            return list(dict.fromkeys(cleaned))
        except re.error as e:
            print(f"Invalid regex pattern: {e}")
            return []

    def _get_candidate_segments(self, full_text: str) -> List[str]:
        """Split text into potential candidates."""
        segments = re.split(r'\n+|•|\*|\d+\.|\.\s+|\;\s+', full_text)
        candidates = []
        for seg in segments:
            seg = seg.strip()
            if 20 < len(seg) < 500:
                candidates.append(seg)
        return candidates

    def _get_project_text_pool(self) -> str:
        """Extract all text content from the current project."""
        return self.db.get_project_text_pool(self.project_id)

    def train_ml_model(self, seed_items: List[str], negative_ratio: float = 2.0) -> Tuple[bool, Dict]:
        """
        Stage 2: Train RandomForest using TF-IDF + handcrafted features.
        Each item gets embeddings + 17 handcrafted features.
        """
        if len(seed_items) < 5:
            return False, {"error": "Need at least 5 seed items to train."}

        # Get all text from the project
        full_text = self._get_project_text_pool()
        if not full_text:
            return False, {"error": "No text content found in project."}

        # Generate candidate segments
        candidates = self._get_candidate_segments(full_text)
        if len(candidates) < 10:
            return False, {"error": "Not enough text content to extract candidates."}

        # Label data
        X_texts = []
        y_labels = []
        seed_set = set(seed_items)

        # Positives: all seed items that appear in candidates
        positive_count = 0
        for seg in candidates:
            if seg in seed_set or any(seed in seg for seed in seed_set):
                X_texts.append(seg)
                y_labels.append(1)
                positive_count += 1

        if positive_count < 3:
            return False, {"error": "Not enough seed items found in the project text."}

        # Negatives: sample random segments that are NOT seeds
        non_seeds = [s for s in candidates if s not in seed_set]
        num_negatives = min(len(non_seeds), int(positive_count * negative_ratio))

        if num_negatives > 0:
            neg_samples = random.sample(non_seeds, num_negatives)
            X_texts.extend(neg_samples)
            y_labels.extend([0] * len(neg_samples))
        else:
            return False, {"error": "No negative examples available."}

        # Feature Engineering with TF-IDF + Handcrafted
        try:
            # Reset vectorizer for training
            self.vectorizer = None
            self.feature_names = None

            # Combine features (embeddings + handcrafted)
            feature_matrix = self.combine_features(X_texts)

            # Train RandomForest
            clf = RandomForestClassifier(
                n_estimators=100,
                random_state=42,
                class_weight='balanced',
                n_jobs=-1,
                max_depth=10,
                min_samples_split=5,
            )
            clf.fit(feature_matrix, y_labels)

            # Calculate feature importance (for debugging)
            feature_importance = dict(zip(self.feature_names, clf.feature_importances_))
            top_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:10]
            print(f"📊 Top 10 features: {top_features}")

            # Save model to database
            model_pickle = pickle.dumps({
                'classifier': clf,
                'vectorizer': self.vectorizer,
                'feature_names': self.feature_names,
                'feature_importance': feature_importance,
            })

            model_id = self.ml_storage.save_model(
                project_id=self.project_id,
                column_name=self.column_name,
                model_pickle=model_pickle,
                feature_names=self.feature_names,
                training_count=len(X_texts),
                positive_count=positive_count,
                negative_count=len(X_texts) - positive_count,
                accuracy_score=clf.score(feature_matrix, y_labels)
            )

            self.ml_model_id = model_id
            self.model = clf

            return True, {
                "model_id": model_id,
                "training_samples": len(X_texts),
                "positive_samples": positive_count,
                "negative_samples": len(X_texts) - positive_count,
                "accuracy": clf.score(feature_matrix, y_labels),
                "feature_count": len(self.feature_names),
                "top_features": dict(top_features[:5]),
            }

        except Exception as e:
            return False, {"error": str(e)}

    def load_ml_model(self, model_id: int) -> bool:
        """Load a previously trained model from database."""
        model_data = self.ml_storage.get_model_by_id(model_id)
        if not model_data:
            return False

        try:
            data = pickle.loads(model_data['model_pickle'])
            self.model = data['classifier']
            self.vectorizer = data['vectorizer']
            self.feature_names = data['feature_names']
            self.ml_model_id = model_id
            return True
        except Exception as e:
            print(f"Error loading model: {e}")
            return False

    def scan_with_ml(self, threshold: float = 0.85) -> List[Dict]:
        """
        Stage 3: Run ML inference on all candidates.
        Returns items with confidence scores and feature breakdown.
        """
        if self.model is None or self.vectorizer is None:
            raise ValueError("ML model not trained or loaded.")

        full_text = self._get_project_text_pool()
        if not full_text:
            return []

        candidates = self._get_candidate_segments(full_text)
        if not candidates:
            return []

        try:
            # Combine features for all candidates
            feature_matrix = self.combine_features(candidates)

            # Predict probabilities
            probs = self.model.predict_proba(feature_matrix)[:, 1]

            # Get feature contributions (simplified)
            results = []
            for text, prob in zip(candidates, probs):
                if prob >= threshold:
                    # Calculate basic features for display
                    features = self.extract_features(text)
                    results.append({
                        "text": text,
                        "confidence": float(prob),
                        "word_count": features['word_count'],
                        "char_count": features['char_count'],
                        "sentence_count": features['sentence_count'],
                        "question_count": features['question_count'],
                        "digit_count": features['digit_count'],
                        "upper_ratio": features['upper_ratio'],
                    })

            return sorted(results, key=lambda x: x["confidence"], reverse=True)

        except Exception as e:
            print(f"Error during ML scan: {e}")
            return []

    def get_available_seed_patterns(self) -> Dict[str, str]:
        """Get common seed extraction patterns."""
        return {
            "Headline after prefix": r'(?:HEADLINE|PROVEN HEADLINE):\s*"([^"]+)"',
            "Text between quotes": r'"([^"]+)"',
            "Bullet points": r'[•\-\*]\s*([^\n]+)',
            "Numbered list": r'\d+\.\s*([^\n]+)',
            "Text after colon": r'[^:]+:\s*([^\n]+)',
            "All caps phrase": r'\b([A-Z][A-Z\s]{2,})\b',
        }