# Feature: JSON Metadata Analysis for Smart Subtitle Language Selection

## Overview

This document describes how to use yt-dlp's JSON metadata to intelligently determine which subtitle languages to download, automatically including original source languages when users request translated subtitles.

## Problem Statement

When users request subtitle languages like `es`, `pt`, or `de`, they often get auto-translated subtitles from the original language (usually English). However, they miss the original source subtitles, which are typically more accurate than translations.

**Current behavior:**
```bash
uv run video-kb download "..." --lang es
# Downloads: Spanish (auto-translated from English)
# Missing: English (original source)
```

**Desired behavior:**
```bash
uv run video-kb download "..." --lang es
# Downloads: Spanish (auto-translated from English) + English (original source)
```

## Solution: JSON Metadata Pre-Analysis

### Step 1: Extract Metadata Using yt-dlp API

Use yt-dlp's Python API to get comprehensive subtitle metadata without downloading:

```python
def get_subtitle_metadata(url: str) -> dict:
    """Get subtitle metadata using yt-dlp API."""
    metadata_opts = {
        'writeinfojson': True,
        'skip_download': True,
        'writesubtitles': False,
        'writeautomaticsub': False,
        'quiet': True,
        'outtmpl': {'infojson': '%(upload_date>%Y-%m-%d)s_%(id)s.%(ext)s'}
    }

    with yt_dlp.YoutubeDL(metadata_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        ydl.download([url])  # Also write the JSON file
        return info
```

### Step 2: Analyze Available Subtitle Types

The metadata contains two key sections for subtitles:

#### `subtitles` - Manual/Professional Subtitles
```json
{
  "subtitles": {
    "en": [
      {
        "url": "https://youtube.com/api/timedtext?lang=en&fmt=vtt",
        "name": "English",
        "ext": "vtt"
      }
    ]
  }
}
```

#### `automatic_captions` - Auto-Generated Subtitles
```json
{
  "automatic_captions": {
    "en": [
      {
        "url": "https://youtube.com/api/timedtext?caps=asr&lang=en&fmt=vtt",
        "name": "English",
        "ext": "vtt"
      }
    ],
    "es": [
      {
        "url": "https://youtube.com/api/timedtext?kind=asr&lang=en&tlang=es&fmt=vtt",
        "name": "Spanish",
        "ext": "vtt"
      }
    ]
  }
}
```

### Step 3: Detect Translation Relationships

Parse subtitle URLs to identify source→target relationships:

#### Original Auto-Generated Subtitles
- **Pattern**: `caps=asr&lang=LANG` (no `tlang`)
- **Example**: `caps=asr&lang=en` → English auto-generated from English speech
- **Classification**: Original language subtitle

#### Auto-Translated Subtitles
- **Pattern**: `lang=SOURCE&tlang=TARGET` or `kind=asr&lang=SOURCE&tlang=TARGET`
- **Example**: `lang=en&tlang=es` → Spanish auto-translated from English
- **Classification**: Translation (source: en, target: es)

#### Manual Subtitles
- **Pattern**: No `caps=asr` or `kind=asr` parameters
- **Example**: `lang=en&fmt=vtt`
- **Classification**: Human-created subtitle

### Step 4: Smart Language Expansion Algorithm

```python
def analyze_and_expand_languages(user_requested: list[str], metadata: dict) -> list[str]:
    """Expand user languages to include source languages for translations."""

    # Combine all available subtitle sources
    subtitles = metadata.get("subtitles", {})
    auto_captions = metadata.get("automatic_captions", {})
    all_available = {**subtitles, **auto_captions}

    expanded_languages = list(user_requested)
    source_languages = set()

    # For each requested language, check if it would be a translation
    for lang in user_requested:
        if lang in all_available:
            subtitle_list = all_available[lang]
            if subtitle_list:
                first_subtitle = subtitle_list[0]
                url = first_subtitle.get("url", "")

                # Parse URL to detect translation
                if "tlang=" in url:
                    # Extract source language
                    # URL format: ...&lang=SOURCE&tlang=TARGET&...
                    import re
                    source_match = re.search(r'lang=([^&]+)', url)
                    if source_match:
                        source_lang = source_match.group(1)
                        source_languages.add(source_lang)

    # Add source languages (with priority and limits)
    priority_sources = ["en", "en-US", "en-GB"]  # English variants first

    for priority_lang in priority_sources:
        if priority_lang in source_languages:
            expanded_languages.append(priority_lang)
            source_languages.remove(priority_lang)
            break  # Only add one English variant

    # Add up to 2 other source languages
    remaining_sources = list(source_languages)[:2]
    expanded_languages.extend(remaining_sources)

    return expanded_languages
```

## Implementation Strategy

### Phase 1: Metadata Extraction
1. Call yt-dlp API with metadata-only options
2. Extract `subtitles` and `automatic_captions` sections
3. Parse available languages and their URLs

### Phase 2: Translation Detection
1. For each user-requested language, find corresponding subtitle entry
2. Parse the subtitle URL to identify translation patterns
3. Extract source language from `lang=` parameter when `tlang=` exists

### Phase 3: Language Expansion
1. Build list of detected source languages
2. Apply priority rules (English variants first)
3. Limit total additions to avoid excessive downloads
4. Return expanded language list for download

### Phase 4: Enhanced Classification
Update filename generation to reflect subtitle relationships:

- `video.auto-orig.en.vtt` - Auto-generated original English
- `video.auto-trans-en.es.vtt` - Spanish auto-translated from English
- `video.manual-orig.fr.vtt` - Human-created French subtitles
- `video.auto-trans-ja.en.vtt` - English auto-translated from Japanese

## Benefits

### For Users
- **Automatic source inclusion**: Get original language subtitles without asking
- **Better quality options**: Original subtitles are more accurate than translations
- **Language learning**: Access both original and translated versions
- **Transparency**: Clear filename indicators show subtitle relationships

### For Implementation
- **Single API call**: Uses existing yt-dlp metadata extraction
- **No subprocess overhead**: Pure Python API usage
- **Robust fallback**: Graceful degradation when analysis fails
- **Conservative limits**: Prevents excessive downloads

## Edge Cases & Considerations

### Multiple Source Languages
- **Scenario**: Video has original Japanese + English auto-captions, user requests Spanish
- **Behavior**: Could translate from either Japanese or English
- **Solution**: Prioritize common languages (English) and limit total additions

### Regional Variants
- **Scenario**: User requests `es`, available languages are `es-419`, `es-ES`
- **Behavior**: Direct language matching vs. variant expansion
- **Solution**: Focus on translation detection first, regional variants second

### Performance
- **Consideration**: Additional API call before download
- **Mitigation**: Metadata extraction is fast, provides valuable intelligence
- **Optimization**: Cache results for playlist downloads

### Rate Limiting
- **Risk**: Too many language requests could trigger YouTube limits
- **Mitigation**: Conservative expansion limits (max 3-4 total languages)
- **Fallback**: Disable expansion on rate limit errors

## Success Metrics

- Users get both translated and original subtitles automatically
- Filename classification clearly indicates subtitle relationships
- No significant performance impact on download times
- Reduced user confusion about subtitle quality and origin
- Graceful fallback when metadata analysis fails

## Future Enhancements

1. **User Control**: CLI options to disable/configure smart expansion
2. **Quality Scoring**: Prefer manual over auto-generated when available
3. **Multi-Source Handling**: Intelligent selection when multiple source languages exist
4. **Caching**: Store analysis results for playlist/channel downloads
