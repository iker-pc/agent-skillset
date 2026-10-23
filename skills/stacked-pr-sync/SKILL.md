---
name: stacked-pr-sync
description: Syncs a GitHub stacked PR (a chain of stacked PRs, e.g. main → PR1 → PR2 → PR3). Detects whether the base branch has changes that are not yet in the first PR, merges them into it, and propagates the merge up through the whole stack. Stops to ask about ambiguous conflicts and ends with a visual report of the result. Use it whenever the user wants to update, sync, refresh, "bring main into" or propagate changes through stacked PRs, PR stacks, chains of dependent branches or PRs built on top of other PRs, even if they don't literally say "stacked PR".
---

# Stacked PR Sync

Updates a stack of PRs in cascade using **merges** (never rebase or force-push) so that every branch contains the latest changes from the branch it is built on.

```
main ──► PR1 ──► PR2 ──► PR3
  └ merge ┘└ merge ┘└ merge ┘
```

Why merge and not rebase: a merge doesn't rewrite history, so no `--force` is needed, review comments anchored to commits are not lost, and nobody with the branch checked out locally ends up with diverged history.

## Requirements

- `git` (≥ 2.38 for `git merge-tree --write-tree`; if older, skip the conflict prediction in step 2).
- GitHub access: an authenticated `gh` (`gh auth status`) or, failing that, the `GITHUB_TOKEN` environment variable.
- A clone of the repository. If there isn't one, clone it into a working directory.

## Step 1 — Identify the stack

The user will give a repo (`owner/repo`) and a PR (number, URL or branch), which can be any PR in the stack, not necessarily the first one. If the repo is not given, infer it from `git remote get-url origin`.

The helper script lives in the `scripts/` folder of this skill, next to this `SKILL.md`, not in the user's project. The working directory is usually the user's repository, so call it with the full path to this skill's directory (shown below as `<skill-dir>`):

```bash
python3 <skill-dir>/scripts/find_stack.py --repo owner/repo --pr 123
# or: --branch feature/my-branch
```

The script walks down the bases to the trunk branch (the first base that is not the head of another open PR) and walks up through the child PRs. It returns JSON with `trunk`, `stack` (ordered bottom to top, each level with its `parent`), `linear` and `warnings`.

Stop and ask the user if:
- `linear` is `false`: the stack branches (two PRs come out of the same branch). Show the tree and ask whether to update every branch or just one.
- There is a warning that the trunk is the branch of an **already merged** PR. In that case the right move is usually to retarget the PR to `main` (`gh pr edit N --base main`) instead of merging, especially if it was squash-merged, because the merge would bring in duplicated commits.

## Step 2 — Diagnosis and plan

Work in a **temporary worktree** so the user's working directory is left untouched:

```bash
git fetch origin --prune
git worktree add ../stack-sync-tmp --detach origin/<trunk>
cd ../stack-sync-tmp
```

For each link `parent → child` (starting with `trunk → PR1`):

```bash
# Is child up to date? (exit 0 = yes)
git merge-base --is-ancestor origin/<parent> origin/<child>
# Missing commits
git log --oneline origin/<child>..origin/<parent>
# Predict conflicts without touching anything (exit 1 = there will be conflicts)
git merge-tree --write-tree --name-only origin/<child> origin/<parent>
```

Note: even if a link is up to date with `origin/<parent>`, it will still be updated if its parent is going to receive a merge in this run, because that merge is a new commit that must be propagated.

Show the plan to the user before executing, for example:

```
Stack: main → #101 → #102 → #103
  main → #101   7 pending commits      ⚠ conflict expected in src/api/client.ts
  #101 → #102   up to date, but will receive the previous merge
  #102 → #103   up to date, but will receive the previous merge
Shall I proceed?
```

If nothing needs updating, say so and finish with the report.

## Step 3 — Cascading merge

Walk the stack bottom to top. Each child is merged with the **local**, already-updated branch of its parent (not with `origin/<parent>`); that is what propagates the change:

