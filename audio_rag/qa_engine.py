"""
Question-Answering engine for the Audio RAG system.
Implements RAG-based query processing and answer generation.
"""

import logging
from typing import Optional

from google import genai

from embeddings_manager import AudioRAGDatabase
from config import Config


logger = logging.getLogger('audio_rag')


class QAEngine:
    """Handles question-answering using RAG approach."""

    def __init__(self, database: AudioRAGDatabase, client: genai.Client, config: Config):
        """
        Initialize the QA engine.

        Args:
            database: AudioRAGDatabase instance
            client: Google GenAI client instance
            config: Configuration instance
        """
        self.database = database
        self.client = client
        self.config = config
        self.conversation_history = []

    def answer_question(
        self,
        query: str,
        n_results: int = 5,
        filename_filter: Optional[str] = None,
        collections: Optional[list] = None
    ) -> dict:
        """
        Generate an answer to a question using RAG approach.

        Args:
            query: User's question
            n_results: Number of relevant chunks to retrieve
            filename_filter: Optional filter to search only in specific file
            collections: Optional list of collection names to query (queries all if None)

        Returns:
            Dictionary containing:
                - answer: Generated answer text
                - sources: List of source chunks with metadata
                - query: Original query
                - confidence: Confidence indicator based on relevance
        """
        logger.info(f"Processing question: {query}")

        # Retrieve relevant passages from database
        if collections and len(collections) > 1:
            # Query multiple collections
            retrieval_results = self.database.query_multiple_collections(
                query=query,
                collection_names=collections,
                n_results=n_results,
                filename_filter=filename_filter
            )
        elif collections and len(collections) == 1:
            # Query single collection (initialize it first)
            self.database.initialize_collection(collections[0])
            retrieval_results = self.database.query_transcriptions(
                query=query,
                n_results=n_results,
                filename_filter=filename_filter
            )
        else:
            # Query current/default collection
            retrieval_results = self.database.query_transcriptions(
                query=query,
                n_results=n_results,
                filename_filter=filename_filter
            )

        documents = retrieval_results['documents']
        metadatas = retrieval_results['metadatas']
        distances = retrieval_results['distances']

        if not documents:
            logger.warning("No relevant documents found in database")
            return {
                'answer': "抱歉，我在資料庫中找不到相關的音訊內容來回答這個問題。請確保已經添加了音訊檔案。",
                'sources': [],
                'query': query,
                'confidence': 'none'
            }

        # Build prompt with retrieved passages
        prompt = self.build_prompt(query, documents, metadatas)

        # Generate answer using Gemini
        logger.info(f"Generating answer with model: {self.config.GEMINI_GENERATION_MODEL}")
        try:
            response = self.client.models.generate_content(
                model=self.config.GEMINI_GENERATION_MODEL,
                contents=prompt
            )

            answer = response.text

        except Exception as e:
            logger.error(f"Error generating answer: {str(e)}", exc_info=True)
            # Fallback: return raw passages
            answer = "抱歉，生成答案時發生錯誤。以下是相關的轉錄內容：\n\n" + "\n\n---\n\n".join(documents)

        # Prepare source information
        sources = []
        for doc, meta, dist in zip(documents, metadatas, distances):
            source_info = {
                'text': doc,
                'filename': meta['filename'],
                'chunk_index': meta['chunk_index'],
                'distance': dist,
                'collection': meta.get('collection_name')  # May be None for single collection queries
            }
            sources.append(source_info)

        # Determine confidence based on average distance (lower is better)
        avg_distance = sum(distances) / len(distances) if distances else 1.0
        if avg_distance < 0.5:
            confidence = 'high'
        elif avg_distance < 0.8:
            confidence = 'medium'
        else:
            confidence = 'low'

        result = {
            'answer': answer,
            'sources': sources,
            'query': query,
            'confidence': confidence
        }

        # Add to conversation history
        self.add_to_history(query, answer)

        logger.info(f"Answer generated successfully (confidence: {confidence})")

        return result

    def build_prompt(
        self,
        query: str,
        passages: list,
        metadata: list
    ) -> str:
        """
        Build an augmented prompt with retrieved passages.
        Adapted from tutorial/QA_RAG.ipynb.

        Args:
            query: User's question
            passages: List of retrieved text passages
            metadata: List of metadata for each passage

        Returns:
            Complete prompt string
        """
        # Format query as single line
        query_oneline = query.replace("\n", " ")

        # Build prompt with instructions (supports both Chinese and English)
        prompt = f"""你是一個有幫助且知識豐富的助手，能夠使用參考資料回答問題。
請根據以下提供的音訊轉錄內容來回答問題。請確保回答完整且具體，包含所有相關背景資訊。
如果參考資料與問題無關，請告知使用者無法根據現有資料回答。

You are a helpful and informative bot that answers questions using the reference passages included below.
Be sure to respond in a complete sentence, being comprehensive, including all relevant background information.
If the passage is irrelevant to the answer, you may ignore it.

問題 QUESTION: {query_oneline}

參考資料 REFERENCE PASSAGES:
"""

        # Add retrieved passages with source attribution
        for idx, (passage, meta) in enumerate(zip(passages, metadata), 1):
            passage_oneline = passage.replace("\n", " ")
            filename = meta['audio_filename']
            chunk_idx = meta['chunk_index']

            prompt += f"\n[來源 {idx}，檔案: {filename}，片段: {chunk_idx}]\n{passage_oneline}\n"

        return prompt

    def add_to_history(self, query: str, answer: str):
        """
        Track conversation for potential context.

        Args:
            query: User's question
            answer: Generated answer
        """
        self.conversation_history.append({
            'query': query,
            'answer': answer
        })

        # Keep only last 10 exchanges to avoid memory issues
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]

        logger.debug(f"Added to conversation history (total: {len(self.conversation_history)} exchanges)")

    def clear_history(self):
        """Reset conversation history."""
        self.conversation_history.clear()
        logger.info("Conversation history cleared")

    def get_history(self) -> list:
        """
        Get conversation history.

        Returns:
            List of conversation exchanges
        """
        return self.conversation_history.copy()

    def format_answer_with_sources(self, result: dict) -> str:
        """
        Format answer with source attribution for display.

        Args:
            result: Result dictionary from answer_question()

        Returns:
            Formatted string with answer and sources
        """
        output = []

        # Answer section
        output.append("=" * 60)
        output.append("回答 ANSWER")
        output.append("=" * 60)
        output.append(result['answer'])
        output.append("")

        # Sources section
        if result['sources']:
            output.append("=" * 60)
            output.append("資料來源 SOURCES")
            output.append("=" * 60)

            for idx, source in enumerate(result['sources'], 1):
                # Build source line with optional collection name
                source_line = f"\n[來源 {idx}] 檔案: {source['filename']} (片段 {source['chunk_index']})"
                if source.get('collection'):
                    source_line += f" [集合: {source['collection']}]"
                output.append(source_line)

                # Show first 200 characters of source text
                text_preview = source['text'][:200]
                if len(source['text']) > 200:
                    text_preview += "..."
                output.append(f"內容預覽: {text_preview}")

            output.append("")

        # Confidence indicator
        confidence_emoji = {
            'high': '🟢',
            'medium': '🟡',
            'low': '🔴',
            'none': '⚪'
        }

        emoji = confidence_emoji.get(result['confidence'], '⚪')
        output.append(f"信心程度 Confidence: {emoji} {result['confidence'].upper()}")
        output.append("=" * 60)

        return "\n".join(output)
