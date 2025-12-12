"""
Export management for audio transcriptions.
Handles exporting transcriptions to various formats.
"""

import json
import logging
from pathlib import Path
from datetime import datetime

from embeddings_manager import AudioRAGDatabase
from utils import sanitize_filename, get_unique_filename, format_file_size


logger = logging.getLogger('audio_rag')


class ExportManager:
    """Handles transcription export functionality."""

    def __init__(self, database: AudioRAGDatabase, export_dir: str):
        """
        Initialize the export manager.

        Args:
            database: AudioRAGDatabase instance
            export_dir: Directory for exported transcriptions
        """
        self.database = database
        self.export_dir = Path(export_dir)

        # Ensure export directory exists
        self.export_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Export manager initialized with directory: {export_dir}")

    def export_single(
        self,
        filename: str,
        format: str = 'txt',
        include_metadata: bool = False
    ) -> str:
        """
        Export a single file (audio or text) to file.

        Args:
            filename: Name of the file to export
            format: Export format ('txt' or 'json')
            include_metadata: Include metadata header in text export

        Returns:
            Path to exported file

        Raises:
            ValueError: If format is invalid or file not found
        """
        logger.info(f"Exporting content for: {filename} (format: {format})")

        # Check if file exists in database
        if not self.database.check_file_exists(filename):
            raise ValueError(f"File '{filename}' not found in database")

        # Get complete transcription
        transcription = self.database.get_transcription_by_file(filename)

        if not transcription:
            raise ValueError(f"No transcription found for '{filename}'")

        # Get file info for metadata
        all_files = self.database.get_all_files()
        file_info = next((f for f in all_files if f['filename'] == filename), None)

        # Prepare export filename
        base_name = Path(filename).stem
        safe_name = sanitize_filename(base_name)

        if format == 'txt':
            export_path = self._export_text(
                transcription,
                safe_name,
                file_info,
                include_metadata
            )
        elif format == 'json':
            export_path = self._export_json(
                transcription,
                safe_name,
                file_info
            )
        else:
            raise ValueError(f"Invalid format: {format}. Use 'txt' or 'json'")

        logger.info(f"Exported to: {export_path}")

        return str(export_path)

    def _export_text(
        self,
        transcription: str,
        base_name: str,
        file_info: dict,
        include_metadata: bool
    ) -> Path:
        """
        Export transcription as plain text file.

        Args:
            transcription: Transcription text
            base_name: Base filename (without extension)
            file_info: File metadata dictionary
            include_metadata: Include metadata header

        Returns:
            Path to exported file
        """
        # Get unique filename
        filename = get_unique_filename(
            directory=str(self.export_dir),
            base_name=base_name,
            extension='txt'
        )

        export_path = self.export_dir / filename

        # Build content
        content = []

        if include_metadata and file_info:
            content.append("=" * 60)
            content.append("文件內容 DOCUMENT CONTENT")
            content.append("=" * 60)
            content.append(f"檔案名稱 Filename: {file_info['filename']}")
            content.append(f"來源類型 Source Type: {file_info.get('source_type', 'unknown')}")
            content.append(f"處理日期 Processing Date: {file_info['processing_date']}")
            content.append(f"檔案大小 File Size: {format_file_size(file_info['file_size'])}")
            content.append(f"格式 Format: {file_info['file_format']}")
            content.append(f"片段數量 Total Chunks: {file_info['total_chunks']}")
            content.append("=" * 60)
            content.append("")

        content.append(transcription)

        # Write to file
        with open(export_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))

        return export_path

    def _export_json(
        self,
        transcription: str,
        base_name: str,
        file_info: dict
    ) -> Path:
        """
        Export transcription as JSON with full metadata.

        Args:
            transcription: Transcription text
            base_name: Base filename (without extension)
            file_info: File metadata dictionary

        Returns:
            Path to exported file
        """
        # Get unique filename
        filename = get_unique_filename(
            directory=str(self.export_dir),
            base_name=base_name,
            extension='json'
        )

        export_path = self.export_dir / filename

        # Build JSON structure
        data = {
            'transcription': transcription,
            'metadata': file_info,
            'export_date': datetime.now().isoformat(),
            'export_format': 'json'
        }

        # Write to file
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return export_path

    def export_all(
        self,
        format: str = 'txt',
        include_metadata: bool = True
    ) -> list:
        """
        Export all transcriptions in the database.

        Args:
            format: Export format ('txt' or 'json')
            include_metadata: Include metadata header in text exports

        Returns:
            List of paths to exported files
        """
        logger.info(f"Exporting all transcriptions (format: {format})")

        all_files = self.database.get_all_files()

        if not all_files:
            logger.warning("No files found in database")
            return []

        exported_paths = []

        for file_info in all_files:
            try:
                export_path = self.export_single(
                    filename=file_info['filename'],
                    format=format,
                    include_metadata=include_metadata
                )
                exported_paths.append(export_path)

            except Exception as e:
                logger.error(f"Failed to export {file_info['filename']}: {str(e)}")
                continue

        logger.info(f"Exported {len(exported_paths)} out of {len(all_files)} files")

        return exported_paths

    def export_with_chunks(self, filename: str) -> str:
        """
        Export content with individual chunk information.

        Args:
            filename: Name of the file to export

        Returns:
            Path to exported file
        """
        logger.info(f"Exporting chunked content for: {filename}")

        # Check if file exists
        if not self.database.check_file_exists(filename):
            raise ValueError(f"File '{filename}' not found in database")

        # Get all chunks for this file
        results = self.database.collection.get(
            where={"filename": filename}
        )

        if not results['documents']:
            raise ValueError(f"No transcription found for '{filename}'")

        # Sort by chunk index
        chunks_data = list(zip(
            results['documents'],
            results['metadatas']
        ))
        chunks_data.sort(key=lambda x: x[1]['chunk_index'])

        # Prepare export
        base_name = Path(filename).stem
        safe_name = sanitize_filename(base_name) + "_chunks"

        filename_out = get_unique_filename(
            directory=str(self.export_dir),
            base_name=safe_name,
            extension='json'
        )

        export_path = self.export_dir / filename_out

        # Build JSON structure with chunks
        data = {
            'filename': filename,
            'total_chunks': len(chunks_data),
            'chunks': [],
            'metadata': chunks_data[0][1] if chunks_data else {},
            'export_date': datetime.now().isoformat()
        }

        for chunk_text, chunk_meta in chunks_data:
            data['chunks'].append({
                'index': chunk_meta['chunk_index'],
                'text': chunk_text
            })

        # Write to file
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Exported chunked transcription to: {export_path}")

        return str(export_path)

    def list_exports(self) -> list:
        """
        List all exported transcription files.

        Returns:
            List of export file paths
        """
        export_files = []

        for ext in ['txt', 'json']:
            export_files.extend(list(self.export_dir.glob(f"*.{ext}")))

        # Sort by modification time (most recent first)
        export_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        return [str(f) for f in export_files]

    def delete_export(self, export_path: str) -> bool:
        """
        Delete an exported file.

        Args:
            export_path: Path to export file

        Returns:
            True if deleted, False otherwise
        """
        try:
            path = Path(export_path)
            if path.exists() and path.parent == self.export_dir:
                path.unlink()
                logger.info(f"Deleted export file: {export_path}")
                return True
            else:
                logger.warning(f"Export file not found or invalid path: {export_path}")
                return False

        except Exception as e:
            logger.error(f"Failed to delete export file: {str(e)}")
            return False
