import os
import shutil
from typing import List, Optional
from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import Qt


class FileHandler:
    @staticmethod
    def get_file_paths(title: str = "Select Files", filter_str: str = "All Files (*.*)") -> List[str]:
        """Open file dialog to select files"""
        paths, _ = QFileDialog.getOpenFileNames(
            None, title, "", filter_str
        )
        return paths

    @staticmethod
    def get_directory_path(title: str = "Select Directory") -> Optional[str]:
        """Open file dialog to select a directory"""
        path = QFileDialog.getExistingDirectory(
            None, title
        )
        return path

    @staticmethod
    def get_save_path(title: str = "Save File", filename: str = "file",
                      filter_str: str = "All Files (*.*)") -> Optional[str]:
        """Open file dialog to save a file"""
        path, _ = QFileDialog.getSaveFileName(
            None, title, filename, filter_str
        )
        return path

    @staticmethod
    def copy_file(source: str, destination: str) -> bool:
        """Copy a file"""
        try:
            shutil.copy2(source, destination)
            return True
        except Exception:
            return False

    @staticmethod
    def get_relative_path(file_path: str, base_dir: str) -> str:
        """Get relative path from base directory"""
        try:
            return os.path.relpath(file_path, base_dir)
        except ValueError:
            return file_path

    @staticmethod
    def get_absolute_path(relative_path: str, base_dir: str) -> str:
        """Get absolute path from relative path and base directory"""
        if os.path.isabs(relative_path):
            return relative_path
        return os.path.join(base_dir, relative_path)

    @staticmethod
    def get_file_extension(file_path: str) -> str:
        """Get file extension without dot"""
        return os.path.splitext(file_path)[1][1:].lower()

    @staticmethod
    def get_file_size(file_path: str) -> int:
        """Get file size in bytes"""
        try:
            return os.path.getsize(file_path)
        except Exception:
            return 0

    @staticmethod
    def get_file_type(file_path: str) -> str:
        """Get file type category based on extension"""
        ext = FileHandler.get_file_extension(file_path)
        image_exts = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico', 'tiff']
        video_exts = ['mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv', 'flv', 'wmv']
        audio_exts = ['mp3', 'wav', 'flac', 'aac', 'ogg', 'wma', 'm4a']
        document_exts = ['pdf', 'doc', 'docx', 'txt', 'csv', 'json', 'xml', 'xls', 'xlsx']

        if ext in image_exts:
            return 'image'
        elif ext in video_exts:
            return 'video'
        elif ext in audio_exts:
            return 'audio'
        elif ext in document_exts:
            return 'document'
        else:
            return 'unknown'