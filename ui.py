"""Djangifyed – Web UI

Run:  uvicorn ui:app --port 8080 --reload
"""

from __future__ import annotations

import base64
import html as html_lib
import io
import json
import os
import shutil
import tempfile
import traceback
from dataclasses import asdict
from pathlib import Path

from fastapi import Cookie, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

import auto

app = FastAPI(title="Djangifyed Web UI", version="1.0.0")

# ── Token management ───────────────────────────────────────────────────────────
_TOKEN_FILE = Path(tempfile.gettempdir()) / "djangifyed_token.txt"

def _encode_token(token: str) -> str:
    """Simple token encoding (base64)."""
    return base64.b64encode(token.encode()).decode()

def _decode_token(encoded: str) -> str:
    """Decode token from base64."""
    try:
        return base64.b64decode(encoded.encode()).decode()
    except:
        return ""

def _get_stored_token() -> str | None:
    """Retrieve stored token if available."""
    if _TOKEN_FILE.exists():
        try:
            encoded = _TOKEN_FILE.read_text().strip()
            return _decode_token(encoded)
        except:
            return None
    return None

def _save_token(token: str) -> None:
    """Store token locally."""
    if token and len(token) > 10:
        encoded = _encode_token(token)
        _TOKEN_FILE.write_text(encoded)
        os.environ["HF_TOKEN"] = token

def _has_token() -> bool:
    """Check if HF_TOKEN is available."""
    stored = _get_stored_token()
    if stored:
        os.environ["HF_TOKEN"] = stored
        return True
    return bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN"))

# ── paths ──────────────────────────────────────────────────────────────────────
_WORK_DIR = Path(tempfile.gettempdir()) / "djangifyed_sessions"
_WORK_DIR.mkdir(exist_ok=True)

