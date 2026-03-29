"""Comprehensive tests for Legacy Web Modernizer (auto.py).

Covers: discover_files, HTML rewriting (all targets), PHP conversion, skeleton
creation, asset migration, plan building, zip packaging, execute_plan, and a
thorough collection of edge-case inputs.
"""

import ast
import json
import zipfile
from pathlib import Path
from typing import Mapping, Union

import pytest

import auto

# ─────────────────────────── helpers ──────────────────────────────────────────


def make_legacy(tmp_path: Path, files: Mapping[str, Union[str, bytes]]) -> Path:
    """Create a 'legacy' source directory with the supplied file tree."""
    src = tmp_path / "legacy"
    src.mkdir(exist_ok=True)
    for rel, content in files.items():
        dest = src / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            dest.write_bytes(content)
        else:
            dest.write_text(str(content), encoding="utf-8")
    return src


# ─────────────────────────── discover_files ───────────────────────────────────


class TestDiscoverFiles:
    def test_empty_directory(self, tmp_path):
        inv = auto.discover_files(tmp_path)
        assert inv.total_files == 0
        assert inv.html_files == 0

    def test_counts_html_and_htm(self, tmp_path):
        (tmp_path / "index.html").write_text("<html></html>")
        (tmp_path / "about.htm").write_text("<html></html>")
        inv = auto.discover_files(tmp_path)
        assert inv.html_files == 2

    def test_counts_all_types(self, tmp_path):
        src = make_legacy(tmp_path, {
            "index.html": "<html></html>",
            "style.css": "body{}",
            "app.js": "console.log(1)",
            "login.php": "<?php echo 'x'; ?>",
        })
        inv = auto.discover_files(src)
        assert inv.html_files == 1
        assert inv.css_files == 1
        assert inv.js_files == 1
        assert inv.php_files == 1
        assert inv.total_files == 4

    def test_skips_git_dir(self, tmp_path):
        git = tmp_path / ".git"
        git.mkdir()
        (git / "config").write_text("...")
        (tmp_path / "index.html").write_text("<html></html>")
        inv = auto.discover_files(tmp_path)
        assert inv.total_files == 1

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules"
        nm.mkdir()
        (nm / "jquery.js").write_text("/* jQuery */")
        (tmp_path / "index.html").write_text("<html></html>")
        inv = auto.discover_files(tmp_path)
        assert inv.total_files == 1

    def test_skips_venv(self, tmp_path):
        vd = tmp_path / ".venv"
        vd.mkdir()
        (vd / "pyvenv.cfg").write_text("home = /usr")
        (tmp_path / "page.html").write_text("<html></html>")
        inv = auto.discover_files(tmp_path)
        assert inv.total_files == 1

    def test_nested_directories(self, tmp_path):
        deep = tmp_path / "sections" / "blog" / "2024"
        deep.mkdir(parents=True)
        (deep / "post.html").write_text("<html>Post</html>")
        (tmp_path / "index.html").write_text("<html>Home</html>")
        inv = auto.discover_files(tmp_path)
        assert inv.html_files == 2

    def test_all_static_extensions_are_counted(self, tmp_path):
        for ext in [".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg",
                    ".webp", ".ico", ".woff", ".woff2", ".ttf", ".eot"]:
            (tmp_path / f"asset{ext}").write_bytes(b"data")
        inv = auto.discover_files(tmp_path)
        assert inv.static_files == 13  # all listed extensions

    def test_phtml_counts_as_php(self, tmp_path):
        (tmp_path / "widget.phtml").write_text("<?php echo 1; ?>")
        inv = auto.discover_files(tmp_path)
        assert inv.php_files == 1

    def test_unknown_extensions_in_total_only(self, tmp_path):
        (tmp_path / "readme.txt").write_text("hello")
        (tmp_path / "data.xml").write_text("<data/>")
        inv = auto.discover_files(tmp_path)
        assert inv.total_files == 2
        assert inv.html_files == 0
        assert inv.css_files == 0


# ─────────────────────────── HTML rewriting – Django ──────────────────────────


