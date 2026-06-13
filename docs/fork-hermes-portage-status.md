# Fork Hermes Portage Status

This file tracks fork-only integration state while upstream PRs are pending.
It is intended for the `fork/hermes-portage` branch, not for upstream PR-PATCH
candidate branches.

## Current Fork State

| Field | Value |
| --- | --- |
| Fork branch | `fork/hermes-portage` |
| Base branch | `upstream/dev` |
| Integrated stack | PR-PATCH-001 + PR-PATCH-002 + PR-PATCH-003 |
| Latest local PR-PATCH commit | `70baccc feat(portage): add opt-in plugin tool hooks` |
| Latest fork integration commit | `5570ec2 Merge branch 'portage-hermes/PR-PATCH-003-plugin-hooks-middleware' into fork/hermes-portage` |
| Upstream-ready PR02 diff | `34d2ae1..60d58da` |
| Fork integration policy | Merge locally into `fork/hermes-portage`; push to `origin` only. |

## Blocking Items

| ID | Status | Scope | Blocker | Evidence | Next action |
| --- | --- | --- | --- | --- | --- |
| BLOCK-PR02-UPSTREAM-001 | blocked | PR-PATCH-002 upstream draft PR | PR-PATCH-001 upstream PR is still open, so PR02 is stacked and `upstream/dev...PR02` contains PR01 + PR02. | Upstream PR #4107 is open; PR02-only diff is `34d2ae1..60d58da`. | After #4107 is merged, rebase PR02 onto updated `upstream/dev`, rerun gates, then create the draft upstream PR with `.codex-log/pr-patch-002-upstream-pr-body.md`. |
| BLOCK-PR03-UPSTREAM-001 | blocked | PR-PATCH-003 upstream draft PR | Upstream already has plugin-system discussion/work, so another plugin PR is high duplicate/rejection risk. | Upstream issue #415 is open; upstream PR #416 was closed unmerged. Local PR03 branch is `portage-hermes/PR-PATCH-003-plugin-hooks-middleware` at `70baccc`; fork integration commit is `5570ec2`. Tests: `83 passed` for PR01/PR02/PR03 targeted stack and `compileall` OK. | If maintainers explicitly accept a smaller opt-in hook middleware slice, run `git checkout portage-hermes/PR-PATCH-003-plugin-hooks-middleware`, `git rebase upstream/dev`, `scripts\18_validate_upstream_diff_clean.bat`, rerun PR03 tests, then prepare a template-complete draft PR referencing #415/#416. |

## Fork Functional Queue

| PR-PATCH | Fork status | Upstream status | Notes |
| --- | --- | --- | --- |
| PR-PATCH-001-capability-registry | integrated in `fork/hermes-portage` | upstream PR #4107 open | Required foundation for PR02. |
| PR-PATCH-002-toolset-scopes-profils | integrated in `fork/hermes-portage` | waiting for #4107 | Keep upstream candidate branch clean; do not add this tracker there. |
| PR-PATCH-003-plugin-hooks-middleware | integrated in `fork/hermes-portage` | blocked by #415/#416 duplicate risk | Upstream candidate branch remains clean and pushed to `origin`; tracker lives only on fork-stable. |

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

When maintainers green-light a PR03 slice despite #415/#416:

```powershell
git fetch upstream origin
git checkout portage-hermes/PR-PATCH-003-plugin-hooks-middleware
git rebase upstream/dev
scripts\18_validate_upstream_diff_clean.bat
python -m pytest tests/test_plugin_hooks.py tests/test_tool_policy.py tests/test_workspace_confine.py tests/test_public_blocked_tool_nonstring.py tests/test_ask_user_tool.py tests/test_update_plan_tool.py
gh pr create -R pewdiepie-archdaemon/odysseus --base dev --head JayceeB1:portage-hermes/PR-PATCH-003-plugin-hooks-middleware --title "feat(portage): add opt-in plugin tool hooks" --body-file .codex-log/pr-patch-003-upstream-pr-body.md --draft
```
