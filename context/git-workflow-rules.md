# Git Workflow Rules

> Policy. Loaded into AI tool context. Update only when the convention itself changes.

## Branch model — GitFlow (lite)

Long-lived branches:

| Branch | Purpose | Direct commits? |
|---|---|---|
| `master` | Production releases. Tagged at every release. | **Never.** Only fast-forwarded from `release/*` PRs. |
| `release` | Release-candidate staging. Cut from `develop` when scoping a release. | Only via PR from `develop`; bug-fix-only commits while stabilizing. |
| `develop` | Integration branch. Tip is the latest accepted feature work. | Only via PR from `feature/*` branches. |
| `main` | Mirror of `master` for backwards-compat with the existing default. | Treat as read-only; same content as `master`. |

Short-lived branches:

| Pattern | When to create | Where to merge | Lifecycle |
|---|---|---|---|
| `feature/<short-name>` | One per feature, fix, or doc change | PR into `develop` | Delete after merge |
| `bugfix/<short-name>` | Non-emergency fixes off `develop` | PR into `develop` | Delete after merge |
| `hotfix/<short-name>` | Production-emergency fixes off `master` | PR into both `master` and `develop` | Delete after merge |
| `release/<version>` *(optional)* | Per-version stabilization (e.g. `release/v0.2`) | PR `master` AND back-merge to `develop` | Delete after release tagged |

## Feature branch rules

- **One feature per branch.** Don't pile unrelated changes onto a single feature branch — it complicates review and revert.
- **Branch off `develop`.** Always: `git checkout -b feature/<name> develop`.
- **Keep them short-lived.** Days, not weeks. Long-running feature branches drift from `develop` and become merge nightmares.
- **Naming:** lowercase, hyphenated, descriptive. Examples:
  - `feature/llm-query-planner`
  - `feature/zip-centroid-coverage`
  - `feature/dealer-widget-mvp`
  - `bugfix/duplicate-listing-survivorship`
- **No direct pushes to `master`, `release`, `develop`, or `main`.** Use PRs.

## PR flow

```
feature/<name> ──PR──▶ develop ──PR──▶ release ──PR──▶ master ──tag──▶ production
                                          │
                                          └──── back-merge to develop after release
```

Hotfix path:
```
master ──┐
         │ branch
         ▼
hotfix/<name> ──PR──▶ master (then tag) AND ──PR──▶ develop
```

## Commit messages

- Subject under 72 chars, imperative mood ("Add", "Fix", not "Added", "Fixed").
- Reference the *why*, not just the *what*.
- Use a body for anything non-trivial; bullet what changed.
- Don't append fabricated co-author trailers; if a tool helped, the user can add the trailer themselves on review.

## What lives on which branch (CarPapi-specific)

- **`master` / `main`** — currently `19be1ec`, contains the Django/Scrapy crawler + the FastAPI chat-API + the four-guideline implementation. This is the production line.
- **`release`** — same SHA today; will diverge when we cut a stabilization branch.
- **`develop`** — same SHA today; will lead `master` once new feature branches start landing.
- **Short-lived feature branches** are created from `develop` per the rules above.

## Examples

Starting a new feature:
```bash
git fetch origin
git checkout -b feature/value-score-regression origin/develop
# ... work, commit ...
git push -u origin feature/value-score-regression
# Open PR on GitHub: feature/value-score-regression → develop
```

Cutting a release:
```bash
git checkout -b release/v0.2 origin/develop
# bug-fix-only commits while testing
# When stable: open PR release/v0.2 → master, tag v0.2 after merge
# Then: open PR release/v0.2 → develop (back-merge)
```

Hotfixing production:
```bash
git checkout -b hotfix/dedup-collision origin/master
# fix, commit, push
# Open PR to master AND to develop (separate PRs)
```

## Cleanup after merge

- Delete the merged feature branch on the remote: `git push origin --delete feature/<name>`
- Prune local tracking branches: `git fetch --prune`

## What this rule blocks

- Pushing directly to `master`, `release`, `develop`, or `main` — bypasses review.
- Creating long-lived `feature/*` branches that accumulate unrelated work.
- Mixing two features in one PR — split into two branches and two PRs.
- Skipping the back-merge from `release` → `develop` after a release.

## What this rule does NOT govern

- Branch protection rules on GitHub (set those in the repo Settings UI).
- CI/CD wiring (separate concern; see infra docs when they exist).
- Per-commit signing requirements.