class TestRewriteHtmlForDjango:
    def test_css_href_rewritten(self):
        html = '<link rel="stylesheet" href="/css/site.css">'
        result = auto.rewrite_html_for_django(html)
        assert '{% static "css/site.css" %}' in result
        assert "/css/site.css" not in result

    def test_js_src_rewritten(self):
        html = '<script src="/js/app.js"></script>'
        result = auto.rewrite_html_for_django(html)
        assert '{% static "js/app.js" %}' in result
        assert "/js/app.js" not in result

    def test_img_src_rewritten(self):
        html = '<img src="/images/logo.png" alt="logo">'
        result = auto.rewrite_html_for_django(html)
        assert '{% static "images/logo.png" %}' in result

    def test_favicon_rewritten(self):
        html = '<link rel="icon" href="/favicon.ico">'
        result = auto.rewrite_html_for_django(html)
        assert '{% static "favicon.ico" %}' in result

    def test_woff2_rewritten(self):
        html = '<link rel="preload" href="/fonts/inter.woff2" as="font">'
        result = auto.rewrite_html_for_django(html)
        assert '{% static "fonts/inter.woff2" %}' in result

    def test_external_https_url_not_rewritten(self):
        html = '<script src="https://cdn.example.com/jquery.min.js"></script>'
        result = auto.rewrite_html_for_django(html)
        assert "https://cdn.example.com/jquery.min.js" in result
        assert "{% static" not in result

    def test_relative_static_url_rewritten(self):
        html = '<link rel="stylesheet" href="css/style.css">'
        result = auto.rewrite_html_for_django(html)
        assert '{% static "css/style.css" %}' in result

    def test_relative_page_link_not_rewritten_for_django(self):
        html = '<a href="generic.html">Generic</a>'
        result = auto.rewrite_html_for_django(html)
        assert 'href="generic.html"' in result

    def test_index_page_link_rewritten_to_root(self):
        html = '<a href="index.html">Home</a>'
        result = auto.rewrite_html_for_django(html)
        assert 'href="/"' in result
        assert 'index.html' not in result

    def test_llm_url_tag_home_stripped(self):
        html = '<a href="{% url \'home\' %}">Home</a>'
        result = auto.rewrite_html_for_django(html)
        assert '{% url' not in result
        assert 'href="/"' in result

    def test_llm_url_tag_generic_stripped(self):
        html = '<a href="{% url \'generic\' %}">Page</a>'
        result = auto.rewrite_html_for_django(html)
        assert '{% url' not in result
        assert '/generic.html' in result

    def test_subdir_page_link_not_rewritten(self):
        html = '<a href="sub/page.html">Page</a>'
        result = auto.rewrite_html_for_django(html)
        assert 'href="sub/page.html"' in result

    def test_anchor_link_not_rewritten(self):
        html = '<a href="#section">Jump</a>'
        result = auto.rewrite_html_for_django(html)
        assert 'href="#section"' in result

    def test_load_static_added_when_static_refs_present(self):
        html = '<link href="/style.css"><script src="/app.js"></script>'
        result = auto.rewrite_html_for_django(html)
        assert "{% load static %}" in result

    def test_load_static_added_even_with_no_static_refs(self):
        html = "<html><body><h1>Hello</h1></body></html>"
        result = auto.rewrite_html_for_django(html)
        assert "{% load static %}" in result

    def test_load_static_not_duplicated(self):
        html = "{% load static %}\n<link href='/a.css'>"
        result = auto.rewrite_html_for_django(html)
        assert result.count("{% load static %}") == 1

    def test_multiple_assets_all_rewritten(self):
        html = (
            '<link href="/style/main.css">'
            '<script src="/scripts/bundle.js"></script>'
            '<img src="/img/hero.png">'
        )
        result = auto.rewrite_html_for_django(html)
        assert '{% static "style/main.css" %}' in result
        assert '{% static "scripts/bundle.js" %}' in result
        assert '{% static "img/hero.png" %}' in result

    def test_single_quoted_attrs(self):
        html = "<link href='/css/app.css'>"
        result = auto.rewrite_html_for_django(html)
        assert "{% static" in result
        assert "css/app.css" in result

    def test_leading_slash_stripped_from_path(self):
        html = '<link href="/css/site.css">'
        result = auto.rewrite_html_for_django(html)
        assert '{% static "css/site.css" %}' in result  # no leading /


# ─────────────────────────── HTML rewriting – FastAPI ─────────────────────────


class TestRewriteHtmlForFastapi:
    def test_css_href_rewritten(self):
        html = '<link rel="stylesheet" href="/css/site.css">'
        result = auto.rewrite_html_for_fastapi(html)
        assert 'url_for("static"' in result
        assert 'path="css/site.css"' in result

    def test_js_src_rewritten(self):
        html = '<script src="/js/bundle.js"></script>'
        result = auto.rewrite_html_for_fastapi(html)
        assert 'url_for("static"' in result
        assert 'path="js/bundle.js"' in result

    def test_img_src_rewritten(self):
        html = '<img src="/images/banner.jpg">'
        result = auto.rewrite_html_for_fastapi(html)
        assert 'url_for("static"' in result
        assert "images/banner.jpg" in result

    def test_external_url_not_rewritten(self):
        html = '<script src="https://cdn.example.com/react.js"></script>'
        result = auto.rewrite_html_for_fastapi(html)
        assert "https://cdn.example.com/react.js" in result
        assert "url_for" not in result

    def test_relative_static_url_rewritten(self):
        html = '<link href="styles/app.css">'
        result = auto.rewrite_html_for_fastapi(html)
        assert 'url_for("static"' in result
        assert 'path="styles/app.css"' in result

    def test_relative_page_link_not_rewritten(self):
        html = '<a href="generic.html">Generic</a>'
        result = auto.rewrite_html_for_fastapi(html)
        assert 'href="generic.html"' in result
        assert 'url_for("static"' not in result

    def test_multiple_assets(self):
        html = '<link href="/a.css"><script src="/b.js"><img src="/c.png">'
        result = auto.rewrite_html_for_fastapi(html)
        assert result.count("url_for") == 3


# ─────────────────────────── HTML rewriting – Rust ────────────────────────────


