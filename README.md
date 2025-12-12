# Audio RAG Query System

A production-ready RAG (Retrieval-Augmented Generation) system that processes **audio files and text documents** into a searchable knowledge base. Built with Google GenAI, ChromaDB, and Gemini models.

## Features

- **Batch Audio Processing**: Transcribe multiple audio files at once with progress tracking
- **Direct Text File Support**: Add .txt and .md files directly (no transcription needed)
- **Multi-Collection Support**: Organize content by topic/project in separate collections
- **Persistent Vector Database**: ChromaDB storage - no need to re-process files
- **Interactive Q&A**: Ask questions about your content in natural language
- **Multiple Export Formats**: Export transcriptions as text or JSON with metadata
- **Source Attribution**: See which file and segment each answer came from
- **Multi-language Support**: Works with both English and Chinese (中文)

## System Architecture

```
audio_rag/
├── main.py                    # CLI entry point
├── config.py                  # Configuration management
├── audio_processor.py         # Audio transcription & chunking
├── embeddings_manager.py      # ChromaDB & embeddings
├── qa_engine.py               # RAG query & answer generation
├── export_manager.py          # Transcription export
├── utils.py                   # Helper functions
└── data/
    ├── chromadb/             # Persistent vector database
    └── transcriptions/       # Exported text files
```

## Installation

### Prerequisites