# ── HTML templates (embedded – no CDN dependency) ─────────────────────────────
_HEAD = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Djangifyed</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{background:#0f0f0f;color:#e0e0e0;font-family:system-ui,sans-serif;min-height:100vh;
         display:flex;flex-direction:column;align-items:center;padding:2rem 1rem}
    h1{font-size:2rem;font-weight:700;margin-bottom:.25rem;
       background:linear-gradient(90deg,#6366f1,#38bdf8);
       -webkit-background-clip:text;-webkit-text-fill-color:transparent}
    h2{font-size:1.25rem;font-weight:600;margin-bottom:1rem;color:#94a3b8}
    p.sub{color:#64748b;font-size:.9rem;margin-bottom:2rem}
    .card{background:#1a1a2e;border:1px solid #2d2d44;border-radius:.75rem;
          padding:2rem;width:100%;max-width:640px;margin-bottom:1.5rem}
    label{display:block;margin-bottom:.25rem;font-size:.85rem;color:#94a3b8;font-weight:500}
    input[type=text],input[type=url],select{
      width:100%;padding:.6rem .8rem;border-radius:.5rem;border:1px solid #3f3f5e;
      background:#0f0f1a;color:#e0e0e0;font-size:.95rem;margin-bottom:1rem}
    input[type=file]{color:#94a3b8;margin-bottom:1rem}
    .or-divider{text-align:center;color:#4b5563;font-size:.8rem;
                margin:.5rem 0;letter-spacing:.05em}
    .radio-group{display:flex;gap:.75rem;flex-wrap:wrap;margin-bottom:1rem}
    .radio-group label{display:flex;align-items:center;gap:.35rem;cursor:pointer;
                       background:#16213e;padding:.45rem .8rem;border-radius:.5rem;
                       border:1px solid #2d2d44;font-size:.85rem;color:#cbd5e1}
    .radio-group label:has(input:checked){border-color:#6366f1;background:#1e1b4b}
    .checkbox-row{display:flex;align-items:center;gap:.5rem;margin-bottom:1.25rem}
    .checkbox-row input{width:1rem;height:1rem;accent-color:#6366f1}
    .checkbox-row label{font-size:.875rem;color:#94a3b8;margin:0}
    button[type=submit]{width:100%;padding:.75rem;border-radius:.5rem;border:none;
      background:linear-gradient(90deg,#6366f1,#38bdf8);color:#fff;
      font-size:1rem;font-weight:600;cursor:pointer;transition:opacity .2s}
    button[type=submit]:hover{opacity:.85}
    .result-card{background:#162032;border:1px solid #1e3a5f;border-radius:.75rem;
                 padding:1.75rem;width:100%;max-width:640px;margin-bottom:1rem}
    .result-card h3{font-size:1rem;font-weight:600;margin-bottom:.75rem;color:#38bdf8}
    pre{background:#0f1623;border-radius:.5rem;padding:1rem;
        font-size:.8rem;overflow-x:auto;color:#94a3b8;line-height:1.6;
        white-space:pre-wrap;word-break:break-all}
    .badge{display:inline-block;padding:.2rem .6rem;border-radius:999px;
           font-size:.75rem;font-weight:600;margin-right:.35rem}
    .ok{background:#14532d;color:#86efac}.err{background:#450a0a;color:#fca5a5}
    .dl-btn{display:block;text-align:center;margin-top:1rem;padding:.65rem 1rem;
            border-radius:.5rem;background:#6366f1;color:#fff;font-weight:600;
            text-decoration:none;font-size:.95rem}
    .dl-btn:hover{background:#4f46e5}
    .back{display:block;text-align:center;margin-top:.75rem;color:#6366f1;
          font-size:.875rem;text-decoration:none}
  </style>
</head>
<body>
"""

_FOOT = "</body></html>\n"

_FORM_PAGE = (
    _HEAD
    + """
<h1>Djangifyed</h1>
<p class="sub">Modernise any legacy HTML/CSS/PHP site to Django, FastAPI or Rust (Axum)</p>

<div class="card">
  <form method="post" action="/modernize" enctype="multipart/form-data">

    <label>Project name</label>
    <input type="text" name="project_name" value="mysite" required>

    <label>Source — Git / HTTP URL</label>
    <input type="url" name="repo_url" placeholder="https://github.com/user/legacy-site">
    <div class="or-divider">— OR —</div>
    <label>Upload a .zip of the source</label>
    <input type="file" name="zip_file" accept=".zip">
    <div class="or-divider">— OR —</div>
    <label>Absolute local path on this machine</label>
    <input type="text" name="local_path" placeholder="/home/user/old-website">

    <label>Target stack</label>
    <div class="radio-group">
      <label><input type="radio" name="target" value="fastapi" checked> FastAPI</label>
      <label><input type="radio" name="target" value="django"> Django</label>
      <label><input type="radio" name="target" value="dual"> Both (Dual)</label>
      <label><input type="radio" name="target" value="rust"> Rust / Axum</label>
    </div>

    <div class="checkbox-row">
      <input type="checkbox" id="create_zip" name="create_zip" value="1" checked>
      <label for="create_zip">Package output as downloadable .zip</label>
    </div>

    <button type="submit">&#x26A1; Modernise</button>
  </form>
</div>
"""
    + _FOOT
)


# ── routes ─────────────────────────────────────────────────────────────────────


@app.post("/setup-token", response_class=HTMLResponse)
async def setup_token(token: str = Form("")):
    """Save HuggingFace token and redirect to main page."""
    if token and len(token) > 10:
        _save_token(token)
    return HTMLResponse(_FORM_PAGE)


@app.get("/", response_class=HTMLResponse)
async def index():
    """Main page - shows token setup if needed."""
    # Check if token is already available
    has_token = _has_token()
    
    if not has_token:
        # Show token setup modal
        token_modal = """<div style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8);display:flex;align-items:center;justify-content:center;z-index:1000;"><div style="background:#1a1a2e;padding:2rem;border-radius:1rem;max-width:500px;border:1px solid #3f3f5e;"><h2 style="color:#38bdf8;margin-bottom:1rem;">Setup HuggingFace LLM (Free)</h2><p style="color:#94a3b8;margin-bottom:1.5rem;font-size:0.95rem;">To enable AI-powered code conversion, provide your HuggingFace token.</p><p style="color:#64748b;margin-bottom:1.5rem;font-size:0.85rem;">Get free token (no credit card): <a href="https://huggingface.co/settings/tokens" target="_blank" style="color:#6366f1;text-decoration:underline;">https://huggingface.co/settings/tokens</a></p><form action="/setup-token" method="post" style="display:flex;gap:0.5rem;"><input type="password" name="token" placeholder="hf_..." required style="flex:1;padding:0.6rem;border:1px solid #3f3f5e;border-radius:0.5rem;background:#0f0f1a;color:#e0e0e0;font-size:0.95rem;"><button type="submit" style="padding:0.6rem 1.5rem;background:#6366f1;color:#fff;border:none;border-radius:0.5rem;cursor:pointer;font-weight:600;">Save Token</button></form><p style="color:#64748b;margin-top:1rem;font-size:0.8rem;">Token is stored locally (not sent anywhere). Click skip to use fallback (offline mode works fine).</p><a href="/" style="display:inline-block;margin-top:1rem;color:#6366f1;text-decoration:none;font-size:0.9rem;">Skip for now (use offline)</a></div></div>"""
        return HTMLResponse(_HEAD + token_modal + _FOOT)
    
    return HTMLResponse(_FORM_PAGE)


@app.post("/modernize", response_class=HTMLResponse)
async def modernize(
    request: Request,
    project_name: str = Form("mysite"),
    repo_url: str = Form(""),
    local_path: str = Form(""),
    target: str = Form("fastapi"),
    create_zip: str = Form(""),
    zip_file: UploadFile | None = File(None),
):
    work = _WORK_DIR / project_name.replace(" ", "_").replace("/", "_")
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    source: Path | None = None
    error: str | None = None

    try:
        # ── resolve source ──────────────────────────────────────────────────
        if zip_file and zip_file.filename:
            import zipfile as zf

            uploaded = work / "uploaded.zip"
            uploaded.write_bytes(await zip_file.read())
            zip_src = work / "zip_source"
            zip_src.mkdir()
            with zf.ZipFile(uploaded) as z:
                z.extractall(zip_src)
            source = zip_src

        elif local_path and local_path.strip():
            p = Path(local_path.strip())
            if not p.is_dir():
                raise ValueError(f"Local path not found: {p}")
            source = p

        elif repo_url and repo_url.strip():
            source = auto.clone_repo(repo_url.strip(), work / "cloned")

        else:
            raise ValueError("Provide a URL, a zip upload, or a local path.")

        # ── run pipeline ────────────────────────────────────────────────────
        output_dir = work / "output"
        want_zip = create_zip == "1"
        plan = auto.build_plan(project_name, source, target, output_dir)
        auto.execute_plan(plan, source=source, create_zip=want_zip)

        # ── build result HTML ────────────────────────────────────────────────
        inv = plan.inventory
        inv_lines = (
            f"Total files : {inv.total_files}\n"
            f"HTML        : {inv.html_files}\n"
            f"CSS         : {inv.css_files}\n"
            f"JS          : {inv.js_files}\n"
            f"PHP         : {inv.php_files}\n"
            f"Static      : {inv.static_files}\n"
        )
        structure = "\n".join(
            str(p.relative_to(output_dir))
            for p in sorted(output_dir.rglob("*"))
            if p.is_file()
        )
        generated_projects = [
            str(p.relative_to(output_dir))
            for p in sorted(output_dir.iterdir())
            if p.is_dir()
        ]
        run_commands: list[str] = []
        safe_project_name = project_name.replace(" ", "_").replace("/", "_")
        if (output_dir / f"{safe_project_name}_fastapi").exists():
            run_commands.append(
                f"cd {output_dir / f'{safe_project_name}_fastapi'} && uvicorn app.main:app --port 8010"
            )
        if (output_dir / f"{safe_project_name}_django" / "manage.py").exists():
            run_commands.append(
                f"cd {output_dir / f'{safe_project_name}_django'} && python manage.py runserver 127.0.0.1:8011"
            )
        if (output_dir / f"{safe_project_name}_axum").exists():
            run_commands.append(
                f"cd {output_dir / f'{safe_project_name}_axum'} && cargo run"
            )

        preview_candidates = [
            output_dir / f"{safe_project_name}_fastapi" / "app" / "templates" / "index.html",
            output_dir / f"{safe_project_name}_django" / "templates" / "index.html",
            output_dir / f"{safe_project_name}_axum" / "templates" / "index.html",
        ]
        preview_html = ""
        for preview_path in preview_candidates:
            if preview_path.exists():
                preview_html = preview_path.read_text(encoding="utf-8", errors="ignore")[:1200]
                break

        # Detect LLM availability 
        hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        if hf_token:
            llm_status = "✓ HuggingFace LLM active (free tier with real API calls)"
        else:
            llm_status = "⚠ No HF_TOKEN set. LLM disabled. Set HF_TOKEN env var to enable HuggingFace Inference API."

        zip_files = sorted(output_dir.glob("*.zip"))
        dl_section = ""
        if zip_files:
            zname = zip_files[0].name
            dl_section = f'<a class="dl-btn" href="/download?file={zname}">&#x2B07; Download {zname}</a>'

        html = (
            _HEAD
            + f"""
<h1>Djangifyed</h1>
<h2>✓ {project_name} modernised to <em>{target}</em></h2>

<div class="result-card">
  <h3>Status</h3>
  <pre>{llm_status}</pre>
</div>

<div class="result-card">
  <h3>Inventory</h3>
  <pre>{inv_lines}</pre>
</div>

<div class="result-card">
  <h3>Output structure</h3>
    <pre>{html_lib.escape(structure or "(empty)")}</pre>
</div>

<div class="result-card">
    <h3>Generated projects</h3>
    <pre>{html_lib.escape(chr(10).join(generated_projects) or "(none)")}</pre>
</div>

<div class="result-card">
    <h3>Run commands</h3>
    <pre>{html_lib.escape(chr(10).join(run_commands) or "(no runnable project generated)")}</pre>
</div>

<div class="result-card">
    <h3>Converted index preview</h3>
    <pre>{html_lib.escape(preview_html or "(no index template generated)")}</pre>
</div>

<div class="result-card">
  <h3>Recommended models</h3>
  <pre>{chr(10).join(plan.recommended_models)}</pre>
</div>

<div class="result-card">
  <h3>Security actions</h3>
  <pre>{chr(10).join(plan.security_actions)}</pre>
</div>

{dl_section}
<a class="back" href="/">&#x21A9; Modernise another site</a>
"""
            + _FOOT
        )
        return HTMLResponse(html)

    except Exception:
        tb = traceback.format_exc()
        html = (
            _HEAD
            + f"""
<h1>Djangifyed</h1>
<h2><span class="badge err">Error</span> Modernisation failed</h2>
<div class="result-card">
  <h3>Details</h3>
  <pre>{tb}</pre>
</div>
<a class="back" href="/">&#x21A9; Try again</a>
"""
            + _FOOT
        )
        return HTMLResponse(html, status_code=500)


@app.get("/download")
async def download(file: str):
    """Serve a generated zip. `file` is a plain filename (no path traversal)."""
    # Sanitise: reject any path separators
    if "/" in file or "\\" in file or ".." in file:
        from fastapi.responses import JSONResponse

        return JSONResponse({"error": "Invalid filename"}, status_code=400)

    # Walk sessions to find the zip
    for session_dir in _WORK_DIR.iterdir():
        candidate = session_dir / "output" / file
        if candidate.exists() and candidate.is_file():
            return FileResponse(
                path=str(candidate),
                media_type="application/zip",
                filename=file,
            )

    from fastapi.responses import JSONResponse

    return JSONResponse({"error": "File not found"}, status_code=404)