class TestRewriteHtmlForRust:
    def test_css_href_prefixed_with_static(self):
        html = '<link rel="stylesheet" href="/css/site.css">'
        result = auto.rewrite_html_for_rust(html)
        assert 'href="/static/css/site.css"' in result

    def test_js_src_prefixed(self):
        html = '<script src="/js/app.js"></script>'
        result = auto.rewrite_html_for_rust(html)
        assert 'src="/static/js/app.js"' in result

    def test_img_src_prefixed(self):
        html = '<img src="/img/logo.png">'
        result = auto.rewrite_html_for_rust(html)
        assert 'src="/static/img/logo.png"' in result

    def test_already_static_path_not_double_prefixed(self):
        html = '<link href="/static/css/app.css">'
        result = auto.rewrite_html_for_rust(html)
        assert "/static/static/" not in result
        assert "/static/css/app.css" in result

    def test_external_https_url_not_prefixed(self):
        html = '<script src="https://cdn.com/react.js"></script>'
        result = auto.rewrite_html_for_rust(html)
        assert "https://cdn.com/react.js" in result
        assert "/static/https" not in result

    def test_relative_static_url_prefixed(self):
        html = '<link href="css/style.css">'
        result = auto.rewrite_html_for_rust(html)
        assert 'href="/static/css/style.css"' in result

    def test_relative_page_link_not_prefixed(self):
        html = '<a href="generic.html">Generic</a>'
        result = auto.rewrite_html_for_rust(html)
        assert 'href="generic.html"' in result
        assert '/static/generic.html' not in result


# ─────────────────────────── PHP conversion ───────────────────────────────────


class TestConvertPhpFile:
    def test_stub_generated_when_no_translator(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auto, "PHPTranslator", None)
        php_path = tmp_path / "login.php"
        php_path.write_text("<?php echo 'Hello'; ?>")
        py_path = tmp_path / "login.py"
        auto.convert_php_file(php_path, py_path)
        content = py_path.read_text(encoding="utf-8")
        assert "Converted from PHP" in content or "Manual review" in content
        assert "<?php echo 'Hello'; ?>" in content

    def test_stub_is_valid_python(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auto, "PHPTranslator", None)
        php_path = tmp_path / "calc.php"
        php_path.write_text("<?php\n$x = 42;\necho $x;\n?>")
        py_path = tmp_path / "calc.py"
        auto.convert_php_file(php_path, py_path)
        content = py_path.read_text(encoding="utf-8")
        ast.parse(content)  # raises SyntaxError if invalid

    def test_stub_safe_with_triple_double_quotes(self, tmp_path, monkeypatch):
        """json.dumps encoding must survive triple-quote PHP strings."""
        monkeypatch.setattr(auto, "PHPTranslator", None)
        php_path = tmp_path / "tricky.php"
        php_path.write_text('<?php echo """triple"""; ?>')
        py_path = tmp_path / "tricky.py"
        auto.convert_php_file(php_path, py_path)
        content = py_path.read_text(encoding="utf-8")
        ast.parse(content)  # must be valid Python

    def test_stub_safe_with_backslashes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auto, "PHPTranslator", None)
        php_path = tmp_path / "path.php"
        php_path.write_text('<?php echo "C:\\\\Users\\\\Admin"; ?>')
        py_path = tmp_path / "path.py"
        auto.convert_php_file(php_path, py_path)
        ast.parse(py_path.read_text(encoding="utf-8"))

    def test_creates_parent_directories(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auto, "PHPTranslator", None)
        php_path = tmp_path / "page.php"
        php_path.write_text("<?php echo 1; ?>")
        nested_py = tmp_path / "output" / "deep" / "page.py"
        auto.convert_php_file(php_path, nested_py)
        assert nested_py.exists()

    def test_utf16_php_stub_preserves_original_text_without_nuls(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auto, "PHPTranslator", None)
        php_path = tmp_path / "utf16.php"
        php_path.write_bytes('<?php echo "Hello"; ?>'.encode("utf-16"))
        py_path = tmp_path / "utf16.py"
        auto.convert_php_file(php_path, py_path)
        content = py_path.read_text(encoding="utf-8")
        assert "Hello" in content
        assert "\\u0000" not in content


# ─────────────────────────── FastAPI skeleton ─────────────────────────────────


class TestCreateFastapiSkeleton:
    def test_creates_main_py(self, tmp_path):
        root = auto.create_fastapi_skeleton(tmp_path, "myapp")
        assert (root / "app" / "main.py").exists()

    def test_creates_requirements_txt(self, tmp_path):
        root = auto.create_fastapi_skeleton(tmp_path, "myapp")
        req = root / "requirements.txt"
        assert req.exists()
        content = req.read_text()
        assert "fastapi" in content
        assert "uvicorn" in content
        assert "jinja2" in content

    def test_creates_templates_dir(self, tmp_path):
        root = auto.create_fastapi_skeleton(tmp_path, "myapp")
        assert (root / "app" / "templates").is_dir()

    def test_creates_static_dir(self, tmp_path):
        root = auto.create_fastapi_skeleton(tmp_path, "myapp")
        assert (root / "app" / "static").is_dir()

    def test_main_py_has_security_middleware(self, tmp_path):
        root = auto.create_fastapi_skeleton(tmp_path, "myapp")
        main_py = (root / "app" / "main.py").read_text()
        assert "SecurityHeadersMiddleware" in main_py
        assert "X-Content-Type-Options" in main_py
        assert "X-Frame-Options" in main_py

    def test_main_py_has_health_endpoint(self, tmp_path):
        root = auto.create_fastapi_skeleton(tmp_path, "myapp")
        assert "/health" in (root / "app" / "main.py").read_text()

    def test_root_folder_name(self, tmp_path):
        root = auto.create_fastapi_skeleton(tmp_path, "coolsite")
        assert root.name == "coolsite_fastapi"

    def test_main_py_has_catch_all_template_route(self, tmp_path):
        root = auto.create_fastapi_skeleton(tmp_path, "myapp")
        main_py = (root / "app" / "main.py").read_text()
        assert "/{template_path:path}" in main_py
        assert "resolve_template_name" in main_py

    def test_main_py_uses_current_template_response_signature(self, tmp_path):
        root = auto.create_fastapi_skeleton(tmp_path, "myapp")
        main_py = (root / "app" / "main.py").read_text()
        assert "TemplateResponse(request, 'index.html')" in main_py


