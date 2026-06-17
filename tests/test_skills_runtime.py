"""Tests for PR-PATCH-009 skills runtime and learning loop."""

import pytest

from src.skills import (
    ManifestValidationError,
    SkillAuditLog,
    SkillManifest,
    SkillRuntime,
    SkillRuntimePolicy,
    propose_skill_update,
)

pytestmark = [pytest.mark.area_unit, pytest.mark.portage, pytest.mark.pr_009]


def test_skill_runtime_enables_matching_skill_when_permissions_allowed():
    manifest = SkillManifest.from_mapping(
        {
            "name": "repo-status",
            "description": "Check repository status",
            "permissions": ["files"],
            "triggers": ["repo status"],
            "status": "published",
        }
    )

    resolution = SkillRuntime(SkillRuntimePolicy.allow("files")).resolve(
        [manifest],
        "please get repo status",
    )

    assert resolution.enabled == (manifest,)
    messages = resolution.untrusted_context_messages()
    assert messages[0]["role"] == "user"
    assert messages[0]["metadata"]["trusted"] is False
    assert messages[0]["metadata"]["source"] == "skill:repo-status"


def test_skill_runtime_refuses_shell_skill_without_permission():
    manifest = SkillManifest.from_mapping(
        {
            "name": "shell-helper",
            "description": "Run shell commands",
            "permissions": ["shell"],
            "triggers": ["run command"],
            "status": "published",
        }
    )

    resolution = SkillRuntime(SkillRuntimePolicy.allow("files")).resolve(
        [manifest],
        "run command",
    )

    assert resolution.enabled == ()
    assert resolution.disabled[0] == (manifest, "permission-denied:shell")


def test_invalid_manifest_is_refused_fail_closed():
    with pytest.raises(ManifestValidationError):
        SkillManifest.from_mapping(
            {
                "name": "../escape",
                "permissions": ["shell"],
                "status": "published",
            }
        )

    with pytest.raises(ManifestValidationError):
        SkillManifest.from_mapping(
            {
                "name": "unsafe-permission",
                "permissions": ["godmode"],
                "status": "published",
            }
        )


def test_learning_loop_proposes_update_without_committing(tmp_path):
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("# unchanged\n", encoding="utf-8")

    proposal = propose_skill_update(
        target_skill="repo-status",
        summary="Add validation after git status",
        run_trace=[{"type": "tool", "text": "token=SECRET123 git status"}],
    )

    assert proposal.requires_approval is True
    assert proposal.committed is False
    assert "token=<redacted>" in proposal.proposed_markdown
    assert skill_file.read_text(encoding="utf-8") == "# unchanged\n"


def test_skill_audit_log_redacts_secret_reasons():
    manifest = SkillManifest.from_mapping(
        {
            "name": "audited-skill",
            "description": "Audited",
            "permissions": [],
            "triggers": ["audit"],
            "status": "published",
        }
    )
    log = SkillAuditLog()

    event = log.record_install_review(
        manifest,
        decision="needs-human-review",
        reasons=("api_key=SECRET123 requested network install",),
    )

    assert log.events == [event]
    assert event.to_trace()["reasons"] == ["api_key=<redacted> requested network install"]
