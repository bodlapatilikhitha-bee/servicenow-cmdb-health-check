from datetime import datetime
from pathlib import Path

from cmdb_health import checks
from cmdb_health.cli import main

DATA = Path(__file__).resolve().parents[1] / "data"
TODAY = datetime(2026, 11, 20)


def ci(sys_id, name="srv", cls="cmdb_ci_linux_server", serial="", status="1", src="ServiceNow", seen="2026-11-19"):
    return {"sys_id": sys_id, "name": name, "sys_class_name": cls, "serial_number": serial,
            "operational_status": status, "discovery_source": src, "last_discovered": seen}


def test_duplicate_serial_detected():
    found = list(checks.check_duplicates([ci("a", "x", serial="S1"), ci("b", "y", serial="s-1")]))
    assert [f.sys_id for f in found] == ["b"]


def test_duplicate_name_same_class_only():
    same = list(checks.check_duplicates([ci("a", "Web-01"), ci("b", "web01")]))
    diff = list(checks.check_duplicates([ci("a", "web01"), ci("b", "web01", cls="cmdb_ci_win_server")]))
    assert len(same) == 1 and diff == []


def test_stale_only_for_operational_discovered():
    cis = [ci("a", seen="2026-09-01"), ci("b", seen="2026-09-01", status="2"), ci("c", seen="2026-09-01", src="")]
    assert [f.sys_id for f in checks.check_stale(cis, TODAY)] == ["a"]


def test_bad_date_is_reported_not_crash():
    assert list(checks.check_stale([ci("a", seen="not-a-date")], TODAY))[0].check == "stale_ci"


def test_dangling_and_orphan():
    cis = [ci("a"), ci("b")]
    rels = [{"sys_id": "r1", "parent": "a", "child": "zzz", "type": "Depends on"}]
    assert [f.check for f in checks.check_dangling_relationships(cis, rels)] == ["dangling_relationship"]
    assert [f.sys_id for f in checks.check_orphans(cis, rels)] == ["b"]


def test_csdm_service_needs_infrastructure():
    cis = [ci("svc", cls="cmdb_ci_service_auto", src=""), ci("srv")]
    assert list(checks.check_csdm_services(cis, [{"parent": "svc", "child": "srv"}])) == []
    assert len(list(checks.check_csdm_services(cis, []))) == 1


def test_sample_data_finds_seeded_problems():
    report = checks.run_all(checks.load_csv(DATA / "sample_cmdb_ci.csv"),
                            checks.load_csv(DATA / "sample_cmdb_rel_ci.csv"), today=TODAY)
    counts = report.by_check()
    for key in ("duplicate_ci", "stale_ci", "missing_required_fields",
                "dangling_relationship", "csdm_service_without_infra"):
        assert counts.get(key, 0) >= 1, key
    assert 0 <= report.health_score() <= 100


def test_cli_writes_findings(tmp_path):
    out = tmp_path / "findings.csv"
    rc = main(["--cis", str(DATA / "sample_cmdb_ci.csv"), "--rels", str(DATA / "sample_cmdb_rel_ci.csv"),
               "--as-of", "2026-11-20", "--out", str(out)])
    assert rc == 0 and out.read_text().startswith("check,severity")


def test_cli_missing_file_returns_2():
    assert main(["--cis", "nope.csv", "--rels", "nope.csv"]) == 2
