"""Builtin toolset profiles for Odysseus surfaces."""

from __future__ import annotations

from typing import Mapping


MINIMAL_TOOLS = frozenset({
    "ask_user",
    "update_plan",
    "ui_control",
})

RESEARCH_TOOLS = frozenset({
    "web_search",
    "web_fetch",
    "trigger_research",
    "manage_research",
})

FILES_TOOLS = frozenset({
    "get_workspace",
    "read_file",
    "grep",
    "glob",
    "ls",
    "write_file",
    "edit_file",
})

SHELL_TOOLS = frozenset({
    "bash",
    "python",
})

ADMIN_TOOLS = frozenset({
    "ask_teacher",
    "chat_with_model",
    "create_session",
    "list_models",
    "list_sessions",
    "manage_documents",
    "manage_endpoints",
    "manage_mcp",
    "manage_memory",
    "manage_session",
    "manage_settings",
    "manage_skills",
    "manage_tasks",
    "manage_" + "to" + "kens",
    "manage_webhooks",
    "pipeline",
    "send_to_session",
})

CRON_TOOLS = frozenset({
    "api_call",
    "archive_email",
    "bulk_email",
    "create_document",
    "delete_email",
    "list_email_accounts",
    "list_emails",
    "manage_calendar",
    "manage_memory",
    "manage_notes",
    "manage_tasks",
    "mark_email_read",
    "read_email",
    "reply_to_email",
    "resolve_contact",
    "search_chats",
    "send_email",
    "update_document",
})

GATEWAY_TOOLS = frozenset({
    "api_call",
    "list_email_accounts",
    "list_emails",
    "manage_calendar",
    "manage_memory",
    "manage_notes",
    "manage_tasks",
    "read_email",
    "reply_to_email",
    "resolve_contact",
    "send_email",
})

BROWSER_TOOLS = frozenset({
    "web_fetch",
    "web_search",
})


BUILTIN_TOOLSETS: Mapping[str, frozenset[str]] = {
    "minimal": MINIMAL_TOOLS,
    "research": RESEARCH_TOOLS,
    "files": FILES_TOOLS,
    "shell": SHELL_TOOLS,
    "admin": ADMIN_TOOLS,
    "cron": CRON_TOOLS,
    "gateway": GATEWAY_TOOLS,
    "browser": BROWSER_TOOLS,
}


# None means historical behavior for that surface unless a caller explicitly
# requests a profile.
SURFACE_DEFAULT_TOOLSETS: Mapping[str, tuple[str, ...] | None] = {
    "web": None,
    "api": None,
    "admin": ("minimal", "admin", "research", "files", "shell", "browser"),
    "cron": ("minimal", "cron", "research"),
    "gateway": ("minimal", "gateway", "research"),
    "browser": ("minimal", "browser"),
}
