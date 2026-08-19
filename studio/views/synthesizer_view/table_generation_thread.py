# studio/views/table_generation_thread.py
from PySide6.QtCore import QThread, Signal
from views.synthesizer_view.table_generator import TableGenerator


class TableGenerationThread(QThread):
    """Thread for generating tables with progress tracking."""

    progress_update = Signal(str, int, int)
    column_complete = Signal(int, list)
    generation_complete = Signal(list)
    error_occurred = Signal(str)
    item_progress = Signal(int, int)  # current, total

    def __init__(self, db, llm, selected_projects, columns):
        super().__init__()
        self.db = db
        self.llm = llm
        self.selected_projects = selected_projects
        self.columns = columns
        self.generator = None

    def run(self):
        try:
            # Create generator with both callbacks
            self.generator = TableGenerator(
                self.db,
                self.llm,
                self.selected_projects,
                progress_callback=self._on_progress,
                item_progress_callback=self._on_item_progress  # NEW
            )

            # Add columns
            for col in self.columns:
                self.generator.add_column(col)

            # Generate results
            results = self.generator.generate()

            self.generation_complete.emit(results)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(str(e))

    def _on_progress(self, message: str, current: int, total: int):
        """Handle column-level progress."""
        self.progress_update.emit(message, current, total)

    def _on_item_progress(self, current: int, total: int):
        """Handle item-level progress."""
        self.item_progress.emit(current, total)