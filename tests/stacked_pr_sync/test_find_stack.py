"""Tests for the pure graph logic of skills/stacked-pr-sync/scripts/find_stack.py.
No network, no `gh`: we feed the functions the PR list GitHub would return."""
import json
import subprocess
import sys

import pytest

from conftest import SKILLS_DIR, load_script

find_stack = load_script("stacked-pr-sync", "find_stack.py")
SCRIPT = SKILLS_DIR / "stacked-pr-sync" / "scripts" / "find_stack.py"


def pr(number, head, base, title=None):
    return {
        "number": number,
        "title": title or f"PR {number}",
        "url": f"https://github.com/o/r/pull/{number}",
        "headRefName": head,
        "baseRefName": base,
    }


# main -> #1 (feat/a) -> #2 (feat/b) -> #3 (feat/c)
LINEAR = [
    pr(1, "feat/a", "main"),
    pr(2, "feat/b", "feat/a"),
    pr(3, "feat/c", "feat/b"),
]


def levels(result):
    return [(s["level"], s["number"], s["parent"]) for s in result["stack"]]


class TestFindStart:
    def test_by_number(self):
        assert find_stack.find_start(LINEAR, pr_number=2)["headRefName"] == "feat/b"

    def test_by_branch(self):
        assert find_stack.find_start(LINEAR, branch="feat/c")["number"] == 3

    def test_missing_returns_none(self):
        assert find_stack.find_start(LINEAR, pr_number=99) is None
        assert find_stack.find_start(LINEAR, branch="nope") is None


class TestBuildStack:
    def test_linear_stack_from_the_bottom(self):
        result = find_stack.build_stack(LINEAR, LINEAR[0])
        assert result["trunk"] == "main"
        assert result["linear"] is True
        assert result["warnings"] == []
        assert levels(result) == [(1, 1, "main"), (2, 2, "feat/a"), (3, 3, "feat/b")]

    @pytest.mark.parametrize("start_index", [1, 2])
    def test_any_pr_in_the_stack_yields_the_same_stack(self, start_index):
        from_bottom = find_stack.build_stack(LINEAR, LINEAR[0])
        from_middle = find_stack.build_stack(LINEAR, LINEAR[start_index])
        assert from_middle == from_bottom

    def test_single_pr_is_a_stack_of_one(self):
        prs = [pr(7, "feat/solo", "main")]
        result = find_stack.build_stack(prs, prs[0])
        assert result["trunk"] == "main"
        assert levels(result) == [(1, 7, "main")]
        assert result["linear"] is True

    def test_unrelated_prs_are_ignored(self):
        prs = LINEAR + [pr(50, "other/x", "main"), pr(51, "other/y", "develop")]
        result = find_stack.build_stack(prs, LINEAR[1])
        assert [s["number"] for s in result["stack"]] == [1, 2, 3]

    def test_branching_stack_is_reported(self):
        # main -> #1 -> {#2, #4}; #2 -> #3
        prs = LINEAR + [pr(4, "feat/d", "feat/a")]
        result = find_stack.build_stack(prs, prs[0])
        assert result["linear"] is False
        assert len(result["warnings"]) == 1
        assert "feat/a" in result["warnings"][0]
        assert "#2" in result["warnings"][0] and "#4" in result["warnings"][0]
        # BFS order, children sorted by number
        assert [s["number"] for s in result["stack"]] == [1, 2, 4, 3]
        assert levels(result)[2] == (2, 4, "feat/a")

    def test_trunk_can_be_any_branch_not_owned_by_an_open_pr(self):
        prs = [pr(1, "feat/a", "release/2.0"), pr(2, "feat/b", "feat/a")]
        result = find_stack.build_stack(prs, prs[1])
        assert result["trunk"] == "release/2.0"

    def test_cycle_in_bases_does_not_loop_forever(self):
        # #1 is based on #2's branch and #2 on #1's branch: a broken state on
        # GitHub, but the walk must terminate.
        prs = [pr(1, "feat/a", "feat/b"), pr(2, "feat/b", "feat/a")]
        result = find_stack.build_stack(prs, prs[0])
        assert result["trunk"] in {"feat/a", "feat/b"}
        assert sorted(s["number"] for s in result["stack"]) == [1, 2]
        assert any("Cycle detected" in w for w in result["warnings"])

    def test_stack_entries_carry_pr_metadata(self):
        result = find_stack.build_stack(LINEAR, LINEAR[0])
        first = result["stack"][0]
        assert first == {
            "level": 1,
            "number": 1,
            "title": "PR 1",
            "url": "https://github.com/o/r/pull/1",
            "head": "feat/a",
            "parent": "main",
        }


class TestMergedTrunkWarning:
    def test_no_merged_pr_means_no_warning(self):
        assert find_stack.merged_trunk_warning("main", 1, []) is None

    def test_merged_trunk_suggests_retargeting(self):
        merged = [pr(9, "feat/old", "main")]
        text = find_stack.merged_trunk_warning("feat/old", 1, merged)
        assert "#9" in text
        assert "retarget #1" in text
        assert "'main'" in text


class TestNormalizeApi:
    def test_rest_payload_is_mapped_to_gh_field_names(self):
        raw = {
            "number": 5,
            "title": "T",
            "html_url": "u",
            "head": {"ref": "feat/x"},
            "base": {"ref": "main"},
        }
        assert find_stack._normalize_api(raw) == pr(5, "feat/x", "main", title="T") | {"url": "u"}


class TestCli:
    def test_requires_repo_and_pr_or_branch(self):
        proc = subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True)
        assert proc.returncode == 2
        assert "--repo" in proc.stderr

    def test_pr_and_branch_are_mutually_exclusive(self):
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--repo", "o/r", "--pr", "1", "--branch", "x"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 2
        assert "not allowed with" in proc.stderr

    def test_end_to_end_with_stubbed_github(self, monkeypatch, capsys):
        merged_lookups = []

        def fake_list_prs(repo, state, use_gh, head=None):
            if state == "open":
                return LINEAR
            merged_lookups.append(head)
            return []

        monkeypatch.setattr(find_stack, "_gh_available", lambda: True)
        monkeypatch.setattr(find_stack, "list_prs", fake_list_prs)
        monkeypatch.setattr(sys, "argv", ["find_stack.py", "--repo", "o/r", "--pr", "3"])

        find_stack.main()

        out = json.loads(capsys.readouterr().out)
        assert out["trunk"] == "main"
        assert [s["number"] for s in out["stack"]] == [1, 2, 3]
        assert merged_lookups == ["main"]

    def test_unknown_pr_exits_with_error(self, monkeypatch):
        monkeypatch.setattr(find_stack, "_gh_available", lambda: True)
        monkeypatch.setattr(find_stack, "list_prs", lambda *a, **k: LINEAR)
        monkeypatch.setattr(sys, "argv", ["find_stack.py", "--repo", "o/r", "--pr", "42"])
        with pytest.raises(SystemExit) as exc:
            find_stack.main()
        assert "no matching open PR" in str(exc.value)