# ─────────────────────────── Django skeleton ──────────────────────────────────


class TestCreateDjangoSkeleton:
    def test_creates_manage_py(self, tmp_path):
        root = auto.create_django_skeleton(tmp_path, "myapp")
        assert (root / "manage.py").exists()

    def test_project_root_folder_name(self, tmp_path):
        root = auto.create_django_skeleton(tmp_path, "coolsite")
        assert root.name == "coolsite_django"


# ─────────────────────────── Rust skeleton ────────────────────────────────────


class TestCreateRustSkeleton:
    def test_creates_cargo_toml(self, tmp_path):
        root = auto.create_rust_skeleton(tmp_path, "myapp")
        assert (root / "Cargo.toml").exists()

    def test_cargo_toml_has_axum_and_tokio(self, tmp_path):
        root = auto.create_rust_skeleton(tmp_path, "myapp")
        content = (root / "Cargo.toml").read_text()
        assert "axum" in content
        assert "tokio" in content

    def test_creates_main_rs(self, tmp_path):
        root = auto.create_rust_skeleton(tmp_path, "myapp")
        assert (root / "src" / "main.rs").exists()

    def test_creates_routes_rs(self, tmp_path):
        root = auto.create_rust_skeleton(tmp_path, "myapp")
        assert (root / "src" / "routes.rs").exists()

    def test_creates_templates_dir(self, tmp_path):
        root = auto.create_rust_skeleton(tmp_path, "myapp")
        assert (root / "templates").is_dir()

    def test_creates_static_dir(self, tmp_path):
        root = auto.create_rust_skeleton(tmp_path, "myapp")
        assert (root / "static").is_dir()

    def test_root_folder_name(self, tmp_path):
        root = auto.create_rust_skeleton(tmp_path, "coolsite")
        assert root.name == "coolsite_axum"

    def test_package_name_sanitized_for_cargo(self, tmp_path):
        root = auto.create_rust_skeleton(tmp_path, "My Cool-Site!")
        cargo = (root / "Cargo.toml").read_text()
        # Cargo package name must be lowercase snake_case characters only
        import re
        name_match = re.search(r'name\s*=\s*"([^"]+)"', cargo)
        assert name_match
        pkg_name = name_match.group(1)
        assert re.fullmatch(r"[a-z0-9_]+", pkg_name)

    def test_main_rs_has_health_route(self, tmp_path):
        root = auto.create_rust_skeleton(tmp_path, "myapp")
        main_rs = (root / "src" / "main.rs").read_text()
        assert '"/health"' in main_rs

    def test_main_rs_has_security_headers(self, tmp_path):
        root = auto.create_rust_skeleton(tmp_path, "myapp")
        main_rs = (root / "src" / "main.rs").read_text()
        assert "X_CONTENT_TYPE_OPTIONS" in main_rs
        assert "X_FRAME_OPTIONS" in main_rs


# ─────────────────────────── asset migration ──────────────────────────────────


