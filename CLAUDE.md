# Claude Development Notes

## Project Overview

Modern Python CLI tool built with 2025 best practices for downloading and extracting transcribed text from videos using yt-dlp. Features single-source configuration, optimized tooling, and zero duplication.

## Quick Start

```bash
# 1. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Setup project
uv sync --extra dev          # Install all dependencies
uv run pre-commit install    # Setup git hooks

# 3. Test the CLI
uv run video-kb download "https://youtu.be/dQw4w9WgXcQ" --verbose
```

## Daily Development Workflow

### Code → Test → Commit
```bash
# Make changes to code
uv run --extra dev pytest                    # Quick test
uv run --extra dev ruff check --fix         # Auto-fix issues
git add . && git commit -m "..."  # Pre-commit runs automatically
```

### Available Commands
```bash
# Development
uv run video-kb --help          # Test CLI
uv run --extra dev pytest                   # Run tests
uv run --extra dev pytest --cov             # With coverage
uv run --extra dev mypy video_kb_simple/    # Type check

# Quality assurance (all use pyproject.toml configs)
uv run --extra dev ruff check --fix         # Lint + auto-fix
uv run --extra dev ruff format              # Format code
uv run --extra dev bandit -r video_kb_simple/  # Security scan
uv run --extra dev pre-commit run --all-files   # Run all hooks

# Build & install
uv build                        # Build wheel
uv pip install -e .            # Install locally
```

## 2025 Architecture Highlights

### Zero-Duplication Configuration
```
pyproject.toml           # Single source of truth
├── [tool.ruff]         # Linting & formatting config
├── [tool.mypy]         # Type checking config
├── [tool.pytest]      # Testing config
├── [tool.bandit]       # Security config
└── dependencies        # Runtime + dev packages

.pre-commit-config.yaml  # Execution orchestration only
└── uv run commands     # Uses tools from pyproject.toml
```

### Modern Stack Benefits
- **uv**: 10x faster than pip/poetry, Rust-based
- **ruff**: 100x faster than black+flake8+isort combined
- **typer**: Auto-generated help, rich terminal output
- **pydantic**: Runtime type validation + serialization
- **Single environment**: No tool version mismatches

### Project Architecture
```
video_kb_simple/
├── cli.py              # Typer interface (commands + validation)
├── downloader.py       # yt-dlp wrapper (typed + error handling)
└── __main__.py         # Entry point

tests/                  # Comprehensive test suite
├── test_cli.py         # CLI integration tests
└── test_downloader.py  # Core logic unit tests
```

## Usage Examples

### Basic Usage
```bash
# Download transcript
video-kb download "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Custom output directory and format
video-kb download "https://youtu.be/dQw4w9WgXcQ" -o ./transcripts -f vtt

# Verbose output
video-kb download "https://youtu.be/dQw4w9WgXcQ" --verbose
```

### Development Testing
```bash
# Test with a real video (for development)
video-kb download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --verbose

# Check available formats
video-kb list-formats "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

## Code Quality Pipeline

### Automated Quality Gates
```bash
# Pre-commit runs on every commit:
1. Basic file checks     # trailing whitespace, YAML syntax
2. ruff check --fix     # auto-fix linting issues
3. ruff format          # consistent code style
4. mypy                 # type safety verification
5. bandit               # security vulnerability scan
6. pytest              # test suite execution
```

### Configuration Philosophy
- **Single source**: All tool configs in `pyproject.toml`
- **Local execution**: Pre-commit uses `uv run` (no version drift)
- **Strict typing**: Full annotations required, no `Any` types
- **Security first**: Bandit + dependency scanning
- **Fast feedback**: Tools optimized for speed (ruff, uv)

## Working with This Repo

### First Time Setup
```bash
git clone <repo-url> && cd video-kb-simple
uv sync --extra dev && uv run pre-commit install
```

### Making Changes
```bash
# 1. Make code changes
# 2. Test locally
uv run pytest
uv run video-kb download "https://youtu.be/dQw4w9WgXcQ"

# 3. Commit (pre-commit runs automatically)
git add . && git commit -m "feat: add new feature"
```

### Common Tasks
```bash
# Add new dependency
uv add requests                    # Runtime dependency
uv add --dev black                 # Development dependency

# Update dependencies
uv sync                           # Sync with lockfile
uv update                         # Update all deps

# Build & publish
uv build                          # Create wheel
uv publish                        # Publish to PyPI
```

### Troubleshooting
- **Import errors**: Run `uv sync --dev` to ensure all deps installed
- **Pre-commit fails**: Run `uv run pre-commit run --all-files` to see details
- **Type errors**: Check `uv run mypy video_kb_simple/` output
- **Tests fail**: Run `uv run pytest -v` for detailed output

### Key Files
- `pyproject.toml` - All configuration lives here
- `video_kb_simple/cli.py` - Main CLI interface
- `video_kb_simple/downloader.py` - yt-dlp integration
- `CLAUDE.md` - This file (development notes)
