# Video-KB AI Enhancement Plan

## Overview

Transform the video-kb-simple CLI from a basic transcript downloader into a comprehensive knowledge management system that uses AI to analyze, categorize, and provide insights from video content.

**Core Principles:**
- **Text-only approach**: Work exclusively with transcripts and descriptions
- **Lightweight architecture**: Single SQLite database, minimal dependencies
- **Incremental enhancement**: Build on existing clean codebase structure
- **AI-powered insights**: Use modern LLMs for content analysis and knowledge extraction

## Current State Analysis

### Existing Capabilities
- Download transcripts from YouTube videos and playlists
- Support multiple subtitle formats (SRT, VTT, ASS, TXT)
- Atomic file operations with safe exit handling
- Playlist/channel batch processing with rate limiting
- Clean filename generation with ISO date prefixes
- Manual vs auto-generated subtitle detection

### Current Limitations
1. **No data persistence**: Each download is isolated
2. **No content analysis**: Raw transcripts only
3. **No knowledge extraction**: Can't discover topics, themes, or relationships
4. **Missing video descriptions**: Critical metadata and links not captured
5. **No search capability**: Can't find content across transcripts
6. **No cross-video insights**: Can't track concept evolution or relationships

## Enhanced Architecture

### Data Storage Strategy - SQLite Only

**Single SQLite Database** (`video_kb.db`)
- Lightweight, portable, zero-configuration
- Built-in full-text search (FTS5 extension)
- ACID transactions for data integrity
- Easy backup and sharing (single file)
- Excellent Python integration

### Database Schema

```sql
-- Core video metadata
CREATE TABLE videos (
    id INTEGER PRIMARY KEY,
    video_id TEXT UNIQUE,
    title TEXT NOT NULL,
    uploader TEXT,
    duration INTEGER,
    upload_date TEXT,
    url TEXT NOT NULL,
    view_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Raw transcript content
CREATE TABLE transcripts (
    id INTEGER PRIMARY KEY,
    video_id INTEGER REFERENCES videos(id),
    content TEXT NOT NULL,
    format TEXT,
    language TEXT,
    source TEXT, -- 'manual' or 'auto'
    file_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Video descriptions with links and metadata
CREATE TABLE descriptions (
    id INTEGER PRIMARY KEY,
    video_id INTEGER REFERENCES videos(id),
    content TEXT NOT NULL,
    links_extracted TEXT, -- JSON array of URLs
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- AI analysis results
CREATE TABLE analyses (
    id INTEGER PRIMARY KEY,
    video_id INTEGER REFERENCES videos(id),
    analysis_type TEXT, -- 'summary', 'topics', 'entities', etc.
    content TEXT NOT NULL, -- JSON with analysis results
    ai_model TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Discovered topics across videos
CREATE TABLE topics (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE,
    description TEXT,
    category TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Many-to-many relationship between videos and topics
CREATE TABLE video_topics (
    video_id INTEGER REFERENCES videos(id),
    topic_id INTEGER REFERENCES topics(id),
    relevance_score REAL,
    PRIMARY KEY (video_id, topic_id)
);

-- Vector embeddings for semantic search
CREATE TABLE embeddings (
    id INTEGER PRIMARY KEY,
    video_id INTEGER REFERENCES videos(id),
    chunk_text TEXT,
    embedding BLOB, -- Serialized vector
    chunk_index INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Full-text search virtual table
CREATE VIRTUAL TABLE content_fts USING fts5(
    video_id,
    title,
    transcript,
    description,
    analysis_summary
);
```

## Enhanced CLI Commands

### New Commands
```bash
# Analysis commands
video-kb analyze [video_id|all]     # Run AI analysis on transcripts
video-kb migrate                    # Import existing transcript files to database

# Search commands
video-kb search "query"             # Full-text search across all content
video-kb search --semantic "query"  # Semantic similarity search
video-kb find-similar VIDEO_ID     # Find videos with similar content

# Knowledge management
video-kb topics                     # List discovered topics
video-kb topics --video VIDEO_ID   # Show topics for specific video
video-kb insights                   # Generate cross-video insights
video-kb timeline TOPIC            # Show topic evolution over time

# Export commands
video-kb export --format json|csv|md  # Export analysis results
video-kb export --topic TOPIC_NAME    # Export content by topic
```

### Enhanced Existing Commands
```bash
# Enhanced download with description capture
video-kb download URL --include-description
video-kb download-playlist URL --include-description
```

## AI Analysis Pipeline

### Per-Video Analysis
```python
# Analysis structure stored as JSON in analyses table
{
    "summary": {
        "executive": "One paragraph overview",
        "detailed": "Bullet point summary",
        "key_quotes": ["Important quote 1", "Important quote 2"]
    },
    "topics": [
        {"name": "Intermittent Fasting", "confidence": 0.95, "segments": [...]},
        {"name": "Ketosis", "confidence": 0.87, "segments": [...]}
    ],
    "entities": {
        "people": ["Dr. Jason Fung", "Dr. Rhonda Patrick"],
        "studies": ["PMID:12345678", "doi:10.1234/example"],
        "tools": ["Continuous Glucose Monitor", "Ketone Meter"],
        "supplements": ["Magnesium", "Vitamin D3"]
    },
    "sentiment": {
        "overall": "positive",
        "confidence": 0.82,
        "emotional_tone": "educational"
    },
    "links_mentioned": [
        {"url": "https://example.com", "context": "Study about X", "timestamp": "5:23"}
    ]
}
```

### Cross-Video Analysis
- Topic clustering and evolution tracking
- Concept relationship mapping
- Knowledge gap identification
- Content recommendation based on similarity

