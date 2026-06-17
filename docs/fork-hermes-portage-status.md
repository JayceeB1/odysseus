# Fork Hermes Portage Status

This file tracks fork-only integration state while upstream PRs are pending.
It is intended for the `fork/hermes-portage` branch, not for upstream PR-PATCH
candidate branches.

## Current Fork State

| Field | Value |
| --- | --- |
| Fork branch | `fork/hermes-portage` |
| Base branch | `upstream/dev` |
| Current upstream/dev | `97a7f59 fix(ui): share one z-order stack across Notes and modals (#3798)` |
| Integrated stack | PR-PATCH-001 + PR-PATCH-002 + PR-PATCH-003 + PR-PATCH-004 + PR-PATCH-005 + PR-PATCH-006 + PR-PATCH-015 |
| Latest local PR-PATCH commit | `4e61483 feat(evals): add opt-in trajectory recorder` |
| Latest fork integration commit | `2095a46 merge: integrate PR15 into fork hermes portage` |
| Latest fork maintenance commit | `5914518 test(fork): make canvas coords node import windows-safe` |
| Upstream-ready PR02 diff | `34d2ae1..60d58da` |
| Fork integration policy | Merge locally into `fork/hermes-portage`; push to `origin` only. |

## Maintenance Notes

- `fork/hermes-portage` was synced with `upstream/dev` at `97a7f59` via `7be8f1c merge: sync fork hermes portage with upstream dev`.
- The upstream `tests/test_canvas_coords_empty_touches_js.py` Node ESM import used a Windows absolute path (`F:/...`) that fails under Node's default ESM loader. The fork-only follow-up `5914518` changes that test import to a `file://` URI.
- Validation after the sync: `python -m pytest tests/test_canvas_coords_empty_touches_js.py tests/test_notes_z_order_js.py -q` -> `8 passed`, 1 SQLAlchemy warning.

## Blocking Items

| ID | Status | Scope | Blocker | Evidence | Next action |
| --- | --- | --- | --- | --- | --- |
| BLOCK-PR02-UPSTREAM-001 | blocked | PR-PATCH-002 upstream draft PR | PR-PATCH-001 upstream PR is still open, so PR02 is stacked and `upstream/dev...PR02` contains PR01 + PR02. | Upstream PR #4107 is open; PR02-only diff is `34d2ae1..60d58da`. | After #4107 is merged, rebase PR02 onto updated `upstream/dev`, rerun gates, then create the draft upstream PR with `.codex-log/pr-patch-002-upstream-pr-body.md`. |
| BLOCK-PR03-UPSTREAM-001 | blocked | PR-PATCH-003 upstream draft PR | Upstream already has plugin-system discussion/work, so another plugin PR is high duplicate/rejection risk. | Upstream issue #415 is open; upstream PR #416 was closed unmerged. Local PR03 branch is `portage-hermes/PR-PATCH-003-plugin-hooks-middleware` at `70baccc`; fork integration commit is `5570ec2`. Tests: `83 passed` for PR01/PR02/PR03 targeted stack and `compileall` OK. | If maintainers explicitly accept a smaller opt-in hook middleware slice, run `git checkout portage-hermes/PR-PATCH-003-plugin-hooks-middleware`, `git rebase upstream/dev`, `scripts\18_validate_upstream_diff_clean.bat`, rerun PR03 tests, then prepare a template-complete draft PR referencing #415/#416. |
| BLOCK-PR04-UPSTREAM-001 | blocked | PR-PATCH-004 upstream draft PR | Upstream has open overlapping `agent_loop.py` refactors, so a new context-engine adapter PR is high conflict/rejection risk until those are resolved or maintainers ask for this smaller slice. | No exact `TurnContext` duplicate found. Open overlap: PR #3265 extracts streamed agent turns, PR #4246 changes context-aware RAG/agent loop retrieval, PR #1154 changes prompt/context budget handling. Local PR04 branch is `portage-hermes/PR-PATCH-004-turncontext-contextengine` at `1eb619e`; fork integration commit is `e9b051a`. Tests: PR04 context suite `135 passed`; fork PR01-PR03 stack `83 passed`; `uvicorn app:app` smoke returned HTTP 200. | After #3265/#4246/#1154 are merged, closed, or maintainers confirm this slice should proceed independently, run `git checkout portage-hermes/PR-PATCH-004-turncontext-contextengine`, `git rebase upstream/dev`, `scripts\18_validate_upstream_diff_clean.bat`, rerun PR04 tests, then prepare a template-complete draft PR. |
| BLOCK-PR05-UPSTREAM-001 | blocked | PR-PATCH-005 upstream draft PR | The executor budget facade is implemented and validated locally, but there is no linked maintainer issue or concrete upstream problem statement yet. Opening an official PR now is high rejection risk as speculative abstraction work under `AGENTS.md`. | Local PR05 branch is `portage-hermes/PR-PATCH-005-executor-budgets-result-store` at `6010906`; targeted validation passed: `13 passed` for executor budget tests, `23 passed` for tool policy/truncation/unknown-tool regressions, `72 passed` for agent loop/context budget/sentinel stack, plus app health smoke. | Keep PR05 integrated in `fork/hermes-portage` for fork functionality. Before any upstream PR, obtain or write a concrete linked issue/problem statement, rebase PR05 onto current `upstream/dev`, rerun gates, and prepare a template-complete draft PR. |
| BLOCK-PR06-UPSTREAM-001 | blocked | PR-PATCH-006 upstream draft PR | PR06 is implemented as an opt-in provider error classifier/recovery helper, but there is no linked maintainer issue or concrete upstream problem statement yet. Upstream also has active overlapping provider/retry/fallback work, so opening an official PR now is high rejection risk as speculative unintegrated abstraction work under `AGENTS.md`. | Local PR06 branch is `portage-hermes/PR-PATCH-006-provider-error-classifier` at `5e74e15`; fork integration commit is `5118f8b`. Duplicate/readiness search found no exact PR, but relevant overlaps include PR #4431 (`feat(llm): exponential backoff + Retry-After for LLM call retries`), PR #3504 (`fix(search): stabilize provider fallback behavior`), merged PR #868, and merged PR #1733. Validation passed: PR06 provider tests `8 passed`, existing provider/classification/fallback regressions `72 passed`, endpoint fallback regressions `8 passed`, app health smoke returned `healthy`, and fork scheduler conflict tests `16 passed`. | Keep PR06 integrated in `fork/hermes-portage` for fork functionality. Before any upstream PR, obtain or write a concrete linked issue/problem statement, confirm overlap status for #4431/#3504, rebase PR06 onto current `upstream/dev`, rerun gates, and prepare a template-complete draft PR. |
| BLOCK-PR15-UPSTREAM-001 | blocked | PR-PATCH-015 upstream draft PR | PR15 is implemented as an opt-in trajectory recorder and deterministic batch-eval helper, but there is no linked maintainer issue or concrete upstream problem statement yet. Opening an official PR now is high rejection risk as speculative evaluation infrastructure under `AGENTS.md`. | Local PR15 branch is `portage-hermes/PR-PATCH-015-trajectory-recorder-batch-eval` at `4e61483`; fork integration commit is `2095a46`. Duplicate/readiness search found no exact PR/issue for `trajectory recorder`, `batch eval`, `agent trajectories`, or `eval runner`. Validation passed: PR15 tests plus final metrics regression `20 passed`; fork PR15/sync smoke `28 passed`; CLI smoke via `python -m src.evals.cli` passed; upstream diff clean gate passed. | Keep PR15 integrated in `fork/hermes-portage` for fork functionality. Before any upstream PR, obtain or write a concrete linked issue/problem statement, rerun readiness search, read the official PR template, and prepare a template-complete draft PR for human approval. |

