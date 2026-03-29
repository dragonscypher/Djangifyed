#!/usr/bin/env python3
"""
Djangifyed — Setup and Usage Guide

Two ways to run Djangifyed:

1. WEB UI (recommended for one-off conversions):
   python run_server.py
   → Open browser to http://127.0.0.1:8000
   → Fill form and modernize on the web

2. CLI (for batch/scripting):
   python auto.py --source ./legacy_site --project-name mysite --target fastapi

3. ENABLE LLM-POWERED CODE CONVERSION (optional but recommended):
   
   Option A: Use Ollama (local inference server):
     1. Install: https://ollama.ai/download
     2. Pull a model: ollama pull mistral
     3. Start server: ollama serve (runs on localhost:11434)
     4. Run Djangifyed (it will auto-detect Ollama and use it)
   
   Option B: Use Transformers (automatic, slower first run):
     1. First use will download the model (~400MB) from Hugging Face
     2. Subsequent runs use cached model
     3. Requires more RAM/CPU than Ollama
   
   Without LLM: Uses heuristic regex-based conversion (instant but less smart)
   With LLM: Uses AI to intelligently convert HTML/PHP (slower, smarter)

FEATURES:
- HTML/CSS/PHP detection and analysis
- Multiple target frameworks: Django, FastAPI, Rust/Axum
- Dual-target output (both Django AND FastAPI)
- Smart asset rewriting (templates + static files)
- PHP→Python conversion (LLM-powered or best-effort)
- Zip packaging for easy sharing
- Web UI for interactive use
- Comprehensive test suite (100 tests)
- CI/CD integration

EXAMPLES:

1. Convert a GitHub repo:
   python auto.py --source https://github.com/user/legacy-site --project-name oldsite --target fastapi

2. Convert a local folder to dual targets:
   python auto.py --source ./mysite --project-name mysite --target dual --create-zip

3. Plan-only mode (analyze without converting):
   python auto.py --source ./website --project-name webx --target django --plan-only

4. Local path with venv:
   python auto.py --source /Users/name/Projects/oldweb --project-name web2k --target rust --init-venv

ARCHITECTURE:
- auto.py: Core modernization engine
- ui.py: FastAPI web interface
- run_server.py: Web server launcher
- tests/: Comprehensive test suite (100 tests)
- requirements.txt: All dependencies

For more: https://github.com/user/Djangifyed
"""

if __name__ == "__main__":
    print(__doc__)
