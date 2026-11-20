"""Command line entry point: python -m cmdb_health.cli --cis ... --rels ..."""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import datetime

from .checks import load_csv, run_all


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Run CMDB data-quality checks on CSV exports.")
    p.add_argument("--cis", required=True, help="CSV export of cmdb_ci")
    p.add_argument("--rels", required=True, help="CSV export of cmdb_rel_ci")
    p.add_argument("--out", help="write findings to this CSV file")
    p.add_argument("--stale-days", type=int, default=30)
    p.add_argument("--as-of", help="evaluation date YYYY-MM-DD (default: today)")
    p.add_argument("--fail-under", type=float, default=0.0, help="exit 1 if health score is below this")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        cis, rels = load_csv(args.cis), load_csv(args.rels)
    except (OSError, csv.Error) as exc:
        logging.error("Could not read input: %s", exc)
        return 2

    today = datetime.strptime(args.as_of, "%Y-%m-%d") if args.as_of else None
    report = run_all(cis, rels, today=today, stale_days=args.stale_days)

    print(f"CIs checked: {report.total_cis}")
    print(f"Health score: {report.health_score()} / 100")
    for check, n in sorted(report.by_check().items()):
        print(f"  {check:32} {n}")

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["check", "severity", "sys_id", "name", "detail"])
            for f in report.findings:
                w.writerow([f.check, f.severity, f.sys_id, f.name, f.detail])
        print(f"Findings written to {args.out}")

    return 1 if report.health_score() < args.fail_under else 0


if __name__ == "__main__":
    sys.exit(main())
