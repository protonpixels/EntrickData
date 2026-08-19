# studio\core\database.py

import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from .project_types import ProjectType


class StudioDatabase:
    """Unified database manager for all project types with container support"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._research_pages_cache = {}  # Add cache
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Create database and tables if they don't exist"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Projects table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                project_type TEXT NOT NULL,
                headline TEXT,
                container_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT,  -- JSON with type-specific config
                data_path TEXT, -- Path to project data
                is_active INTEGER DEFAULT 1
            )
        ''')

        # Containers table (NEW)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS containers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                parent_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_id) REFERENCES containers(id) ON DELETE CASCADE
            )
        ''')

        # Container order (for custom sorting within containers)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS container_order (
                container_id INTEGER,
                project_id INTEGER,
                position INTEGER DEFAULT 0,
                PRIMARY KEY (container_id, project_id),
                FOREIGN KEY (container_id) REFERENCES containers(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        ''')

        # Add container_id column if it doesn't exist (for existing databases)
        try:
            cursor.execute('ALTER TABLE projects ADD COLUMN container_id INTEGER')
        except sqlite3.OperationalError:
            pass  # Column already exists

        conn.commit()
        conn.close()

    # In StudioDatabase class, add this method:

    def _init_project_db(self, db_path: str, project_type: str, metadata: Dict = None):
        """Initialize a project-specific database"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        if project_type == ProjectType.DATA_TABLE.value:
            # Data Table project schema
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    _row_created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    _row_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Add initial columns from metadata if provided
            if metadata and 'column_config' in metadata:
                for col_config in metadata['column_config']:
                    col_name = col_config.get('name')
                    col_type = col_config.get('type', 'text')
                    if col_name:
                        sqlite_type = self._get_sqlite_type(col_type)
                        try:
                            cursor.execute(f"ALTER TABLE data ADD COLUMN '{col_name}' {sqlite_type}")
                        except sqlite3.OperationalError:
                            pass  # Column might already exist

        elif project_type == ProjectType.DATA_RESEARCH.value:
            # Data Research project schema
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    title TEXT,
                    main_text TEXT,
                    main_html TEXT,
                    metadata TEXT,
                    raw_html TEXT,
                    content_hash TEXT,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Add FTS for search
            cursor.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
                    title, main_text, content=pages
                )
            ''')
            # Trigger to keep FTS in sync
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS pages_fts_insert AFTER INSERT ON pages BEGIN
                    INSERT INTO pages_fts(rowid, title, main_text)
                    VALUES (new.id, new.title, new.main_text);
                END
            ''')
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS pages_fts_update AFTER UPDATE ON pages BEGIN
                    UPDATE pages_fts SET title = new.title, main_text = new.main_text
                    WHERE rowid = new.id;
                END
            ''')
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS pages_fts_delete AFTER DELETE ON pages BEGIN
                    DELETE FROM pages_fts WHERE rowid = old.id;
                END
    ''')

        elif project_type == ProjectType.DATA_DOCUMENT.value:
            # Data Document project schema (similar to research but without URL uniqueness)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT,
                    title TEXT,
                    main_text TEXT,
                    main_html TEXT,
                    metadata TEXT,
                    raw_html TEXT,
                    content_hash TEXT,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

        elif project_type == ProjectType.DATA_CHAT.value:
            # Data Chat project schema
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    role TEXT,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

        conn.commit()
        conn.close()
    # ========== CONTAINER METHODS ==========

    def create_container(self, name: str, parent_id: Optional[int] = None) -> int:
        """Create a new container"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO containers (name, parent_id)
            VALUES (?, ?)
        ''', (name, parent_id))

        container_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return container_id

    def get_container(self, container_id: int) -> Optional[Dict]:
        """Get container by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, name, parent_id, created_at, updated_at
            FROM containers WHERE id = ?
        ''', (container_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'id': row[0],
                'name': row[1],
                'parent_id': row[2],
                'created_at': row[3],
                'updated_at': row[4]
            }
        return None

    def get_container_tree(self) -> List[Dict]:
        """Get nested container tree with projects"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get all containers
        cursor.execute('''
            SELECT id, name, parent_id FROM containers
            ORDER BY name
        ''')
        containers = cursor.fetchall()

        # Get all projects
        cursor.execute('''
            SELECT id, name, project_type, headline, container_id
            FROM projects WHERE is_active = 1
            ORDER BY name
        ''')
        projects = cursor.fetchall()

        conn.close()

        # Build container map
        container_map = {}
        for c_id, name, parent_id in containers:
            container_map[c_id] = {
                'id': c_id,
                'name': name,
                'parent_id': parent_id,
                'children': [],
                'projects': []
            }

        # Build hierarchy
        root_containers = []
        for c_id, container in container_map.items():
            if container['parent_id'] is None:
                root_containers.append(container)
            else:
                parent = container_map.get(container['parent_id'])
                if parent:
                    parent['children'].append(container)

        # Add projects to containers
        for p_id, name, p_type, headline, container_id in projects:
            project_data = {
                'id': p_id,
                'name': name,
                'project_type': p_type,
                'headline': headline or ''
            }
            if container_id and container_id in container_map:
                container_map[container_id]['projects'].append(project_data)
            else:
                # Add to "Uncategorized" - we'll handle this separately
                pass

        return root_containers

    def get_uncategorized_projects(self) -> List[Dict]:
        """Get projects without a container"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, name, project_type, headline
            FROM projects
            WHERE container_id IS NULL AND is_active = 1
            ORDER BY name
        ''')

        projects = []
        for row in cursor.fetchall():
            projects.append({
                'id': row[0],
                'name': row[1],
                'project_type': row[2],
                'headline': row[3] or ''
            })

        conn.close()
        return projects

    def move_to_container(self, project_id: int, container_id: Optional[int]):
        """Move a project to a container (or remove from container)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE projects SET container_id = ? WHERE id = ?
        ''', (container_id, project_id))

        conn.commit()
        conn.close()

    def delete_container(self, container_id: int, move_to_parent: bool = True):
        """Delete a container and optionally move projects to parent"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get parent container ID
        cursor.execute('SELECT parent_id FROM containers WHERE id = ?', (container_id,))
        row = cursor.fetchone()
        parent_id = row[0] if row else None

        if move_to_parent:
            # Move projects to parent container
            cursor.execute('''
                UPDATE projects SET container_id = ? WHERE container_id = ?
            ''', (parent_id, container_id))
        else:
            # Set projects to uncategorized
            cursor.execute('''
                UPDATE projects SET container_id = NULL WHERE container_id = ?
            ''', (container_id,))

        # Delete the container
        cursor.execute('DELETE FROM containers WHERE id = ?', (container_id,))

        conn.commit()
        conn.close()

    def rename_container(self, container_id: int, new_name: str):
        """Rename a container"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE containers SET name = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (new_name, container_id))

        conn.commit()
        conn.close()

    # ========== UPDATED PROJECT METHODS ==========
    def create_project(self, name: str, project_type: str, headline: str = "",
                       metadata: Dict = None, container_id: Optional[int] = None) -> int:
        """Create a new project with optional container"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create project directory
        project_dir = os.path.join(
            os.path.dirname(self.db_path),
            '..', 'projects',
            project_type
        )
        os.makedirs(project_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        data_path = os.path.join(project_dir, f"project_{timestamp}.db")

        # Initialize project database based on type
        self._init_project_db(data_path, project_type, metadata)

        cursor.execute('''
            INSERT INTO projects (name, project_type, headline, metadata, data_path, container_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, project_type, headline, json.dumps(metadata or {}), data_path, container_id))

        project_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return project_id

    def get_all_projects(self) -> List[Dict]:
        """Get all projects with container info"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, name, project_type, headline, created_at, updated_at, metadata, data_path, container_id
            FROM projects
            WHERE is_active = 1
            ORDER BY updated_at DESC
        ''')

        projects = []
        for row in cursor.fetchall():
            projects.append({
                'id': row[0],
                'name': row[1],
                'project_type': row[2],
                'headline': row[3] or '',
                'created_at': row[4],
                'updated_at': row[5],
                'metadata': json.loads(row[6]) if row[6] else {},
                'data_path': row[7],
                'container_id': row[8]
            })

        conn.close()
        return projects

    def get_projects_by_container(self, container_id: int) -> List[Dict]:
        """Get all projects in a specific container"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, name, project_type, headline, created_at, updated_at, metadata, data_path
            FROM projects
            WHERE container_id = ? AND is_active = 1
            ORDER BY name
        ''', (container_id,))

        projects = []
        for row in cursor.fetchall():
            projects.append({
                'id': row[0],
                'name': row[1],
                'project_type': row[2],
                'headline': row[3] or '',
                'created_at': row[4],
                'updated_at': row[5],
                'metadata': json.loads(row[6]) if row[6] else {},
                'data_path': row[7]
            })

        conn.close()
        return projects

    def get_project(self, project_id: int) -> Optional[Dict]:
        """Get a specific project with container info"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, name, project_type, headline, created_at, updated_at, metadata, data_path, container_id
            FROM projects
            WHERE id = ? AND is_active = 1
        ''', (project_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'id': row[0],
                'name': row[1],
                'project_type': row[2],
                'headline': row[3] or '',
                'created_at': row[4],
                'updated_at': row[5],
                'metadata': json.loads(row[6]) if row[6] else {},
                'data_path': row[7],
                'container_id': row[8]
            }
        return None

    def update_project(self, project_id: int, name: str = None, headline: str = None,
                       metadata: Dict = None):
        """Update project metadata"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)

        if headline is not None:
            updates.append("headline = ?")
            params.append(headline)

        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(project_id)

        if updates:
            sql = f"UPDATE projects SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(sql, params)
            conn.commit()

        conn.close()

    def delete_project(self, project_id: int):
        """Soft delete a project"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('UPDATE projects SET is_active = 0 WHERE id = ?', (project_id,))
        conn.commit()
        conn.close()

    # ========== DATA TABLE METHODS ==========

    def get_table_columns(self, data_path: str) -> List[Dict]:
        """Get column definitions for a data table project"""
        if not os.path.exists(data_path):
            return []

        conn = sqlite3.connect(data_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(data)")
        columns = []
        for col in cursor.fetchall():
            # Skip internal columns
            if col[1] not in ['id', '_row_created_at', '_row_updated_at']:
                columns.append({
                    'name': col[1],
                    'type': col[2]
                })

        conn.close()
        return columns

    def get_table_data(self, data_path: str) -> List[List]:
        """Get all data from a data table project"""
        if not os.path.exists(data_path):
            return []

        conn = sqlite3.connect(data_path)
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT * FROM data ORDER BY id')
            rows = cursor.fetchall()
            conn.close()

            # Get column names (excluding internal columns)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(data)")
            all_columns = [col[1] for col in cursor.fetchall()]

            # Find which columns to include (all except internal ones)
            skip_columns = ['id', '_row_created_at', '_row_updated_at']
            include_indices = [i for i, col in enumerate(all_columns) if col not in skip_columns]

            # Convert to list of lists with only non-internal columns
            result = []
            for row in rows:
                result.append([row[i] for i in include_indices])

            conn.close()
            return result
        except sqlite3.OperationalError:
            conn.close()
            return []

    def add_table_column(self, data_path: str, column_name: str, column_type: str):
        """Add a column to a data table project"""
        if not os.path.exists(data_path):
            return

        conn = sqlite3.connect(data_path)
        cursor = conn.cursor()

        # Get existing columns
        cursor.execute("PRAGMA table_info(data)")
        existing_columns = [col[1] for col in cursor.fetchall()]

        # Check if column already exists
        if column_name not in existing_columns:
            sqlite_type = self._get_sqlite_type(column_type)
            try:
                cursor.execute(f"ALTER TABLE data ADD COLUMN '{column_name}' {sqlite_type}")
                conn.commit()
            except sqlite3.OperationalError:
                pass

        conn.close()

    def add_table_row(self, data_path: str, row_data: List):
        """Add a row to a data table project"""
        if not os.path.exists(data_path):
            return

        conn = sqlite3.connect(data_path)
        cursor = conn.cursor()

        # Get column names in database order
        cursor.execute("PRAGMA table_info(data)")
        all_columns = cursor.fetchall()

        # Filter out internal columns
        columns = []
        for col in all_columns:
            col_name = col[1]
            if col_name not in ['id', '_row_created_at', '_row_updated_at']:
                columns.append(col_name)

        # row_data should already be in database column order
        values = row_data[:len(columns)]
        while len(values) < len(columns):
            values.append('')

        # Prepare INSERT statement
        placeholders = ', '.join(['?' for _ in values])
        columns_str = ', '.join([f'"{col}"' for col in columns[:len(values)]])

        sql = f"INSERT INTO data ({columns_str}) VALUES ({placeholders})"
        cursor.execute(sql, values)

        conn.commit()
        conn.close()

    def update_table_row(self, data_path: str, row_id: int, row_data: List):
        """Update a row in a data table project"""
        if not os.path.exists(data_path):
            return

        conn = sqlite3.connect(data_path)
        cursor = conn.cursor()

        # Get column names in database order
        cursor.execute("PRAGMA table_info(data)")
        all_columns = cursor.fetchall()

        # Get the column names (excluding internal columns)
        columns = []
        for col in all_columns:
            col_name = col[1]
            if col_name not in ['id', '_row_created_at','_row_updated_at']:
                columns.append(col_name)

        # row_data should already be in database column order
        # But make sure we have the right number of values
        values = row_data[:len(columns)]
        while len(values) < len(columns):
            values.append('')

        # Prepare UPDATE statement with column names
        set_clause = ', '.join([f'"{col}" = ?' for col in columns[:len(values)]])
        sql = f"UPDATE data SET {set_clause}, _row_updated_at = CURRENT_TIMESTAMP WHERE id = ?"

        cursor.execute(sql, values + [row_id])
        conn.commit()
        conn.close()

    def delete_table_row(self, data_path: str, row_id: int):
        """Delete a row from a data table project"""
        if not os.path.exists(data_path):
            return

        conn = sqlite3.connect(data_path)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM data WHERE id = ?', (row_id,))
        conn.commit()
        conn.close()

    def get_table_row_count(self, data_path: str) -> int:
        """Get the number of rows in a data table project"""
        if not os.path.exists(data_path):
            return 0

        conn = sqlite3.connect(data_path)
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT COUNT(*) FROM data')
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except sqlite3.OperationalError:
            conn.close()
            return 0

    # ========== DATA RESEARCH METHODS ==========


    def get_research_pages(self, data_path: str) -> List[Dict]:
        """Get all pages from a research project with caching."""
        # Check cache first
        if data_path in self._research_pages_cache:
            return self._research_pages_cache[data_path]

        if not os.path.exists(data_path):
            return []

        conn = sqlite3.connect(data_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT id, url, title, main_text, main_html, metadata, raw_html, fetched_at
                FROM pages ORDER BY fetched_at DESC
            ''')
            rows = cursor.fetchall()
            conn.close()

            result = [{
                'id': row[0],
                'url': row[1],
                'title': row[2] or '',
                'main_text': row[3] or '',
                'main_html': row[4] or '',
                'metadata': json.loads(row[5]) if row[5] else {},
                'raw_html': row[6] or '',
                'fetched_at': row[7]
            } for row in rows]

            # Cache the result
            self._research_pages_cache[data_path] = result
            return result
        except sqlite3.OperationalError:
            conn.close()
            return []

    def clear_cache(self):
        """Clear the research pages cache."""
        self._research_pages_cache = {}

    def add_research_page(self, data_path: str, page_data: Dict) -> int:
        """Add a page to a research project"""
        if not os.path.exists(data_path):
            return -1

        conn = sqlite3.connect(data_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO pages (url, title, main_text, main_html, metadata, raw_html, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            page_data.get('url', ''),
            page_data.get('title', ''),
            page_data.get('main_text', ''),
            page_data.get('main_html', ''),
            json.dumps(page_data.get('metadata', {})),
            page_data.get('raw_html', ''),
            page_data.get('content_hash', '')
        ))

        page_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return page_id

    def add_research_element(self, data_path: str, element_data: Dict):
        """Add an element to a research project"""
        if not os.path.exists(data_path):
            return

        conn = sqlite3.connect(data_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO elements (page_id, element_type, position, content, html_fragment, attributes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            element_data.get('page_id'),
            element_data.get('type', ''),
            element_data.get('position', 0),
            element_data.get('content', ''),
            element_data.get('html', ''),
            json.dumps(element_data.get('attributes', {}))
        ))

        conn.commit()
        conn.close()

    def search_research_pages(self, data_path: str, query: str) -> List[Dict]:
        """Search pages in a research project using FTS"""
        if not os.path.exists(data_path):
            return []

        conn = sqlite3.connect(data_path)
        cursor = conn.cursor()

        try:
            fts_query = f'"{query}"' if ' ' in query else query
            cursor.execute('''
                SELECT p.id, p.url, p.title, p.main_text
                FROM pages p
                JOIN pages_fts fts ON p.id = fts.rowid
                WHERE pages_fts MATCH ?
                ORDER BY rank
            ''', (fts_query,))

            rows = cursor.fetchall()
            conn.close()

            return [{
                'id': row[0],
                'url': row[1],
                'title': row[2] or '',
                'snippet': (row[3][:200] + '...') if row[3] and len(row[3]) > 200 else (row[3] or '')
            } for row in rows]
        except sqlite3.OperationalError:
            conn.close()
            return []

    def _get_sqlite_type(self, column_type: str) -> str:
        """Map column types to SQLite types"""
        type_map = {
            'text': 'TEXT',
            'string': 'TEXT',
            'integer': 'INTEGER',
            'float': 'REAL',
            'real': 'REAL',
            'category': 'TEXT',
            'image': 'TEXT',
            'video': 'TEXT',
            'audio': 'TEXT',
            'file_path': 'TEXT',
            'url': 'TEXT',
            'email': 'TEXT',
            'date': 'TEXT',
            'datetime': 'TEXT',
            'boolean': 'INTEGER',
            'bool': 'INTEGER'
        }
        return type_map.get(column_type.lower(), 'TEXT')

    def get_elements_for_page(self, data_path: str, page_id: int) -> List[Dict]:
        """Get elements for a specific page"""
        if not os.path.exists(data_path):
            return []

        conn = sqlite3.connect(data_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT element_type, position, content, html_fragment, attributes
                FROM elements WHERE page_id = ? ORDER BY position
            ''', (page_id,))
            rows = cursor.fetchall()
            conn.close()

            return [{
                'type': row[0],
                'position': row[1],
                'content': row[2],
                'html': row[3],
                'attributes': json.loads(row[4]) if row[4] else {}
            } for row in rows]
        except sqlite3.OperationalError:
            conn.close()
            return []

    def get_all_data_table_projects(self) -> List[Dict]:
        """Get all data table projects"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, name, headline, metadata, data_path
            FROM projects
            WHERE project_type = ? AND is_active = 1
            ORDER BY name
        ''', (ProjectType.DATA_TABLE.value,))

        projects = []
        for row in cursor.fetchall():
            projects.append({
                'id': row[0],
                'name': row[1],
                'headline': row[2] or '',
                'metadata': json.loads(row[3]) if row[3] else {},
                'data_path': row[4]
            })

        conn.close()
        return projects

    def get_table_column_names(self, data_path: str) -> List[str]:
        """Get column names from a data table project in the correct order"""
        if not os.path.exists(data_path):
            return []

        conn = sqlite3.connect(data_path)
        cursor = conn.cursor()

        try:
            cursor.execute("PRAGMA table_info(data)")
            # Get columns in the order they appear in the table
            columns = [col[1] for col in cursor.fetchall()
                       if col[1] not in ['id', '_row_created_at', '_row_updated_at']]
            conn.close()
            return columns
        except sqlite3.OperationalError:
            conn.close()
            return []

    def sync_schema_with_metadata(self, project_id: int):
        """Sync the database schema with the metadata column config"""
        project = self.get_project(project_id)
        if not project:
            return

        data_path = project['data_path']
        if not os.path.exists(data_path):
            return

        # Get columns from database
        conn = sqlite3.connect(data_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(data)")
        db_columns = cursor.fetchall()
        conn.close()

        db_column_names = []
        for col in db_columns:
            col_name = col[1]
            if col_name not in ['id', '_row_created_at', '_row_updated_at']:
                db_column_names.append(col_name)

        # Get columns from metadata
        metadata = project.get('metadata', {})
        metadata_columns = metadata.get('column_config', [])
        metadata_column_names = [col['name'] for col in metadata_columns]

        # If they don't match, update metadata to match database
        if sorted(db_column_names) != sorted(metadata_column_names):
            # Rebuild metadata from database schema
            new_config = []
            for col_name in db_column_names:
                # Find existing config for this column
                existing = next((c for c in metadata_columns if c.get('name') == col_name), None)
                if existing:
                    new_config.append(existing)
                else:
                    # Create default config
                    new_config.append({
                        'name': col_name,
                        'type': 'text',
                        'type_display': 'Text',
                        'required': False,
                        'unique': False,
                        'desc': ''
                    })

            metadata['column_config'] = new_config
            self.update_project(project_id, metadata=metadata)

    def get_table_data(self, data_path: str) -> List[List]:
        """Get all data from a data table project"""
        if not os.path.exists(data_path):
            return []

        conn = sqlite3.connect(data_path)
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT * FROM data ORDER BY id')
            rows = cursor.fetchall()

            # Get column names (excluding internal columns)
            cursor2 = conn.cursor()  # Use the same connection, not a new one
            cursor2.execute("PRAGMA table_info(data)")
            all_columns = cursor2.fetchall()
            cursor2.close()

            skip_columns = ['id', '_row_created_at', '_row_updated_at']
            include_indices = [i for i, col in enumerate(all_columns) if col[1] not in skip_columns]

            result = []
            for row in rows:
                result.append([row[i] for i in include_indices])

            conn.close()
            return result
        except sqlite3.OperationalError as e:
            conn.close()
            print(f"Error getting table data: {e}")
            return []

    def get_project_text_pool(self, project_id: int) -> str:
        """Get all text content from a project for ML training."""
        project = self.get_project(project_id)
        if not project:
            return ""

        project_type = project.get('project_type')
        data_path = project.get('data_path')

        if project_type == 'data_table':
            rows = self.get_table_data(data_path)
            text_parts = []
            for row in rows:
                text_parts.extend([str(cell) for cell in row if cell])
            return '\n'.join(text_parts)

        elif project_type in ['data_research', 'data_document']:
            # Use the WebExtractor to clean the text properly
            from studio.core.web_extractor import WebExtractor
            extractor = WebExtractor()

            pages = self.get_research_pages(data_path)
            text_parts = []

            for page in pages:
                main_text = page.get('main_text', '')
                raw_html = page.get('raw_html', '')

                # If we have raw HTML, extract clean text from it
                if raw_html:
                    try:
                        # Use the WebExtractor's clean method
                        clean_text = extractor.clean_html(raw_html)
                        if clean_text:
                            text_parts.append(clean_text)
                    except Exception as e:
                        print(f"Error extracting text from page: {e}")
                elif main_text:
                    # Fallback to stored main_text
                    text_parts.append(main_text)

                # Also include title if available
                title = page.get('title', '')
                if title:
                    text_parts.append(title)

            return '\n\n'.join(text_parts)

        elif project_type == 'data_chat':
            import sqlite3
            conn = sqlite3.connect(data_path)
            cursor = conn.cursor()
            try:
                cursor.execute('SELECT content FROM chat_messages')
                rows = cursor.fetchall()
                conn.close()
                return '\n'.join([row[0] for row in rows if row[0]])
            except sqlite3.OperationalError:
                conn.close()
                return ""

        return ""

    def create_table_from_results(self, name: str, results: list, columns: list) -> int:
        """Create a table project from results (without context)."""
        # Build metadata - only column names, no context
        metadata = {
            'column_config': [
                {'name': col.name, 'type': 'text', 'required': False}
                for col in columns
            ]
        }

        # Create project
        project_id = self.create_project(
            name=name,
            project_type='data_table',
            metadata=metadata
        )

        if not project_id:
            return None

        # Get data path
        project_data = self.get_project(project_id)
        data_path = project_data['data_path']

        # Add rows - only the items, not context
        for row_idx in range(len(results[0])):
            row_data = []
            for col_idx in range(len(columns)):
                if col_idx < len(results) and row_idx < len(results[col_idx]):
                    row_data.append(results[col_idx][row_idx].get('item', ''))
                else:
                    row_data.append('')
            self.add_table_row(data_path, row_data)

        return project_id