import os
import json
import requests
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import platform
import hashlib
import subprocess
import sys


class AIBackend(ABC):
    """Abstract base class for AI backends"""

    @abstractmethod
    def query(self, prompt: str, context: str = "", model: str = "") -> str:
        """Send a query to the AI backend"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the backend is available"""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get the backend name"""
        pass

    @abstractmethod
    def get_models(self) -> List[str]:
        """Get available models"""
        pass

    @abstractmethod
    def get_install_guide(self) -> str:
        """Get installation guide"""
        pass


import os
import requests
from typing import Optional, Dict, Any, List
import subprocess
import sys


class QwenBackend(AIBackend):
    """Pure offline Qwen backend - 100% local, no terminal needed"""

    def __init__(self):
        self.base_url = "http://localhost:11434"
        self.model_name = "qwen2.5:1.5b"
        self.available = False
        self.model_available = False
        self.model_path = self._get_model_path()
        self._check_availability()

    def _get_model_path(self):
        """Get the path where models are stored"""
        # Check common Ollama model locations
        home = os.path.expanduser("~")
        possible_paths = [
            os.path.join(home, ".ollama", "models"),
            os.path.join(home, ".cache", "ollama", "models"),
            os.path.join(os.path.dirname(sys.executable), "models"),
            os.path.join(os.getcwd(), "models")
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        # Create a models directory in the app folder if none exists
        app_models = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
        os.makedirs(app_models, exist_ok=True)
        return app_models

    def _check_availability(self):
        """Check if Ollama is running and Qwen model is available"""
        # First check if Ollama is running
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m.get('name', '') for m in models]

                for model in model_names:
                    if 'qwen' in model.lower():
                        self.model_available = True
                        self.model_name = model
                        break

                self.available = True
                return
        except:
            pass

        # If Ollama is not running, check if we have a bundled model
        if self._check_bundled_model():
            self.model_available = True
            self.available = True
            return

        self.available = False
        self.model_available = False

    def _check_bundled_model(self) -> bool:
        """Check if we have a bundled model file"""
        model_file = os.path.join(self.model_path, "qwen2.5-1.5b-instruct.gguf")
        return os.path.exists(model_file)

    def install_model(self, progress_callback=None):
        """Install Qwen model automatically - no terminal needed"""
        try:
            # Try using Ollama first (most common)
            if self._install_with_ollama(progress_callback):
                return True

            # If Ollama fails, download GGUF directly
            return self._download_gguf_directly(progress_callback)

        except Exception as e:
            print(f"Installation error: {e}")
            return False

    def _install_with_ollama(self, progress_callback=None):
        """Install using Ollama"""
        try:
            # Check if ollama is installed
            result = subprocess.run(["ollama", "--version"], capture_output=True, text=True)
            if result.returncode != 0:
                return False

            # Pull the model
            if progress_callback:
                progress_callback("Pulling Qwen model from Ollama...", 50)

            result = subprocess.run(
                ["ollama", "pull", "qwen2.5:1.5b"],
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes
            )

            if result.returncode == 0:
                if progress_callback:
                    progress_callback("Model downloaded successfully!", 100)
                self.model_available = True
                self.available = True
                return True

            return False

        except Exception as e:
            print(f"Ollama install error: {e}")
            return False

    def _download_gguf_directly(self, progress_callback=None):
        """Download GGUF directly from Hugging Face"""
        try:
            # Use a smaller, well-tested GGUF file
            import requests

            # Hugging Face direct download URL for Qwen 1.5B GGUF
            url = "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"

            model_file = os.path.join(self.model_path, "qwen2.5-1.5b-instruct.gguf")

            if progress_callback:
                progress_callback("Downloading Qwen model (~1.1 GB)...", 10)

            # Download with progress
            response = requests.get(url, stream=True)
            total_size = int(response.headers.get('content-length', 0))
            block_size = 8192

            with open(model_file, 'wb') as f:
                downloaded = 0
                for data in response.iter_content(block_size):
                    f.write(data)
                    downloaded += len(data)
                    if progress_callback and total_size > 0:
                        progress = int((downloaded / total_size) * 80) + 10
                        progress_callback(f"Downloading... {progress}%", progress)

            if progress_callback:
                progress_callback("Model downloaded successfully!", 100)

            self.model_available = True
            self.available = True
            return True

        except Exception as e:
            print(f"Direct download error: {e}")
            return False

    def is_available(self) -> bool:
        return self.available

    def is_model_available(self) -> bool:
        return self.model_available

    def get_name(self) -> str:
        return f"🔒 Qwen ({self.model_name})"

    def get_models(self) -> List[str]:
        return [self.model_name] if self.model_available else ["qwen2.5:1.5b"]

    def get_install_guide(self) -> str:
        return "Click 'Install Model' to download Qwen automatically."

    def query(self, prompt: str, context: str = "", model: str = "") -> str:
        """Query Qwen - 100% offline"""
        if not self.available:
            return "⚠️ Please click 'Install Model' to set up Qwen."

        if not self.model_available:
            return "⚠️ Model not found. Click 'Install Model' to download."

        if not model:
            model = self.model_name

        full_prompt = self._build_prompt(prompt, context)

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "top_p": 0.9,
                        "max_tokens": 1000
                    }
                },
                timeout=120
            )
            if response.status_code == 200:
                return response.json().get('response', '').strip()
            else:
                return f"⚠️ Error: {response.status_code}"
        except requests.exceptions.Timeout:
            return "⚠️ Request timed out. The model might still be loading."
        except Exception as e:
            return f"⚠️ Error: {str(e)}"

    def _build_prompt(self, prompt: str, context: str) -> str:
        if context:
            return f"""You are a helpful data analyst assistant. Answer questions based on the provided context.

Context:
{context}

Question: {prompt}

Answer concisely and accurately based on the context provided. If you don't know the answer, say so."""
        return prompt


class AIBackendManager:
    def __init__(self):
        self.backends = {}
        self.active_backend_id = None
        self._init_backends()

    def _init_backends(self):
        self.backends = {
            "qwen": QwenBackend(),
        }

    def get_active_backend(self) -> Optional[AIBackend]:
        if self.active_backend_id and self.active_backend_id in self.backends:
            return self.backends[self.active_backend_id]
        return None

    def auto_select_backend(self) -> str:
        """Auto-select the best available backend"""
        qwen = self.backends.get("qwen")
        if qwen:
            self.active_backend_id = "qwen"
            return "qwen"
        return None