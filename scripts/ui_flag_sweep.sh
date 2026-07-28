#!/usr/bin/env bash
#
# Feature-flag sweep: drive the ungated surfaces of the running app with feature
# flags OFF, and catch the surfaces that break.
#
# Why: gating is two-sided — an entry surface hides a disabled feature, and the
# owning service refuses it (FeatureDisabledError). A surface that is *not*
# gated but calls a gated service anyway looks fine on a tenant that has the
# feature and dies on one that doesn't. Nothing in the Python suite renders
# pages, so this is the check: force every flag off on a scratch tenant, walk
# the always-present home/admin tabs, and report anything that failed to render.
#
# Two passes:
#   1. all-off  — every flag forced off on the primary dev tenant.
#   2. mixed    — the second dev tenant as seeded (online features on, community
#                 features off), which catches the flag-A-on/flag-B-off crossings
#                 an all-off pass cannot see.
#
# Prereqs (see the ui-validation skill): scripts/setup_env.sh, the app running
# (./start.sh mock > /tmp/app.log), and scripts/seed_dev.py.
#
# Usage:
#   scripts/ui_flag_sweep.sh [--tenant default] [--mixed-tenant second]
#                            [--login staff_user] [--out /tmp/ui-flag-sweep]
#                            [--targets scripts/ui_flag_targets.json]
#   APP_LOG=/tmp/app.log scripts/ui_flag_sweep.sh      # server-side traceback check
#
# Exits non-zero if any pass reported a rendered failure; screenshots and text
# dumps for every target land in --out/<pass>/.
set -uo pipefail
cd "$(dirname "$0")/.."

TENANT=default
MIXED_TENANT=second
LOGIN=staff_user
OUT=/tmp/ui-flag-sweep
TARGETS=scripts/ui_flag_targets.json
APP_LOG=${APP_LOG:-/tmp/app.log}

while [ $# -gt 0 ]; do
  case "$1" in
    --tenant) TENANT=$2; shift 2 ;;
    --mixed-tenant) MIXED_TENANT=$2; shift 2 ;;
    --login) LOGIN=$2; shift 2 ;;
    --out) OUT=$2; shift 2 ;;
    --targets) TARGETS=$2; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "$OUT"
SNAPSHOT=$OUT/flags-snapshot.json
LOG_MARK=$(wc -l < "$APP_LOG" 2>/dev/null || echo 0)
FAILED=0

# Restore the tenant's real flag state however we exit — an interrupted sweep
# must not leave the dev database with every feature switched off.
restore_flags() {
  if [ -f "$SNAPSHOT" ]; then
    echo "--- restoring $TENANT feature flags"
    poetry run python scripts/set_feature_flags.py --tenant "$TENANT" --restore "$SNAPSHOT" >/dev/null
  fi
}
trap restore_flags EXIT INT TERM

write_config() {  # $1=tenant  $2=outdir -> writes $2/config.json
  mkdir -p "$2"
  TENANT_SLUG=$1 OUTDIR=$2 LOGIN_AS=$LOGIN TARGETS_FILE=$TARGETS python3 - <<'PY'
import json, os
targets = json.load(open(os.environ['TARGETS_FILE']))['targets']
config = {
    'loginAs': os.environ['LOGIN_AS'],
    'tenant': os.environ['TENANT_SLUG'],
    'outDir': os.environ['OUTDIR'],
    'targets': targets,
}
json.dump(config, open(os.path.join(os.environ['OUTDIR'], 'config.json'), 'w'), indent=2)
PY
}

run_pass() {  # $1=label  $2=tenant
  local label=$1 tenant=$2 dir="$OUT/$1"
  echo
  echo "=== pass '$label' (tenant '$tenant') ==="
  write_config "$tenant" "$dir"
  poetry run python scripts/set_feature_flags.py --tenant "$tenant" --show | sed -n '/live flags/,$p'
  if NODE_PATH=$(npm root -g) node scripts/ui_smoke.js "$dir/config.json" > "$dir/run.log" 2>&1; then
    echo "pass '$label': OK (screenshots in $dir)"
  else
    FAILED=1
    echo "pass '$label': FAILURES"
    sed -n '/=== rendered failures ===/,$p' "$dir/run.log"
    echo "  full output: $dir/run.log"
  fi
}

echo "--- snapshotting $TENANT feature flags, then forcing every flag off"
poetry run python scripts/set_feature_flags.py --tenant "$TENANT" --snapshot "$SNAPSHOT" --off all
run_pass all-off "$TENANT"
restore_flags

if poetry run python scripts/set_feature_flags.py --tenant "$MIXED_TENANT" --show >/dev/null 2>&1; then
  run_pass mixed "$MIXED_TENANT"
else
  echo "(skipping mixed pass: no tenant '$MIXED_TENANT' — run scripts/seed_dev.py)"
fi

# Server-side half, and not a nicety: a section that loads its data in a
# background task (the Service Health board, any deferred loader) fails *after*
# the DOM has been checked, so the browser half sees a plausible-looking page and
# only the log shows the FeatureDisabledError.
if [ -f "$APP_LOG" ]; then
  echo
  echo "=== server-side errors logged during the sweep ==="
  tail -n "+$((LOG_MARK + 1))" "$APP_LOG" > "$OUT/app-log-slice.txt"
  if grep -nE "Failed to build tab|Unhandled exception in a UI event handler|FeatureDisabledError:" \
       -A6 "$OUT/app-log-slice.txt"; then
    FAILED=1
    echo "  (full server log slice: $OUT/app-log-slice.txt)"
  else
    echo "(none)"
  fi
fi

echo
[ "$FAILED" -eq 0 ] && echo "flag sweep: clean" || echo "flag sweep: FAILURES (see above)"
exit "$FAILED"
