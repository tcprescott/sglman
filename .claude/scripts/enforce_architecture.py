#!/usr/bin/env python3
"""
PreToolUse hook: enforce the three-layer architecture boundary.

Reads a Claude Code tool-execution payload from stdin and exits with:
  0 — no violation (or not a Python file / not a tracked layer)
  2 — violation found (stderr describes exactly what was wrong)

Boundaries enforced:
  Presentation (pages/, theme/, frontend.py, api/, discordbot/)
    → MUST NOT import from application.repositories
  Repository (application/repositories/)
    → MUST NOT import from application.services
    → MUST NOT import from pages or theme
  Service (application/services/)
    → MUST NOT import nicegui (UI/session deps) — except allowlisted files
"""

import json
import os
import re
import sys


IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
    re.MULTILINE,
)

# Service files permitted to import NiceGUI despite the layer rule.
# auth_service.py needs app.storage.user for session identity.
NICEGUI_ALLOWLIST = {"auth_service.py"}


def extract_imports(content: str) -> list[str]:
    modules = []
    for m in IMPORT_RE.finditer(content):
        module = m.group(1) or m.group(2)
        if module:
            modules.append(module.strip())
    return modules


def classify(path: str) -> str | None:
    """Return 'presentation', 'service', 'repository', or None.

    api/ (REST routers) and discordbot/ (Discord interaction handlers) are
    entry surfaces — a second and third presentation layer alongside the web
    UI — so they obey the same rule: they may call services and do read-only
    load-or-404 model lookups, but must never import application.repositories.
    """
    norm = path.replace("\\", "/")
    if (
        "/pages/" in norm
        or norm.endswith("/pages")
        or "/theme/" in norm
        or norm.endswith("/theme")
        or norm.endswith("frontend.py")
        or "/api/" in norm
        or norm.startswith("api/")
        or "/discordbot/" in norm
        or norm.startswith("discordbot/")
    ):
        return "presentation"
    if "/application/services/" in norm or norm.endswith("/application/services"):
        return "service"
    if "/application/repositories/" in norm or norm.endswith(
        "/application/repositories"
    ):
        return "repository"
    return None


def check(file_path: str, content: str) -> list[str]:
    if not file_path.endswith(".py"):
        return []

    layer = classify(file_path)
    if layer is None:
        return []

    imports = extract_imports(content)
    violations = []

    if layer == "presentation":
        for mod in imports:
            if mod.startswith("application.repositories") or ".repositories." in mod:
                violations.append(
                    f"ARCHITECTURE VIOLATION in '{file_path}':\n"
                    f"  Presentation layer imports from repository layer: '{mod}'\n"
                    f"  pages/, theme/, api/, and discordbot/ must never import "
                    f"directly from application/repositories/.\n"
                    f"  Fix: route all data access through application/services/ instead."
                )

    elif layer == "repository":
        for mod in imports:
            if mod.startswith("application.services") or ".services." in mod:
                violations.append(
                    f"ARCHITECTURE VIOLATION in '{file_path}':\n"
                    f"  Repository layer imports from service layer: '{mod}'\n"
                    f"  application/repositories/ must never import from "
                    f"application/services/.\n"
                    f"  Fix: data flows upward — Repository → Service → Presentation. "
                    f"Move shared logic into a utility or model method."
                )
            if (
                mod.startswith("pages.")
                or mod == "pages"
                or mod.startswith("theme.")
                or mod == "theme"
            ):
                violations.append(
                    f"ARCHITECTURE VIOLATION in '{file_path}':\n"
                    f"  Repository layer imports from presentation layer: '{mod}'\n"
                    f"  application/repositories/ must never import from pages/ or theme/.\n"
                    f"  Fix: repositories are pure data access — remove all UI dependencies."
                )

    elif layer == "service":
        if os.path.basename(file_path) not in NICEGUI_ALLOWLIST:
            for mod in imports:
                if mod == "nicegui" or mod.startswith("nicegui."):
                    violations.append(
                        f"ARCHITECTURE VIOLATION in '{file_path}':\n"
                        f"  Service layer imports from NiceGUI: '{mod}'\n"
                        f"  application/services/ must not import nicegui (no UI/session deps).\n"
                        f"  Fix: keep UI/session access in the presentation layer; "
                        f"pass plain values into the service."
                    )

    return violations


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"enforce_architecture: could not parse stdin JSON: {exc}", file=sys.stderr)
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path:
        sys.exit(0)

    if tool_name == "Write":
        content = tool_input.get("content", "")
    elif tool_name == "Edit":
        content = tool_input.get("new_string", "")
    else:
        sys.exit(0)

    if not content:
        sys.exit(0)

    violations = check(file_path, content)
    if violations:
        for v in violations:
            print(v, file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
