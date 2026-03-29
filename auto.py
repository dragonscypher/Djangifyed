import argparse
import ast
import importlib
import importlib.util
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

try:
    PHPTranslator = importlib.import_module("php2py").PHPTranslator
except Exception:
    PHPTranslator = None


HTML_EXTENSIONS = {".html", ".htm"}
CSS_EXTENSIONS = {".css"}
JS_EXTENSIONS = {".js"}
PHP_EXTENSIONS = {".php", ".phtml"}
STATIC_EXTENSIONS = {
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


@dataclass
class LegacyInventory:
    html_files: int
    css_files: int
    js_files: int
    php_files: int
    static_files: int
    total_files: int


@dataclass
class ModernizationPlan:
    project_name: str
    source: str
    target_stack: str
    output_root: str
    recommended_models: list[str]
    inventory: LegacyInventory
    security_actions: list[str]
    execution_actions: list[str]


def run_command(command: list[str], cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=str(cwd) if cwd else None, check=True)


def clone_repo(repo_url: str, destination: Path) -> Path:
    run_command(["git", "clone", "--depth", "1", repo_url, str(destination)])
    return destination


def create_venv(root: Path) -> Path:
    env_dir = root / ".venv"
    if env_dir.exists():
        return env_dir
    venv.create(env_dir, with_pip=True)
    return env_dir


def discover_files(source: Path) -> LegacyInventory:
    html = css = js = php = static = total = 0
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        total += 1
        ext = path.suffix.lower()
        if ext in HTML_EXTENSIONS:
            html += 1
        elif ext in CSS_EXTENSIONS:
            css += 1
        elif ext in JS_EXTENSIONS:
            js += 1
        elif ext in PHP_EXTENSIONS:
            php += 1
        if ext in STATIC_EXTENSIONS:
            static += 1
    return LegacyInventory(
        html_files=html,
        css_files=css,
        js_files=js,
        php_files=php,
        static_files=static,
        total_files=total,
    )


_HF_FALLBACK_MODELS = [
    "Qwen/Qwen2.5-Coder-32B-Instruct",
    "deepseek-ai/deepseek-coder-6.7b-instruct",
    "bigcode/starcoder2-15b",
    "codellama/CodeLlama-13b-Instruct-hf",
    "Salesforce/codet5p-220m",
]

_HF_CHAT_MODELS = [
    "Qwen/Qwen2.5-Coder-32B-Instruct",
    "meta-llama/Meta-Llama-3-8B-Instruct",
    "Qwen/Qwen3-Coder-480B-A35B-Instruct",
    "Qwen/Qwen2.5-7B-Instruct-1M",
]


def search_hf_models(query: str = "code generation python migration", limit: int = 5) -> list[str]:
    """Query Hugging Face Hub for models useful for code modernization.

    Falls back to a curated list when the hub is unreachable or
    huggingface_hub is not installed.
    """
    try:
        hub = importlib.import_module("huggingface_hub")
        results = list(
            hub.list_models(
                search=query,
                pipeline_tag="text-generation",
                sort="downloads",
                direction=-1,
                limit=limit,
            )
        )
        ids = [m.modelId for m in results if getattr(m, "modelId", None)]
        return ids if ids else _HF_FALLBACK_MODELS
    except Exception:
        return _HF_FALLBACK_MODELS


def recommend_models() -> list[str]:
    """Return HuggingFace model IDs suitable for code modernization tasks."""
    return search_hf_models()


def build_plan(project_name: str, source: Path, target_stack: str, output_root: Path) -> ModernizationPlan:
    inventory = discover_files(source)
    security_actions = [
        "Enable secure headers (CSP/HSTS/X-Frame-Options equivalent)",
        "Validate and sanitize migrated request inputs",
        "Move secrets to environment variables",
        "Generate dependency update guidance for target stack",
    ]
    execution_actions = [
        "Create target project scaffolding",
        "Copy templates and static assets",
        "Rewrite HTML asset links for target templating",
        "Translate PHP to Python (best effort) and store review notes",
        "Generate API starter routes and health endpoint",
        "Package output as zip if requested",
    ]

    return ModernizationPlan(
        project_name=project_name,
        source=str(source),
        target_stack=target_stack,
        output_root=str(output_root),
        recommended_models=recommend_models(),
        inventory=inventory,
        security_actions=security_actions,
        execution_actions=execution_actions,
    )


def save_plan(plan: ModernizationPlan, output_root: Path) -> Path:
    plan_path = output_root / "modernization_plan.json"
    output_root.mkdir(parents=True, exist_ok=True)
    with plan_path.open("w", encoding="utf-8") as f:
        json.dump(asdict(plan), f, indent=2)
    return plan_path


def should_copy(path: Path) -> bool:
    return path.is_file() and not any(part in SKIP_DIRS for part in path.parts)


def relativize(path: Path, base: Path) -> Path:
    return Path(os.path.relpath(path, base))


def _decode_legacy_text(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1252", "latin-1"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "\x00" in text and encoding not in {"utf-16", "utf-16-le", "utf-16-be"}:
            continue
        return text.replace("\r\n", "\n")
    return data.decode("utf-8", errors="ignore").replace("\r\n", "\n")


def read_legacy_text(path: Path) -> str:
    return _decode_legacy_text(path.read_bytes())


def _clean_llm_output(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_+-]*\n?", "", cleaned)
        cleaned = re.sub(r"\n```$", "", cleaned)
    return cleaned.strip()


def _looks_like_html(text: str) -> bool:
    stripped = text.strip().lower()
    if not stripped:
        return False
    return bool(re.search(r"</?[a-z][^>]*>", stripped))


def _looks_like_python(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    try:
        ast.parse(stripped)
        return True
    except SyntaxError:
        return False


def _split_url_suffix(value: str) -> tuple[str, str]:
    match = re.match(r"^([^?#]*)([?#].*)?$", value)
    if not match:
        return value, ""
    return match.group(1), match.group(2) or ""


_PAGE_HREF_RE = re.compile(
    r"(?P<prefix>\bhref\s*=\s*)(?P<quote>[\"'])(?P<value>[^\"']+)(?P=quote)",
    flags=re.IGNORECASE,
)


# Matches LLM-generated {% url 'name' %} tags inside href attributes
_LLM_URL_TAG_RE = re.compile(
    r"""\{%\s*url\s+['"]([^'"]+)['"]\s*%\}""",
)


def _strip_llm_url_tags(content: str) -> str:
    """Replace any LLM-generated {% url 'name' %} with plain URL paths."""

    def replace(match: re.Match[str]) -> str:
        name = match.group(1).strip().lower()
        if name in ("home", "index"):
            return "/"
        if not name.endswith(".html"):
            return "/" + name + ".html"
        return "/" + name

    return _LLM_URL_TAG_RE.sub(replace, content)


def _rewrite_page_links_for_django(content: str) -> str:
    """Convert local same-directory .html page hrefs to plain URL paths.

    index.html -> /, others stay as-is (routes match filenames).
    """

    def replace(match: re.Match[str]) -> str:
        value = match.group("value")
        if not value or value.startswith(("#", "//", "{{", "{%")):
            return match.group(0)
        if re.match(r"^[a-z][a-z0-9+.-]*:", value, flags=re.IGNORECASE):
            return match.group(0)
        path_part = re.split(r"[?#]", value)[0]
        suffix = value[len(path_part):]
        if Path(path_part).suffix.lower() != ".html":
            return match.group(0)
        if "/" in path_part or "\\" in path_part:
            return match.group(0)  # sub-directory link — leave as-is
        # index.html -> "/", others stay as-is (relative links work with our routes)
        if path_part.lower() == "index.html":
            return match.group("prefix") + match.group("quote") + "/" + suffix + match.group("quote")
        return match.group(0)

    return _PAGE_HREF_RE.sub(replace, content)


def _normalize_asset_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    normalized = normalized.lstrip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    while normalized.startswith("../"):
        normalized = normalized[3:]
    normalized = posixpath.normpath(normalized)
    if normalized in {"", "."}:
        return ""
    normalized = normalized.lstrip("/")
    if normalized.lower().startswith("static/"):
        normalized = normalized[7:]
    return normalized


def _is_static_asset_reference(value: str) -> bool:
    candidate = value.strip()
    if not candidate:
        return False
    if candidate.startswith(("#", "//", "{{", "{%")):
        return False
    if re.match(r"^[a-z][a-z0-9+.-]*:", candidate, flags=re.IGNORECASE):
        return False

    path_part, _ = _split_url_suffix(candidate)
    ext = Path(path_part).suffix.lower()
    return ext in STATIC_EXTENSIONS


def _rewrite_html_asset_attributes(content: str, transform: Callable[[str], str]) -> str:
    pattern = re.compile(
        r"""(?P<prefix>\b(?:href|src)\s*=\s*)(?P<quote>[\"'])(?P<value>[^\"']+)(?P=quote)""",
        flags=re.IGNORECASE,
    )

    def replace(match: re.Match[str]) -> str:
        value = match.group("value")
        if not _is_static_asset_reference(value):
            return match.group(0)
        path_part, suffix = _split_url_suffix(value)
        normalized = _normalize_asset_path(path_part)
        if not normalized:
            return match.group(0)
        rewritten = transform(normalized) + suffix
        return f'{match.group("prefix")}{match.group("quote")}{rewritten}{match.group("quote")}'

    return pattern.sub(replace, content)


def _get_llm_html_suggestions(html: str, target: str) -> str:
    """Use HuggingFace Inference API to modernize HTML. Falls back to heuristic."""
    client = _load_llm_for_conversion()
    if not client:
        return None

    try:
        prompt = (
            f"Rewrite this legacy HTML for {target.upper()} while preserving the same layout, text, and DOM structure.\n"
            f"Only change what is needed to make asset references and templating work in {target}.\n"
            f"Return the COMPLETE HTML document. Do not truncate or omit any sections.\n"
            f"Do not explain anything. Return only HTML.\n\n"
            f"HTML:\n{html}\n"
            f"Output ONLY the modernized HTML, no explanations:"
        )
        result = _clean_llm_output(_call_hf_inference(client, prompt))
        if _looks_like_html(result) and "error" not in result.lower():
            # Reject LLM output if it lost significant content (truncation guard)
            if len(result) < len(html) * 0.7:
                print(f"[WARN] LLM output too short ({len(result)} vs {len(html)} original). Falling back to heuristics.")
                return None
            return result
    except Exception:
        pass

    return None


def rewrite_html_for_django(content: str) -> str:
    """Rewrite page links and static refs for Django templates."""
    source = _get_llm_html_suggestions(content, "django") or content

    # Pass 0: strip any LLM-generated {% url 'xxx' %} tags → plain paths
    result = _strip_llm_url_tags(source)

    # Pass 1: convert index.html hrefs to "/"
    result = _rewrite_page_links_for_django(result)

    # Pass 2: rewrite static asset refs to {% static %} tags
    result = _rewrite_html_asset_attributes(
        result,
        lambda path: '{% static "' + _normalize_asset_path(path) + '" %}',
    )
    result = re.sub(
        r"\{[%]\s*static\s+(['\"])/?([^'\"]+)\1\s*[%]\}",
        lambda m: '{% static "' + _normalize_asset_path(m.group(2)) + '" %}',
        result,
    )
    if "{% load static %}" not in result:
        result = "{% load static %}\n" + result
    return result


def rewrite_html_for_fastapi(content: str) -> str:
    """Rewrite static refs to use Jinja2 url_for helper."""
    source = _get_llm_html_suggestions(content, "fastapi") or content

    result = _rewrite_html_asset_attributes(
        source,
        lambda path: f'{{{{ url_for("static", path="{_normalize_asset_path(path)}") }}}}',
    )
    result = re.sub(
        r"url_for\((['\"])static\1,\s*path=(['\"])/?([^'\"]+)\2\)",
        lambda m: f'url_for({m.group(1)}static{m.group(1)}, path={m.group(2)}{_normalize_asset_path(m.group(3))}{m.group(2)})',
        result,
    )
    return result


def rewrite_html_for_rust(content: str) -> str:
    """Prefix static refs with /static/ for Axum ServeDir mount."""
    source = _get_llm_html_suggestions(content, "rust") or content

    result = _rewrite_html_asset_attributes(
        source,
        lambda path: "/static/" + _normalize_asset_path(path),
    )
    result = re.sub(
        r"([=\"'])/static/+static/",
        lambda m: m.group(1) + "/static/",
        result,
    )
    return result


def _load_llm_for_conversion():
    """Load HuggingFace Inference Client for real API calls. Returns client or None."""
    try:
        import os

        from huggingface_hub import InferenceClient

        # Check for HF token
        hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        if not hf_token:
            print("[INFO] No HF_TOKEN set. LLM features disabled. Set HF_TOKEN to enable.")
            return None
        
        # Create client (auto-selects best provider)
        client = InferenceClient(api_key=hf_token)
        return client
    except ImportError:
        print("[WARN] huggingface_hub not installed. Install: pip install huggingface_hub")
        return None
    except Exception as e:
        print(f"[WARN] LLM init failed: {e}")
        return None


def _call_hf_inference(client, prompt: str, model: str = None) -> str:
    """Call HuggingFace Inference API for code generation.
    
    Gracefully fails - if LLM unavailable, returns empty string and
    calling code falls back to regex heuristics.
    """
    if not client:
        return ""

    models_to_try = [model] if model else _HF_CHAT_MODELS
    for candidate in models_to_try:
        try:
            message = client.chat.completions.create(
                model=candidate,
                messages=[{"role": "user", "content": prompt[:12000]}],
                max_tokens=4096,
                temperature=0.1,
            )
            if message.choices and len(message.choices) > 0:
                return _clean_llm_output(message.choices[0].message.content)
        except Exception:
            continue
    return ""


def convert_php_file(php_path: Path, py_path: Path) -> None:
    """Convert PHP to Python using HF LLM, then php2py, then fallback stub."""
    php_code = read_legacy_text(php_path)
    py_path.parent.mkdir(parents=True, exist_ok=True)

    # Try HuggingFace LLM first
    client = _load_llm_for_conversion()
    if client:
        try:
            prompt = (
                f"Convert this PHP code to well-formed Python that preserves the same behavior as closely as possible.\n"
                f"Output ONLY the Python code, no explanations.\n\n"
                f"PHP:\n{php_code[:4000]}\n\nPython:"
            )
            converted = _clean_llm_output(_call_hf_inference(client, prompt))
            if _looks_like_python(converted):
                py_path.write_text(converted, encoding="utf-8")
                return
        except Exception:
            pass

    # Fallback to php2py library
    if PHPTranslator is not None:
        try:
            python_code = PHPTranslator().from_php(php_code)
            py_path.write_text(python_code, encoding="utf-8")
            return
        except Exception:
            pass

    # Final fallback: generate stub for manual review
    stub = (
        "# Converted from PHP — Manual review needed!\n"
        "# Original PHP code preserved below for reference.\n\n"
        f"ORIGINAL_PHP = {json.dumps(php_code)}\n\n"
        "# TODO: Implement Python equivalent\n"
    )
    py_path.write_text(stub, encoding="utf-8")


def _patch_django_settings(project_root: Path, project_name: str) -> None:
    """Patch generated settings.py to wire templates dir and STATICFILES_DIRS."""
    settings_path = project_root / project_name / "settings.py"
    if not settings_path.exists():
        return
    content = settings_path.read_text(encoding="utf-8")
    content = content.replace("'DIRS': [],", "'DIRS': [BASE_DIR / 'templates'],")
    if "STATICFILES_DIRS" not in content:
        content += "\nSTATICFILES_DIRS = [BASE_DIR / 'static']\n"
    settings_path.write_text(content, encoding="utf-8")


def create_django_skeleton(destination: Path, project_name: str) -> Path:
    project_root = destination / f"{project_name}_django"
    pkg_dir = project_root / project_name

    # If already fully created (has settings.py), only (re-)patch settings and return.
    if (pkg_dir / "settings.py").exists():
        _patch_django_settings(project_root, project_name)
        return project_root

    project_root.mkdir(parents=True, exist_ok=True)

    django_available = importlib.util.find_spec("django") is not None

    try:
        if not django_available:
            raise RuntimeError("Django is not installed in the current interpreter")
        run_command([sys.executable, "-m", "django", "startproject", project_name, str(project_root)])
        _patch_django_settings(project_root, project_name)
    except Exception:
        # Fallback: generate a complete minimal Django project without django-admin.
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
        (pkg_dir / "settings.py").write_text(
            "from pathlib import Path\n\n"
            "BASE_DIR = Path(__file__).resolve().parent.parent\n\n"
            "SECRET_KEY = 'django-insecure-change-me-before-production'\n\n"
            "DEBUG = True\n\n"
            "ALLOWED_HOSTS = ['*']\n\n"
            "INSTALLED_APPS = [\n"
            "    'django.contrib.admin',\n"
            "    'django.contrib.auth',\n"
            "    'django.contrib.contenttypes',\n"
            "    'django.contrib.sessions',\n"
            "    'django.contrib.messages',\n"
            "    'django.contrib.staticfiles',\n"
            "]\n\n"
            "MIDDLEWARE = [\n"
            "    'django.middleware.security.SecurityMiddleware',\n"
            "    'django.contrib.sessions.middleware.SessionMiddleware',\n"
            "    'django.middleware.common.CommonMiddleware',\n"
            "    'django.middleware.csrf.CsrfViewMiddleware',\n"
            "    'django.contrib.auth.middleware.AuthenticationMiddleware',\n"
            "    'django.contrib.messages.middleware.MessageMiddleware',\n"
            "    'django.middleware.clickjacking.XFrameOptionsMiddleware',\n"
            "]\n\n"
            f"ROOT_URLCONF = '{project_name}.urls'\n\n"
            "TEMPLATES = [{\n"
            "    'BACKEND': 'django.template.backends.django.DjangoTemplates',\n"
            "    'DIRS': [BASE_DIR / 'templates'],\n"
            "    'APP_DIRS': True,\n"
            "    'OPTIONS': {\n"
            "        'context_processors': [\n"
            "            'django.template.context_processors.debug',\n"
            "            'django.template.context_processors.request',\n"
            "            'django.contrib.auth.context_processors.auth',\n"
            "            'django.contrib.messages.context_processors.messages',\n"
            "        ],\n"
            "    },\n"
            "}]\n\n"
            f"WSGI_APPLICATION = '{project_name}.wsgi.application'\n\n"
            "DATABASES = {\n"
            "    'default': {\n"
            "        'ENGINE': 'django.db.backends.sqlite3',\n"
            "        'NAME': BASE_DIR / 'db.sqlite3',\n"
            "    }\n"
            "}\n\n"
            "STATIC_URL = '/static/'\n"
            "STATICFILES_DIRS = [BASE_DIR / 'static']\n",
            encoding="utf-8",
        )
        (pkg_dir / "urls.py").write_text(
            "from django.contrib import admin\n"
            "from django.urls import path\n\n"
            "urlpatterns = [\n"
            "    path('admin/', admin.site.urls),\n"
            "]\n",
            encoding="utf-8",
        )
        (pkg_dir / "wsgi.py").write_text(
            "import os\n"
            "from django.core.wsgi import get_wsgi_application\n\n"
            f"os.environ.setdefault('DJANGO_SETTINGS_MODULE', '{project_name}.settings')\n\n"
            "application = get_wsgi_application()\n",
            encoding="utf-8",
        )
        (pkg_dir / "asgi.py").write_text(
            "import os\n"
            "from django.core.asgi import get_asgi_application\n\n"
            f"os.environ.setdefault('DJANGO_SETTINGS_MODULE', '{project_name}.settings')\n\n"
            "application = get_asgi_application()\n",
            encoding="utf-8",
        )
        (project_root / "manage.py").write_text(
            "#!/usr/bin/env python\n"
            "import os\n"
            "import sys\n\n"
            "def main():\n"
            f"    os.environ.setdefault('DJANGO_SETTINGS_MODULE', '{project_name}.settings')\n"
            "    try:\n"
            "        from django.core.management import execute_from_command_line\n"
            "    except ImportError as exc:\n"
            "        raise ImportError('Django is required to run this project') from exc\n"
            "    execute_from_command_line(sys.argv)\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n",
            encoding="utf-8",
        )
    (project_root / "requirements.txt").write_text(
        "django>=4.2\n",
        encoding="utf-8",
    )
    return project_root


def patch_django_urls(django_root: Path, project_name: str) -> None:
    """Generate urls.py with named TemplateView routes for every discovered HTML page."""
    template_dir = django_root / "templates"
    pkg_dir = django_root / project_name
    urls_path = pkg_dir / "urls.py"

    if not template_dir.exists() or not pkg_dir.exists():
        return

    html_pages = sorted(p.relative_to(template_dir) for p in template_dir.rglob("*.html"))
    if not html_pages:
        return

    lines = [
        "from django.contrib import admin",
        "from django.urls import path",
        "from django.views.generic import TemplateView",
        "",
        "urlpatterns = [",
        "    path('admin/', admin.site.urls),",
    ]

    seen_names: set[str] = set()
    for rel_path in html_pages:
        template_name = rel_path.as_posix()
        raw_name = re.sub(r"[^a-z0-9]", "_", rel_path.stem.lower())
        url_name = raw_name
        suffix = 0
        while url_name in seen_names:
            suffix += 1
            url_name = f"{raw_name}_{suffix}"
        seen_names.add(url_name)

        if template_name == "index.html":
            lines.append(f"    path('', TemplateView.as_view(template_name='{template_name}'), name='{url_name}'),")
        else:
            lines.append(f"    path('{template_name}', TemplateView.as_view(template_name='{template_name}'), name='{url_name}'),")

    lines.append("]")
    lines.append("")
    urls_path.write_text("\n".join(lines), encoding="utf-8")


def create_fastapi_skeleton(destination: Path, project_name: str) -> Path:
    root = destination / f"{project_name}_fastapi"
    app_dir = root / "app"
    templates_dir = app_dir / "templates"
    static_dir = app_dir / "static"
    app_dir.mkdir(parents=True, exist_ok=True)
    templates_dir.mkdir(parents=True, exist_ok=True)
    static_dir.mkdir(parents=True, exist_ok=True)

    (app_dir / "main.py").write_text(
        "from pathlib import Path\n\n"
        "from fastapi import FastAPI, HTTPException, Request\n"
        "from fastapi.middleware.trustedhost import TrustedHostMiddleware\n"
        "from fastapi.responses import HTMLResponse\n"
        "from fastapi.staticfiles import StaticFiles\n"
        "from fastapi.templating import Jinja2Templates\n"
        "from starlette.middleware.base import BaseHTTPMiddleware\n\n"
        "BASE_DIR = Path(__file__).resolve().parent\n"
        "app = FastAPI(title='Legacy Modernizer Output')\n"
        "templates = Jinja2Templates(directory=str(BASE_DIR / 'templates'))\n"
        "app.mount('/static', StaticFiles(directory=str(BASE_DIR / 'static')), name='static')\n\n"
        "class SecurityHeadersMiddleware(BaseHTTPMiddleware):\n"
        "    async def dispatch(self, request, call_next):\n"
        "        response = await call_next(request)\n"
        "        response.headers['X-Content-Type-Options'] = 'nosniff'\n"
        "        response.headers['X-Frame-Options'] = 'DENY'\n"
        "        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'\n"
        "        return response\n\n"
        "app.add_middleware(SecurityHeadersMiddleware)\n"
        "app.add_middleware(TrustedHostMiddleware, allowed_hosts=['*'])\n\n"
        "def resolve_template_name(template_path: str) -> str:\n"
        "    templates_root = (BASE_DIR / 'templates').resolve()\n"
        "    clean = template_path.strip('/')\n"
        "    candidates = ['index.html'] if not clean else []\n"
        "    if clean:\n"
        "        clean_path = Path(clean)\n"
        "        if clean_path.suffix:\n"
        "            candidates.append(clean)\n"
        "        else:\n"
        "            candidates.append(f'{clean}.html')\n"
        "            candidates.append(str(clean_path / 'index.html'))\n"
        "    for candidate in candidates:\n"
        "        resolved = (templates_root / candidate).resolve()\n"
        "        if templates_root not in resolved.parents and resolved != templates_root:\n"
        "            continue\n"
        "        if resolved.exists() and resolved.is_file():\n"
        "            return candidate.replace('\\\\', '/')\n"
        "    raise HTTPException(status_code=404, detail='Page not found')\n\n"
        "@app.get('/health')\n"
        "def health():\n"
        "    return {'status': 'ok'}\n\n"
        "@app.get('/', response_class=HTMLResponse)\n"
        "def index(request: Request):\n"
        "    return templates.TemplateResponse(request, 'index.html')\n\n"
        "@app.get('/{template_path:path}', response_class=HTMLResponse)\n"
        "def render_template_page(request: Request, template_path: str):\n"
        "    template_name = resolve_template_name(template_path)\n"
        "    return templates.TemplateResponse(request, template_name)\n",
        encoding="utf-8",
    )

    (root / "requirements.txt").write_text(
        "fastapi>=0.115.0\nuvicorn[standard]>=0.30.0\njinja2>=3.1.4\n",
        encoding="utf-8",
    )
    return root


def create_rust_skeleton(destination: Path, project_name: str) -> Path:
    """Generate a minimal Axum + Askama Rust project skeleton."""
    rust_name = re.sub(r"[^a-z0-9_]", "_", project_name.lower())
    root = destination / f"{project_name}_axum"
    src_dir = root / "src"
    for d in (src_dir, root / "templates", root / "static"):
        d.mkdir(parents=True, exist_ok=True)

    (root / "Cargo.toml").write_text(
        f'[package]\nname = "{rust_name}"\nversion = "0.1.0"\nedition = "2021"\n\n'
        "[dependencies]\n"
        'axum = "0.7"\n'
        'tokio = { version = "1", features = ["full"] }\n'
        'tower-http = { version = "0.5", features = ["fs", "set-header"] }\n'
        'serde_json = "1"\n',
        encoding="utf-8",
    )
    (src_dir / "routes.rs").write_text(
        "use axum::response::IntoResponse;\n"
        "use axum::Json;\n"
        "use serde_json::json;\n\n"
        "pub async fn health() -> impl IntoResponse {\n"
        '    Json(json!({"status": "ok"}))\n}\n',
        encoding="utf-8",
    )
    (src_dir / "main.rs").write_text(
        "mod routes;\n\n"
        "use axum::{routing::get, Router};\n"
        "use tower_http::services::ServeDir;\n"
        "use tower_http::set_header::SetResponseHeaderLayer;\n"
        "use axum::http::{header, HeaderValue};\n\n"
        "#[tokio::main]\n"
        "async fn main() {\n"
        "    let app = Router::new()\n"
        '        .route("/health", get(routes::health))\n'
        '        .nest_service("/static", ServeDir::new("static"))\n'
        "        // Serve all HTML pages from templates/ directory;\n"
        "        // index.html is served automatically for / requests\n"
        "        .fallback_service(\n"
        "            ServeDir::new(\"templates\").append_index_html_on_directories(true),\n"
        "        )\n"
        "        .layer(SetResponseHeaderLayer::if_not_present(\n"
        "            header::X_CONTENT_TYPE_OPTIONS,\n"
        '            HeaderValue::from_static("nosniff"),\n'
        "        ))\n"
        "        .layer(SetResponseHeaderLayer::if_not_present(\n"
        "            header::X_FRAME_OPTIONS,\n"
        '            HeaderValue::from_static("DENY"),\n'
        "        ));\n\n"
        '    let listener = tokio::net::TcpListener::bind("0.0.0.0:8000").await.unwrap();\n'
        '    println!("Listening on http://0.0.0.0:8000");\n'
        "    axum::serve(listener, app).await.unwrap();\n"
        "}\n",
        encoding="utf-8",
    )
    return root


def migrate_assets_to_target(source: Path, target_root: Path, mode: str) -> None:
    if mode == "django":
        template_root = target_root / "templates"
        static_root = target_root / "static"
    elif mode == "rust":
        template_root = target_root / "templates"
        static_root = target_root / "static"
    else:  # fastapi
        template_root = target_root / "app" / "templates"
        static_root = target_root / "app" / "static"

    template_root.mkdir(parents=True, exist_ok=True)
    static_root.mkdir(parents=True, exist_ok=True)

    for path in source.rglob("*"):
        if not should_copy(path):
            continue

        rel = relativize(path, source)
        ext = path.suffix.lower()

        if ext in HTML_EXTENSIONS:
            html = read_legacy_text(path)
            if mode == "django":
                html = rewrite_html_for_django(html)
            elif mode == "rust":
                html = rewrite_html_for_rust(html)
            else:
                html = rewrite_html_for_fastapi(html)
            destination = template_root / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(html, encoding="utf-8")
            # Ensure a default index.html exists for FastAPI/Rust default route.
            default_index = template_root / "index.html"
            if not default_index.exists() and mode in {"fastapi", "rust"}:
                default_index.write_text(html, encoding="utf-8")
        elif ext in PHP_EXTENSIONS:
            destination = target_root / "converted_php" / rel.with_suffix(".py")
            convert_php_file(path, destination)
        elif ext in STATIC_EXTENSIONS:
            destination = static_root / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            if ext in CSS_EXTENSIONS | JS_EXTENSIONS:
                destination.write_text(read_legacy_text(path), encoding="utf-8")
            else:
                shutil.copy2(path, destination)


def write_project_notes(output_root: Path, plan: ModernizationPlan) -> None:
    notes_path = output_root / "MODERNIZATION_NOTES.md"
    notes = [
        "# Modernization Notes",
        "",
        "## Recommended Hugging Face Models",
    ]
    notes.extend([f"- {item}" for item in plan.recommended_models])
    notes.append("")
    notes.append("## Security Checklist")
    notes.extend([f"- {item}" for item in plan.security_actions])
    notes.append("")
    notes.append("## Inventory")
    notes.append(f"- Total files scanned: {plan.inventory.total_files}")
    notes.append(f"- HTML files: {plan.inventory.html_files}")
    notes.append(f"- CSS files: {plan.inventory.css_files}")
    notes.append(f"- JS files: {plan.inventory.js_files}")
    notes.append(f"- PHP files: {plan.inventory.php_files}")
    notes_path.write_text("\n".join(notes) + "\n", encoding="utf-8")


def package_zip(output_root: Path, project_name: str) -> Path:
    zip_path = output_root / f"{project_name}_modernized.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output_root.rglob("*")):
            if not path.is_file() or path == zip_path:
                continue
            archive.write(path, arcname=path.relative_to(output_root).as_posix())
    return zip_path


def execute_plan(plan: ModernizationPlan, source: Path, create_zip: bool) -> None:
    output_root = Path(plan.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    if plan.target_stack in {"django", "dual"}:
        django_root = create_django_skeleton(output_root, plan.project_name)
        migrate_assets_to_target(source, django_root, mode="django")
        patch_django_urls(django_root, plan.project_name)

    if plan.target_stack in {"fastapi", "dual"}:
        fastapi_root = create_fastapi_skeleton(output_root, plan.project_name)
        migrate_assets_to_target(source, fastapi_root, mode="fastapi")

    if plan.target_stack == "rust":
        rust_root = create_rust_skeleton(output_root, plan.project_name)
        migrate_assets_to_target(source, rust_root, mode="rust")

    write_project_notes(output_root, plan)

    if create_zip:
        zip_path = package_zip(output_root, plan.project_name)
        print(f"Created zip package: {zip_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Modernize legacy web sources (HTML/CSS/JS/PHP) into Django and/or FastAPI projects "
            "with a planning-first workflow."
        )
    )
    parser.add_argument("--source", type=str, help="Path to local legacy website folder")
    parser.add_argument("--repo-url", type=str, help="Git repository URL containing legacy website")
    parser.add_argument("--project-name", type=str, default="modernized_site", help="Base name for generated projects")
    parser.add_argument(
        "--target",
        type=str,
        choices=["django", "fastapi", "dual", "rust"],
        default="dual",
        help="Target modern stack (rust generates an Axum + Askama skeleton)",
    )
    parser.add_argument("--output-root", type=str, default="output", help="Folder for generated projects")
    parser.add_argument("--plan-only", action="store_true", help="Generate plan and stop without execution")
    parser.add_argument("--zip", action="store_true", help="Create a downloadable zip package")
    parser.add_argument("--init-venv", action="store_true", help="Create .venv in current workspace")
    return parser.parse_args()


def resolve_source(args: argparse.Namespace) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    if args.source:
        source = Path(args.source).resolve()
        if not source.exists() or not source.is_dir():
            raise ValueError(f"Source directory does not exist: {source}")
        return source, None

    if args.repo_url:
        temp_dir = tempfile.TemporaryDirectory(prefix="legacy_repo_")
        repo_path = Path(temp_dir.name) / "repo"
        clone_repo(args.repo_url, repo_path)
        return repo_path, temp_dir

    raise ValueError("You must provide either --source or --repo-url")


def main() -> None:
    args = parse_args()

    if args.init_venv:
        env_path = create_venv(Path.cwd())
        print(f"Created virtual environment at: {env_path}")

    source = None
    temp_dir = None
    try:
        source, temp_dir = resolve_source(args)
        output_root = Path(args.output_root).resolve()

        plan = build_plan(
            project_name=args.project_name,
            source=source,
            target_stack=args.target,
            output_root=output_root,
        )
        plan_path = save_plan(plan, output_root)
        print(f"Planning complete. Plan file: {plan_path}")

        if args.plan_only:
            print("Plan-only mode selected. Skipping execution.")
            return

        execute_plan(plan, source=source, create_zip=args.zip)
        print(f"Modernization complete. Output folder: {output_root}")
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


if __name__ == "__main__":
    main()