class TestMigrateAssetsToTarget:
    def test_html_goes_to_fastapi_templates(self, tmp_path):
        src = make_legacy(tmp_path, {"index.html": "<html><body>Hi</body></html>"})
        dst = tmp_path / "project_fastapi"
        auto.migrate_assets_to_target(src, dst, mode="fastapi")
        assert (dst / "app" / "templates" / "index.html").exists()

    def test_css_goes_to_fastapi_static(self, tmp_path):
        src = make_legacy(tmp_path, {"style.css": "body{}"})
        dst = tmp_path / "proj_fastapi"
        auto.migrate_assets_to_target(src, dst, mode="fastapi")
        assert (dst / "app" / "static" / "style.css").exists()

    def test_js_goes_to_fastapi_static(self, tmp_path):
        src = make_legacy(tmp_path, {"app.js": "console.log(1)"})
        dst = tmp_path / "proj_fastapi"
        auto.migrate_assets_to_target(src, dst, mode="fastapi")
        assert (dst / "app" / "static" / "app.js").exists()

    def test_php_goes_to_converted_php(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auto, "PHPTranslator", None)
        src = make_legacy(tmp_path, {"login.php": "<?php echo 'x'; ?>"})
        dst = tmp_path / "proj_fastapi"
        auto.migrate_assets_to_target(src, dst, mode="fastapi")
        assert (dst / "converted_php" / "login.py").exists()

    def test_binary_image_copied_correctly(self, tmp_path):
        original = b"\x89PNG\r\n\x1a\n" + bytes(range(200))
        src = make_legacy(tmp_path, {"logo.png": original})
        dst = tmp_path / "proj_fastapi"
        auto.migrate_assets_to_target(src, dst, mode="fastapi")
        assert (dst / "app" / "static" / "logo.png").read_bytes() == original

    def test_nested_html_preserved_in_templates(self, tmp_path):
        src = make_legacy(tmp_path, {"pages/about.html": "<html>About</html>"})
        dst = tmp_path / "proj_fastapi"
        auto.migrate_assets_to_target(src, dst, mode="fastapi")
        assert (dst / "app" / "templates" / "pages" / "about.html").exists()

    def test_html_rewritten_for_django(self, tmp_path):
        src = make_legacy(tmp_path, {"index.html": '<link href="/css/app.css">'})
        dst = tmp_path / "proj_django"
        auto.migrate_assets_to_target(src, dst, mode="django")
        files = list(dst.rglob("index.html"))
        assert files
        assert "{% static" in files[0].read_text()

    def test_html_rewritten_for_fastapi(self, tmp_path):
        src = make_legacy(tmp_path, {"index.html": '<link href="/css/app.css">'})
        dst = tmp_path / "proj_fastapi"
        auto.migrate_assets_to_target(src, dst, mode="fastapi")
        content = (dst / "app" / "templates" / "index.html").read_text()
        assert "url_for" in content

    def test_relative_assets_are_rewritten_for_fastapi(self, tmp_path):
        src = make_legacy(
            tmp_path,
            {
                "index.html": '<link href="assets/css/main.css"><img src="images/logo.png">',
                "assets/css/main.css": "body{}",
                "images/logo.png": b"\x89PNG\r\n\x1a\n",
            },
        )
        dst = tmp_path / "proj_fastapi"
        auto.migrate_assets_to_target(src, dst, mode="fastapi")
        content = (dst / "app" / "templates" / "index.html").read_text(encoding="utf-8")
        assert 'url_for("static", path="assets/css/main.css")' in content
        assert 'url_for("static", path="images/logo.png")' in content
        assert (dst / "app" / "static" / "assets" / "css" / "main.css").exists()
        assert (dst / "app" / "static" / "images" / "logo.png").exists()

    def test_html_rewritten_for_rust(self, tmp_path):
        src = make_legacy(tmp_path, {"index.html": '<link href="/css/app.css">'})
        dst = tmp_path / "proj_axum"
        auto.migrate_assets_to_target(src, dst, mode="rust")
        content = (dst / "templates" / "index.html").read_text()
        assert "/static/css/app.css" in content

    def test_fastapi_default_index_created(self, tmp_path):
        src = make_legacy(tmp_path, {"about.html": "<html>About</html>"})
        dst = tmp_path / "proj_fastapi"
        auto.migrate_assets_to_target(src, dst, mode="fastapi")
        assert (dst / "app" / "templates" / "index.html").exists()

    def test_git_dir_skipped(self, tmp_path):
        src = make_legacy(tmp_path, {"index.html": "<html></html>"})
        (src / ".git").mkdir()
        (src / ".git" / "secret").write_text("secret data")
        dst = tmp_path / "proj_fastapi"
        auto.migrate_assets_to_target(src, dst, mode="fastapi")
        assert not list(dst.rglob("secret"))

    def test_rust_html_goes_to_templates(self, tmp_path):
        src = make_legacy(tmp_path, {"index.html": "<html></html>"})
        dst = tmp_path / "proj_axum"
        auto.migrate_assets_to_target(src, dst, mode="rust")
        assert (dst / "templates" / "index.html").exists()

    def test_rust_static_goes_to_static(self, tmp_path):
        src = make_legacy(tmp_path, {"style.css": "body{}"})
        dst = tmp_path / "proj_axum"
        auto.migrate_assets_to_target(src, dst, mode="rust")
        assert (dst / "static" / "style.css").exists()

    def test_utf16_html_is_decoded_and_rewritten(self, tmp_path):
        src = make_legacy(tmp_path, {
            "index.html": '<link href="/css/app.css"><img src="/img/logo.png">'.encode("utf-16"),
        })
        dst = tmp_path / "proj_fastapi"
        auto.migrate_assets_to_target(src, dst, mode="fastapi")
        content = (dst / "app" / "templates" / "index.html").read_text(encoding="utf-8")
        assert "\x00" not in content
        assert 'url_for("static", path="css/app.css")' in content
        assert 'url_for("static", path="img/logo.png")' in content

    def test_utf16_css_is_normalized_to_utf8(self, tmp_path):
        src = make_legacy(tmp_path, {
            "style.css": "body{color:red}".encode("utf-16"),
        })
        dst = tmp_path / "proj_fastapi"
        auto.migrate_assets_to_target(src, dst, mode="fastapi")
        content = (dst / "app" / "static" / "style.css").read_text(encoding="utf-8")
        assert content == "body{color:red}"


# ─────────────────────────── build_plan ───────────────────────────────────────


class TestBuildPlan:
    def test_returns_correct_inventory(self, tmp_path):
        src = make_legacy(tmp_path, {
            "index.html": "<html></html>",
            "style.css": "body{}",
            "login.php": "<?php ?>",
        })
        plan = auto.build_plan("mysite", src, "dual", tmp_path / "out")
        assert plan.inventory.html_files == 1
        assert plan.inventory.css_files == 1
        assert plan.inventory.php_files == 1

    def test_project_name_stored(self, tmp_path):
        src = make_legacy(tmp_path, {"x.html": "<html/>"})
        plan = auto.build_plan("mysite", src, "fastapi", tmp_path / "out")
        assert plan.project_name == "mysite"

    def test_recommended_models_list_not_empty(self, tmp_path):
        src = make_legacy(tmp_path, {"x.html": "<html/>"})
        plan = auto.build_plan("mysite", src, "fastapi", tmp_path / "o")
        assert len(plan.recommended_models) > 0

    def test_security_actions_not_empty(self, tmp_path):
        src = make_legacy(tmp_path, {"x.html": "<html/>"})
        plan = auto.build_plan("mysite", src, "django", tmp_path / "o")
        assert len(plan.security_actions) > 0

    def test_plan_is_json_serialisable(self, tmp_path):
        src = make_legacy(tmp_path, {"x.html": "<html/>"})
        plan = auto.build_plan("mysite", src, "dual", tmp_path / "o")
        from dataclasses import asdict
        data = asdict(plan)
        round_tripped = json.loads(json.dumps(data))
        assert round_tripped["project_name"] == "mysite"


