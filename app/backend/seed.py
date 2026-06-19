"""Seed a fresh DB from app/data/seed/* so the app demos with no robot.

    python -m app.backend.seed
"""

from __future__ import annotations

import json
import os

from app.backend import assets as assets_mod
from app.backend import config, ingest
from app.backend import store as store_mod


def _load_json(path):
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_jsonl(path):
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main() -> None:
    config.ensure_dirs()
    if os.path.isfile(config.DB_PATH):
        os.remove(config.DB_PATH)
    s = store_mod.Store(config.DB_PATH)
    seed = config.SEED_DIR

    n_ev = 0
    for e in _load_json(os.path.join(seed, "events.sample.json")):
        s.upsert_event(ingest.normalize_event(e)); n_ev += 1
    n_br = 0
    for b in _load_json(os.path.join(seed, "briefs.sample.json")):
        s.upsert_brief(ingest.normalize_brief(b)); n_br += 1
    n_rec = 0
    for r in _load_jsonl(os.path.join(seed, "workstation_log.sample.jsonl")):
        s.insert_record(ingest.normalize_record(r)); n_rec += 1
    n_acc = 0
    for a in _load_json(os.path.join(seed, "acceptance.sample.json")):
        s.insert_acceptance(ingest.normalize_acceptance(a)); n_acc += 1
    n_rep = 0
    for rp in _load_json(os.path.join(seed, "reports.sample.json")):
        s.insert_report(ingest.normalize_report(rp)); n_rep += 1
    n_as = 0
    if os.path.isfile(config.ASSETS_CSV):
        n_as = assets_mod.seed_assets(s, assets_mod.load_assets_csv(config.ASSETS_CSV))

    s.close()
    print(f"seeded {config.DB_PATH}: events={n_ev} briefs={n_br} records={n_rec} "
          f"acceptance={n_acc} reports={n_rep} assets={n_as}")


if __name__ == "__main__":
    main()
