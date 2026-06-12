# Fork Hermes Portage Status

This file tracks fork-only integration state while upstream PRs are pending.
It is intended for the `fork/hermes-portage` branch, not for upstream PR-PATCH
candidate branches.

## Current Fork State

| Field | Value |
| --- | --- |
| Fork branch | `fork/hermes-portage` |
| Base branch | `upstream/dev` |
| Integrated stack | PR-PATCH-001 + PR-PATCH-002 |
| Latest local PR-PATCH commit | `60d58da feat(tools): add toolset profile policy` |
| Upstream-ready PR02 diff | `34d2ae1..60d58da` |
| Fork integration policy | Merge locally into `fork/hermes-portage`; push to `origin` only. |

## Blocking Items

| ID | Status | Scope | Blocker | Evidence | Next action |
| --- | --- | --- | --- | --- | --- |
| BLOCK-PR02-UPSTREAM-001 | blocked | PR-PATCH-002 upstream draft PR | PR-PATCH-001 upstream PR is still open, so PR02 is stacked and `upstream/dev...PR02` contains PR01 + PR02. | Upstream PR #4107 is open; PR02-only diff is `34d2ae1..60d58da`. | After #4107 is merged, rebase PR02 onto updated `upstream/dev`, rerun gates, then create the draft upstream PR with `.codex-log/pr-patch-002-upstream-pr-body.md`. |

## Fork Functional Queue

| PR-PATCH | Fork status | Upstream status | Notes |
| --- | --- | --- | --- |
| PR-PATCH-001-capability-registry | integrated in `fork/hermes-portage` | upstream PR #4107 open | Required foundation for PR02. |
| PR-PATCH-002-toolset-scopes-profils | integrated in `fork/hermes-portage` | waiting for #4107 | Keep upstream candidate branch clean; do not add this tracker there. |

## Resume Commands

When #4107 is merged upstream:

```powershell
git fetch upstream origin
git checkout portage-hermes/PR-PATCH-002-toolset-scopes-profils
git rebase upstream/dev
scripts\18_validate_upstream_diff_clean.bat
python -m pytest tests/test_toolset_policy.py tests/test_toolset_agent_loop.py tests/test_capability_registry.py tests/test_tool_policy.py
gh pr create -R pewdiepie-archdaemon/odysseus --base dev --head JayceeB1:portage-hermes/PR-PATCH-002-toolset-scopes-profils --title "feat(tools): add toolset profile policy" --body-file .codex-log/pr-patch-002-upstream-pr-body.md --draft
```

When continuing fork-only work while upstream is blocked:

```powershell
git checkout fork/hermes-portage
git pull --ff-only origin fork/hermes-portage
python -m pytest tests/test_toolset_policy.py tests/test_toolset_agent_loop.py tests/test_capability_registry.py tests/test_tool_policy.py
```
