#!/usr/bin/env python3
"""Nationwide dealer-locator sweep orchestrator.

Iterates the 50 states + DC, invoking each per-maker scraper in
tools/ for each state. Per-state failures don't kill the run.
Progress + per-state results are appended to output/scrape.log.

Run modes:
  --resume        skip (state, maker) pairs already present in
                  output/dealers_final.json (default).
  --restart       ignore existing data, re-scrape everything.
  --states CA,TX  only these states. Default: 50 states + DC.
  --makers ford,chevy,stellantis-ram,japan
                  subset to run. Default: all 4 scraper scripts.

Each maker's scraper writes to output/dealers_final.json in place
with per-(make, state) slice replacement, so re-runs are safe.

Run in the background and tail the log:

    python scripts/scrape_all_states.py > /tmp/scrape.out 2>&1 &
    tail -f output/scrape.log
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "dealers_final.json"
LOG = ROOT / "output" / "scrape.log"
VENV_PY = Path(
    "/Users/cbagci/Library/CloudStorage/OneDrive-UCSF/Documents/carpapi/venv/bin/python"
)

# Each entry: human-friendly key → (script path, extra args, slug-state map key)
SCRAPERS: dict[str, tuple[Path, list[str], list[str]]] = {
    # key:           (script,                                            extra args,        the make-id values written to dealers_final.json)
    "ford":          (ROOT / "tools" / "ford_dealers.py",                [],                ["15"]),
    "chevy":         (ROOT / "tools" / "Chevrolet-GMC-Buick.py",         [],                ["9"]),
    "stellantis-ram":(ROOT / "tools" / "dodge-ram-chrysler-jeep.py",     ["--brand", "R"],  ["66"]),
    "japan":         (ROOT / "tools" / "japan.py",                       [],                ["27", "44", "46"]),
}

# 50 states + DC. Excludes territories and military codes.
ALL_STATES = [
    "AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL",
    "IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE",
    "NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD",
    "TN","TX","UT","VT","VA","WA","WV","WI","WY",
]

# state-name slugs (snake-case, hyphenated) matching the maker URL convention
STATE_SLUGS = {
    "AL":"alabama","AK":"alaska","AZ":"arizona","AR":"arkansas","CA":"california",
    "CO":"colorado","CT":"connecticut","DE":"delaware","DC":"district-of-columbia",
    "FL":"florida","GA":"georgia","HI":"hawaii","ID":"idaho","IL":"illinois",
    "IN":"indiana","IA":"iowa","KS":"kansas","KY":"kentucky","LA":"louisiana",
    "ME":"maine","MD":"maryland","MA":"massachusetts","MI":"michigan","MN":"minnesota",
    "MS":"mississippi","MO":"missouri","MT":"montana","NE":"nebraska","NV":"nevada",
    "NH":"new-hampshire","NJ":"new-jersey","NM":"new-mexico","NY":"new-york",
    "NC":"north-carolina","ND":"north-dakota","OH":"ohio","OK":"oklahoma","OR":"oregon",
    "PA":"pennsylvania","RI":"rhode-island","SC":"south-carolina","SD":"south-dakota",
    "TN":"tennessee","TX":"texas","UT":"utah","VT":"vermont","VA":"virginia",
    "WA":"washington","WV":"west-virginia","WI":"wisconsin","WY":"wyoming",
}


def log(line: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    full = f"[{ts}] {line}"
    print(full, flush=True)
    with LOG.open("a") as f:
        f.write(full + "\n")


def already_done(state_code: str, make_ids: list[str]) -> bool:
    """A (state, maker) pair is 'done' when at least one matching entry
    exists in dealers_final.json. Used by --resume."""
    if not OUTPUT.exists():
        return False
    try:
        data = json.loads(OUTPUT.read_text())
    except Exception:                                         # noqa: BLE001
        return False
    slug = STATE_SLUGS[state_code]
    for d in data:
        if d.get("state") == slug and d.get("make_id") in make_ids:
            return True
    return False


def run_scraper(scraper_key: str, state_code: str) -> int:
    script, extra, _ = SCRAPERS[scraper_key]
    cmd = [str(VENV_PY), str(script), "--state", state_code, *extra]
    log(f"  ▶ {scraper_key} {state_code}: {' '.join(cmd[1:])}")
    t0 = time.time()
    proc = subprocess.run(
        cmd, cwd=str(ROOT), text=True, capture_output=True, check=False,
    )
    dur = time.time() - t0
    tail = (proc.stdout or "").strip().splitlines()[-2:] if proc.stdout else []
    for line in tail:
        log(f"    | {line}")
    if proc.returncode != 0:
        for line in (proc.stderr or "").strip().splitlines()[-5:]:
            log(f"    | stderr: {line}")
        log(f"  ✗ {scraper_key} {state_code}: rc={proc.returncode} ({dur:.1f}s)")
    else:
        log(f"  ✓ {scraper_key} {state_code}: ok ({dur:.1f}s)")
    return proc.returncode


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--states", default=",".join(ALL_STATES),
                   help="Comma-separated USPS codes. Default: 50 states + DC.")
    p.add_argument("--makers", default=",".join(SCRAPERS),
                   help=f"Comma-separated subset of: {','.join(SCRAPERS)}")
    p.add_argument("--restart", action="store_true",
                   help="Ignore existing dealer entries; re-scrape everything.")
    p.add_argument("--sleep-between-states", type=float, default=0.0,
                   help="Sleep N seconds between states (rate-limit budget).")
    args = p.parse_args()

    states = [s.strip().upper() for s in args.states.split(",") if s.strip()]
    makers = [m.strip().lower() for m in args.makers.split(",") if m.strip()]
    bad = [m for m in makers if m not in SCRAPERS]
    if bad:
        log(f"unknown maker(s): {bad}; valid: {list(SCRAPERS)}")
        return 2

    log("=" * 72)
    log(f"nationwide sweep starting: {len(states)} states × {len(makers)} makers")
    log(f"  states: {','.join(states)}")
    log(f"  makers: {','.join(makers)}")
    log(f"  mode:   {'RESTART' if args.restart else 'RESUME'}")
    log(f"  output: {OUTPUT}")
    log(f"  log:    {LOG}")

    total_runs = 0
    failures = 0
    skipped = 0
    t_overall = time.time()
    for state_code in states:
        if state_code not in STATE_SLUGS:
            log(f"skipping unknown state code: {state_code}")
            continue
        log(f"── {state_code} ────────────────────────────────────────────")
        for maker in makers:
            _, _, make_ids = SCRAPERS[maker]
            if not args.restart and already_done(state_code, make_ids):
                log(f"  · {maker} {state_code}: skipped (already in output)")
                skipped += 1
                continue
            rc = run_scraper(maker, state_code)
            total_runs += 1
            if rc != 0:
                failures += 1
        if args.sleep_between_states:
            time.sleep(args.sleep_between_states)

    dur = time.time() - t_overall
    log("=" * 72)
    log(f"DONE in {dur/60:.1f} min · runs={total_runs} failures={failures} skipped={skipped}")
    log(f"next step: python web/backend/seed_dealers.py to upsert into public.dealers")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
