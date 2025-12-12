"""
Embeddings and database management for the Audio RAG system.
Handles ChromaDB integration and embedding generation with Google GenAI.
"""

import logging
from typing import Optional
from datetime import datetime

import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings
from google import genai
from google.genai import types
from google.api_core import retry

from config import Config


logger = logging.getLogger('audio_rag')


# Define a helper to retry when per-minute quota is reached
is_retriable = lambda e: (isinstance(e, genai.errors.APIError) and e.code in {429, 503})


class GeminiEmbeddingFunction(EmbeddingFunction):
    """
    Custom embedding function for ChromaDB using Google GenAI.
    Ported from tutorial/QA_RAG.ipynb.
    """

    def __init__(self, client: genai.Client, model: str = "models/text-embedding-004"):
        """
        Initialize the embedding function.

        Args:
            client: Google GenAI client instance
            model: Embedding model to use
        """
        self.client = client
        self.model = model
        # Specify whether to generate embeddings for documents, or queries
        self.document_mode = True

    @retry.Retry(predicate=is_retriable)
    def __call__(self, input: Documents) -> Embeddings:
        """
        Generate embeddings for the input documents.

        Args:
            input: List of documents/queries to embed

        Returns:
            List of embedding vectors
        """
        if self.document_mode:
            embedding_task = "retrieval_document"
        else:
            embedding_task = "retrieval_query"

        logger.debug(f"Generating embeddings in {embedding_task} mode for {len(input)} items")

        response = self.client.models.embed_content(
            model=self.model,
            contents=input,
            config=types.EmbedContentConfig(
                task_type=embedding_task,
            ),
        )

        return [e.values for e in response.embeddings]


