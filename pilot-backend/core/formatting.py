"""
Utilities for converting UI trees and action history into
compact, LLM-readable strings.
"""
from typing import Any, Dict, List


def format_ui_tree(ui_tree: Dict[str, Any]) -> str:
    """
    Convert a UI element tree (dict from Android) to a compact
    human-readable string for LLM prompts.

    Each line looks like:
      [3] Button: "Confirm UberX" [clickable]
      [5] EditText: hint:"Where to?" [clickable, editable]
    """
    lines: List[str] = []

    package = ui_tree.get("package", "unknown")
    screen_title = ui_tree.get("screen_title") or ui_tree.get("activity", "")
    header = f"App: {package}"
    if screen_title:
        header += f"  Screen: {screen_title}"
    lines.append(header)
    lines.append("")

    elements = ui_tree.get("elements", [])
    if not elements:
        lines.append("(No UI elements found on screen)")
        return "\n".join(lines)

    for el in elements:
        el_id = el.get("id", "?")
        # Android sends "class"; Python models use "class_name"
        class_name = el.get("class") or el.get("class_name") or "View"

        text = el.get("text") or ""
        hint = el.get("hint") or ""
        content_desc = el.get("content_desc") or ""
        resource_id = el.get("resource_id") or ""

        # Build human label
        label_parts: List[str] = []
        if text:
            label_parts.append(f'"{text}"')
        if hint and not text:
            label_parts.append(f'hint:"{hint}"')
        if content_desc:
            label_parts.append(f'desc:"{content_desc}"')
        if resource_id and not label_parts:
            label_parts.append(f'id:{resource_id.split("/")[-1]}')

        label = " ".join(label_parts) if label_parts else "(no label)"

        # Build flags
        flags: List[str] = []
        if el.get("clickable"):
            flags.append("clickable")
        if el.get("editable"):
            flags.append("editable")
        if el.get("scrollable"):
            flags.append("scrollable")
        if el.get("checked") is True:
            flags.append("checked")

        flags_str = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"[{el_id}] {class_name}: {label}{flags_str}")

    return "\n".join(lines)


def format_action_history(history: List[Dict[str, Any]]) -> str:
    """Format recent action history for LLM context."""
    if not history:
        return "(no previous actions)"

    lines: List[str] = []
    for i, action in enumerate(history, 1):
        action_type = action.get("action", "unknown")
        result = action.get("result", "unknown")
        status = action.get("status_text") or action.get("status") or ""

        if action_type == "tap":
            desc = f"tap(element #{action.get('element_id', '?')})"
        elif action_type == "type":
            val = action.get("value", "")
            desc = f"type(element #{action.get('element_id', '?')}, '{val}')"
        elif action_type == "open_app":
            desc = f"open_app({action.get('package', '?')})"
        elif action_type == "scroll_down":
            desc = "scroll_down"
        elif action_type == "scroll_up":
            desc = "scroll_up"
        elif action_type == "scroll_left":
            desc = "scroll_left"
        elif action_type == "scroll_right":
            desc = "scroll_right"
        elif action_type == "back":
            desc = "back"
        elif action_type == "home":
            desc = "home"
        elif action_type == "wait":
            desc = f"wait({action.get('seconds', 2)}s)"
        else:
            desc = action_type

        result_str = f" → {result}" if result and result != "unknown" else ""
        status_str = f" ({status})" if status else ""
        lines.append(f"{i}. {desc}{result_str}{status_str}")

    return "\n".join(lines)
