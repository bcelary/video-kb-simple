# Intelligent Subtitle Filename Classification

## Overview

Enhance subtitle filename generation to clearly indicate the type and origin of downloaded subtitles, making it easier for users to understand what kind of transcript they have.

## Problem Statement

Currently, subtitle files are saved with generic `NA` placeholders that provide no information about subtitle quality or origin:

```
2025-08-09_OVqIkyDtxxo_breaking-tesla-s-robotaxi-stress-test.NA.en.vtt
2025-08-09_OVqIkyDtxxo_breaking-tesla-s-robotaxi-stress-test.NA.pl.vtt
```

Users cannot tell:
- Whether subtitles are auto-generated (potentially error-prone) or human-created (higher quality)
- Whether subtitles are original language or translated
- What to expect in terms of accuracy and completeness

## Solution

### New Filename Pattern

Replace the generic `NA` with descriptive type indicators:

```
2025-08-09_OVqIkyDtxxo_title.auto-orig.en.vtt     # Auto-generated original English
2025-08-09_OVqIkyDtxxo_title.auto-trans.pl.vtt    # Auto-translated from English to Polish
2025-08-09_OVqIkyDtxxo_title.manual.en.vtt        # Human-created English subtitles
```

### Subtitle Type Classification

Based on YouTube's subtitle metadata URL parameters:

| Type | Description | URL Indicators | Example |
|------|-------------|----------------|---------|
| `auto-orig` | Auto-generated original language | `kind=asr&lang=en` (no `tlang=`) | English speech → English subtitles |
| `auto-trans` | Auto-translated from original | `kind=asr&lang=en&tlang=pl` | English speech → Polish subtitles |
| `manual` | Human-created subtitles | No `kind=asr` parameter | Professional transcription |

## Technical Implementation

### Metadata Analysis

YouTube provides rich metadata in `requested_subtitles`:

```json
{
  "requested_subtitles": {
    "en": {
      "url": "https://youtube.com/api/timedtext?kind=asr&lang=en&variant=punctuated",
      "name": "English",
      "ext": "vtt"
    },
    "pl": {
      "url": "https://youtube.com/api/timedtext?kind=asr&lang=en&tlang=pl",
      "name": "Polish",
      "ext": "vtt"
    }
  }
}
```

### URL Parameter Analysis

- `kind=asr` → Auto-generated (Automatic Speech Recognition)
- `lang=en` → Source language of the speech
- `tlang=pl` → Target language (indicates translation)
- `variant=punctuated` → Includes punctuation formatting

### Implementation Strategy

**Location**: Enhance `_create_slugified_filename()` method in `video_kb_simple/downloader.py`

**Approach**: Post-download analysis + filename enhancement

1. **Add subtitle type detection method**:
   ```python
   def _determine_subtitle_type(self, lang: str, info_dict: dict) -> str:
       """Determine subtitle type from metadata URL for a given language."""
   ```

2. **Parse URL parameters** from `info_dict['requested_subtitles'][lang]['url']`

3. **Enhanced filename creation**:
   - Extract language code from original filename using regex
   - Look up subtitle metadata for that language
   - Parse URL to determine type classification
   - Replace `NA` with descriptive type indicator

4. **File mapping strategy**:
   - yt-dlp creates predictable filenames: `Title [VideoID].LANG.vtt`
   - Extract language using regex: `\.([a-z-]+)\.vtt$`
   - Match to metadata using extracted language code

### Code Flow

```python
# Current: _create_slugified_filename()
old_filename = "2025-08-09_OVqIkyDtxxo.NA.en.vtt"

# Enhanced:
lang = extract_language_from_filename(old_filename)  # → "en"
subtitle_type = determine_subtitle_type(lang, info_dict)  # → "auto-orig"
new_filename = old_filename.replace("NA", subtitle_type)  # → "auto-orig"
```

## Benefits

### For Users
- **Quality Expectations**: Know immediately if subtitles are AI-generated or human-created
- **Translation Awareness**: Understand if viewing original or translated content
- **Better Organization**: Easy to sort/filter files by subtitle type
- **Informed Decisions**: Choose appropriate subtitles based on accuracy needs

### For Developers
- **Extensible Design**: Easy to add new subtitle type classifications
- **Robust Fallback**: Falls back to current `NA` behavior if parsing fails
- **No Breaking Changes**: Existing functionality remains unchanged

## Edge Cases & Fallbacks

1. **Missing Metadata**: If `requested_subtitles` is unavailable → fallback to `NA`
2. **Unparseable URLs**: If URL format changes → fallback to `NA`
3. **Unknown Language**: If language extraction fails → fallback to `NA`
4. **Network Errors**: If subtitle download fails → no filename changes needed

## Testing Strategy

1. **Unit Tests**: Test URL parsing with various parameter combinations
2. **Integration Tests**: Verify filename generation with real YouTube videos
3. **Edge Case Tests**: Test fallback behavior with malformed data
4. **Regression Tests**: Ensure existing functionality remains intact

## Future Enhancements

1. **Variant Information**: Include punctuation/formatting info (`auto-orig-punct`)
2. **Quality Indicators**: Add confidence scores if available in metadata
3. **Language Detection**: Auto-detect subtitle language if metadata is missing
4. **Custom Patterns**: Allow users to configure filename patterns

## Implementation Notes

- **Performance**: Minimal overhead - only processes already-downloaded metadata
- **Compatibility**: Works with existing yt-dlp versions and YouTube API
- **Maintainability**: Isolated changes to filename generation logic
- **User Experience**: Provides immediate value without requiring user configuration

## Success Metrics

- Users can identify subtitle types without opening files
- Reduced confusion about subtitle quality and origin
- Improved file organization and management
- No performance degradation or breaking changes
