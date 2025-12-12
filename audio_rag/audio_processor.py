"""
Audio processing module for transcription and chunking.
Handles audio file transcription using Google GenAI and text chunking.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from tqdm import tqdm

from google import genai

from utils import get_file_size, chunk_text_with_overlap, format_timestamp
from config import Config


logger = logging.getLogger('audio_rag')


class AudioProcessingError(Exception):
    """Base exception for audio processing errors."""
    pass


class AudioUploadError(AudioProcessingError):
    """Exception raised when audio upload fails."""
    pass


class TranscriptionError(AudioProcessingError):
    """Exception raised when transcription fails."""
    pass


class AudioProcessor:
    """Handles audio file transcription and text chunking."""

    def __init__(self, client: genai.Client, config: Config):
        """
        Initialize the audio processor.

        Args:
            client: Google GenAI client instance
            config: Configuration instance
        """
        self.client = client
        self.config = config
        self.transcription_cache = {}  # In-memory cache for current session

    def transcribe_audio(self, audio_path: str) -> dict:
        """
        Transcribe a single audio file.

        Args:
            audio_path: Path to the audio file

        Returns:
            Dictionary containing:
                - filename: Original filename
                - transcription: Transcribed text
                - file_size: File size in bytes
                - timestamp: Processing timestamp
                - duration: Audio duration (if available)
                - format: Audio format

        Raises:
            AudioUploadError: If file upload fails
            TranscriptionError: If transcription fails
        """
        path = Path(audio_path)

        # Check if already in cache
        if audio_path in self.transcription_cache:
            logger.info(f"Using cached transcription for {path.name}")
            return self.transcription_cache[audio_path]

        logger.info(f"Transcribing audio file: {path.name}")

        try:
            # Upload audio file to Google GenAI
            logger.debug(f"Uploading file: {audio_path}")
            myfile = self.client.files.upload(file=audio_path)

        except Exception as e:
            error_msg = f"Failed to upload audio file {path.name}: {str(e)}"
            logger.error(error_msg)
            raise AudioUploadError(error_msg) from e

        try:
            # Generate transcription using Gemini model
            # Using Chinese prompt as in the original tutorial
            prompt = '產生音訊資料的轉錄稿'

            logger.debug(f"Generating transcription with model: {self.config.GEMINI_TRANSCRIPTION_MODEL}")
            response = self.client.models.generate_content(
                model=self.config.GEMINI_TRANSCRIPTION_MODEL,
                contents=[prompt, myfile]
            )

            transcription = response.text

            if not transcription or not transcription.strip():
                raise TranscriptionError(f"Empty transcription received for {path.name}")

            logger.info(f"Successfully transcribed {path.name} ({len(transcription)} characters)")

        except Exception as e:
            error_msg = f"Failed to transcribe audio file {path.name}: {str(e)}"
            logger.error(error_msg)
            raise TranscriptionError(error_msg) from e

        # Build result dictionary
        result = {
            'filename': path.name,
            'original_path': str(path.absolute()),
            'transcription': transcription,
            'file_size': get_file_size(audio_path),
            'timestamp': format_timestamp(),
            'format': path.suffix.lower().lstrip('.'),
            'transcription_model': self.config.GEMINI_TRANSCRIPTION_MODEL
        }

        # Cache the result
        self.transcription_cache[audio_path] = result

        return result

    def batch_transcribe(
        self,
        audio_paths: list,
        progress_callback: Optional[Callable] = None
    ) -> tuple:
        """
        Transcribe multiple audio files with progress tracking.

        Args:
            audio_paths: List of paths to audio files
            progress_callback: Optional callback function for progress updates

        Returns:
            Tuple of (successful_transcriptions, failed_files)
                - successful_transcriptions: List of transcription dictionaries
                - failed_files: List of tuples (filename, error_message)
        """
        logger.info(f"Starting batch transcription of {len(audio_paths)} files")

        successful_transcriptions = []
        failed_files = []

        # Use tqdm for progress bar
        with tqdm(total=len(audio_paths), desc="Transcribing audio files", unit="file") as pbar:
            for audio_path in audio_paths:
                try:
                    result = self.transcribe_audio(audio_path)
                    successful_transcriptions.append(result)

                    if progress_callback:
                        progress_callback(result)

                except (AudioUploadError, TranscriptionError) as e:
                    filename = Path(audio_path).name
                    error_msg = str(e)
                    failed_files.append((filename, error_msg))
                    logger.warning(f"Skipping {filename}: {error_msg}")

                except Exception as e:
                    filename = Path(audio_path).name
                    error_msg = f"Unexpected error: {str(e)}"
                    failed_files.append((filename, error_msg))
                    logger.error(f"Unexpected error processing {filename}: {str(e)}", exc_info=True)

                finally:
                    pbar.update(1)

        logger.info(
            f"Batch transcription complete: "
            f"{len(successful_transcriptions)} successful, "
            f"{len(failed_files)} failed"
        )

        return successful_transcriptions, failed_files

    def chunk_transcription(
        self,
        transcription_data: dict,
        chunk_size: Optional[int] = None,
        overlap: Optional[int] = None
    ) -> list:
        """
        Split a transcription into chunks for better retrieval.

        Args:
            transcription_data: Transcription dictionary from transcribe_audio()
            chunk_size: Size of each chunk in characters (default: from config)
            overlap: Overlap between chunks in characters (default: from config)

        Returns:
            List of dictionaries, each containing:
                - chunk_text: The text chunk
                - chunk_index: Index of this chunk
                - total_chunks: Total number of chunks
                - All metadata from original transcription
        """
        if chunk_size is None:
            chunk_size = self.config.CHUNK_SIZE
        if overlap is None:
            overlap = self.config.CHUNK_OVERLAP

        transcription = transcription_data['transcription']
        chunks = chunk_text_with_overlap(transcription, chunk_size, overlap)

        logger.info(
            f"Split transcription of {transcription_data['filename']} "
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
                'audio_filename': transcription_data['filename'],
                'original_path': transcription_data['original_path'],
                'file_size': transcription_data['file_size'],
                'transcription_date': transcription_data['timestamp'],
                'audio_format': transcription_data['format'],
                'transcription_model': transcription_data['transcription_model']
            }
            chunk_list.append(chunk_data)

        return chunk_list

    def process_audio_files(self, audio_paths: list) -> tuple:
        """
        Complete pipeline: transcribe and chunk multiple audio files.

        Args:
            audio_paths: List of paths to audio files

        Returns:
            Tuple of (chunk_list, failed_files)
                - chunk_list: List of all chunks from all transcriptions
                - failed_files: List of tuples (filename, error_message)
        """
        logger.info(f"Processing {len(audio_paths)} audio files")

        # Transcribe all files
        transcriptions, failed_files = self.batch_transcribe(audio_paths)

        # Chunk all successful transcriptions
        all_chunks = []
        for transcription in transcriptions:
            chunks = self.chunk_transcription(transcription)
            all_chunks.extend(chunks)

        logger.info(f"Generated {len(all_chunks)} total chunks from {len(transcriptions)} files")

        return all_chunks, failed_files

    def clear_cache(self):
        """Clear the transcription cache."""
        self.transcription_cache.clear()
        logger.debug("Transcription cache cleared")