class TestSavePlan:
    def test_creates_json_file(self, tmp_path):
        src = make_legacy(tmp_path, {"x.html": "<html/>"})
        out = tmp_path / "output"
        plan = auto.build_plan("demo", src, "dual", out)
        plan_path = auto.save_plan(plan, out)
        assert plan_path.exists()
        data = json.loads(plan_path.read_text())
        assert data["project_name"] == "demo"

    def test_creates_output_dir_when_missing(self, tmp_path):
        src = make_legacy(tmp_path, {"x.html": "<html/>"})
        out = tmp_path / "does" / "not" / "exist"
        plan = auto.build_plan("demo", src, "fastapi", out)
        auto.save_plan(plan, out)
        assert out.is_dir()


# ─────────────────────────── package_zip ──────────────────────────────────────


class TestPackageZip:
    def test_creates_zip_file(self, tmp_path):
        out = tmp_path / "output"
        out.mkdir()
        (out / "file.txt").write_text("hello")
        zip_path = auto.package_zip(out, "myproject")
        assert zip_path.exists()
        assert zip_path.suffix == ".zip"

    def test_zip_contains_files(self, tmp_path):
        out = tmp_path / "output"
        out.mkdir()
        (out / "notes.md").write_text("# Notes")
        zip_path = auto.package_zip(out, "demo")
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert any("notes.md" in n for n in names)

    def test_zip_readable(self, tmp_path):
        out = tmp_path / "output"
        out.mkdir()
        (out / "readme.txt").write_text("content")
        zip_path = auto.package_zip(out, "demo")
        with zipfile.ZipFile(zip_path) as zf:
            assert zf.testzip() is None  # no corrupt entries

    def test_zip_does_not_include_itself(self, tmp_path):
        out = tmp_path / "output"
        out.mkdir()
        (out / "notes.md").write_text("# Notes")
        zip_path = auto.package_zip(out, "demo")
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert zip_path.name not in names


# ─────────────────────────── execute_plan ─────────────────────────────────────


class TestExecutePlan:
    def test_fastapi_output_created(self, tmp_path):
        src = make_legacy(tmp_path, {
            "index.html": "<html><body>Home</body></html>",
            "style.css": "body{margin:0}",
            "app.js": "console.log(1)",
        })
        out = tmp_path / "output"
        plan = auto.build_plan("testapp", src, "fastapi", out)
        auto.execute_plan(plan, source=src, create_zip=False)
        assert (out / "testapp_fastapi").is_dir()
        assert (out / "testapp_fastapi" / "app" / "main.py").exists()

    def test_django_output_created(self, tmp_path):
        src = make_legacy(tmp_path, {"index.html": "<html></html>"})
        out = tmp_path / "output"
        plan = auto.build_plan("testapp", src, "django", out)
        auto.execute_plan(plan, source=src, create_zip=False)
        assert (out / "testapp_django").is_dir()

    def test_dual_creates_both_targets(self, tmp_path):
        src = make_legacy(tmp_path, {"index.html": "<html></html>"})
        out = tmp_path / "output"
        plan = auto.build_plan("testapp", src, "dual", out)
        auto.execute_plan(plan, source=src, create_zip=False)
        assert (out / "testapp_fastapi").is_dir()
        assert (out / "testapp_django").is_dir()

    def test_rust_output_created(self, tmp_path):
        src = make_legacy(tmp_path, {"index.html": "<html></html>"})
        out = tmp_path / "output"
        plan = auto.build_plan("testapp", src, "rust", out)
        auto.execute_plan(plan, source=src, create_zip=False)
        assert (out / "testapp_axum").is_dir()
        assert (out / "testapp_axum" / "Cargo.toml").exists()

    def test_zip_created_when_requested(self, tmp_path):
        src = make_legacy(tmp_path, {"index.html": "<html></html>"})
        out = tmp_path / "output"
        plan = auto.build_plan("testapp", src, "fastapi", out)
        auto.execute_plan(plan, source=src, create_zip=True)
        assert len(list(out.glob("*.zip"))) == 1

    def test_notes_file_created(self, tmp_path):
        src = make_legacy(tmp_path, {"index.html": "<html></html>"})
        out = tmp_path / "output"
        plan = auto.build_plan("testapp", src, "fastapi", out)
        auto.execute_plan(plan, source=src, create_zip=False)
        assert (out / "MODERNIZATION_NOTES.md").exists()

    def test_php_file_converted(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auto, "PHPTranslator", None)
        src = make_legacy(tmp_path, {"auth.php": "<?php session_start(); ?>"})
        out = tmp_path / "output"
        plan = auto.build_plan("testapp", src, "fastapi", out)
        auto.execute_plan(plan, source=src, create_zip=False)
        assert any(out.rglob("auth.py"))

    def test_html_assets_reach_correct_directory(self, tmp_path):
        src = make_legacy(tmp_path, {
            "index.html": '<link href="/style.css"><img src="/logo.png">',
            "style.css": "body{}",
            "logo.png": b"\x89PNG\r\n" + b"\x00" * 50,
        })
        out = tmp_path / "output"
        plan = auto.build_plan("testapp", src, "fastapi", out)
        auto.execute_plan(plan, source=src, create_zip=False)
        assert (out / "testapp_fastapi" / "app" / "templates" / "index.html").exists()
        assert (out / "testapp_fastapi" / "app" / "static" / "style.css").exists()
        assert (out / "testapp_fastapi" / "app" / "static" / "logo.png").exists()


