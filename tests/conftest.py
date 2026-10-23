import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"


def load_script(skill: str, script: str):
    """Imports a skill's script as a module. Skill folders use hyphens, so a
    normal `import` is not possible; we load it from its path instead."""
    path = SKILLS_DIR / skill / "scripts" / script
    name = f"{skill}.{script}".replace("-", "_").replace(".py", "")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def skills_dir() -> Path:
    return SKILLS_DIR
