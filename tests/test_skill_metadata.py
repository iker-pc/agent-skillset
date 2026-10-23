"""Every folder under skills/ must be a valid skill: it has a SKILL.md whose
front matter declares `name` (matching the folder) and `description`."""
import re
from pathlib import Path

import pytest

from conftest import SKILLS_DIR

SKILL_DIRS = sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def parse_front_matter(text: str) -> dict:
    match = FRONT_MATTER.match(text)
    assert match, "SKILL.md must start with a YAML front matter block (--- ... ---)"
    fields = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


def test_there_is_at_least_one_skill():
    assert SKILL_DIRS, "skills/ is empty"


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_has_valid_skill_md(skill_dir: Path):
    skill_md = skill_dir / "SKILL.md"
    assert skill_md.is_file(), f"{skill_dir.name} has no SKILL.md"

    fields = parse_front_matter(skill_md.read_text(encoding="utf-8"))
    assert fields.get("name") == skill_dir.name, (
        f"front matter name {fields.get('name')!r} != folder {skill_dir.name!r}"
    )
    assert fields.get("description"), "front matter has no description"


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_folder_name_is_kebab_case(skill_dir: Path):
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", skill_dir.name), (
        f"{skill_dir.name!r} should be lowercase kebab-case"
    )
