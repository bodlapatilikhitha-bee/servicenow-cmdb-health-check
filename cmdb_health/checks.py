"""Data-quality checks for a ServiceNow CMDB export.

Works on CSV exports of cmdb_ci (or a child class) and cmdb_rel_ci so the
checks can run before an import, in CI, or against a nightly extract.
Written for this portfolio on synthetic data.
"""
from __future__ import annotations

import csv
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

REQUIRED_FIELDS = ("sys_id", "name", "sys_class_name", "operational_status")
# CSDM: an application service should depend on at least one infrastructure CI.
SERVICE_CLASSES = {"cmdb_ci_service_auto", "cmdb_ci_service_discovered", "cmdb_ci_service"}
INFRA_CLASSES = {"cmdb_ci_server", "cmdb_ci_linux_server", "cmdb_ci_win_server",
                 "cmdb_ci_db_instance", "cmdb_ci_app_server", "cmdb_ci_netgear"}


@dataclass
class Finding:
    check: str
    severity: str  # high | medium | low
    sys_id: str
    name: str
    detail: str


@dataclass
class Report:
    total_cis: int
    findings: list[Finding] = field(default_factory=list)

    def by_check(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for f in self.findings:
            counts[f.check] += 1
        return dict(counts)

    def health_score(self) -> float:
        """100 minus weighted findings per CI, floored at 0."""
        if not self.total_cis:
            return 100.0
        weights = {"high": 3, "medium": 2, "low": 1}
        penalty = sum(weights[f.severity] for f in self.findings) / self.total_cis
        return round(max(0.0, 100.0 - penalty * 20), 1)


def load_csv(path: str | Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [{k.strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def _norm(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def check_missing_fields(cis):
    for ci in cis:
        missing = [f for f in REQUIRED_FIELDS if not ci.get(f)]
        if missing:
            yield Finding("missing_required_fields", "medium", ci.get("sys_id", ""), ci.get("name", ""),
                          "missing: " + ", ".join(missing))


def check_duplicates(cis):
    """Flags CIs sharing a serial number, or the same normalized name + class."""
    by_serial, by_name = defaultdict(list), defaultdict(list)
    for ci in cis:
        if ci.get("serial_number"):
            by_serial[_norm(ci["serial_number"])].append(ci)
        by_name[(_norm(ci.get("name", "")), ci.get("sys_class_name", ""))].append(ci)
    seen = set()
    for key, group in list(by_serial.items()) + list(by_name.items()):
        if len(group) > 1 and key:
            ids = sorted(c["sys_id"] for c in group)
            sig = tuple(ids)
            if sig in seen:
                continue
            seen.add(sig)
            for c in group[1:]:
                yield Finding("duplicate_ci", "high", c["sys_id"], c.get("name", ""),
                              f"possible duplicate of {group[0]['sys_id']}")


def check_stale(cis, today: datetime, days: int = 30):
    cutoff = today - timedelta(days=days)
    for ci in cis:
        if ci.get("operational_status") != "1" or not ci.get("discovery_source"):
            continue  # only operational, discovered CIs are expected to be refreshed
        raw = ci.get("last_discovered", "")
        try:
            seen = datetime.strptime(raw[:10], "%Y-%m-%d")
        except ValueError:
            yield Finding("stale_ci", "medium", ci["sys_id"], ci.get("name", ""), "no valid last_discovered")
            continue
        if seen < cutoff:
            yield Finding("stale_ci", "medium", ci["sys_id"], ci.get("name", ""),
                          f"last discovered {raw[:10]} (> {days} days)")


def check_orphans(cis, rels):
    related = {r["parent"] for r in rels} | {r["child"] for r in rels}
    for ci in cis:
        if ci.get("sys_class_name") in INFRA_CLASSES | SERVICE_CLASSES and ci["sys_id"] not in related:
            yield Finding("orphan_ci", "low", ci["sys_id"], ci.get("name", ""), "no relationships")


def check_dangling_relationships(cis, rels):
    ids = {ci["sys_id"] for ci in cis}
    for r in rels:
        for end in ("parent", "child"):
            if r[end] not in ids:
                yield Finding("dangling_relationship", "high", r.get("sys_id", ""), r.get("type", ""),
                              f"{end} {r[end]} not found in CI export")


def check_csdm_services(cis, rels):
    by_id = {ci["sys_id"]: ci for ci in cis}
    children = defaultdict(set)
    for r in rels:
        children[r["parent"]].add(r["child"])
    for ci in cis:
        if ci.get("sys_class_name") in SERVICE_CLASSES:
            kids = [by_id.get(c, {}).get("sys_class_name") for c in children[ci["sys_id"]]]
            if not any(k in INFRA_CLASSES for k in kids):
                yield Finding("csdm_service_without_infra", "medium", ci["sys_id"], ci.get("name", ""),
                              "application service has no infrastructure dependency")


def run_all(cis, rels, today: datetime | None = None, stale_days: int = 30) -> Report:
    today = today or datetime.now()
    report = Report(total_cis=len(cis))
    for gen in (check_missing_fields(cis), check_duplicates(cis), check_stale(cis, today, stale_days),
                check_orphans(cis, rels), check_dangling_relationships(cis, rels),
                check_csdm_services(cis, rels)):
        report.findings.extend(gen)
    log.info("Checked %d CIs, %d findings", len(cis), len(report.findings))
    return report
