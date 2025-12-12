"""
Text file processing module for direct text document ingestion.
Handles .txt and .md files.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from tqdm import tqdm

from utils import get_file_size, chunk_text_with_overlap, format_timestamp
from config import Config


logger = logging.getLogger('audio_rag')


class TextProcessingError(Exception):
    """Base exception for text processing errors."""
    pass


class TextReadError(TextProcessingError):
    """Exception raised when text file reading fails."""
    pass


class TextProcessor:
    """Handles text file reading and chunking."""

    def __init__(self, config: Config):
        """
        Initialize the text processor.

        Args:
            config: Configuration instance
        """
        self.config = config

    def process_text_file(self, file_path: str) -> dict:
        """
        Process a single text file.

        Args:
            file_path: Path to the text file

        Returns:
            Dictionary containing:
                - filename: Original filename
                - content: Text content
                - file_size: File size in bytes
                - timestamp: Processing timestamp
                - format: File format (txt, md)
                - source_type: 'text' (to distinguish from audio)

        Raises:
            TextReadError: If file reading fails
        """
        path = Path(file_path)

        logger.info(f"Processing text file: {path.name}")

        try:
            # Read file with UTF-8 encoding
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if not content or not content.strip():
                raise TextReadError(f"Empty or blank file: {path.name}")

            logger.info(f"Successfully read {path.name} ({len(content)} characters)")

        except UnicodeDecodeError as e:
            error_msg = f"Failed to read {path.name}: Invalid UTF-8 encoding"
            logger.error(error_msg)
            raise TextReadError(error_msg) from e

        except Exception as e:
            error_msg = f"Failed to read text file {path.name}: {str(e)}"
            logger.error(error_msg)
            raise TextReadError(error_msg) from e

        # Build result dictionary
        result = {
            'filename': path.name,
            'original_path': str(path.absolute()),
            'content': content,
            'file_size': get_file_size(file_path),
            'timestamp': format_timestamp(),
            'format': path.suffix.lower().lstrip('.'),
            'source_type': 'text'  # Distinguish from audio
        }

        return result

    def batch_process(
        self,
        file_paths: list,
        progress_callback: Optional[Callable] = None
    ) -> tuple:
        """
        Process multiple text files with progress tracking.

        Args:
            file_paths: List of paths to text files
            progress_callback: Optional callback function for progress updates

        Returns:
            Tuple of (successful_results, failed_files)
                - successful_results: List of processing dictionaries
                - failed_files: List of tuples (filename, error_message)
        """
        logger.info(f"Starting batch processing of {len(file_paths)} text file(s)")

        successful_results = []
        failed_files = []

        # Use tqdm for progress bar
        with tqdm(total=len(file_paths), desc="Processing text files", unit="file") as pbar:
            for file_path in file_paths:
                try:
                    result = self.process_text_file(file_path)
                    successful_results.append(result)

                    if progress_callback:
                        progress_callback(result)

                except TextReadError as e:
                    filename = Path(file_path).name
                    error_msg = str(e)
                    failed_files.append((filename, error_msg))
                    logger.warning(f"Skipping {filename}: {error_msg}")

                except Exception as e:
                    filename = Path(file_path).name
                    error_msg = f"Unexpected error: {str(e)}"
                    failed_files.append((filename, error_msg))
                    logger.error(f"Unexpected error processing {filename}: {str(e)}", exc_info=True)

                finally:
                    pbar.update(1)

        logger.info(
            f"Batch processing complete: "
            f"{len(successful_results)} successful, "
            f"{len(failed_files)} failed"
        )

        return successful_results, failed_files

    def chunk_text(
        self,
        text_data: dict,
        chunk_size: Optional[int] = None,
        overlap: Optional[int] = None
    ) -> list:
        """
        Split text content into chunks for better retrieval.

        Args:
            text_data: Text dictionary from process_text_file()
            chunk_size: Size of each chunk in characters (default: from config)
            overlap: Overlap between chunks in characters (default: from config)

        Returns:
            List of dictionaries, each containing:
                - chunk_text: The text chunk
                - chunk_index: Index of this chunk
                - total_chunks: Total number of chunks
                - All metadata from original text data
        """
        if chunk_size is None:
            chunk_size = self.config.CHUNK_SIZE
        if overlap is None:
            overlap = self.config.CHUNK_OVERLAP

        content = text_data['content']
        chunks = chunk_text_with_overlap(content, chunk_size, overlap)

        logger.info(
            f"Split text file {text_data['filename']} "
            f"into {len(chunks)} chunks"
        )

        # Create chunk dictionaries with metadata
        chunk_list = []
        for idx, chunk_text in enumerate(chunks):
            chunk_data = {
                'chunk_text': chunk_text,
                'chunk_index': idx,
                'total_chunks': len(chunks),
                # Include all original metadata
                'filename': text_data['filename'],
                'original_path': text_data['original_path'],
                'file_size': text_data['file_size'],
                'processing_date': text_data['timestamp'],
                'file_format': text_data['format'],
                'source_type': text_data['source_type']
            }
            chunk_list.append(chunk_data)

        return chunk_list

    def process_files(self, file_paths: list) -> tuple:
        """
        Complete pipeline: read and chunk multiple text files.

        Args:
            file_paths: List of paths to text files

        Returns:
            Tuple of (chunk_list, failed_files)
                - chunk_list: List of all chunks from all files
                - failed_files: List of tuples (filename, error_message)
        """
        logger.info(f"Processing {len(file_paths)} text file(s)")

        # Process all files
        results, failed_files = self.batch_process(file_paths)

        # Chunk all successful results
        all_chunks = []
        for result in results:
            chunks = self.chunk_text(result)
            all_chunks.extend(chunks)

        logger.info(f"Generated {len(all_chunks)} total chunks from {len(results)} file(s)")

        return all_chunks, failed_files