- Python 3.8 or higher
- Google GenAI API key ([Get one here](https://makersuite.google.com/app/apikey))

### Setup Steps

1. **Clone or download this repository**

2. **Install dependencies**:
   ```bash
   cd genAI
   pip install -r audio_rag/requirements.txt
   ```

3. **Configure API key**:
   ```bash
   # Copy the example file
   cp .env.example .env

   # Edit .env and add your API key
   # GOOGLE_API_KEY=your_actual_api_key_here
   ```

## Usage

### Command-Line Interface

Navigate to the `audio_rag` directory to run commands:

```bash
cd audio_rag
```

#### 1. Add Files (Audio or Text)

Process and index files into the database:

```bash
# Add audio files
python main.py add ../tutorial/test.mp3

# Add text files
python main.py add document.txt notes.md

# Add mixed files (audio + text)
python main.py add audio1.mp3 document.txt notes.md file2.wav

# Add to specific collection
python main.py add meeting1.mp3 meeting2.mp3 --collection work_meetings

# Skip files already in database
python main.py add *.mp3 *.txt --skip-existing
```

**Supported formats:**
- **Audio**: `.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.aac`, `.wma`
- **Text**: `.txt`, `.md` (Markdown)

#### 2. Query Your Audio Content

Interactive Q&A mode:

```bash
python main.py query
```

Example session:
```
Question: 請問音訊中提到的主要議題是什麼？
[Detailed answer with sources...]

Question: What were the key points discussed?
[Answer...]

Question: exit
```

Advanced query options:
```bash
# Query specific collection
python main.py query --collection work_meetings

# Query MULTIPLE collections (comma-separated)
python main.py query --collection work,meetings,research

# Query ALL collections
python main.py query --all-collections

# Filter to specific file
python main.py query --filter interview.mp3

# Retrieve more context (default: 5)
python main.py query --top-k 10

# Combine options - query multiple collections with more results
python main.py query --collection lectures,training --top-k 10
```

#### 3. Export Transcriptions

Export transcriptions to text files:

```bash
# Export all transcriptions as text
python main.py export --all

# Export specific file
python main.py export --file test.mp3

# Export as JSON with metadata
python main.py export --all --format json
```

Exports are saved to `audio_rag/data/transcriptions/`

#### 4. Manage Collections

Organize your content into separate collections (e.g., work_meetings, lectures, podcasts):

```bash
# List all collections
python main.py collections

# List files in specific collection
python main.py list --collection work_meetings

# Add files to a collection
python main.py add file1.mp3 file2.txt --collection my_collection

# Query a specific collection
python main.py query --collection my_collection
```

**Common collection use cases:**
- `work_meetings` - Meeting recordings and transcripts
- `training_sessions` - Training materials and videos
- `customer_feedback` - Customer interview recordings
- `research_papers` - Academic papers and notes
- `podcasts` - Podcast episodes

**Query across multiple collections:**

You can search across multiple collections simultaneously to find information scattered across different sources:

```bash
# Query multiple collections - results are merged and ranked by relevance
python main.py query --collection meetings,training,research

# Query ALL collections in your database
python main.py query --all-collections
```

The system will:
1. Search each specified collection
2. Merge results from all collections
3. Rank them by relevance (similarity score)
4. Show you the top N most relevant results
5. Indicate which collection each result came from

#### 5. Manage Your Database

List indexed files:
```bash
# List all files in default collection
python main.py list

# List files in specific collection
python main.py list --collection work_meetings
```

View database statistics:
```bash
python main.py stats
```

Delete a file from database:
```bash
python main.py delete test.mp3
```

#### 6. Interactive Menu

Run without arguments for an interactive menu:

```bash
python main.py
```

## How It Works

### 1. File Processing

**Audio files** are uploaded to Google GenAI and transcribed using **Gemini 2.5 Flash**:

**Text files** (.txt, .md) are read directly with UTF-8 encoding:

```python
# From tutorial/audio2text.py
client.models.generate_content(
    model='gemini-2.5-flash',
    contents=[prompt, audio_file]
)
```

### 2. Text Chunking

Long transcriptions are split into ~1000 character chunks with 50-character overlap, preserving sentence boundaries for better retrieval.

### 3. Embedding & Storage

Text chunks are embedded using **text-embedding-004** and stored in ChromaDB with metadata:

```python
{
    'filename': 'interview.mp3',
    'source_type': 'audio',  # or 'text'
    'chunk_index': 0,
    'total_chunks': 5,
    'processing_date': '2025-12-12T10:30:00',
    'file_size': 23550610,
    'file_format': 'mp3',  # or 'txt', 'md'
    ...
}
```

Files are organized into **collections** for better organization (optional).

### 4. RAG Query Process

When you ask a question:

1. **Retrieval**: Your question is embedded and used to find the most relevant transcription chunks
2. **Augmentation**: Retrieved chunks are added to a prompt with your question
3. **Generation**: **Gemini 2.0 Flash** generates a comprehensive answer based on the context

## Configuration

### Environment Variables

Set in `.env` file:

```bash
GOOGLE_API_KEY=your_api_key_here
```

### Model Configuration

Edit `audio_rag/config.py`:

```python
# Model configurations
GEMINI_TRANSCRIPTION_MODEL = "gemini-2.5-flash"  # For audio transcription
GEMINI_GENERATION_MODEL = "gemini-2.5-flash"     # For answer generation
EMBEDDING_MODEL = "models/text-embedding-004"    # For embeddings

# Chunking configuration
CHUNK_SIZE = 1000        # Characters per chunk
CHUNK_OVERLAP = 50       # Character overlap between chunks
```

## Examples

### Example 1: Process and Query Mixed Content

```bash
# Add lecture recording + lecture notes
python main.py add lecture_2023.mp3 lecture_notes.md

# Query the combined content
python main.py query

Question: What was the main topic discussed?
[Answer combines info from audio and notes...]

Question: What examples were given?
[Answer with sources from both files...]
```

### Example 2: Organize by Collections

```bash
# Create work meetings collection
python main.py add meeting1.mp3 meeting_notes.txt --collection work_meetings

# Create training collection
python main.py add training_video.mp3 slides.md --collection training

# List all collections
python main.py collections

# Query specific collection
python main.py query --collection work_meetings
Question: What action items were discussed?
```

### Example 3: Research Paper Analysis

```bash
# Add research papers (text files)
python main.py add paper1.md paper2.md paper3.txt --collection research

# Query the research collection
python main.py query --collection research --top-k 10

Question: What are the common methodologies across these papers?
[Answer synthesized from all papers...]
```

### Example 4: Query Across Multiple Collections

```bash
# Set up different collections
python main.py add meeting1.mp3 --collection meetings
python main.py add lecture1.mp3 --collection training
python main.py add paper1.md --collection research

# Query across specific collections
python main.py query --collection meetings,training

Question: What topics were discussed?
[Answer combines results from both meetings and training collections...]

# Query ALL collections at once
python main.py query --all-collections

Question: What are the key takeaways?
[Answer synthesizes information from meetings, training, AND research...]
```

### Example 5: Podcast + Show Notes

```bash
# Combine podcast audio with show notes
python main.py add podcast_ep01.mp3 shownotes.md --collection podcast

# Export everything
python main.py export --all

# Query specific episode
python main.py query --filter podcast_ep01.mp3
```

## Project Structure

```
genAI/
├── audio_rag/
│   ├── __init__.py            # Package initialization
│   ├── main.py                # CLI application (START HERE)
│   ├── config.py              # Configuration management
│   ├── audio_processor.py     # Audio transcription logic
│   ├── text_processor.py      # Text file processing (NEW!)
│   ├── embeddings_manager.py  # ChromaDB + collections (UPDATED!)
│   ├── qa_engine.py           # RAG query engine
│   ├── export_manager.py      # Export functionality
│   ├── utils.py               # Helper functions
│   ├── requirements.txt       # Python dependencies
│   └── data/                  # Data directory (auto-created)
│       ├── chromadb/          # Vector database storage (multi-collection)
│       └── transcriptions/    # Exported transcriptions
├── tutorial/                  # Original tutorial code
│   ├── audio2text.py         # Basic audio transcription
│   ├── QA_RAG.ipynb          # RAG tutorial notebook
│   └── test.mp3              # Sample audio file
├── .env                       # API key (create from .env.example)
├── .env.example              # API key template
├── .gitignore                # Git ignore rules
└── README.md                 # This file
```

## Troubleshooting

### "Google API key not found"

Make sure you've created a `.env` file in the `genAI/` directory with your API key:

```bash
cp .env.example .env
# Edit .env and add your key
```

### "No relevant documents found"

This means the database is empty. Add audio files first:

```bash
python main.py add your_audio.mp3
```

### API Rate Limits

The system includes automatic retry logic for rate limits (429 errors). If you're processing many files, add delays between batches.

### ChromaDB Errors

If you encounter ChromaDB issues, try deleting and recreating the database:

```bash
rm -rf audio_rag/data/chromadb/
# Then re-add your audio files
```

## Advanced Usage

### Programmatic Access

You can also use the modules programmatically:

```python
from audio_rag import Config, AudioProcessor, AudioRAGDatabase, QAEngine
from google import genai

# Initialize
config = Config()
client = genai.Client(api_key=config.load_api_key())

# Process audio
processor = AudioProcessor(client, config)
result = processor.transcribe_audio('my_audio.mp3')

# Add to database
database = AudioRAGDatabase(config.get_chromadb_path(), client, config)
database.initialize_collection()
chunks = processor.chunk_transcription(result)
database.add_transcriptions(chunks)

# Query
qa_engine = QAEngine(database, client, config)
answer = qa_engine.answer_question("What is discussed in the audio?")
print(answer['answer'])
```

### Logging

Logs are written to `audio_rag.log` in the current directory. Check this file for detailed debugging information.

## Technology Stack

- **Google GenAI**: Audio transcription and answer generation
- **Gemini 2.5 Flash**: Fast audio-to-text transcription
- **Gemini 2.0 Flash**: High-quality answer generation
- **ChromaDB**: Vector database for semantic search
- **text-embedding-004**: State-of-the-art text embeddings
- **Python 3.8+**: Core language
- **tqdm**: Progress bars for batch processing

## Credits

Built upon the official Google GenAI tutorials:
- Audio transcription: `tutorial/audio2text.py`
- RAG implementation: `tutorial/QA_RAG.ipynb`

## License

This project is provided as-is for educational and commercial use.

## Support

For issues or questions:
1. Check the Troubleshooting section above
2. Review logs in `audio_rag.log`
3. Consult the [Google GenAI documentation](https://ai.google.dev/docs)

---

**Built with Google GenAI, ChromaDB, and Gemini** | Version 1.0.0
