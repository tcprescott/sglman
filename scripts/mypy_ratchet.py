#!/usr/bin/env python3
"""Run mypy and fail only when a file's error count grows.

Mypy has been informational (`continue-on-error`) since it was added, which
means it never stopped anything: the count only ever went up. Making it blocking
outright is not on the table — the tree carries ~1450 errors, and most are
Tortoise reverse relations and FK ``*_id`` attributes that mypy structurally
cannot see on a dynamically-built ORM model. Those are the ORM's shape, not
defects to fix.

A ratchet gets the value without the cleanup: ``scripts/mypy_baseline.json``
records the per-file error count, and a run fails when any file exceeds its
entry or a clean file starts producing errors. Existing debt stays put; new debt
does not land. Fixing errors and re-recording makes the baseline smaller, and it
can only grow when somebody deliberately runs ``--update``.

Usage::

    python scripts/mypy_ratchet.py            # check (what CI runs)
    python scripts/mypy_ratchet.py --update   # re-record after fixing errors
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = ROOT / "scripts" / "mypy_baseline.json"

# Same surface the CI lint job has always checked.
TARGETS = ["application", "api", "middleware", "main.py", "frontend.py"]

ERROR_RE = re.compile(r"^(?P<path>[^:]+):\d+:(?:\d+:)? error: ")


def run_mypy() -> Counter[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", *TARGETS],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if proc.returncode not in (0, 1):
        print(proc.stdout or proc.stderr, file=sys.stderr)
        raise SystemExit(f"mypy failed to run (exit {proc.returncode})")

    counts: Counter[str] = Counter()
    for line in proc.stdout.splitlines():
        m = ERROR_RE.match(line)
        if m:
            counts[m.group("path").replace("\\", "/")] += 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--update", action="store_true",
        help="re-record the current counts as the accepted baseline",
    )
    args = ap.parse_args()

    counts = run_mypy()

    if args.update:
        BASELINE_PATH.write_text(
            json.dumps(dict(sorted(counts.items())), indent=2) + "\n", encoding="utf-8"
        )
        print(f"baseline updated: {sum(counts.values())} errors across {len(counts)} files")
        return 0

    baseline: dict[str, int] = (
        json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        if BASELINE_PATH.exists() else {}
    )

    regressions = sorted(
        (path, baseline.get(path, 0), n)
        for path, n in counts.items()
        if n > baseline.get(path, 0)
    )
    improvements = sorted(
        (path, was, counts.get(path, 0))
        for path, was in baseline.items()
        if counts.get(path, 0) < was
    )

    if regressions:
        print("Mypy regressions — these files gained type errors:\n", file=sys.stderr)
        for path, was, now in regressions:
            print(f"  {path}: {was} -> {now}", file=sys.stderr)
        print(
            "\nRun `poetry run mypy " + " ".join(TARGETS) + "` to see them.\n"
            "If an error is a Tortoise-ORM false positive mypy cannot resolve, "
            "silence it at the line with a targeted `# type: ignore[code]` rather "
            "than re-recording the baseline.",
            file=sys.stderr,
        )
        return 1

    total = sum(counts.values())
    msg = f"mypy ratchet: {total} error(s), none above baseline"
    if improvements:
        freed = sum(was - now for _, was, now in improvements)
        msg += (
            f" — {freed} fewer in {len(improvements)} file(s); "
            "re-record with `python scripts/mypy_ratchet.py --update`"
        )
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
