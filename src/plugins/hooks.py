"""Hook dispatch helpers used by runtime code."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from src.plugins.manager import get_plugin_manager
from src.plugins.models import HookDecision, HookPoint, ToolInvocationContext


async def dispatch_before_tool(
    *,
    tool_name: str,
    content: str,
    owner: Optional[str] = None,
    session_id: Optional[str] = None,
    workspace: Optional[str] = None,
) -> HookDecision:
    context = ToolInvocationContext(
        tool_name=tool_name,
        content=content,
        owner=owner,
        session_id=session_id,
        run_id=session_id,
        workspace=workspace,
    )
    return await get_plugin_manager().dispatch(HookPoint.BEFORE_TOOL, context)


async def dispatch_after_tool(
    *,
    tool_name: str,
    content: str,
    result: Mapping[str, Any],
    owner: Optional[str] = None,
    session_id: Optional[str] = None,
    workspace: Optional[str] = None,
) -> HookDecision:
    context = ToolInvocationContext(
        tool_name=tool_name,
        content=content,
        owner=owner,
        session_id=session_id,
        run_id=session_id,
        workspace=workspace,
        result=result,
    )
    return await get_plugin_manager().dispatch(HookPoint.AFTER_TOOL, context)
