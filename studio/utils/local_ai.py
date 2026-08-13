"""
Local AI integration using the downloaded Qwen model
No external dependencies - uses the bundled model file
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, Callable, List, Dict
import platform
import time


class LocalQwenBackend:
    """Local Qwen backend using downloaded GGUF model file"""

    def __init__(self, model_path: str = None):
        self.model_path = model_path or self._find_model()
        self.model_loaded = False
        self.llama = None
        self.model_info = None

        if self.model_path and os.path.exists(self.model_path):
            self._load_model_info()
            self._try_load_model()

    def _find_model(self) -> Optional[str]:
        """Find the Qwen model file in common locations"""
        # Get the project root directory
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent  # Go up two levels from utils/

        # Search paths
        search_paths = [
            # 1. In the ai_model folder (next to the project)
            project_root.parent / "ai_model" / "models" / "qwen2.5-1.5b-instruct.gguf",
            # 2. In the ai_model folder (inside the project)
            project_root / "ai_model" / "models" / "qwen2.5-1.5b-instruct.gguf",
            # 3. In the models folder (project root)
            project_root / "models" / "qwen2.5-1.5b-instruct.gguf",
            # 4. In the user's data directory
            Path.home() / ".datastudio" / "models" / "qwen2.5-1.5b-instruct.gguf",
            # 5. In the current working directory
            Path.cwd() / "models" / "qwen2.5-1.5b-instruct.gguf",
        ]

        for path in search_paths:
            if path.exists():
                print(f"✅ Found model at: {path}")
                return str(path)

        print("⚠️ Model not found. Please run download_ai_model.py first.")
        return None

    def _load_model_info(self):
        """Load model information from the info file"""
        info_path = Path(self.model_path).parent / "model_info.json"
        if info_path.exists():
            try:
                with open(info_path, 'r') as f:
                    self.model_info = json.load(f)
                print(f"📋 Model info: {self.model_info.get('model_name', 'Unknown')}")
                print(f"📊 File size: {self._format_size(self.model_info.get('file_size', 0))}")
            except:
                pass

    def _format_size(self, size: int) -> str:
        """Format file size for display"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def _try_load_model(self) -> bool:
        """Try to load the model using llama-cpp-python"""
        try:
            # Check if llama-cpp-python is installed
            try:
                from llama_cpp import Llama
            except ImportError:
                print("⚠️ llama-cpp-python not installed.")
                print("   Install with: pip install llama-cpp-python")
                return False

            import multiprocessing

            # Calculate optimal thread count
            n_threads = max(1, multiprocessing.cpu_count() - 1)

            print(f"🔄 Loading model with {n_threads} threads...")
            print(f"📁 Model path: {self.model_path}")

            # Load the model with optimal settings
            self.llama = Llama(
                model_path=self.model_path,
                n_ctx=4096,  # Context window
                n_threads=n_threads,
                n_gpu_layers=0,  # CPU only (use -1 for GPU if available)
                verbose=False,
                use_mmap=True,  # Memory map for efficiency
                use_mlock=False,
                seed=42,
                n_batch=512,  # Batch size for processing
                f16_kv=True,  # Use half-precision for KV cache
            )

            self.model_loaded = True
            print("✅ Model loaded successfully!")
            return True

        except Exception as e:
            print(f"❌ Error loading model: {e}")
            return False

    def is_available(self) -> bool:
        """Check if the model is available and loaded"""
        return self.model_loaded

    def is_model_downloaded(self) -> bool:
        """Check if the model file exists"""
        return self.model_path is not None and os.path.exists(self.model_path)

    def get_name(self) -> str:
        """Get the backend name"""
        if self.model_info:
            return f"🔒 {self.model_info.get('model_name', 'Qwen')}"
        return "🔒 Qwen (Local)"

    def get_models(self) -> List[str]:
        """Get available models"""
        return ["qwen2.5:1.5b"] if self.model_loaded else []

    def get_model_info(self) -> Dict:
        """Get model information"""
        return {
            "name": self.model_info.get('model_name', 'Qwen2.5 1.5B') if self.model_info else "Qwen2.5 1.5B",
            "path": self.model_path,
            "size": self.model_info.get('file_size', 0) if self.model_info else 0,
            "loaded": self.model_loaded
        }

    def query(self, prompt: str, context: str = "", model: str = "") -> str:
        """Query the model"""
        if not self.model_loaded:
            return "⚠️ Model not loaded. Please check the model file."

        full_prompt = self._build_prompt(prompt, context)

        try:
            # Generate response
            start_time = time.time()
            response = self.llama(
                full_prompt,
                max_tokens=1000,
                temperature=0.7,
                top_p=0.9,
                top_k=40,
                echo=False,
                stop=["</s>", "User:", "Question:", "Context:"],
                frequency_penalty=0.0,
                presence_penalty=0.0,
                repeat_penalty=1.1,
            )

            elapsed = time.time() - start_time
            result = response['choices'][0]['text'].strip()

            # Print performance info (optional)
            if result:
                print(f"⏱️ Response generated in {elapsed:.2f}s ({len(result)} chars)")

            return result

        except Exception as e:
            return f"⚠️ Error: {str(e)}"

    def _build_prompt(self, prompt: str, context: str) -> str:
        """Build the prompt with context"""
        if context:
            return f"""You are a helpful data analyst assistant. Answer questions based on the provided context.

Context:
{context}

Question: {prompt}

Answer concisely and accurately based on the context provided. If you don't know the answer, say so."""
        return prompt


class LocalAIManager:
    """Manager for local AI backends"""

    def __init__(self):
        self.backends = {}
        self.active_backend_id = None
        self._init_backends()

    def _init_backends(self):
        """Initialize all local backends"""
        # Try to find and load the model
        qwen = LocalQwenBackend()
        if qwen.is_model_downloaded():
            self.backends["qwen"] = qwen
        else:
            print("ℹ️ No local model found. Please run download_ai_model.py")

    def get_available_backends(self) -> List[Dict]:
        """Get all available backends with their status"""
        backends = []
        for name, backend in self.backends.items():
            backends.append({
                "id": name,
                "name": backend.get_name(),
                "available": backend.is_available(),
                "models": backend.get_models(),
                "model_downloaded": backend.is_model_downloaded()
            })
        return backends

    def set_active_backend(self, backend_id: str) -> bool:
        """Set the active backend"""
        if backend_id in self.backends:
            self.active_backend_id = backend_id
            return True
        return False

    def get_active_backend(self) -> Optional[LocalQwenBackend]:
        """Get the active backend"""
        if self.active_backend_id and self.active_backend_id in self.backends:
            return self.backends[self.active_backend_id]
        return None

    def query(self, prompt: str, context: str = "", model: str = "") -> str:
        """Send a query using the active backend"""
        backend = self.get_active_backend()
        if not backend:
            return "⚠️ No AI backend available. Please enable AI in settings."

        return backend.query(prompt, context, model)

    def auto_select_backend(self) -> str:
        """Automatically select the best available backend"""
        # Check if we have a loaded model
        for name, backend in self.backends.items():
            if backend.is_available():
                self.active_backend_id = name
                return name

        # Check if we have a downloaded model that failed to load
        for name, backend in self.backends.items():
            if backend.is_model_downloaded():
                # Try to reload it
                backend._try_load_model()
                if backend.is_available():
                    self.active_backend_id = name
                    return name

        return None