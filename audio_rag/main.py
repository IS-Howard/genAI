#!/usr/bin/env python3
"""
Audio RAG Query System - Main CLI Application
Processes audio files into a searchable knowledge base with RAG.
"""

import sys
import argparse
import logging
from pathlib import Path

from google import genai

from config import Config
from utils import (
    setup_logger,
    print_banner,
    print_success,
    print_error,
    print_info,
    validate_audio_paths,
    format_file_size
)
from audio_processor import AudioProcessor
from text_processor import TextProcessor
from embeddings_manager import AudioRAGDatabase
from qa_engine import QAEngine
from export_manager import ExportManager


class AudioRAGCLI:
    """Interactive CLI application for Audio RAG system."""

    def __init__(self):
        """Initialize the CLI application."""
        # Setup logging
        self.logger = setup_logger()

        # Load configuration
        try:
            self.config = Config()
            api_key = self.config.load_api_key()
        except ValueError as e:
            print_error(str(e))
            sys.exit(1)

        # Initialize Google GenAI client
        self.client = genai.Client(api_key=api_key)

        # Initialize components
        self.audio_processor = AudioProcessor(self.client, self.config)
        self.text_processor = TextProcessor(self.config)
        self.database = AudioRAGDatabase(
            persist_directory=self.config.get_chromadb_path(),
            client=self.client,
            config=self.config
        )
        self.qa_engine = QAEngine(self.database, self.client, self.config)
        self.export_manager = ExportManager(
            database=self.database,
            export_dir=self.config.get_transcription_export_path()
        )

        # Initialize database collection (will be done when needed)
        # Removed automatic initialization to support multiple collections

        self.logger.info("Audio RAG CLI initialized successfully")

    def cmd_add(self, file_paths: list, skip_existing: bool = False, collection: str = None):
        """
        Add files (audio or text) to the database.

        Args:
            file_paths: List of paths to files
            skip_existing: Skip files that are already in database
            collection: Collection name (optional)
        """
        print_banner("Adding Files to Database")

        # Initialize collection
        if collection:
            print_info(f"Using collection: {collection}")
            self.database.initialize_collection(collection)
        else:
            # Use default collection
            self.database.initialize_collection()

        # Separate files by type
        audio_files = []
        text_files = []
        invalid_files = []

        for path in file_paths:
            is_valid, file_type = self.config.validate_file(path)

            if is_valid:
                if file_type == 'audio':
                    audio_files.append(path)
                elif file_type == 'text':
                    text_files.append(path)
            else:
                invalid_files.append(path)

        # Report invalid files
        if invalid_files:
            print_error(f"Invalid files (skipping {len(invalid_files)}):")
            for path in invalid_files:
                print(f"  - {path}")
            print()

        if not audio_files and not text_files:
            print_error("No valid files to process")
            return

        # Check for existing files if skip_existing is True
        if skip_existing:
            audio_files = [p for p in audio_files if not self.database.check_file_exists(Path(p).name)]
            text_files = [p for p in text_files if not self.database.check_file_exists(Path(p).name)]

            if not audio_files and not text_files:
                print_info("All files already in database")
                return

        print_info(f"Processing {len(audio_files)} audio file(s) and {len(text_files)} text file(s)...")
        print()

        all_chunks = []
        all_failed = []

        # Process audio files
        if audio_files:
            print_info("Processing audio files...")
            chunks, failed = self.audio_processor.process_audio_files(audio_files)
            all_chunks.extend(chunks)
            all_failed.extend(failed)

        # Process text files
        if text_files:
            print_info("Processing text files...")
            chunks, failed = self.text_processor.process_files(text_files)
            all_chunks.extend(chunks)
            all_failed.extend(failed)

        # Add to database
        if all_chunks:
            num_added = self.database.add_transcriptions(all_chunks)
            print()
            print_success(f"Successfully added {num_added} chunks from {len(file_paths) - len(all_failed) - len(invalid_files)} file(s)")

        # Report failed files
        if all_failed:
            print()
            print_error(f"Failed to process {len(all_failed)} file(s):")
            for filename, error in all_failed:
                print(f"  - {filename}: {error}")

        print()

    def cmd_query(self, filter_file: str = None, top_k: int = 5, collection: str = None, all_collections: bool = False):
        """
        Interactive Q&A mode.

        Args:
            filter_file: Optional filename to filter searches
            top_k: Number of results to retrieve
            collection: Collection name(s) - comma-separated for multiple (optional)
            all_collections: Query all available collections
        """
        print_banner("Interactive Query Mode")

        # Parse collections
        collections_list = None
        if all_collections:
            # Get all available collections
            collections_list = self.database.list_collections()
            if not collections_list:
                print_error("No collections found in database!")
                return
            print_info(f"Querying ALL collections: {', '.join(collections_list)}")
        elif collection:
            # Parse comma-separated collections
            collections_list = [c.strip() for c in collection.split(',')]
            if len(collections_list) > 1:
                print_info(f"Querying {len(collections_list)} collections: {', '.join(collections_list)}")
            else:
                print_info(f"Using collection: {collections_list[0]}")
                # Initialize single collection
                self.database.initialize_collection(collections_list[0])
        else:
            # Use default collection
            self.database.initialize_collection()

        # Check if database has content
        if collections_list and len(collections_list) == 1:
            stats = self.database.get_stats()
            if stats['total_chunks'] == 0:
                print_error("Database is empty! Please add files first using 'add' command.")
                return
            print_info(f"Database contains {stats['total_files']} file(s) with {stats['total_chunks']} chunk(s)")
        elif collections_list and len(collections_list) > 1:
            print_info(f"Searching across {len(collections_list)} collections")
        else:
            stats = self.database.get_stats()
            if stats['total_chunks'] == 0:
                print_error("Database is empty! Please add files first using 'add' command.")
                return
            print_info(f"Database contains {stats['total_files']} file(s) with {stats['total_chunks']} chunk(s)")

        if filter_file:
            print_info(f"Filtering queries to file: {filter_file}")

        print_info("Enter your questions below. Type 'exit' or 'quit' to end.\n")

        while True:
            try:
                # Get user input
                query = input("Question: ").strip()

                if not query:
                    continue

                # Check for exit commands
                if query.lower() in ['exit', 'quit', 'q']:
                    print_info("Exiting query mode...")
                    break

                # Special commands
                if query.lower() == 'clear':
                    self.qa_engine.clear_history()
                    print_success("Conversation history cleared")
                    continue

                if query.lower() == 'history':
                    history = self.qa_engine.get_history()
                    if history:
                        print("\nConversation History:")
                        for i, exchange in enumerate(history, 1):
                            print(f"\n{i}. Q: {exchange['query']}")
                            print(f"   A: {exchange['answer'][:100]}...")
                    else:
                        print_info("No conversation history")
                    continue

                # Process question
                print()
                result = self.qa_engine.answer_question(
                    query=query,
                    n_results=top_k,
                    filename_filter=filter_file,
                    collections=collections_list
                )

                # Display formatted answer
                formatted_output = self.qa_engine.format_answer_with_sources(result)
                print(formatted_output)
                print()

            except KeyboardInterrupt:
                print("\n")
                print_info("Interrupted by user. Exiting query mode...")
                break

            except Exception as e:
                print_error(f"Error processing query: {str(e)}")
                self.logger.error(f"Query error: {str(e)}", exc_info=True)
                continue

    def cmd_export(self, filename: str = None, format: str = 'txt', include_metadata: bool = True):
        """
        Export transcriptions.

        Args:
            filename: Specific filename to export (None for all)
            format: Export format ('txt' or 'json')
            include_metadata: Include metadata in exports
        """
        print_banner("Exporting Transcriptions")

        try:
            if filename:
                # Export single file
                export_path = self.export_manager.export_single(
                    filename=filename,
                    format=format,
                    include_metadata=include_metadata
                )
                print_success(f"Exported to: {export_path}")

            else:
                # Export all files
                export_paths = self.export_manager.export_all(
                    format=format,
                    include_metadata=include_metadata
                )

                if export_paths:
                    print_success(f"Exported {len(export_paths)} file(s) to:")
                    for path in export_paths:
                        print(f"  - {path}")
                else:
                    print_info("No files to export")

        except Exception as e:
            print_error(f"Export failed: {str(e)}")
            self.logger.error(f"Export error: {str(e)}", exc_info=True)

        print()

    def cmd_list_files(self, collection: str = None):
        """
        List all indexed files.

        Args:
            collection: Collection name (optional)
        """
        print_banner("Indexed Files")

        # Initialize collection
        if collection:
            print_info(f"Collection: {collection}\n")
            self.database.initialize_collection(collection)
        else:
            self.database.initialize_collection()

        all_files = self.database.get_all_files()

        if not all_files:
            print_info("No files in database")
            return

        print(f"Total: {len(all_files)} file(s)\n")

        for idx, file_info in enumerate(all_files, 1):
            source_icon = "🎵" if file_info['source_type'] == 'audio' else "📄"
            print(f"{idx}. {source_icon} {file_info['filename']}")
            print(f"   Type: {file_info['source_type']}")
            print(f"   Chunks: {file_info['total_chunks']}")
            print(f"   Size: {format_file_size(file_info['file_size'])}")
            print(f"   Format: {file_info['file_format']}")
            print(f"   Added: {file_info['processing_date']}")
            print()

    def cmd_collections(self):
        """List all available collections."""
        print_banner("Collections")

        collections = self.database.list_collections()

        if not collections:
            print_info("No collections found")
            return

        print(f"Total: {len(collections)} collection(s)\n")

        for idx, collection_name in enumerate(collections, 1):
            info = self.database.get_collection_info(collection_name)
            if info['exists']:
                print(f"{idx}. {collection_name}")
                print(f"   Files: {info['total_files']}")
                print(f"   Chunks: {info['total_chunks']}")
                print()
            else:
                print(f"{idx}. {collection_name} (error accessing)")
                print()

    def cmd_delete(self, filename: str):
        """
        Remove audio file from database.

        Args:
            filename: Name of the audio file to remove
        """
        print_banner("Delete Audio File")

        # Confirm deletion
        response = input(f"Are you sure you want to delete '{filename}'? (yes/no): ").strip().lower()

        if response not in ['yes', 'y']:
            print_info("Deletion cancelled")
            return

        try:
            deleted_count = self.database.delete_audio_file(filename)

            if deleted_count > 0:
                print_success(f"Deleted {deleted_count} chunk(s) for '{filename}'")
            else:
                print_error(f"File '{filename}' not found in database")

        except Exception as e:
            print_error(f"Deletion failed: {str(e)}")
            self.logger.error(f"Delete error: {str(e)}", exc_info=True)

        print()

    def cmd_stats(self):
        """Show database statistics."""
        print_banner("Database Statistics")

        stats = self.database.get_stats()

        print(f"Total Audio Files: {stats['total_files']}")
        print(f"Total Chunks: {stats['total_chunks']}")
        print(f"ChromaDB Path: {self.config.get_chromadb_path()}")
        print(f"Export Path: {self.config.get_transcription_export_path()}")
        print()

        if stats['files']:
            print("Recent Files:")
            for file_info in stats['files'][:5]:  # Show 5 most recent
                print(f"  - {file_info['filename']} ({file_info['total_chunks']} chunks)")
        print()

    def run_interactive_menu(self):
        """Run interactive menu mode."""
        print_banner("Audio RAG Query System")

        while True:
            print("\nCommands:")
            print("  1. Add files (audio/text)")
            print("  2. Query (Q&A)")
            print("  3. Export transcriptions")
            print("  4. List files")
            print("  5. List collections")
            print("  6. Database statistics")
            print("  7. Delete file")
            print("  8. Exit")
            print()

            choice = input("Select option (1-8): ").strip()

            if choice == '1':
                paths_input = input("Enter file paths (space-separated): ").strip()
                if paths_input:
                    paths = paths_input.split()
                    self.cmd_add(paths)

            elif choice == '2':
                self.cmd_query()

            elif choice == '3':
                filename = input("Enter filename (or press Enter for all): ").strip()
                filename = filename if filename else None
                self.cmd_export(filename=filename)

            elif choice == '4':
                self.cmd_list_files()

            elif choice == '5':
                self.cmd_collections()

            elif choice == '6':
                self.cmd_stats()

            elif choice == '7':
                filename = input("Enter filename to delete: ").strip()
                if filename:
                    self.cmd_delete(filename)

            elif choice == '8':
                print_info("Goodbye!")
                break

            else:
                print_error("Invalid option. Please select 1-8.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Audio RAG Query System - Process audio/text files into a searchable knowledge base',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add audio and text files
  python main.py add audio1.mp3 document.txt notes.md

  # Add files to specific collection
  python main.py add meeting1.mp3 --collection work_meetings

  # Interactive query mode
  python main.py query

  # Query specific collection
  python main.py query --collection work_meetings

  # Query multiple collections
  python main.py query --collection work,meetings,research

  # Query ALL collections
  python main.py query --all-collections

  # List all collections
  python main.py collections

  # Export all transcriptions
  python main.py export --all

  # List indexed files
  python main.py list

  # Interactive menu
  python main.py
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Add command
    add_parser = subparsers.add_parser('add', help='Add files (audio/text) to database')
    add_parser.add_argument('files', nargs='+', help='File paths (.mp3, .wav, .txt, .md, etc.)')
    add_parser.add_argument('--skip-existing', action='store_true',
                           help='Skip files already in database')
    add_parser.add_argument('--collection', type=str,
                           help='Collection name (optional, default: audio_transcriptions)')

    # Query command
    query_parser = subparsers.add_parser('query', help='Interactive Q&A mode')
    query_parser.add_argument('--filter', dest='filter_file',
                             help='Filter to specific file')
    query_parser.add_argument('--top-k', type=int, default=5,
                             help='Number of results to retrieve (default: 5)')
    query_parser.add_argument('--collection', type=str,
                             help='Collection name(s) - use comma to separate multiple (e.g., work,meetings)')
    query_parser.add_argument('--all-collections', action='store_true',
                             help='Query all available collections')

    # Collections command
    subparsers.add_parser('collections', help='List all collections')

    # Export command
    export_parser = subparsers.add_parser('export', help='Export transcriptions')
    export_parser.add_argument('--file', dest='filename',
                              help='Specific file to export')
    export_parser.add_argument('--all', action='store_true',
                              help='Export all transcriptions')
    export_parser.add_argument('--format', choices=['txt', 'json'], default='txt',
                              help='Export format (default: txt)')

    # List command
    list_parser = subparsers.add_parser('list', help='List indexed files')
    list_parser.add_argument('--collection', type=str,
                            help='Collection name (optional)')

    # Stats command
    subparsers.add_parser('stats', help='Show database statistics')

    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete audio file from database')
    delete_parser.add_argument('filename', help='Audio filename to delete')

    args = parser.parse_args()

    # Initialize CLI
    try:
        cli = AudioRAGCLI()
    except Exception as e:
        print_error(f"Initialization failed: {str(e)}")
        sys.exit(1)

    # Execute command
    try:
        if args.command == 'add':
            cli.cmd_add(args.files, args.skip_existing, args.collection)

        elif args.command == 'query':
            cli.cmd_query(args.filter_file, args.top_k, args.collection, args.all_collections)

        elif args.command == 'export':
            if args.all:
                cli.cmd_export(filename=None, format=args.format)
            else:
                cli.cmd_export(filename=args.filename, format=args.format)

        elif args.command == 'list':
            cli.cmd_list_files(args.collection)

        elif args.command == 'collections':
            cli.cmd_collections()

        elif args.command == 'stats':
            cli.cmd_stats()

        elif args.command == 'delete':
            cli.cmd_delete(args.filename)

        else:
            # No command specified - run interactive menu
            cli.run_interactive_menu()

    except KeyboardInterrupt:
        print("\n")
        print_info("Interrupted by user")
        sys.exit(0)

    except Exception as e:
        print_error(f"Error: {str(e)}")
        logging.getLogger('audio_rag').error(f"Runtime error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
