"""
Configuration management for Audio RAG system.
Handles API keys, paths, and model settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv


class Config:
    """Centralized configuration for the Audio RAG system."""

    # Model configurations
    GEMINI_TRANSCRIPTION_MODEL = "gemini-2.5-flash"
    GEMINI_GENERATION_MODEL = "gemini-2.5-flash"
    EMBEDDING_MODEL = "models/text-embedding-004"

    # Chunking configuration
    CHUNK_SIZE = 1000  # Characters per chunk
    CHUNK_OVERLAP = 50  # Character overlap between chunks

    # Database configuration
    DB_COLLECTION_NAME = "audio_transcriptions"

    def __init__(self, base_dir: str = None):
        """
        Initialize configuration.

        Args:
            base_dir: Base directory for the project. Defaults to audio_rag/ directory.
        """
        if base_dir is None:
            # Default to audio_rag directory
            base_dir = Path(__file__).parent
        else:
            base_dir = Path(base_dir)

        self.base_dir = base_dir
        self._api_key = None

        # Load environment variables from .env file if it exists
        env_path = base_dir.parent / '.env'
        if env_path.exists():
            load_dotenv(env_path)

    def load_api_key(self) -> str:
        """
        Load Google API key from environment variables.

        Returns:
            API key string

        Raises:
            ValueError: If API key is not found
        """
        if self._api_key:
            return self._api_key

        # Try to load from environment variable
        api_key = os.getenv('GOOGLE_API_KEY')

        if not api_key:
            raise ValueError(
                "Google API key not found!\n"
                "Please set the GOOGLE_API_KEY environment variable or create a .env file.\n"
                "See .env.example for the template."
            )

        # Basic validation
        if not api_key.startswith('AIzaSy'):
            raise ValueError(
                "Invalid Google API key format. "
                "Google API keys typically start with 'AIzaSy'."
            )

        self._api_key = api_key
        return self._api_key

    def get_chromadb_path(self) -> str:
        """
        Get the path for ChromaDB persistent storage.
        Creates directory if it doesn't exist.

        Returns:
            Path to ChromaDB directory
        """
        chroma_path = self.base_dir / 'data' / 'chromadb'
        chroma_path.mkdir(parents=True, exist_ok=True)
        return str(chroma_path)

    def get_transcription_export_path(self) -> str:
        """
        Get the path for exported transcriptions.
        Creates directory if it doesn't exist.

        Returns:
            Path to transcriptions directory
        """
        export_path = self.base_dir / 'data' / 'transcriptions'
        export_path.mkdir(parents=True, exist_ok=True)
        return str(export_path)

    def validate_audio_file(self, file_path: str) -> bool:
        """
        Validate that a file exists and is a supported audio format.

        Args:
            file_path: Path to audio file

        Returns:
            True if valid, False otherwise
        """
        path = Path(file_path)

        # Check if file exists
        if not path.exists():
            return False

        # Check if it's a file (not directory)
        if not path.is_file():
            return False

        # Check file extension (common audio formats)
        supported_extensions = {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma'}
        if path.suffix.lower() not in supported_extensions:
            return False

        return True

    def get_supported_audio_formats(self) -> list:
        """
        Get list of supported audio formats.

        Returns:
            List of supported file extensions
        """
        return ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma']

    def validate_text_file(self, file_path: str) -> bool:
        """
        Validate that a file exists and is a supported text format.

        Args:
            file_path: Path to text file

        Returns:
            True if valid, False otherwise
        """
        path = Path(file_path)

        # Check if file exists
        if not path.exists():
            return False

        # Check if it's a file (not directory)
        if not path.is_file():
            return False

        # Check file extension (supported text formats)
        supported_extensions = {'.txt', '.md'}
        if path.suffix.lower() not in supported_extensions:
            return False

        return True

    def get_supported_text_formats(self) -> list:
        """
        Get list of supported text formats.

        Returns:
            List of supported file extensions
        """
        return ['.txt', '.md']

    def get_file_type(self, file_path: str) -> str:
        """
        Determine the type of file (audio or text).

        Args:
            file_path: Path to file

        Returns:
            'audio', 'text', or 'unknown'
        """
        path = Path(file_path)
        extension = path.suffix.lower()

        if extension in self.get_supported_audio_formats():
            return 'audio'
        elif extension in self.get_supported_text_formats():
            return 'text'
        else:
            return 'unknown'

    def validate_file(self, file_path: str) -> tuple:
        """
        Validate a file and determine its type.

        Args:
            file_path: Path to file

        Returns:
            Tuple of (is_valid, file_type)
            - is_valid: bool
            - file_type: 'audio', 'text', or 'unknown'
        """
        file_type = self.get_file_type(file_path)

        if file_type == 'audio':
            return (self.validate_audio_file(file_path), 'audio')
        elif file_type == 'text':
            return (self.validate_text_file(file_path), 'text')
        else:
            return (False, 'unknown')