## Fork Functional Queue

| PR-PATCH | Fork status | Upstream status | Notes |
| --- | --- | --- | --- |
| PR-PATCH-001-capability-registry | integrated in `fork/hermes-portage` | upstream PR #4107 open | Required foundation for PR02. |
| PR-PATCH-002-toolset-scopes-profils | integrated in `fork/hermes-portage` | waiting for #4107 | Keep upstream candidate branch clean; do not add this tracker there. |
| PR-PATCH-003-plugin-hooks-middleware | integrated in `fork/hermes-portage` | blocked by #415/#416 duplicate risk | Upstream candidate branch remains clean and pushed to `origin`; tracker lives only on fork-stable. |
| PR-PATCH-004-turncontext-contextengine | integrated in `fork/hermes-portage` | blocked by open `agent_loop.py` overlap | Upstream candidate branch remains clean and pushed to `origin`; tracker lives only on fork-stable. |
| PR-PATCH-005-executor-budgets-result-store | integrated in `fork/hermes-portage` | blocked pending linked concrete issue/problem statement | Upstream candidate branch remains clean and pushed to `origin`; tracker lives only on fork-stable. |
| PR-PATCH-006-provider-error-classifier | integrated in `fork/hermes-portage` | blocked pending linked concrete issue/problem statement and provider fallback overlap review | Upstream candidate branch remains clean and pushed to `origin`; tracker lives only on fork-stable. |
| PR-PATCH-015-trajectory-recorder-batch-eval | integrated in `fork/hermes-portage` | blocked pending linked concrete issue/problem statement | Upstream candidate branch remains clean and pushed to `origin`; tracker lives only on fork-stable. |

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

When upstream `agent_loop.py` refactors no longer block PR04:

```powershell
git fetch upstream origin
git checkout portage-hermes/PR-PATCH-004-turncontext-contextengine
git rebase upstream/dev
scripts\18_validate_upstream_diff_clean.bat
$env:PYTHONUTF8='1'
python -m pytest -q tests\test_context_engine.py tests\test_context_budget.py tests\test_context_compactor.py tests\test_compaction_summary_failure.py tests\test_compact_truncate_tool_call_args.py tests\test_prompt_security.py tests\test_session_search.py tests\test_session_search_batch_fetch.py tests\test_skill_index_prompt_injection.py tests\test_user_time.py tests\test_agent_loop.py
gh pr create -R pewdiepie-archdaemon/odysseus --base dev --head JayceeB1:portage-hermes/PR-PATCH-004-turncontext-contextengine --title "feat(portage): add turn context engine adapter" --body-file .codex-log/pr-patch-004-upstream-pr-body.md --draft
```
