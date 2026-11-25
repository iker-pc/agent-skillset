# agent-skillset

A collection of agent skills I build and maintain. Each skill lives under `skills/<name>/` with a `SKILL.md` (instructions and trigger description) and, when needed, a `scripts/` directory with helper tools.

## Skills

| Skill | What it does |
|---|---|
| [`stacked-pr-sync`](skills/stacked-pr-sync/) | Syncs a GitHub stacked PR (`main → PR1 → PR2 → PR3`). Detects changes in the base branch that are missing from the first PR, merges them in and propagates the merge up the whole stack using merges only (never rebase or force-push). Stops to ask on ambiguous conflicts and ends with a visual report. |
| [`review-pull-request`](skills/review-pull-request/) | Walks a GitHub PR with a human reviewer: a review subagent on the model you choose writes a plain-language description, a test plan and findings; you accept, edit or discard each comment, which is saved as a pending review; then it guides manual testing (in the app when the PR has a user interface, technical checks when it does not) and publishes only after you choose comment, request changes or approve. |

## Installing a skill

Copy or symlink the skill folder into your agent's skills directory, for example:

```bash
# Claude Code
ln -s "$(pwd)/skills/stacked-pr-sync" ~/.claude/skills/stacked-pr-sync

# Cursor
ln -s "$(pwd)/skills/stacked-pr-sync" ~/.cursor/skills/stacked-pr-sync
```

## Repository layout

```
skills/
  <skill-name>/
    SKILL.md          # required: front matter with name + description, then instructions
    scripts/          # optional: helper scripts the skill tells the agent to run
tests/
  test_skill_metadata.py   # every skill has a valid SKILL.md
  <skill_name>/            # unit tests for that skill's scripts
```

## Running the tests

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Adding a new skill

1. Create `skills/<name>/SKILL.md` with front matter declaring `name` (same as the folder) and `description`.
2. Put any helper scripts under `skills/<name>/scripts/`. Keep the logic that can be tested without network in plain functions so it can be unit-tested.
3. If there are scripts, add tests under `tests/<name_with_underscores>/`.
4. Add a row to the table above.
