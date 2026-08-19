import sqlite3
import json
import pickle
from datetime import datetime
from typing import Optional, Dict, List, Any


class MLModel:
    """ML Model storage using your existing database pattern"""

    TABLE_NAME = "ml_models"

    def __init__(self, db_path: str):
        """Initialize with the path to your main studio database"""
        self.db_path = db_path
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create ml_models table if it doesn't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                column_name TEXT NOT NULL,
                model_pickle BLOB,
                feature_names TEXT,  -- JSON list of feature names
                training_count INTEGER DEFAULT 0,
                positive_count INTEGER DEFAULT 0,
                negative_count INTEGER DEFAULT 0,
                accuracy_score REAL,
                embedding_model TEXT DEFAULT 'all-MiniLM-L6-v2',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create index for faster lookups
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ml_models_project_column 
            ON ml_models(project_id, column_name)
        ''')

        conn.commit()
        conn.close()

    def save_model(self, project_id: int, column_name: str, model_pickle: bytes,
                   feature_names: List[str], training_count: int,
                   positive_count: int, negative_count: int,
                   accuracy_score: float) -> int:
        """Save a trained ML model to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check if model already exists for this project/column
        cursor.execute(f'''
            SELECT id FROM {self.TABLE_NAME}
            WHERE project_id = ? AND column_name = ?
        ''', (project_id, column_name))

        existing = cursor.fetchone()

        if existing:
            # Update existing
            cursor.execute(f'''
                UPDATE {self.TABLE_NAME}
                SET model_pickle = ?, feature_names = ?, training_count = ?,
                    positive_count = ?, negative_count = ?, accuracy_score = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (
                model_pickle,
                json.dumps(feature_names),
                training_count,
                positive_count,
                negative_count,
                accuracy_score,
                existing[0]
            ))
            model_id = existing[0]
        else:
            # Insert new
            cursor.execute(f'''
                INSERT INTO {self.TABLE_NAME}
                (project_id, column_name, model_pickle, feature_names,
                 training_count, positive_count, negative_count, accuracy_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                project_id,
                column_name,
                model_pickle,
                json.dumps(feature_names),
                training_count,
                positive_count,
                negative_count,
                accuracy_score
            ))
            model_id = cursor.lastrowid

        conn.commit()
        conn.close()
        return model_id

    def load_model(self, project_id: int, column_name: str) -> Optional[Dict]:
        """Load a trained model from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT id, model_pickle, feature_names, training_count,
                   positive_count, negative_count, accuracy_score,
                   embedding_model, created_at
            FROM {self.TABLE_NAME}
            WHERE project_id = ? AND column_name = ?
            ORDER BY updated_at DESC
            LIMIT 1
        ''', (project_id, column_name))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'id': row[0],
                'model_pickle': row[1],
                'feature_names': json.loads(row[2]) if row[2] else [],
                'training_count': row[3],
                'positive_count': row[4],
                'negative_count': row[5],
                'accuracy_score': row[6],
                'embedding_model': row[7] or 'all-MiniLM-L6-v2',
                'created_at': row[8]
            }
        return None

    def get_model_by_id(self, model_id: int) -> Optional[Dict]:
        """Load a model by its ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT id, project_id, column_name, model_pickle, feature_names,
                   training_count, positive_count, negative_count, accuracy_score,
                   embedding_model, created_at
            FROM {self.TABLE_NAME}
            WHERE id = ?
        ''', (model_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'id': row[0],
                'project_id': row[1],
                'column_name': row[2],
                'model_pickle': row[3],
                'feature_names': json.loads(row[4]) if row[4] else [],
                'training_count': row[5],
                'positive_count': row[6],
                'negative_count': row[7],
                'accuracy_score': row[8],
                'embedding_model': row[9] or 'all-MiniLM-L6-v2',
                'created_at': row[10]
            }
        return None

    def delete_model(self, project_id: int, column_name: str):
        """Delete a model from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(f'''
            DELETE FROM {self.TABLE_NAME}
            WHERE project_id = ? AND column_name = ?
        ''', (project_id, column_name))

        conn.commit()
        conn.close()

    def list_models(self, project_id: int) -> List[Dict]:
        """List all models for a project"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(f'''
            SELECT id, column_name, training_count, accuracy_score, created_at
            FROM {self.TABLE_NAME}
            WHERE project_id = ?
            ORDER BY updated_at DESC
        ''', (project_id,))

        rows = cursor.fetchall()
        conn.close()

        return [{
            'id': row[0],
            'column_name': row[1],
            'training_count': row[2],
            'accuracy_score': row[3],
            'created_at': row[4]
        } for row in rows]