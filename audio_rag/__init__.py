"""
Audio RAG Query System
A RAG-based system for querying audio transcriptions and text documents.
"""

__version__ = '1.0.0'
__author__ = 'Audio RAG Team'

from config import Config
from audio_processor import AudioProcessor
from text_processor import TextProcessor
from embeddings_manager import AudioRAGDatabase, GeminiEmbeddingFunction
from qa_engine import QAEngine
from export_manager import ExportManager

__all__ = [
    'Config',
    'AudioProcessor',
    'TextProcessor',
    'AudioRAGDatabase',
    'GeminiEmbeddingFunction',
    'QAEngine',
    'ExportManager',
]
