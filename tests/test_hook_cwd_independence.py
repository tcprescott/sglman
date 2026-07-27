"""Guardrail: the Claude Code hooks must not depend on the session's shell cwd.

Hooks are spawned with whatever cwd the session's Bash tool last cd'd into. Any
hook path resolved relative to that cwd — the script path in ``settings.json``,
a bare ``Path("tests")``, ``git`` run without a working directory — points at
the wrong tree once the session moves into a subdirectory. A PreToolUse hook
that cannot start exits non-zero, which the harness reads as "blocked", so a
stale cwd stops every Write/Edit/Bash call in the session.

These assertions are mechanical so the invariant survives new hooks being added.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SETTINGS = REPO / ".claude" / "settings.json"
SCRIPTS = REPO / ".claude" / "scripts"
HOOKS = REPO / ".claude" / "hooks"

ANCHOR_IMPORT = "from _hook_paths import anchor"


def _hook_commands() -> list[str]:
    config = json.loads(SETTINGS.read_text())
    return [
        hook["command"]
        for event in config["hooks"].values()
        for group in event
        for hook in group.get("hooks", [])
        if hook.get("type") == "command"
    ]


def test_settings_declares_hooks() -> None:
    """Guard the guard: an empty parse would make every assertion below vacuous."""
    assert len(_hook_commands()) >= 20


@pytest.mark.parametrize("command", _hook_commands())
def test_hook_command_is_anchored_to_project_dir(command: str) -> None:
    """No hook may be invoked through a cwd-relative path."""
    assert "${CLAUDE_PROJECT_DIR" in command, (
        f"hook command {command!r} resolves its script relative to the session cwd; "
        f'invoke it as "${{CLAUDE_PROJECT_DIR:-.}}/.claude/..." instead'
    )


@pytest.mark.parametrize("command", _hook_commands())
def test_hook_command_points_at_a_real_file(command: str) -> None:
    """A typo'd path fails the same way a stale cwd does — non-zero, i.e. blocked."""
    marker = ".claude/"
    start = command.index(marker)
    relative = command[start:].rstrip('"').strip()
    assert (REPO / relative).is_file(), f"hook command {command!r} names a missing file"


@pytest.mark.parametrize(
    "script", sorted(p for p in SCRIPTS.glob("*.py") if not p.name.startswith("_"))
)
def test_hook_script_anchors_its_cwd(script: Path) -> None:
    """Every hook script pins cwd to the repo before it resolves any path."""
    source = script.read_text()
    assert ANCHOR_IMPORT in source, (
        f"{script.name} does not import the cwd anchor; add "
        f"'{ANCHOR_IMPORT}' and call anchor() after the imports"
    )
    assert "anchor()" in source, f"{script.name} imports anchor but never calls it"


@pytest.mark.parametrize(
    "hook", sorted(p for p in HOOKS.glob("*.sh") if not p.name.startswith("_"))
)
def test_shell_hook_does_not_resolve_root_from_cwd(hook: Path) -> None:
    """Shell hooks take the repo root from _repo.sh, not from `git` in the cwd.

    `git rev-parse --show-toplevel` run in a foreign cwd fails, and these hooks
    `exit 0` on failure — so the check silently stops running instead of
    reporting anything.
    """
    source = hook.read_text()
    assert "rev-parse --show-toplevel" not in source, (
        f"{hook.name} resolves the repo root from the session cwd; "
        f'source "$( dirname "${{BASH_SOURCE[0]}}" )/_repo.sh" instead'
    )


def _run_from(cwd: Path, script: str, payload: dict, env_project_dir: str | None) -> int:
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(Path.home())}
    if env_project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = env_project_dir
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=30,
    ).returncode


VIOLATION = {
    "tool_name": "Write",
    "tool_input": {
        "file_path": str(REPO / "pages" / "probe.py"),
        "content": "from application.repositories.user_repository import UserRepository\n",
    },
}
CLEAN = {
    "tool_name": "Write",
    "tool_input": {"file_path": str(REPO / "pages" / "probe.py"), "content": "import os\n"},
}


@pytest.mark.parametrize("with_env", [True, False], ids=["with-project-dir", "without-project-dir"])
def test_hook_still_detects_a_violation_from_a_foreign_cwd(tmp_path: Path, with_env: bool) -> None:
    """End-to-end: the check fires from outside the repo, env var set or not.

    Without ``CLAUDE_PROJECT_DIR`` the script's own location is the fallback
    anchor, so a runner that does not set the variable still works.
    """
    project_dir = str(REPO) if with_env else None
    assert _run_from(tmp_path, "enforce_architecture.py", VIOLATION, project_dir) == 2
    assert _run_from(tmp_path, "enforce_architecture.py", CLEAN, project_dir) == 0
