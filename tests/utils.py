import importlib
import os
import sys
from pathlib import Path

from sqlmodel import SQLModel


def reload_module(module_name: str):
    """Import a module fresh so env overrides take effect."""
    if module_name in sys.modules:
        del sys.modules[module_name]
    SQLModel.metadata.clear()
    return importlib.import_module(module_name)


def configure_sqlite_env(env_var: str, path: Path) -> str:
    """Ensure a unique sqlite db path for a service and store it in env."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    url = f"sqlite:///{path}"
    os.environ[env_var] = url
    return url


