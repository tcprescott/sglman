#!/usr/bin/env python3
"""
PreToolUse hook: enforce the three-layer architecture boundary.

Reads a Claude Code tool-execution payload from stdin and exits with:
  0 — no violation (or not a Python file / not a tracked layer)
  2 — violation found (stderr describes exactly what was wrong)

Boundaries enforced:
  Presentation (pages/, theme/, frontend.py, api/, discordbot/)
    → MUST NOT import from application.repositories
    → MUST NOT reach through a service to its repository
      (`service.repository.foo(...)`, `self.x_repository.bar(...)`)
  Repository (application/repositories/)
    → MUST NOT import from application.services
    → MUST NOT import from any presentation surface (pages, theme, api,
      discordbot, frontend) or nicegui
  Service (application/services/)
    → MUST NOT import nicegui (UI/session deps) — except allowlisted files
    → MUST NOT import from any presentation surface (pages, theme, api,
      discordbot, frontend)
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

# CLAUDE.md forbids presentation reaching *through* a service to its repository
# (`service.repository.foo(...)`); the same shape also catches a page holding a
# repository attribute directly (`self.stream_room_repository.get_all()` — the
# exact bug class of the stream-room dialog AttributeError, audit §1.1). The
# attribute must END in `repository`, so names like `repository_url` never match.
REACHTHROUGH_RE = re.compile(r"\.\s*(\w*repository)\s*\.\s*\w+\s*\(")

# Module prefixes that mark the presentation surface, for the upward-import rules.
PRESENTATION_MODULES = ("pages", "theme", "frontend", "api", "discordbot")


def imports_presentation(mod: str) -> str | None:
    for prefix in PRESENTATION_MODULES:
        if mod == prefix or mod.startswith(prefix + "."):
            return prefix
    return None


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
    norm = file_path.replace("\\", "/")
    if "/.claude/" in norm or norm.startswith(".claude/"):
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
        for m in REACHTHROUGH_RE.finditer(content):
            line = content[: m.start()].count("\n") + 1
            snippet = content.splitlines()[line - 1].strip() if content.splitlines() else ""
            violations.append(
                f"ARCHITECTURE VIOLATION in '{file_path}' (line {line}):\n"
                f"  Presentation reaches through to a repository: `{snippet}`\n"
                f"  CLAUDE.md: entry surfaces must not use `service.repository.*` (or hold a\n"
                f"  repository attribute) — the repository is a service implementation detail.\n"
                f"  Fix: call a service method (add one if it doesn't exist yet)."
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
            surface = imports_presentation(mod)
            if surface or mod == "nicegui" or mod.startswith("nicegui."):
                violations.append(
                    f"ARCHITECTURE VIOLATION in '{file_path}':\n"
                    f"  Repository layer imports from the presentation surface: '{mod}'\n"
                    f"  application/repositories/ must never import from pages/, theme/,\n"
                    f"  api/, discordbot/, frontend, or nicegui.\n"
                    f"  Fix: repositories are pure data access — remove all UI dependencies."
                )

    elif layer == "service":
        allowlisted = os.path.basename(file_path) in NICEGUI_ALLOWLIST
        for mod in imports:
            if not allowlisted and (mod == "nicegui" or mod.startswith("nicegui.")):
                violations.append(
                    f"ARCHITECTURE VIOLATION in '{file_path}':\n"
                    f"  Service layer imports from NiceGUI: '{mod}'\n"
                    f"  application/services/ must not import nicegui (no UI/session deps).\n"
                    f"  Fix: keep UI/session access in the presentation layer; "
                    f"pass plain values into the service."
                )
            elif imports_presentation(mod):
                violations.append(
                    f"ARCHITECTURE VIOLATION in '{file_path}':\n"
                    f"  Service layer imports from the presentation surface: '{mod}'\n"
                    f"  application/services/ must not reach up into pages/, theme/, api/,\n"
                    f"  discordbot/, or frontend — data flows Repository → Service → Presentation.\n"
                    f"  Fix: move the shared piece into application/utils/ (or events/), or pass\n"
                    f"  plain values into the service from the caller."
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
