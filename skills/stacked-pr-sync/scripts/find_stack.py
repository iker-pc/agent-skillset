#!/usr/bin/env python3
"""Discovers the structure of a stacked PR on GitHub.

Usage:
    python find_stack.py --repo owner/repo --pr 123
    python find_stack.py --repo owner/repo --branch feature/x

Uses `gh` if available and authenticated; otherwise the REST API with GITHUB_TOKEN.
Prints JSON: {trunk, stack[{level, number, title, url, head, parent}], linear, warnings}
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request

FIELDS = "number,title,url,headRefName,baseRefName"


def _gh_available():
    if not shutil.which("gh"):
        return False
    return subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0


def _api_get(path):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("Error: neither an authenticated `gh` nor GITHUB_TOKEN is available.")
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def _normalize_api(pr):
    return {
        "number": pr["number"],
        "title": pr["title"],
        "url": pr["html_url"],
        "headRefName": pr["head"]["ref"],
        "baseRefName": pr["base"]["ref"],
    }


def list_prs(repo, state, use_gh, head=None):
    if use_gh:
        cmd = ["gh", "pr", "list", "-R", repo, "--state", state, "--limit", "500", "--json", FIELDS]
        if head:
            cmd += ["--head", head]
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
        return json.loads(out)
    api_state = "closed" if state == "merged" else state
    prs, page = [], 1
    while True:
        q = f"/repos/{repo}/pulls?state={api_state}&per_page=100&page={page}"
        if head:
            q += f"&head={repo.split('/')[0]}:{head}"
        batch = _api_get(q)
        if state == "merged":
            batch = [p for p in batch if p.get("merged_at")]
        prs += [_normalize_api(p) for p in batch]
        if len(batch) < 100 or head:
            break
        page += 1
    return prs


def find_start(prs, pr_number=None, branch=None):
    """Returns the open PR matching the given number or head branch, or None."""
    if pr_number is not None:
        return next((p for p in prs if p["number"] == pr_number), None)
    return next((p for p in prs if p["headRefName"] == branch), None)


def build_stack(prs, start):
    """Pure graph logic: given the open PRs and the starting PR, returns
    {trunk, stack, linear, warnings}. Does not talk to GitHub."""
    by_head = {p["headRefName"]: p for p in prs}

    # Walk down to the root of the stack
    root, seen = start, set()
    while root["baseRefName"] in by_head and root["number"] not in seen:
        seen.add(root["number"])
        root = by_head[root["baseRefName"]]
    trunk = root["baseRefName"]

    # Walk up through children (BFS) to detect branching
    children = {}
    for p in prs:
        children.setdefault(p["baseRefName"], []).append(p)
    stack, linear, warnings = [], True, []
    queue, visited = [(root, trunk, 1)], set()
    while queue:
        pr, parent, level = queue.pop(0)
        if pr["number"] in visited:
            warnings.append(
                f"Cycle detected: PR #{pr['number']} ('{pr['headRefName']}') is reached "
                f"again via '{parent}'. The stack's base branches are inconsistent."
            )
            continue
        visited.add(pr["number"])
        stack.append({
            "level": level, "number": pr["number"], "title": pr["title"],
            "url": pr["url"], "head": pr["headRefName"], "parent": parent,
        })
        kids = sorted(children.get(pr["headRefName"], []), key=lambda p: p["number"])
        if len(kids) > 1:
            linear = False
            warnings.append(
                f"The stack branches at '{pr['headRefName']}': "
                + ", ".join(f"#{k['number']}" for k in kids)
            )
        queue += [(k, pr["headRefName"], level + 1) for k in kids]

    return {"trunk": trunk, "stack": stack, "linear": linear, "warnings": warnings}


def merged_trunk_warning(trunk, root_number, merged_prs):
    """Warning text if the trunk branch belongs to an already merged PR, else None."""
    if not merged_prs:
        return None
    m = merged_prs[0]
    return (
        f"The trunk branch '{trunk}' belongs to PR #{m['number']}, already merged into "
        f"'{m['baseRefName']}'. You probably need to retarget #{root_number} "
        f"to '{m['baseRefName']}' instead of merging."
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pr", type=int)
    g.add_argument("--branch")
    args = ap.parse_args()

    use_gh = _gh_available()
    prs = list_prs(args.repo, "open", use_gh)

    start = find_start(prs, pr_number=args.pr, branch=args.branch)
    if not start:
        sys.exit("Error: no matching open PR found in the repository.")

    result = build_stack(prs, start)

    # Is the trunk the branch of an already merged PR?
    merged = list_prs(args.repo, "merged", use_gh, head=result["trunk"])
    warning = merged_trunk_warning(result["trunk"], result["stack"][0]["number"], merged)
    if warning:
        result["warnings"].append(warning)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
