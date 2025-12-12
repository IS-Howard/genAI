"""
Utility functions for the Audio RAG system.
Includes logging setup, file operations, and helper functions.
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path


def setup_logger(log_file: str = 'audio_rag.log', log_level: int = logging.INFO) -> logging.Logger:
    """
    Set up logging configuration for the application.

    Args:
        log_file: Path to log file
        log_level: Logging level (default: INFO)

    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger('audio_rag')
    logger.setLevel(log_level)

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    simple_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )

    # File handler (detailed logging)
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)

    # Console handler (simple logging, only INFO and above)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)  # Only show warnings and errors in console
    console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)

    return logger


def get_file_size(file_path: str) -> int:
    """
    Get file size in bytes.

    Args:
        file_path: Path to file

    Returns:
        File size in bytes
    """
    try:
        return os.path.getsize(file_path)
    except OSError:
        return 0


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: File size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def format_timestamp(dt: datetime = None) -> str:
    """
    Format datetime as ISO string.

    Args:
        dt: Datetime object (defaults to now)

    Returns:
        ISO formatted timestamp
    """
    if dt is None:
        dt = datetime.now()
    return dt.isoformat()


def split_into_sentences(text: str) -> list:
    """
    Split text into sentences, handling both English and Chinese text.

    Args:
        text: Input text

    Returns:
        List of sentences
    """
    # Pattern to match sentence endings in English and Chinese
    # English: . ! ?
    # Chinese: 。！？
    sentence_pattern = r'[^.!?。！？]+[.!?。！？]+'

    sentences = re.findall(sentence_pattern, text)

    # If no sentences found (text might not have punctuation), return as single sentence
    if not sentences:
        return [text]

    return [s.strip() for s in sentences if s.strip()]


def chunk_text_with_overlap(text: str, chunk_size: int = 1000, overlap: int = 50) -> list:
    """
    Split text into chunks with overlap, attempting to preserve sentence boundaries.

    Args:
        text: Input text to chunk
        chunk_size: Target size of each chunk in characters
        overlap: Number of characters to overlap between chunks

    Returns:
        List of text chunks
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    sentences = split_into_sentences(text)

    current_chunk = ""
    for sentence in sentences:
        # If adding this sentence would exceed chunk_size
        if len(current_chunk) + len(sentence) > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())

            # Start new chunk with overlap from previous chunk
            if overlap > 0 and len(current_chunk) >= overlap:
                current_chunk = current_chunk[-overlap:] + sentence
            else:
                current_chunk = sentence
        else:
            current_chunk += sentence

    # Add the last chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing invalid characters.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename
    """
    # Remove invalid characters for filenames
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, '_', filename)

    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip('. ')

    return sanitized


def get_unique_filename(directory: str, base_name: str, extension: str = '') -> str:
    """
    Get a unique filename by appending numbers if file already exists.

    Args:
        directory: Directory path
        base_name: Base filename without extension
        extension: File extension (with or without dot)

    Returns:
        Unique filename
    """
    if not extension.startswith('.') and extension:
        extension = '.' + extension

    path = Path(directory)
    filename = base_name + extension
    full_path = path / filename

    counter = 1
    while full_path.exists():
        filename = f"{base_name}_{counter}{extension}"
        full_path = path / filename
        counter += 1

    return filename


def validate_audio_paths(paths: list, config) -> tuple:
    """
    Validate a list of audio file paths.

    Args:
        paths: List of file paths
        config: Config instance for validation

    Returns:
        Tuple of (valid_paths, invalid_paths)
    """
    valid_paths = []
    invalid_paths = []

    for path in paths:
        if config.validate_audio_file(path):
            valid_paths.append(path)
        else:
            invalid_paths.append(path)

    return valid_paths, invalid_paths


def print_banner(title: str, width: int = 60):
    """
    Print a formatted banner for CLI output.

    Args:
        title: Title text
        width: Banner width
    """
    print()
    print("=" * width)
    print(title.center(width))
    print("=" * width)
    print()


def print_success(message: str):
    """Print success message in green (if terminal supports it)."""
    print(f"✓ {message}")


def print_error(message: str):
    """Print error message in red (if terminal supports it)."""
    print(f"✗ {message}")


def print_info(message: str):
    """Print info message."""
    print(f"ℹ {message}")
