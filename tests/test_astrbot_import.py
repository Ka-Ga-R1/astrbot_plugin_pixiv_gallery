import importlib
import shutil
import sys
import tempfile
from pathlib import Path


def test_main_imports_when_astrbot_loads_plugin_as_nested_package():
    source = Path(__file__).parents[1]
    with tempfile.TemporaryDirectory() as temp:
        plugin_root = Path(temp) / "data" / "plugins" / "astrbot_plugin_pixiv_gallery"
        shutil.copytree(source, plugin_root, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", "tests", "doc_cache"))
        old_path = list(sys.path)
        sys.path[:] = [item for item in sys.path if Path(item or ".").resolve() != source.resolve()]
        sys.path.insert(0, temp)
        try:
            module = importlib.import_module("data.plugins.astrbot_plugin_pixiv_gallery.main")
            assert module.PLUGIN_NAME == "astrbot_plugin_pixiv_gallery"
        finally:
            sys.path[:] = old_path
            for name in list(sys.modules):
                if name == "data" or name.startswith("data."):
                    sys.modules.pop(name, None)