```bash
git switch -C <trunk-local> origin/<trunk>           # reference only
git switch -C <PR1-branch> origin/<PR1-branch>
git merge --no-ff --no-edit <trunk-local>
git switch -C <PR2-branch> origin/<PR2-branch>
git merge --no-ff --no-edit <PR1-branch>
# ...and so on
```

Recommended merge message: `Merge <parent> into <child> (stacked-pr-sync)`.

Identity and signing: merge commits must come out with whatever identity and signing setup the user already has in git. If `commit.gpgsign` is enabled, commits get signed; if it isn't, they don't. Never override `user.name`, `user.email` or `commit.gpgsign` (not with `-c`, not with `--author`, not with `GIT_AUTHOR_*`/`GIT_COMMITTER_*` variables), never pass `--no-gpg-sign` or `-S`, and never take the email from the session context. If a commit fails because signing fails, stop and ask the user. Note that if the commit email doesn't match the signing key's uid, GitHub marks the commit as *Unverified* even though it is signed.

If the project has a quick build or test command and the user has specified it, run it after each merge; if it fails, treat it as a major doubt.

### Conflict resolution

Classify each conflict before acting:

**Resolve it yourself and note it in the report** when it is mechanical and unambiguous:
- Imports or lists where each side adds different items (keep the union).
- Formatting or whitespace changes versus content changes.
- Lockfiles (`package-lock.json`, `yarn.lock`, `poetry.lock`…): take the parent's version and regenerate with the package manager if available; if it isn't, it's a major doubt.
- Generated files, if you know how to regenerate them.

**Stop and ask** when a decision about the code's intent is required:
- Both sides modify the same logic (same function, condition or query) in different ways.
- One side deletes or renames a file or symbol and the other modifies it.
- Changes to database migrations, schemas, API contracts or deployment configuration.
- Resolving it would require inventing new code that is on neither side.
- When in doubt, ask: it is much cheaper than a wrong resolution that spreads through the whole stack.

Format for raising doubts (one section per conflict, all together before continuing):

```
⛔ Conflict in #101 (merging main) — src/api/client.ts, function fetchUser()

  main:   adds retries with exponential backoff
  #101:   changes the endpoint to /v2/users and the response format

  Proposal: keep #101's v2 endpoint and wrap it in main's retries.
  Alternatives: (a) keep only #101  (b) keep only main
  How should I proceed?
```

While waiting for an answer, leave the merge in progress in the worktree (don't `--abort`) and don't touch the upper levels. If the user prefers to give up, run `git merge --abort` and go to the report stating how far the process got.

## Step 4 — Push

Only once **all** planned merges have finished, push bottom to top, without `--force`:

```bash
git push origin <PR1-branch>
git push origin <PR2-branch>
# ...
```

If a push is rejected because someone pushed in the meantime, don't force it: `fetch`, merge `origin/<branch>` into the local one, redo the propagation upwards from that level and try again.

When done, clean up: `git worktree remove ../stack-sync-tmp`.

## Step 5 — Final report

Always use this template:

```markdown
## 🔄 Stack synced — owner/repo

main ──► #101 ──► #102 ──► #103

| Level | PR | Branch | Status | Commits brought in | Conflicts |
|---|---|---|---|---|---|
| 1 | [#101 Title](url) | feature/a | ✅ Updated | 7 | 1 resolved (imports) |
| 2 | [#102 Title](url) | feature/b | ✅ Updated | 1 (merge) | — |
| 3 | [#103 Title](url) | feature/c | ⏸ Pending | — | — |

**Legend:** ✅ updated · ➖ already up to date · ⚠ updated with resolved conflicts · ⛔ stopped · ⏸ not processed

### Conflicts resolved automatically
- #101 · `src/index.ts`: union of imports from both sides.

### Decisions made with the user
- #101 · `src/api/client.ts`: v2 endpoint + retries from main.

### Next steps
- Check CI for #101, #102 and #103.
```

If the process stopped, explain at which level, why, and what would be needed to resume it.

## Rules that are never broken

- Never `git push --force` or rebase branches in the stack.
- Never merge a stack PR into `main` or close PRs: the skill only updates branches.
- Never push a level if any lower level was left unresolved.
