"""Quality gate — parses JUnit XML and enforces thresholds."""
from __future__ import annotations
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPORT = Path("test-results/pytest-report.xml")
MIN_PASS_RATE = 90.0
MAX_CRITICAL_FAILURES = 0
MAX_SKIPPED_PERCENT = 20.0
MIN_TOTAL_TESTS = 15

# for commit

def main():
    if not REPORT.exists():
        print(f"ERROR: {REPORT} not found"); sys.exit(2)
    tree = ET.parse(REPORT)
    root = tree.getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        print("ERROR: no <testsuite>"); sys.exit(2)

    total = int(suite.attrib.get("tests", 0))
    fail = int(suite.attrib.get("failures", 0)) + int(suite.attrib.get("errors", 0))
    skip = int(suite.attrib.get("skipped", 0))
    executed = total - skip
    passed = executed - fail
    rate = (passed / executed * 100) if executed else 0
    skip_pct = (skip / total * 100) if total else 0
    time_s = float(suite.attrib.get("time", 0))

    print("=" * 60)
    print("QUALITY GATE REPORT")
    print("=" * 60)
    print(f"  Total:       {total}")
    print(f"  Passed:      {passed}")
    print(f"  Failed:      {fail}")
    print(f"  Skipped:     {skip}")
    print(f"  Pass rate:   {rate:.1f}%")
    print(f"  Skip rate:   {skip_pct:.1f}%")
    print(f"  Time:        {time_s:.2f}s")
    print("=" * 60)

    violations = []
    if rate < MIN_PASS_RATE:
        violations.append(f"Pass rate {rate:.1f}% < {MIN_PASS_RATE}%")
    if fail > MAX_CRITICAL_FAILURES:
        violations.append(f"{fail} failure(s) (max {MAX_CRITICAL_FAILURES})")
    if skip_pct > MAX_SKIPPED_PERCENT:
        violations.append(f"Skipped {skip_pct:.1f}% > {MAX_SKIPPED_PERCENT}%")
    if total < MIN_TOTAL_TESTS:
        violations.append(f"Only {total} tests (min {MIN_TOTAL_TESTS})")

    if violations:
        print("\nQUALITY GATE: FAILED")
        for v in violations:
            print(f"  ✗ {v}")
        sys.exit(1)
    else:
        print("\nQUALITY GATE: PASSED ✓")


if __name__ == "__main__":
    main()
