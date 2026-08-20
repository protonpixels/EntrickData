# cleanup_data_tables.py
import sqlite3
import os
import shutil


def cleanup_data_table_projects():
    db_path = 'cache/studio.db'

    if not os.path.exists(db_path):
        print("❌ studio.db not found")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all data table projects
    cursor.execute("SELECT id, name, data_path FROM projects WHERE project_type = 'data_table'")
    projects = cursor.fetchall()

    if not projects:
        print("✅ No data table projects found")
        conn.close()
        return

    print(f"📊 Found {len(projects)} data table projects:")
    for pid, name, path in projects:
        print(f"  - {name} (ID: {pid})")

    # Confirm
    response = input(f"\nDelete these {len(projects)} projects? (yes/no): ")
    if response.lower() != 'yes':
        print("❌ Cancelled")
        conn.close()
        return

    # Delete project database files
    for pid, name, data_path in projects:
        if data_path and os.path.exists(data_path):
            print(f"🗑️ Deleting: {data_path}")
            os.remove(data_path)
            # Clean up journal files
            for ext in ['-journal', '-wal', '-shm']:
                journal_path = data_path + ext
                if os.path.exists(journal_path):
                    os.remove(journal_path)

    # Delete from main database
    cursor.execute("DELETE FROM projects WHERE project_type = 'data_table'")
    conn.commit()

    # Verify
    cursor.execute("SELECT COUNT(*) FROM projects WHERE project_type = 'data_table'")
    remaining = cursor.fetchone()[0]

    conn.close()

    print(f"✅ Deleted {len(projects)} data table projects")
    print(f"📊 Remaining: {remaining} data table projects")


if __name__ == "__main__":
    cleanup_data_table_projects()