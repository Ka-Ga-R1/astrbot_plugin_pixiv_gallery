import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_release_version_and_runtime_dependency_boundary():
    metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
    assert "version: 0.1.2" in metadata
    assert "0.1.2" in (ROOT / "pages/pixiv-gallery/index.html").read_text(encoding="utf-8")
    runtime = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "httpx" in runtime
    assert "pytest" not in runtime
    assert "pytest" in (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "0.1.2" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_production_python_has_python310_compatible_syntax():
    for file in [ROOT / "main.py", *sorted((ROOT / "pixiv_gallery").glob("*.py"))]:
        ast.parse(file.read_text(encoding="utf-8-sig"), filename=str(file), feature_version=(3, 10))


def test_checkout_contains_no_local_credentials_or_build_cache_in_plugin_payload():
    excluded_directories = {
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "doc_cache",
        "node_modules",
    }
    files = (
        subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        .stdout.decode()
        .split("\0")
    )
    for filename in filter(None, files):
        path = Path(filename)
        if any(part in excluded_directories for part in path.parts):
            continue
        assert path.name != ".env"
        assert ".backup." not in path.name
        assert path.name not in {"refresh_token", "pixiv-token.txt"}
