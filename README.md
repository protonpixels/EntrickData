# 📊 Data Engineering Studio

A powerful desktop application for data collection, research, and structured data management. Built with PySide6 and SQLite.

## ✨ Features

### 📊 Data Table Projects
- **Create structured datasets** with custom columns
- **Column types**: Text, Integer, Float, Category, Boolean, Image, Video, Audio, File Path
- **Bulk import** files from folders
- **Export** to CSV, TSV, JSON
- **Search and filter** data
- **Reference other tables** for lookups

### 🌐 Data Research Projects
- **Web scraping** with readability extraction
- **Full-text search** across pages
- **Media extraction** (images, videos, iframes)
- **Multiple views**: Text Content, Links, Media, HTML, CSS, JavaScript
- **Editor** for bulk text processing
- **Bulk import** to data tables

### ✏️ Advanced Editor
- **Find and replace** with options
- **Clean text** (normalize whitespace)
- **Bulk import** with:
  - Split by newlines or paragraphs
  - Custom separators
  - Skip patterns
  - Duplicate handling

### 🔗 Linked Tables
- **Cross-table referencing**
- **Search across linked tables**
- **View and copy** linked row data

### 💾 Database
- **SQLite** for reliable storage
- **Full-text search** (FTS5)
- **ACID transactions**
- **Data integrity** with unique constraints

## 🚀 Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/data-engineering-studio.git
cd data-engineering-studio

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py