# AGENTS.md - Google Classroom Agent

## Project Overview

A Python 3.13 automation script that:
1. Scrapes Google Classroom for homework using Playwright (Chromium)
2. Parses scraped content with Google Gemini AI (`gemini-flash-latest`)
3. Writes results to a Google Doc via the Google Docs API

Flat single-directory structure — no packages, no `src/` layout:
- `main.py` — Entry point (sequential pipeline)
- `scraper.py` — Playwright browser automation
- `parser.py` — Gemini AI parsing logic
- `docs_writer.py` — Google Docs API integration
- `config.py` — Centralized configuration / `.env` loading

## Setup & Run Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright Chromium browser
python -m playwright install chromium

# Run the agent
python main.py
```

## Building

```bash
# Build standalone Windows .exe via PyInstaller
pyinstaller GoogleClassroomAgent.spec
# Output: dist/GoogleClassroomAgent.exe
```

## Testing

**No tests exist.** There is no test framework, no `tests/` directory, and no test runner configured.
If adding tests, use `pytest` (add to `requirements.txt` first):

```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_parser.py

# Run a single test function
pytest tests/test_parser.py::test_parse_class_data
```

## Linting & Formatting

**No linter or formatter is configured.** There is no `ruff`, `flake8`, `black`, `pylint`, or `mypy` in the project.
If adding linting, prefer `ruff` (fast, all-in-one):

```bash
# Lint
ruff check .

# Format
ruff format .

# Type check (if adding type hints)
mypy .
```

## Code Style Guidelines

### Imports
- Standard library first, then third-party, then local modules
- Use `import X` for local modules: `import config`, `import parser`
- Use `from X import Y` for specific items from third-party: `from playwright.sync_api import sync_playwright`
- No blank-line separation between import groups (current convention)
- Keep imports at the top of the file; only exception is lazy imports inside functions when needed to avoid circular deps or heavy loads

### Naming
- **Modules**: `snake_case.py` (e.g., `docs_writer.py`)
- **Functions**: `snake_case`, leading underscore for private helpers (e.g., `_get_current_date_formats`, `_scrape_google_slides_text`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `GEMINI_API_KEY`, `SCOPES`, `BASE_DIR`)
- **Local variables**: `snake_case` (e.g., `parsed_results`, `class_texts`)
- **Classes**: Not used in this project (everything is module-level functions)

### Types
- No type annotations on most function signatures currently
- When adding types, use inline annotations: `def func(param: str) -> dict:`
- Use `dict`, `list` (lowercase) for type hints — not `Dict`, `List` from `typing`

### Error Handling
- Catch broad `Exception as e` and print with emoji prefix: `print(f"❌ Error message: {e}")`
- Return empty/fallback values (`{}`, `[]`, `None`) on failure rather than raising
- Use `try/finally` for resource cleanup (e.g., `browser_context.close()`)
- For API rate limits (429), use exponential backoff with jitter

### Logging
- Use `print()` with emoji prefixes — no `logging` module
- Prefixes: `✅` success, `❌` error, `⚠️` warning, `⏳` wait/progress, `💡` tips

### Docstrings
- Use triple-quoted docstrings on public functions
- Keep them brief — describe purpose and parameters
- Example: `"""Scrapes Google Classroom for the configured classes."""`

### Configuration
- All settings centralized in `config.py`
- Use `os.getenv("KEY", "default")` pattern for `.env` overrides
- `BASE_DIR` is PyInstaller-aware (checks `sys.frozen`)

### General Patterns
- The pipeline is sequential: scrape → parse → write → summarize
- `main.py` has `if __name__ == "__main__"` guard; other modules do not
- Google Slides text extraction searches for current date across slides
- Duplicate detection in `docs_writer.py` compares assignment text against existing doc content

## Environment Variables

Set in `.env` file next to the script/exe:
- `GEMINI_API_KEY` — Google Gemini API key
- `GOOGLE_CREDENTIALS_PATH` — Path to service account JSON
- `CHROME_PROFILE_PATH` — Chrome User Data directory
- `CHROME_PROFILE_DIR` — Chrome profile folder name (e.g., "Profile 11")

## Important Notes

- **Credentials**: `credentials.json` contains real secrets — never commit it
- **Browser**: Requires system-installed Google Chrome (uses `channel="chrome"`)
- **Platform**: Windows-focused (uses `%#m` strftime format for Windows)
- **Not a git repo** — no version control is configured
