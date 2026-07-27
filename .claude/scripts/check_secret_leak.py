#!/usr/bin/env python3
"""
PostToolUse hook: block hardcoded secrets in source files.

Secrets must come from the environment (`os.environ` / `os.getenv`), never be
committed as literals. This flags two things in the edited file:
  1. A string that matches the Discord bot-token shape.
  2. An assignment to a secret-named variable (STORAGE_SECRET, DB_PASSWORD,
     *_TOKEN, *_SECRET, *_API_KEY, …) whose value is a hardcoded string literal.

Not flagged, because the name contains a secret-ish word but the value is public
config rather than a credential: names ending ``_URL``/``_URI``/``_ENDPOINT``/
``_PREFIX``/``_SUFFIX``/``_HEADER``/``_PARAM``/``_FIELD``/``_NAME`` (e.g.
``TOKEN_URL``, ``TOKEN_PREFIX``), and any plain ``http(s)://``/``ws(s)://`` value.
A credential smuggled into a URL is still caught — those carry ``@`` (userinfo)
or ``=`` (query parameter).

Exit 0 = clean / not applicable; exit 2 = likely secret (stderr explains).
"""

import ast
import json
import re
import sys

from _hook_paths import anchor

anchor()  # hooks inherit the session's shell cwd; pin paths to the repo

DISCORD_TOKEN_RX = re.compile(r"\b[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}\b")
SECRET_NAME_RX = re.compile(r"(?:SECRET|TOKEN|PASSWORD|PASSWD|API_?KEY)", re.IGNORECASE)
PLACEHOLDER_RX = re.compile(
    r"your|change[\s_-]?me|example|placeholder|replace|dummy|fake|test|<|\{|xxxx", re.IGNORECASE
)
# A lowercase dotted identifier like ``apitoken.created`` — the codebase's
# ``verb.object`` audit-action constants. Not a credential (secrets are
# high-entropy / mixed-case; Discord tokens are matched separately above).
ACTION_CONSTANT_RX = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
# Names that contain a secret-ish word but denote public, non-sensitive config:
# ``TOKEN_URL`` (an OAuth endpoint), ``TOKEN_PREFIX`` (the visible prefix every
# issued token carries). The secret is what these *address* or *label*, never
# their own value.
NON_SECRET_NAME_RX = re.compile(r"_(?:URL|URI|ENDPOINT|PREFIX|SUFFIX|HEADER|PARAM|FIELD|NAME)$")
URL_VALUE_RX = re.compile(r"^(?:https?|wss?)://", re.IGNORECASE)


def looks_like_secret_literal(value: str) -> bool:
    if len(value) < 12:
        return False
    if PLACEHOLDER_RX.search(value):
        return False
    if ACTION_CONSTANT_RX.match(value):
        return False
    # A URL is an address, not a credential — but only a *clean* one. A URL
    # carrying userinfo (``https://user:pw@host``) or a query credential
    # (``?access_token=…``) is exactly the leak this hook exists for, so those
    # fall through and stay flagged.
    if URL_VALUE_RX.match(value) and "@" not in value and "=" not in value:
        return False
    return True


def is_public_config(name: str, value: str) -> bool:
    """True when a secret-ish *name* denotes public config rather than a credential.

    Deliberately narrow, and never a blanket pass on the name: the value must
    also look benign. ``TOKEN_URL``/``TOKEN_PREFIX`` are exempt, while a
    ``*_URL`` that smuggles a credential is left to ``looks_like_secret_literal``
    to reject — the name must not become a way to launder a real secret past the
    check.
    """
    if not NON_SECRET_NAME_RX.search(name):
        return False
    if URL_VALUE_RX.match(value):
        return False  # value-based URL handling above decides, not the name
    # A prefix / header / field label is short by nature; a real key assigned to
    # such a name would run well past this.
    return len(value) <= 32


def assignment_targets(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    norm = file_path.replace("\\", "/")
    if "/.claude/" in norm or "/tests/" in norm or norm.startswith("tests/"):
        sys.exit(0)
    if norm.endswith(".env.example") or norm.endswith("/.env.example"):
        sys.exit(0)

    try:
        with open(file_path, encoding="utf-8") as fh:
            source = fh.read()
    except OSError:
        sys.exit(0)

    violations: list[tuple[int, str]] = []

    for m in DISCORD_TOKEN_RX.finditer(source):
        line = source.count("\n", 0, m.start()) + 1
        violations.append((line, "string matching a Discord bot-token shape"))

    if file_path.endswith(".py"):
        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError:
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                targets = assignment_targets(node)
                if not targets:
                    continue
                value = getattr(node, "value", None)
                if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                    continue
                if not looks_like_secret_literal(value.value):
                    continue
                for name in targets:
                    if is_public_config(name, value.value):
                        continue
                    if SECRET_NAME_RX.search(name):
                        violations.append(
                            (node.lineno, f"hardcoded literal assigned to secret-named '{name}'")
                        )

    if violations:
        for line, what in sorted(set(violations)):
            print(
                f"POSSIBLE SECRET LEAK in '{file_path}' (line {line}): {what}.\n"
                f"  Read secrets from the environment (os.environ / os.getenv), "
                f"never hardcode them.",
                file=sys.stderr,
            )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
