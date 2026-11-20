"""Generates synthetic CMDB CSVs with known data-quality problems. No real data."""
import csv
import random
from pathlib import Path

random.seed(42)
OUT = Path(__file__).parent
classes = ["cmdb_ci_linux_server", "cmdb_ci_win_server", "cmdb_ci_db_instance", "cmdb_ci_app_server"]
cis, rels = [], []
for i in range(1, 121):
    cls = random.choice(classes)
    cis.append({"sys_id": f"ci{i:04d}", "name": f"{cls.split('_')[2]}-{i:04d}.example.local",
                "sys_class_name": cls, "serial_number": f"SN{i:06d}", "operational_status": "1",
                "discovery_source": "ServiceNow", "last_discovered": f"2026-11-{random.randint(1, 19):02d}"})
for s in range(1, 9):
    cis.append({"sys_id": f"svc{s:03d}", "name": f"Sample Application Service {s}",
                "sys_class_name": "cmdb_ci_service_auto", "serial_number": "", "operational_status": "1",
                "discovery_source": "", "last_discovered": ""})
    for c in random.sample(cis[:120], 3):
        rels.append({"sys_id": f"rel{len(rels)+1:04d}", "parent": f"svc{s:03d}", "child": c["sys_id"],
                     "type": "Depends on::Used by"})
# Most infrastructure CIs run on or connect to another CI, so orphans stay rare.
for c in cis[:116]:
    target = random.choice([x for x in cis[:120] if x is not c])
    rels.append({"sys_id": f"rel{len(rels)+1:04d}", "parent": c["sys_id"], "child": target["sys_id"],
                 "type": "Runs on::Runs"})
# Seed known problems
cis[5]["serial_number"] = cis[4]["serial_number"]                 # duplicate serial
cis[10]["last_discovered"] = "2026-08-02"                           # stale
cis[11]["name"] = ""                                                # missing name
rels.append({"sys_id": "rel9999", "parent": "svc001", "child": "ci9999", "type": "Depends on::Used by"})  # dangling
cis.append({"sys_id": "svc999", "name": "Unmapped Service", "sys_class_name": "cmdb_ci_service_auto",
            "serial_number": "", "operational_status": "1", "discovery_source": "", "last_discovered": ""})

for name, rows in (("sample_cmdb_ci.csv", cis), ("sample_cmdb_rel_ci.csv", rels)):
    with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
print(f"wrote {len(cis)} CIs and {len(rels)} relationships")
