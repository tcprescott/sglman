"""Guardrail: every check in ``.claude/scripts/`` is accounted for in CI.

The hooks fire on a Write/Edit inside a Claude session and nowhere else, so
``scripts/guardrails.py`` replays them against files on disk for everyone else.
A check that exists but is not listed there is enforced for exactly one author
on exactly one tool — the failure mode is silent, because nothing goes red.

So the invariant is coverage, not correctness: each script must be replayed, or
be named in ``EXCLUDED_CHECKS`` with a reason. Adding a hook without touching
either fails here.
"""

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / ".claude" / "scripts"
SETTINGS = REPO / ".claude" / "settings.json"


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "_guardrails_runner", REPO / "scripts" / "guardrails.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _script_stems() -> set[str]:
    return {
        p.stem
        for p in SCRIPTS.glob("*.py")
        if not p.stem.startswith("_")
    }


def _settings_stems() -> set[str]:
    config = json.loads(SETTINGS.read_text())
    commands = [
        hook["command"]
        for event in config["hooks"].values()
        for group in event
        for hook in group.get("hooks", [])
        if hook.get("type") == "command"
    ]
    return {
        Path(token.strip('"')).stem
        for command in commands
        for token in command.split()
        if "/.claude/scripts/" in token
    }


def test_scripts_directory_is_not_empty() -> None:
    """Guard the guard: an empty listing would make everything below vacuous."""
    assert len(_script_stems()) > 10


def test_every_check_is_replayed_or_excluded() -> None:
    runner = _load_runner()
    covered = (
        set(runner.FILE_CHECKS)
        | set(runner.CHANGED_ONLY_CHECKS)
        | set(runner.REPO_CHECKS)
        | set(runner.EXCLUDED_CHECKS)
    )
    missing = sorted(_script_stems() - covered)
    assert not missing, (
        "These .claude/scripts/ checks are neither replayed by "
        "scripts/guardrails.py nor listed in its EXCLUDED_CHECKS, so they bind "
        f"Claude sessions only and never CI: {missing}"
    )


def test_runner_names_no_check_that_does_not_exist() -> None:
    runner = _load_runner()
    named = (
        set(runner.FILE_CHECKS)
        | set(runner.CHANGED_ONLY_CHECKS)
        | set(runner.REPO_CHECKS)
        | set(runner.EXCLUDED_CHECKS)
    )
    stale = sorted(named - _script_stems())
    assert not stale, (
        f"scripts/guardrails.py names checks with no script on disk: {stale}"
    )


def test_every_check_is_wired_as_a_hook() -> None:
    """The other half: a script CI replays but no hook runs is dead in-session."""
    orphans = sorted(_script_stems() - _settings_stems())
    assert not orphans, (
        "These .claude/scripts/ checks are not wired into .claude/settings.json, "
        f"so they never fire during a Claude session: {orphans}"
    )