## Implementation Roadmap

### Phase 1: Database Foundation (Week 1-2)
- [ ] Create SQLite schema and Pydantic models
- [ ] Implement database operations layer
- [ ] Create migration script for existing transcript files
- [ ] Enhance downloader to capture video descriptions
- [ ] Add database storage to existing download workflow

### Phase 2: AI Analysis Core (Week 3-4)
- [ ] Integrate OpenAI API for content analysis
- [ ] Implement per-video analysis pipeline
- [ ] Add vector embeddings generation using sentence-transformers
- [ ] Create basic full-text search functionality
- [ ] Add `analyze` command to CLI

### Phase 3: Advanced Search & Discovery (Week 5-6)
- [ ] Implement semantic search with vector similarity
- [ ] Create topic clustering and management
- [ ] Add cross-video analysis capabilities
- [ ] Implement `search`, `topics`, and `insights` commands

### Phase 4: Knowledge Management (Week 7-8)
- [ ] Add timeline analysis for topic evolution
- [ ] Create export functionality in multiple formats
- [ ] Implement similar content recommendations
- [ ] Add configuration management for API keys and settings

## Technical Implementation Details

### New Dependencies
```toml
# Add to pyproject.toml dependencies
"openai >= 1.0.0",              # LLM analysis
"sentence-transformers >= 2.2.0", # Local embeddings
"sqlite-utils >= 3.35.0",       # Enhanced SQLite operations
"numpy >= 1.24.0",              # Vector operations
"spacy >= 3.7.0",               # NLP and entity recognition
"tiktoken >= 0.5.0",            # Token counting for API usage
```

### Project Structure Extension
```
video_kb_simple/
├── cli.py              # Enhanced with new commands
├── downloader.py       # Enhanced with description extraction
├── database/           # New module
│   ├── __init__.py
│   ├── models.py       # Pydantic models for all tables
│   ├── operations.py   # CRUD operations
│   └── migrations.py   # Schema management
├── analysis/           # New module
│   ├── __init__.py
│   ├── ai_analyzer.py  # OpenAI integration
│   ├── embeddings.py   # Vector operations
│   └── insights.py     # Cross-video analysis
├── search/             # New module
│   ├── __init__.py
│   ├── text_search.py  # FTS5 operations
│   └── semantic_search.py # Vector similarity
└── config.py           # Configuration management
```

### Configuration Management
```yaml
# ~/.config/video-kb/config.yaml
openai:
  api_key: "sk-..."
  model: "gpt-4"
  max_tokens: 4000

analysis:
  auto_analyze: true
  chunk_size: 1000
  overlap: 200

search:
  embedding_model: "all-MiniLM-L6-v2"
  similarity_threshold: 0.7

database:
  path: "~/video_kb.db"
  backup_on_analysis: true
```

## Migration Strategy

### Existing File Migration
```python
# video-kb migrate command will:
1. Scan existing transcripts/ directory
2. Extract metadata from filenames (date, video_id, title)
3. Parse transcript content and detect source (manual/auto)
4. Store in database while preserving original files
5. Optionally run analysis on migrated content
```

## Use Cases

### Content Creators
- "Show me the evolution of my stance on topic X over time"
- "Which studies have I referenced multiple times?"
- "Find gaps in my content coverage"
- "What are my most discussed topics?"

### Researchers & Knowledge Workers
- "Find all mentions of 'microbiome' across videos"
- "Show me videos similar to this research paper concept"
- "Export all references and links on topic Y"
- "Generate study notes from videos on subject Z"

## Benefits

### For Users
- **Knowledge Discovery**: Find relevant content across hundreds of videos instantly
- **Insight Generation**: Understand topic evolution and relationships
- **Research Efficiency**: Extract references, studies, and key points automatically
- **Content Gaps**: Identify areas not covered or under-explored

### For Developers
- **Clean Architecture**: Single database, clear separation of concerns
- **Extensible**: Easy to add new analysis types and search features
- **Maintainable**: Builds on existing solid foundation
- **Testable**: Database operations and AI analysis can be unit tested

## Advanced Features & Future Extensions

### Success Metrics
- **Technical**: Database query performance <100ms, analysis accuracy, search relevance
- **User Value**: Knowledge discovery efficiency, insight quality, content gap identification

### Educational Applications
- Create study guides from video series on specific topics
- Track concept evolution and prerequisite relationships
- Generate quiz questions from video content
- Build personalized learning paths based on knowledge gaps

### Multi-Language & Content Expansion
- Cross-language semantic search and analysis
- Integration with external knowledge bases and research databases
- Collaborative knowledge sharing between users
- API endpoints for third-party integrations

### Machine Learning Enhancements (Future)
- Custom topic models trained on domain-specific content
- Automated fact-checking against referenced sources
- Predictive content recommendations
- Personal knowledge graphs per user

## Why This Architecture Works

### Maintains 2025 Best Practices
- **Single source configuration**: All settings in one config file
- **Type safety**: Full Pydantic models throughout
- **Modern Python**: Leverages Python 3.11+ features
- **Fast tools**: Uses efficient libraries (sentence-transformers, SQLite FTS5)
- **Atomic operations**: Safe concurrent access and crash recovery

### Scalability Considerations
- SQLite handles millions of records efficiently for single-user scenarios
- Vector embeddings stored as compressed blobs for space efficiency
- Chunked analysis prevents memory issues with long transcripts
- Incremental analysis allows processing large video collections over time

This enhancement transforms video-kb-simple from a simple download tool into a comprehensive AI-powered knowledge management system while maintaining its lightweight and reliable nature.
