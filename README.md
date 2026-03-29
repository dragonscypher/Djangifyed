# Djangifyed : Legacy Web Modernizer (Planning + Execution + LLM-Powered Conversion)

This project modernizes legacy websites (HTML/CSS/JS/PHP) into modern Python web stacks using **intelligent LLM-powered code conversion**.

It now follows a two-stage workflow:
1. Planning stage: scans legacy files and generates a modernization plan.
2. Execution stage: generates Django and/or FastAPI projects, migrates assets, uses LLM or best-effort to convert PHP, and can export zip output.

## What It Supports

- Local folder input (`--source`)
- Git repository input (`--repo-url`)
- Target output:
    - Django (`--target django`)
    - FastAPI (`--target fastapi`)
    - Rust/Axum (`--target rust`)
    - Both Django & FastAPI (`--target dual`)
- Plan-only mode (`--plan-only`)
- Zip packaging (`--create-zip`)
- Optional local virtual environment creation (`--init-venv`)
- **LLM-powered code conversion** (PHP→Python, HTML modernization)
- Web UI for interactive modernization

## AI/LLM Integration

**Djangifyed now supports intelligent code conversion using LLMs:**

### How It Works

1. **PHP to Python conversion**: Attempts to convert PHP to Python using an LLM before falling back to static translators
2. **HTML rewriting**: Uses LLM to intelligently modernize HTML for target framework (Django/FastAPI/Rust)
3. **Graceful fallback**: If no LLM is available, uses fast heuristic regex-based conversion

### Enable LLM (Optional but Recommended)

**Option 1: Use Ollama (local inference server - recommended)**
```bash
# 1. Install Ollama: https://ollama.ai/download
# 2. Pull a model: ollama pull mistral
# 3. Start server: ollama serve
# 4. Run Djangifyed (auto-detects Ollama on localhost:11434)
python auto.py --source legacy_site --project-name mysite --target fastapi
```

**Option 2: Use Transformers (automatic, first run downloads model)**
```bash
# HuggingFace transformers will auto-download CodeT5 model on first use (~400MB)
# Subsequent runs use cache
python auto.py --source legacy_site --project-name mysite --target fastapi
```

**Without LLM**: Uses regex-based heuristics (instant, less intelligent)  
**With LLM**: Uses AI for smarter conversion (slower first run, much better code quality)

## Why This Approach

Modernization is not only a file copy operation. The script now separates analysis from generation so teams can review what will happen before any conversion runs.

Generated output includes:
- `modernization_plan.json` for traceable planning
- Converted templates and static assets
- Best-effort PHP to Python translation in `converted_php`
- Security checklist and model recommendations in `MODERNIZATION_NOTES.md`

## Install

```bash
python -m pip install -r requirements.txt
```

## Usage

### Web UI (Recommended for Interactive Use)

```bash
python run_server.py
# Open browser to http://127.0.0.1:8000
# Fill form, upload legacy site, and modernize with one click
```

### 1. Plan only from local folder

```bash
python auto.py --source path/to/legacy_site --project-name mysite --target dual --output-root output --plan-only
```

### 2. Full modernization from local folder + zip export

```bash
python auto.py --source path/to/legacy_site --project-name mysite --target dual --output-root output --create-zip
```

### 3. Modernize from repository URL

```bash
python auto.py --repo-url https://github.com/owner/legacy-site.git --project-name mysite --target fastapi --output-root output --create-zip
```

### 4. Create local virtual environment before run

```bash
python auto.py --init-venv --source path/to/legacy_site --project-name mysite --target django
```

### 5. Test with LLM-powered conversion

To get AI-powered code conversion, start Ollama first:
```bash
ollama serve &              # Start Ollama server
python run_server.py &      # Start web UI
# Open http://127.0.0.1:8000 in browser
# Upload legacy site and watch LLM convert PHP/HTML intelligently
```

## Command Reference

```text
--source <path>              Local legacy website directory
--repo-url <url>             Git URL for legacy project
--project-name <name>        Base name for output projects (default: modernized_site)
--target <django|fastapi|dual|rust>
                             Output framework(s)
--output-root <path>         Output directory (default: output)
--plan-only                  Generate plan and stop
--create-zip                 Build downloadable zip package
--init-venv                  Create .venv in current workspace
```

## Notes on PHP Migration

**With LLM enabled (recommended):**
- `.php` files are intelligently converted to Python using AI
- Conversion understands context and semantics
- Much higher quality than regex-based approaches
- Slower first run (model download), fast after cache

**Without LLM:**
- If `php2py` is installed, `.php` files are translated to `.py` as a starting point.
- If not installed, original PHP source is preserved in generated Python stubs for manual migration.

⚠️ **All PHP-to-Python conversion (LLM or automatic) should be reviewed before production use.**

## Models Used

When LLM is enabled, the following models are used (in priority order):

1. **Ollama (if available)**: Uses any model in Ollama (defaults to Mistral)
2. **HuggingFace**: CodeT5P-220M (lightweight, ~400MB download on first use)
3. **Fallback**: Regex-based heuristics (instant, no downloads)

## Testing

Run the comprehensive test suite:

```bash
pytest tests/ -v
```

100 tests covering:
- File discovery and inventory
- HTML rewriting for all targets
- PHP conversion (LLM + fallback)
- Skeleton generation (Django/FastAPI/Rust)
- Asset migration
- Plan building and saving
- Zip packaging
- Edge cases (deep nesting, binary files, spaces in names, etc.)

## CI

GitHub Actions workflow is included at `.github/workflows/ci.yml`.

It validates:
- dependency install
- syntax compilation of `auto.py`
- plan-only smoke run on a tiny sample legacy site

## Security and Quality

The generated FastAPI scaffold includes basic response hardening headers and a health endpoint.

For production hardening, add:
- strict host allow-list
- HTTPS redirects and HSTS
- CSRF/session hardening (for Django)
- dependency scanning and SAST

## Project Goal

Make legacy website modernization repeatable, reviewable, and easier to automate for teams that want to move toward modern Django/FastAPI stacks while preserving original look and behavior.