class AudioRAGDatabase:
    """Manages ChromaDB for audio transcription storage and retrieval."""

    def __init__(self, persist_directory: str, client: genai.Client, config: Config):
        """
        Initialize the database manager.

        Args:
            persist_directory: Directory for persistent ChromaDB storage
            client: Google GenAI client instance
            config: Configuration instance
        """
        self.persist_directory = persist_directory
        self.config = config
        self.genai_client = client

        # Initialize ChromaDB with persistent storage
        logger.info(f"Initializing ChromaDB at {persist_directory}")
        self.chroma_client = chromadb.PersistentClient(path=persist_directory)

        # Create embedding function
        self.embed_fn = GeminiEmbeddingFunction(
            client=client,
            model=config.EMBEDDING_MODEL
        )

        # Collection will be initialized when needed
        self.collection = None

    def initialize_collection(self, collection_name: Optional[str] = None):
        """
        Create or load existing collection.

        Args:
            collection_name: Name of the collection (default: from config)
        """
        if collection_name is None:
            collection_name = self.config.DB_COLLECTION_NAME

        logger.info(f"Initializing collection: {collection_name}")

        # Set embedding function to document mode for adding documents
        self.embed_fn.document_mode = True

        # Get or create collection
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embed_fn
        )

        logger.info(f"Collection '{collection_name}' ready with {self.collection.count()} documents")

        # Store current collection name
        self.current_collection_name = collection_name

    def add_transcriptions(self, chunk_list: list) -> int:
        """
        Add transcription/document chunks to the database.
        Supports both audio transcriptions and text files.

        Args:
            chunk_list: List of chunk dictionaries from AudioProcessor or TextProcessor

        Returns:
            Number of chunks added
        """
        if self.collection is None:
            self.initialize_collection()

        if not chunk_list:
            logger.warning("No chunks to add to database")
            return 0

        # Ensure we're in document mode
        self.embed_fn.document_mode = True

        # Prepare data for ChromaDB
        documents = []
        metadatas = []
        ids = []

        for chunk_data in chunk_list:
            # Extract chunk text
            documents.append(chunk_data['chunk_text'])

            # Normalize metadata keys for both audio and text files
            # Audio files use: audio_filename, transcription_date, audio_format, transcription_model
            # Text files use: filename, processing_date, file_format, source_type

            # Get filename (normalize key)
            filename = chunk_data.get('audio_filename') or chunk_data.get('filename')

            # Get source type (audio or text)
            source_type = chunk_data.get('source_type', 'audio')

            # Build metadata (ChromaDB requires all values to be simple types)
            metadata = {
                'filename': filename,
                'source_type': source_type,
                'original_path': chunk_data.get('original_path', ''),
                'chunk_index': chunk_data['chunk_index'],
                'total_chunks': chunk_data['total_chunks'],
                'processing_date': chunk_data.get('transcription_date') or chunk_data.get('processing_date'),
                'file_size': chunk_data.get('file_size', 0),
                'file_format': chunk_data.get('audio_format') or chunk_data.get('file_format'),
            }

            # Add audio-specific metadata if present
            if source_type == 'audio' and 'transcription_model' in chunk_data:
                metadata['transcription_model'] = chunk_data['transcription_model']

            metadatas.append(metadata)

            # Create unique ID for this chunk
            chunk_id = f"{filename}_{chunk_data['chunk_index']}"
            ids.append(chunk_id)

        # Add to ChromaDB
        logger.info(f"Adding {len(documents)} chunks to database")
        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )

        logger.info(f"Successfully added {len(documents)} chunks")
        return len(documents)

    def query_transcriptions(
        self,
        query: str,
        n_results: int = 5,
        filename_filter: Optional[str] = None
    ) -> dict:
        """
        Query the database for relevant transcription chunks.

        Args:
            query: Query string
            n_results: Number of results to return
            filename_filter: Optional filter to search only in specific file

        Returns:
            Dictionary containing:
                - documents: List of relevant chunks
                - metadatas: List of metadata for each chunk
                - distances: List of similarity distances
        """
        if self.collection is None:
            self.initialize_collection()

        # Switch to query mode
        self.embed_fn.document_mode = False

        logger.info(f"Querying database: '{query}' (top {n_results} results)")

        # Build where clause for filtering
        where = None
        if filename_filter:
            where = {"filename": filename_filter}
            logger.debug(f"Filtering by filename: {filename_filter}")

        # Query ChromaDB
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where
        )

        # Extract results
        result_dict = {
            'documents': results['documents'][0] if results['documents'] else [],
            'metadatas': results['metadatas'][0] if results['metadatas'] else [],
            'distances': results['distances'][0] if results['distances'] else []
        }

        logger.info(f"Retrieved {len(result_dict['documents'])} results")

        return result_dict

    def query_multiple_collections(
        self,
        query: str,
        collection_names: list,
        n_results: int = 5,
        filename_filter: Optional[str] = None
    ) -> dict:
        """
        Query multiple collections and merge results by relevance.

        Args:
            query: Query string
            collection_names: List of collection names to query
            n_results: Total number of results to return (distributed across collections)
            filename_filter: Optional filter to search only in specific file

        Returns:
            Dictionary containing merged results:
                - documents: List of relevant chunks
                - metadatas: List of metadata for each chunk (includes collection_name)
                - distances: List of similarity distances
        """
        logger.info(f"Querying {len(collection_names)} collections: {collection_names}")

        all_documents = []
        all_metadatas = []
        all_distances = []

        # Query each collection
        for collection_name in collection_names:
            try:
                # Temporarily switch to this collection
                temp_collection = self.chroma_client.get_collection(
                    name=collection_name,
                    embedding_function=self.embed_fn
                )

                # Switch to query mode
                self.embed_fn.document_mode = False

                # Build where clause
                where = None
                if filename_filter:
                    where = {"filename": filename_filter}

                # Query
                results = temp_collection.query(
                    query_texts=[query],
                    n_results=n_results,  # Get top N from each collection
                    where=where
                )

                # Collect results
                if results['documents'] and results['documents'][0]:
                    for doc, meta, dist in zip(
                        results['documents'][0],
                        results['metadatas'][0],
                        results['distances'][0]
                    ):
                        # Add collection name to metadata
                        meta['collection_name'] = collection_name
                        all_documents.append(doc)
                        all_metadatas.append(meta)
                        all_distances.append(dist)

                logger.debug(f"Collection '{collection_name}': {len(results['documents'][0] if results['documents'] else [])} results")

            except Exception as e:
                logger.warning(f"Failed to query collection '{collection_name}': {str(e)}")
                continue

        # Sort all results by distance (lower is better)
        if all_documents:
            combined = list(zip(all_documents, all_metadatas, all_distances))
            combined.sort(key=lambda x: x[2])  # Sort by distance

            # Take top n_results
            combined = combined[:n_results]

            # Unpack
            all_documents, all_metadatas, all_distances = zip(*combined) if combined else ([], [], [])
            all_documents = list(all_documents)
            all_metadatas = list(all_metadatas)
            all_distances = list(all_distances)

        result_dict = {
            'documents': all_documents,
            'metadatas': all_metadatas,
            'distances': all_distances
        }

        logger.info(f"Retrieved {len(all_documents)} total results across {len(collection_names)} collections")

        return result_dict

    def get_all_files(self) -> list:
        """
        List all unique files (audio and text) in the database.

        Returns:
            List of dictionaries with file information
        """
        if self.collection is None:
            self.initialize_collection()

        # Get all documents
        all_data = self.collection.get()

        if not all_data['metadatas']:
            return []

        # Extract unique filenames with their metadata
        files_dict = {}
        for metadata in all_data['metadatas']:
            filename = metadata['filename']
            if filename not in files_dict:
                files_dict[filename] = {
                    'filename': filename,
                    'source_type': metadata.get('source_type', 'audio'),
                    'total_chunks': metadata['total_chunks'],
                    'processing_date': metadata['processing_date'],
                    'file_size': metadata['file_size'],
                    'file_format': metadata['file_format']
                }

        # Sort by processing date (most recent first)
        files_list = list(files_dict.values())
        files_list.sort(key=lambda x: x['processing_date'], reverse=True)

        logger.debug(f"Found {len(files_list)} unique file(s) in database")

        return files_list


    def get_transcription_by_file(self, filename: str) -> str:
        """
        Retrieve the complete content for a specific file (audio or text).

        Args:
            filename: Name of the file

        Returns:
            Complete content text (all chunks reassembled)
        """
        if self.collection is None:
            self.initialize_collection()

        logger.info(f"Retrieving complete content for: {filename}")

        # Query for all chunks of this file
        results = self.collection.get(
            where={"filename": filename}
        )

        if not results['documents']:
            logger.warning(f"No transcription found for {filename}")
            return ""

        # Sort chunks by chunk_index
        chunks_with_metadata = list(zip(
            results['documents'],
            results['metadatas']
        ))
        chunks_with_metadata.sort(key=lambda x: x[1]['chunk_index'])

        # Reassemble transcription
        transcription = ' '.join([chunk for chunk, _ in chunks_with_metadata])

        logger.info(f"Retrieved transcription with {len(chunks_with_metadata)} chunks")

        return transcription

    def delete_audio_file(self, filename: str) -> int:
        """
        Remove all chunks associated with a file (audio or text).

        Args:
            filename: Name of the file to remove

        Returns:
            Number of chunks deleted
        """
        if self.collection is None:
            self.initialize_collection()

        logger.info(f"Deleting file from database: {filename}")

        # Get all IDs for this file
        results = self.collection.get(
            where={"filename": filename}
        )

        if not results['ids']:
            logger.warning(f"No data found for {filename}")
            return 0

        # Delete all chunks
        self.collection.delete(ids=results['ids'])

        deleted_count = len(results['ids'])
        logger.info(f"Deleted {deleted_count} chunks for {filename}")

        return deleted_count

    def get_stats(self) -> dict:
        """
        Get database statistics.

        Returns:
            Dictionary with statistics
        """
        if self.collection is None:
            self.initialize_collection()

        total_chunks = self.collection.count()
        all_files = self.get_all_files()

        stats = {
            'total_chunks': total_chunks,
            'total_files': len(all_files),
            'files': all_files
        }

        return stats

    def check_file_exists(self, filename: str) -> bool:
        """
        Check if a file already exists in the database.

        Args:
            filename: Name of the file

        Returns:
            True if file exists, False otherwise
        """
        if self.collection is None:
            self.initialize_collection()

        results = self.collection.get(
            where={"filename": filename},
            limit=1
        )

        return bool(results['ids'])

    def list_collections(self) -> list:
        """
        List all available collections in the database.

        Returns:
            List of collection names
        """
        collections = self.chroma_client.list_collections()
        collection_names = [col.name for col in collections]

        logger.debug(f"Found {len(collection_names)} collection(s)")

        return collection_names

    def get_collection_info(self, collection_name: str) -> dict:
        """
        Get information about a specific collection.

        Args:
            collection_name: Name of the collection

        Returns:
            Dictionary with collection information
        """
        try:
            # Temporarily switch to the collection
            temp_collection = self.chroma_client.get_collection(
                name=collection_name,
                embedding_function=self.embed_fn
            )

            # Get file count
            all_data = temp_collection.get()
            files_dict = {}
            for metadata in all_data['metadatas']:
                filename = metadata['filename']
                if filename not in files_dict:
                    files_dict[filename] = True

            return {
                'name': collection_name,
                'total_chunks': temp_collection.count(),
                'total_files': len(files_dict),
                'exists': True
            }

        except Exception as e:
            logger.warning(f"Collection '{collection_name}' not found or error: {str(e)}")
            return {
                'name': collection_name,
                'exists': False
            }

    def delete_collection(self, collection_name: str) -> bool:
        """
        Delete an entire collection.

        Args:
            collection_name: Name of the collection to delete

        Returns:
            True if deleted, False otherwise
        """
        try:
            self.chroma_client.delete_collection(name=collection_name)
            logger.info(f"Deleted collection: {collection_name}")

            # If we deleted the current collection, reset it
            if hasattr(self, 'current_collection_name') and self.current_collection_name == collection_name:
                self.collection = None
                self.current_collection_name = None

            return True

        except Exception as e:
            logger.error(f"Failed to delete collection {collection_name}: {str(e)}")
            return False
