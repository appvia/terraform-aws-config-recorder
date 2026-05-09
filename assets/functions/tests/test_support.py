"""Shared helpers for unit tests."""

from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import sys
from pathlib import Path


def load_module_from_path(module_name: str, path: Path):
    """Load a Python module directly from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ensure_recorder_dir_on_path() -> Path:
    """Ensure assets/functions is on sys.path; return that directory."""
    recorder_dir = Path(__file__).resolve().parents[1]
    if str(recorder_dir) not in sys.path:
        sys.path.insert(0, str(recorder_dir))
    return recorder_dir


@contextmanager
def temporarily_set_sys_module(module_name: str, module_obj):
    """
    Temporarily set sys.modules[module_name] to module_obj and restore afterwards.
    """
    saved = sys.modules.get(module_name)
    try:
        sys.modules[module_name] = module_obj
        yield
    finally:
        if saved is not None:
            sys.modules[module_name] = saved
        else:
            sys.modules.pop(module_name, None)