# ─────────────────────────── edge cases ───────────────────────────────────────


class TestEdgeCases:
    def test_source_with_only_php_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auto, "PHPTranslator", None)
        src = make_legacy(tmp_path, {
            "index.php": "<?php echo 1; ?>",
            "login.php": "<?php echo 2; ?>",
        })
        out = tmp_path / "output"
        plan = auto.build_plan("phponly", src, "fastapi", out)
        auto.execute_plan(plan, source=src, create_zip=False)
        py_files = [p for p in out.rglob("*.py") if p.name != "main.py"]
        assert len(py_files) >= 2

    def test_deeply_nested_structure(self, tmp_path):
        src = make_legacy(tmp_path, {
            "a/b/c/d/e/deep.html": "<html>Deep</html>",
            "a/b/c/d/e/deep.css": "body{}",
        })
        out = tmp_path / "output"
        plan = auto.build_plan("nested", src, "fastapi", out)
        auto.execute_plan(plan, source=src, create_zip=False)
        assert list(out.rglob("deep.html"))

    def test_empty_source_directory(self, tmp_path):
        src = tmp_path / "empty"
        src.mkdir()
        out = tmp_path / "output"
        plan = auto.build_plan("empty", src, "fastapi", out)
        auto.execute_plan(plan, source=src, create_zip=False)  # must not raise
        assert out.is_dir()

    def test_filename_with_spaces(self, tmp_path):
        src = make_legacy(tmp_path, {"my page.html": "<html>Hello</html>"})
        out = tmp_path / "output"
        plan = auto.build_plan("spaces", src, "fastapi", out)
        auto.execute_plan(plan, source=src, create_zip=False)
        assert list(out.rglob("my page.html"))

    def test_large_file_count(self, tmp_path):
        files: dict[str, str] = {}
        files.update({f"page{i}.html": f"<html>{i}</html>" for i in range(50)})
        files.update({f"style{i}.css": f"body{{color:{i}}}" for i in range(20)})
        src = make_legacy(tmp_path, files)
        inv = auto.discover_files(src)
        assert inv.html_files == 50
        assert inv.css_files == 20

    def test_html_with_no_static_refs_is_not_corrupted(self, tmp_path):
        html = "<html><body><h1>Hello World</h1></body></html>"
        for fn in (auto.rewrite_html_for_django, auto.rewrite_html_for_fastapi,
                   auto.rewrite_html_for_rust):
            result = fn(html)
            assert "<h1>Hello World</h1>" in result

    def test_rust_project_name_special_chars(self, tmp_path):
        src = make_legacy(tmp_path, {"index.html": "<html></html>"})
        out = tmp_path / "output"
        plan = auto.build_plan("my-cool 2025!", src, "rust", out)
        auto.execute_plan(plan, source=src, create_zip=False)
        cargo_files = list(out.rglob("Cargo.toml"))
        assert cargo_files

    def test_woff2_font_goes_to_static(self, tmp_path):
        src = make_legacy(tmp_path, {"fonts/inter.woff2": b"\x00\x01\x00\x00"})
        out = tmp_path / "output"
        plan = auto.build_plan("testapp", src, "fastapi", out)
        auto.execute_plan(plan, source=src, create_zip=False)
        assert list(out.rglob("inter.woff2"))

    def test_binary_image_preserved_byte_for_byte(self, tmp_path):
        original = bytes(range(256)) * 4
        src = make_legacy(tmp_path, {"hero.jpg": original})
        out = tmp_path / "output"
        plan = auto.build_plan("testapp", src, "fastapi", out)
        auto.execute_plan(plan, source=src, create_zip=False)
        copied = list(out.rglob("hero.jpg"))
        assert copied
        assert copied[0].read_bytes() == original

    def test_dual_target_with_mixed_sources(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auto, "PHPTranslator", None)
        src = make_legacy(tmp_path, {
            "index.html": '<link href="/css/main.css"><script src="/js/app.js">',
            "css/main.css": "body{font-size:16px}",
            "js/app.js": "console.log('hello')",
            "login.php": "<?php session_start(); ?>",
            "images/logo.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        })
        out = tmp_path / "output"
        plan = auto.build_plan("fullsite", src, "dual", out)
        auto.execute_plan(plan, source=src, create_zip=True)
        # Django
        assert (out / "fullsite_django" / "templates" / "index.html").exists()
        django_html = (out / "fullsite_django" / "templates" / "index.html").read_text()
        assert "{% load static %}" in django_html
        # FastAPI
        assert (out / "fullsite_fastapi" / "app" / "templates" / "index.html").exists()
        fastapi_html = (out / "fullsite_fastapi" / "app" / "templates" / "index.html").read_text()
        assert "url_for" in fastapi_html
        # PHP converted
        assert list(out.rglob("login.py"))
        # Zip
        assert list(out.glob("*.zip"))


# ─────────────────────── patch_django_urls ────────────────────────────────────


class TestPatchDjangoUrls:
    def _setup_django_project(self, tmp_path, html_files: dict[str, str]) -> tuple:
        """Create a minimal django-like project structure for testing."""
        root = tmp_path / "mysite_django"
        pkg = root / "mysite"
        templates = root / "templates"
        pkg.mkdir(parents=True)
        templates.mkdir(parents=True)
        # Minimal urls.py (as django startproject would create)
        (pkg / "urls.py").write_text(
            "from django.contrib import admin\nfrom django.urls import path\n"
            "urlpatterns = [path('admin/', admin.site.urls)]\n"
        )
        for name, content in html_files.items():
            page = templates / name
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(content)
        return root, pkg

    def test_urls_py_updated_with_index_route(self, tmp_path):
        root, pkg = self._setup_django_project(tmp_path, {"index.html": "<html/>", "generic.html": "<html/>"})
        auto.patch_django_urls(root, "mysite")
        urls = (pkg / "urls.py").read_text()
        assert "path(''" in urls  # empty string = root route for index
        assert "index.html" in urls

    def test_urls_py_has_named_routes(self, tmp_path):
        root, pkg = self._setup_django_project(tmp_path, {
            "index.html": "<html/>",
            "generic.html": "<html/>",
            "elements.html": "<html/>",
        })
        auto.patch_django_urls(root, "mysite")
        urls = (pkg / "urls.py").read_text()
        assert "name='index'" in urls
        assert "name='generic'" in urls
        assert "name='elements'" in urls

    def test_urls_py_admin_route_preserved(self, tmp_path):
        root, pkg = self._setup_django_project(tmp_path, {"index.html": "<html/>"})
        auto.patch_django_urls(root, "mysite")
        urls = (pkg / "urls.py").read_text()
        assert "admin.site.urls" in urls

    def test_urls_py_imports_template_view(self, tmp_path):
        root, pkg = self._setup_django_project(tmp_path, {"index.html": "<html/>"})
        auto.patch_django_urls(root, "mysite")
        urls = (pkg / "urls.py").read_text()
        assert "TemplateView" in urls

    def test_duplicate_stems_get_unique_names(self, tmp_path):
        root, pkg = self._setup_django_project(tmp_path, {
            "index.html": "<html/>",
            "sub/index.html": "<html/>",  # same stem but in subdir
        })
        auto.patch_django_urls(root, "mysite")
        urls = (pkg / "urls.py").read_text()
        assert urls.count("name='index'") == 1  # only one uses the clean name

    def test_execute_plan_django_generates_proper_urls(self, tmp_path):
        """Integration test: full pipeline generates working urls.py."""
        src = make_legacy(tmp_path, {
            "index.html": '<a href="about.html">About</a>',
            "about.html": "<html>About</html>",
        })
        out = tmp_path / "output"
        plan = auto.build_plan("site", src, "django", out)
        auto.execute_plan(plan, src, create_zip=False)
        urls = (out / "site_django" / "site" / "urls.py").read_text()
        assert "name='index'" in urls
        assert "name='about'" in urls
        # Templates keep plain hrefs (no {% url %} tags)
        tmpl = (out / "site_django" / "templates" / "index.html").read_text()
        assert 'href="about.html"' in tmpl
        assert "{% url" not in tmpl

    def test_fastapi_page_links_not_rewritten(self, tmp_path):
        """FastAPI uses dynamic routing so page links must stay as plain hrefs."""
        src = make_legacy(tmp_path, {
            "index.html": '<a href="contact.html">Contact</a>',
            "contact.html": "<html>Contact</html>",
        })
        out = tmp_path / "output"
        plan = auto.build_plan("site", src, "fastapi", out)
        auto.execute_plan(plan, src, create_zip=False)
        tmpl = (out / "site_fastapi" / "app" / "templates" / "index.html").read_text()
        assert 'href="contact.html"' in tmpl
        assert "{% url" not in tmpl

    def test_django_requirements_txt_present(self, tmp_path):
        src = make_legacy(tmp_path, {"index.html": "<html/>"})
        out = tmp_path / "output"
        plan = auto.build_plan("site", src, "django", out)
        auto.execute_plan(plan, src, create_zip=False)
        req = out / "site_django" / "requirements.txt"
        assert req.exists()
        assert "django" in req.read_text().lower()

    def test_rust_no_askama_dependency(self, tmp_path):
        src = make_legacy(tmp_path, {"index.html": "<html/>"})
        out = tmp_path / "output"
        plan = auto.build_plan("site", src, "rust", out)
        auto.execute_plan(plan, src, create_zip=False)
        cargo = (out / "site_axum" / "Cargo.toml").read_text()
        assert "askama" not in cargo

    def test_rust_serves_all_pages_via_fallback(self, tmp_path):
        src = make_legacy(tmp_path, {"index.html": "<html/>"})
        out = tmp_path / "output"
        plan = auto.build_plan("site", src, "rust", out)
        auto.execute_plan(plan, src, create_zip=False)
        main_rs = (out / "site_axum" / "src" / "main.rs").read_text()
        assert "fallback_service" in main_rs
        assert "append_index_html_on_directories" in main_rs
