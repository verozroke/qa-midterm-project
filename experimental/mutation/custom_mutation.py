"""custom_mutation.py — lightweight, reproducible mutation testing.

mutmut is the standard but it hits issues on some Python versions and needs
its own DB.  This script is self-contained: it reads `app/main.py`, applies
a fixed list of realistic mutations, runs the existing pytest suite against
each mutant, and reports a mutation score.

Why bother with a custom runner?
  - Deterministic: the mutant list is version-controlled.
  - Fast: only ~15 mutants, targeted at high-risk lines.
  - CI-friendly: produces a machine-readable JSON result.

Usage:
    cd <project root>
    python experimental/mutation/custom_mutation.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "app" / "main.py"
BACKUP = ROOT / "app" / "main.py.bak"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


@dataclass
class Mutation:
    """A single mutation: replace `original` with `mutated` in the target file.

    `module` is a free-text label used for reporting (groups mutants by the
    functional area they touch).
    """
    id: str
    module: str
    mutation_type: str
    original: str
    mutated: str
    description: str


# ── Mutation catalogue ────────────────────────────────────────────────
# These target the high-risk modules from the midterm risk register:
#   1. Authentication     — invalid credential handling, token validation
#   2. Ticket validation  — input sanitisation, length checks
#   3. Ticket CRUD        — status transitions, update logic
#
# Each mutation replaces a UNIQUE substring in app/main.py — mutmut-style but
# simpler. If you edit main.py and a mutation stops matching, this script will
# report it as "not applied" instead of silently passing.
MUTATIONS = [
    # ─── Authentication module ─────────────────────────────────────────
    Mutation(
        id="M-AUTH-01",
        module="Authentication",
        mutation_type="Comparison operator flip",
        # Anchor to the API login (followed by Invalid credentials) — pattern
        # also exists in the UI login route, but we want to mutate only one
        # site to keep the per-mutation blast radius small and targeted.
        original=(
            'if not user or user["password_hash"] != _hash_pw(password):\n'
            '            return jsonify({"error": "Invalid credentials"}), 401'
        ),
        mutated=(
            'if not user or user["password_hash"] == _hash_pw(password):\n'
            '            return jsonify({"error": "Invalid credentials"}), 401'
        ),
        description="Flip password check (API login) — accepts wrong passwords.",
    ),
    Mutation(
        id="M-AUTH-02",
        module="Authentication",
        mutation_type="Return value mutation",
        original="return info[\"user_id\"]",
        mutated="return None",
        description="Token validation always returns None — breaks all auth.",
    ),
    Mutation(
        id="M-AUTH-03",
        module="Authentication",
        mutation_type="Boolean short-circuit removal",
        original="if not username or not password:",
        mutated="if not username and not password:",
        description="Change OR to AND in credential check — weakens validation.",
    ),
    Mutation(
        id="M-AUTH-04",
        module="Authentication",
        mutation_type="Constant alteration",
        original="expires = datetime.now(timezone.utc) + timedelta(hours=2)",
        mutated="expires = datetime.now(timezone.utc) + timedelta(hours=0)",
        description="Tokens expire immediately on creation.",
    ),
    Mutation(
        id="M-AUTH-05",
        module="Authentication",
        mutation_type="Negation removal",
        original="if datetime.now(timezone.utc) > info[\"expires_at\"]:",
        mutated="if datetime.now(timezone.utc) < info[\"expires_at\"]:",
        description="Expiry check inverted — expired tokens treated as valid.",
    ),

    # ─── Ticket validation module ──────────────────────────────────────
    Mutation(
        id="M-VAL-01",
        module="Ticket Validation",
        mutation_type="Boundary alteration",
        original="elif len(title) > 200:",
        mutated="elif len(title) > 2000:",
        description="Title length limit raised from 200 to 2000 — weaker validation.",
    ),
    Mutation(
        id="M-VAL-02",
        module="Ticket Validation",
        mutation_type="Tuple member removal",
        original='if priority not in ("low", "medium", "high", "critical"):',
        mutated='if priority not in ("low", "medium", "high"):',
        description="'critical' priority no longer accepted — regression.",
    ),
    Mutation(
        id="M-VAL-03",
        module="Ticket Validation",
        mutation_type="Conditional removal",
        original="if errors:\n            return jsonify({\"errors\": errors}), 422",
        mutated="if False:\n            return jsonify({\"errors\": errors}), 422",
        description="Validation errors never returned — invalid tickets accepted.",
    ),
    Mutation(
        id="M-VAL-04",
        module="Ticket Validation",
        mutation_type="Empty-string check removal",
        original='if not title:',
        mutated='if title:',
        description="'Required' check inverted — empty title passes, non-empty fails.",
    ),

    # ─── Ticket CRUD module ────────────────────────────────────────────
    Mutation(
        id="M-CRUD-01",
        module="Ticket CRUD",
        mutation_type="HTTP status code change",
        # Anchor to the GET /api/tickets/<id> handler specifically.
        # The "Ticket not found" text repeats in 3 handlers (GET/PUT/DELETE);
        # `return jsonify(dict(ticket)), 200` uniquely follows the GET one.
        original=(
            '            return jsonify({"error": "Ticket not found"}), 404\n'
            '        return jsonify(dict(ticket)), 200'
        ),
        mutated=(
            '            return jsonify({"error": "Ticket not found"}), 200\n'
            '        return jsonify(dict(ticket)), 200'
        ),
        description="GET missing ticket returns 200 instead of 404.",
    ),
    Mutation(
        id="M-CRUD-02",
        module="Ticket CRUD",
        mutation_type="SQL WHERE clause removal",
        original='"SELECT * FROM tickets WHERE created_by = ? ORDER BY created_at DESC",\n            (g.current_user_id,),',
        mutated='"SELECT * FROM tickets ORDER BY created_at DESC",\n            (),',
        description="User filter removed from list query — privacy leak.",
    ),
    Mutation(
        id="M-CRUD-03",
        module="Ticket CRUD",
        mutation_type="DELETE statement bypass",
        original='db.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))',
        mutated='# db.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))',
        description="Delete is silently a no-op.",
    ),
    Mutation(
        id="M-CRUD-04",
        module="Ticket CRUD",
        mutation_type="Default value change",
        original="priority TEXT NOT NULL DEFAULT 'medium',",
        mutated="priority TEXT NOT NULL DEFAULT 'low',",
        description="Default priority changed — may affect downstream logic.",
    ),

    # ─── Notifications (secondary module) ──────────────────────────────
    Mutation(
        id="M-NOTIF-01",
        module="Notifications",
        mutation_type="LIMIT constant change",
        original="ORDER BY created_at DESC LIMIT 20",
        mutated="ORDER BY created_at DESC LIMIT 0",
        description="Notifications list always empty.",
    ),
    Mutation(
        id="M-NOTIF-02",
        module="Notifications",
        mutation_type="Boolean field mutation",
        original="SET is_read = 1",
        mutated="SET is_read = 0",
        description="'Mark as read' actually marks as unread.",
    ),
]


def apply_mutation(source: str, mutation: Mutation) -> tuple[str, bool]:
    """Return (new_source, was_applied). Applied only if original is unique."""
    count = source.count(mutation.original)
    if count == 0:
        return source, False
    if count > 1:
        # Ambiguous — refuse to mutate rather than corrupt the file.
        print(f"  ⚠  {mutation.id}: `original` appears {count}x, skipping (make it unique).")
        return source, False
    return source.replace(mutation.original, mutation.mutated, 1), True


import atexit

# Child-process handle for the app when we manage it ourselves.
_app_proc: subprocess.Popen | None = None


def _app_is_up(timeout: float = 1.0) -> bool:
    """Is the Flask app reachable on localhost:8080?"""
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:8080/api/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _start_app() -> subprocess.Popen:
    """Start the app in a subprocess and wait until it's ready.

    CRITICAL for mutation testing: the app must be STARTED AFTER the file
    is mutated, so the mutated bytes are what gets imported. If we reused
    a long-running app, every mutant would falsely 'survive'.
    """
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        if _app_is_up(timeout=0.5):
            return proc
        time.sleep(0.2)
    proc.kill()
    raise RuntimeError("App failed to start within 10s.")


def _stop_app(proc: subprocess.Popen | None):
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    except Exception:
        pass


# Set at startup; referenced by run_tests. Makes the decision explicit rather
# than trying-and-failing 15 times on every single mutant.
_TEST_TARGETS: list[str] = []
_MANAGE_APP: bool = False  # if True, restart app fresh for every mutant


def run_tests() -> tuple[bool, str]:
    """Run the pytest suite against the current (possibly mutated) code.

    If _MANAGE_APP is True, we kill any old app process and start a fresh one
    so the API tests exercise the mutated bytes. Unit tests are immune —
    they use create_app() directly, which imports the file fresh anyway.
    """
    global _app_proc

    if _MANAGE_APP:
        # Kill the user's existing app if any — we need control of the port.
        _stop_app(_app_proc)
        _app_proc = None
        try:
            _app_proc = _start_app()
        except RuntimeError as e:
            return False, f"App start failed: {e}"

    cmd = [sys.executable, "-m", "pytest", *_TEST_TARGETS,
           "-x", "-q", "--tb=no", "--no-header",
           "-p", "no:cacheprovider"]
    try:
        proc = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        return proc.returncode == 0, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"


@atexit.register
def _cleanup():
    _stop_app(_app_proc)


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Decide execution mode. Three possibilities, in order of coverage:
    #
    #   A. App NOT running, --manage-app given → we start/restart the app
    #      for every mutant. Best coverage (unit + API tests), ~2× slower.
    #
    #   B. App NOT running, no flag → only unit tests. Still meaningful
    #      (unit tests use create_app() so they see mutations), but fewer
    #      code paths are exercised → lower score, more false survivors.
    #
    #   C. App IS running already → we DON'T touch it, but warn clearly:
    #      API tests will hit the stale (unmutated) process and report
    #      false survival. Unit tests still work.
    global _TEST_TARGETS, _MANAGE_APP
    manage_flag = "--manage-app" in sys.argv

    if manage_flag:
        _TEST_TARGETS = ["tests/unit/", "tests/api/"]
        _MANAGE_APP = True
        print("✓ --manage-app: will restart the Flask process for every mutant.")
    elif _app_is_up():
        _TEST_TARGETS = ["tests/unit/"]
        _MANAGE_APP = False
        print("⚠ App is already running — API tests would hit the STALE")
        print("  unmutated process and report false survival.  Falling back")
        print("  to UNIT TESTS ONLY.  For a full run, stop the app and")
        print("  re-run this script with  --manage-app.\n")
    else:
        _TEST_TARGETS = ["tests/unit/"]
        _MANAGE_APP = False
        print("ℹ App not running — using UNIT TESTS ONLY.")
        print("  For better coverage, re-run with  --manage-app  (restarts")
        print("  the app between every mutant).\n")

    # Sanity check — unmodified tests must pass first.
    print("── Running baseline tests (unmodified code) ──")
    ok, out = run_tests()
    if not ok:
        print("✗ Baseline tests FAILED. Fix the suite before running mutation.")
        print(out[-2000:])
        sys.exit(1)
    print("✓ Baseline tests pass.\n")

    shutil.copy2(TARGET, BACKUP)
    original_source = BACKUP.read_text(encoding="utf-8")

    results = []
    start = time.time()

    try:
        for i, m in enumerate(MUTATIONS, 1):
            print(f"[{i:>2}/{len(MUTATIONS)}] {m.id} ({m.module}): {m.mutation_type}")
            mutated_source, applied = apply_mutation(original_source, m)
            if not applied:
                print(f"       ⚠ NOT APPLIED — pattern not found.")
                results.append({**asdict(m), "status": "not_applied", "duration_s": 0.0})
                continue

            TARGET.write_text(mutated_source, encoding="utf-8")
            t0 = time.time()
            tests_passed, test_output = run_tests()
            dt = time.time() - t0

            # Mutant "killed" if tests FAIL (suite detected the bug).
            # Mutant "survived" if tests still PASS (gap in coverage).
            status = "survived" if tests_passed else "killed"
            icon = "🟢 killed  " if status == "killed" else "🔴 SURVIVED"
            print(f"       {icon}  ({dt:.1f}s)")

            results.append({**asdict(m), "status": status, "duration_s": round(dt, 2)})
    finally:
        # Always restore original file — never leave mutations in place.
        TARGET.write_text(original_source, encoding="utf-8")
        BACKUP.unlink(missing_ok=True)
        print("\n✓ Restored original app/main.py")

    # ── Report ────────────────────────────────────────────────────────
    total = len(results)
    applied = [r for r in results if r["status"] != "not_applied"]
    killed = [r for r in applied if r["status"] == "killed"]
    survived = [r for r in applied if r["status"] == "survived"]
    score = (len(killed) / len(applied) * 100) if applied else 0.0

    by_module = {}
    for r in applied:
        mod = r["module"]
        by_module.setdefault(mod, {"created": 0, "killed": 0, "survived": 0})
        by_module[mod]["created"] += 1
        by_module[mod][r["status"]] += 1

    print("\n" + "=" * 70)
    print(f"  MUTATION TESTING REPORT   (elapsed: {time.time()-start:.1f}s)")
    print("=" * 70)
    print(f"  Mutants defined : {total}")
    print(f"  Applied         : {len(applied)}")
    print(f"  Killed          : {len(killed)}")
    print(f"  Survived        : {len(survived)}")
    print(f"  MUTATION SCORE  : {score:.1f}%")
    print()
    print(f"  {'Module':<22} {'Created':>8} {'Killed':>8} {'Survived':>10} {'Score':>8}")
    print("  " + "-" * 60)
    for mod, s in sorted(by_module.items()):
        msc = (s["killed"] / s["created"] * 100) if s["created"] else 0
        print(f"  {mod:<22} {s['created']:>8} {s['killed']:>8} {s['survived']:>10} {msc:>7.1f}%")
    print("=" * 70)

    if survived:
        print("\n  ⚠ SURVIVING MUTANTS (investigate for coverage gaps):")
        for r in survived:
            print(f"    • {r['id']} [{r['module']}] {r['description']}")

    out_file = RESULTS_DIR / "mutation_report.json"
    out_file.write_text(json.dumps({
        "summary": {
            "total": total, "applied": len(applied),
            "killed": len(killed), "survived": len(survived),
            "mutation_score": round(score, 2),
        },
        "by_module": by_module,
        "results": results,
    }, indent=2))
    print(f"\n  ✓ JSON report: {out_file.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
