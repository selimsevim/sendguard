#!/usr/bin/env python3
"""SendGuard synthetic data generator.

Produces chunked CSVs for SFMC data extension import (SFMC rejects very large
files, so each dataset is split into part-files of --chunk-size rows, default
100k, each with its own header):
  - subscribers_partNNN.csv         (default 1,000,000 rows total)
  - engagement_events_partNNN.csv   (default 1,500,000 rows total)
  - campaign_audience_partNNN.csv   (default 200,000 rows total, WITH planted defects)

SFMC import: load part 001 with "Add and Update" (or Overwrite), then the
remaining parts into the SAME data extension with "Add and Update" -- never
Overwrite on parts >= 002 or earlier parts are wiped.

Planted defects (campaign_audience only):
  (a) ~8,000 duplicate subscriber_keys
  (b) ~5,000 members whose status is 'unsubscribed' in subscribers
  (c) parity defect is NOT planted -- created live in the demo

IMPORTANT (SFMC import): campaign_audience contains intentional duplicate
subscriber_keys. If you make subscriber_key the primary key of the target DE,
SFMC will silently dedupe on import and defect (a) disappears. Use
audience_row_id as the DE primary key (it is unique), or import with no PK.

Usage:
  python generate_data.py                  # full size
  python generate_data.py --small          # 10k/15k/2k rows, quick smoke test
  python generate_data.py --outdir ./out
"""

import argparse
import csv
import json
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from faker import Faker

SEED = 42
CAMPAIGN_IDS = [
    "CAMP-2026-SUMMER-LAUNCH",
    "CAMP-2026-SPRING-PROMO",
    "CAMP-2026-LOYALTY-Q2",
    "CAMP-2026-WINBACK",
    "CAMP-2026-NEWSLETTER-W23",
]
EVENT_TYPES = ["open", "click", "send", "bounce"]
EVENT_WEIGHTS = [0.40, 0.15, 0.40, 0.05]
COUNTRIES = ["NO", "SE", "DK", "FI", "DE", "NL", "GB", "US", "FR", "ES"]
EMAIL_DOMAINS = ["example.com", "example.org", "example.net", "mail-example.com"]

NOW = datetime(2026, 6, 10, 12, 0, 0)  # fixed so output is reproducible


def log(msg: str) -> None:
    print(f"[datagen] {msg}", flush=True)


class ChunkedCsvWriter:
    """Writes rows across numbered part-files (name_part001.csv, ...), each
    capped at chunk_size rows and carrying its own header, so every part can
    be imported into SFMC independently."""

    def __init__(self, outdir: Path, name: str, header: list[str], chunk_size: int):
        self.outdir, self.name, self.header = outdir, name, header
        self.chunk_size = chunk_size
        self.rows_in_part = 0
        self.part = 0
        self.total = 0
        self.files: list[str] = []
        self._fh = None
        self._writer = None

    def _roll(self):
        if self._fh:
            self._fh.close()
        self.part += 1
        path = self.outdir / f"{self.name}_part{self.part:03d}.csv"
        self.files.append(path.name)
        self._fh = open(path, "w", newline="")
        self._writer = csv.writer(self._fh)
        self._writer.writerow(self.header)
        self.rows_in_part = 0

    def writerow(self, row):
        if self._writer is None or self.rows_in_part >= self.chunk_size:
            self._roll()
        self._writer.writerow(row)
        self.rows_in_part += 1
        self.total += 1

    def close(self):
        if self._fh:
            self._fh.close()
        log(f"{self.name}: {self.total} rows across {self.part} part-files")


def build_name_pool(fake: Faker, size: int = 20000) -> list[tuple[str, str]]:
    """Pre-generate a pool of names with Faker; composing emails from the pool
    is ~50x faster than calling fake.email() per row at the 1M scale."""
    log(f"building name pool of {size} via Faker...")
    return [(fake.first_name(), fake.last_name()) for _ in range(size)]


def make_email(pool: list[tuple[str, str]], idx: int, rng: random.Random) -> str:
    first, last = pool[idx % len(pool)]
    domain = rng.choice(EMAIL_DOMAINS)
    return f"{first.lower()}.{last.lower()}.{idx}@{domain}".replace(" ", "")


def rand_date(rng: random.Random, days_back: int) -> str:
    dt = NOW - timedelta(days=rng.uniform(0, days_back))
    return dt.strftime("%Y-%m-%d")


def gen_subscribers(outdir: Path, n: int, unsub_rate: float, pool, rng, chunk_size: int) -> tuple[list[str], list[str], dict]:
    """Write subscribers part-files. Returns (active_keys, unsub_keys, key->email map)."""
    w = ChunkedCsvWriter(outdir, "subscribers",
                         ["subscriber_key", "email", "signup_date", "country", "status"], chunk_size)
    active_keys: list[str] = []
    unsub_keys: list[str] = []
    emails: dict[str, str] = {}
    t0 = time.time()
    for i in range(n):
        key = f"SUB{i:08d}"
        email = make_email(pool, i, rng)
        status = "unsubscribed" if rng.random() < unsub_rate else "active"
        w.writerow([key, email, rand_date(rng, 1095), rng.choice(COUNTRIES), status])
        emails[key] = email
        (unsub_keys if status == "unsubscribed" else active_keys).append(key)
        if i and i % 250000 == 0:
            log(f"  subscribers: {i}/{n}")
    w.close()
    log(f"subscribers: {len(unsub_keys)} unsubscribed, done in {time.time()-t0:.1f}s")
    return active_keys, unsub_keys, emails


def gen_events(outdir: Path, n: int, all_keys: list[str], rng, chunk_size: int) -> None:
    w = ChunkedCsvWriter(outdir, "engagement_events",
                         ["event_id", "subscriber_key", "event_type", "event_date", "campaign_id"], chunk_size)
    t0 = time.time()
    for i in range(n):
        w.writerow([
            f"EVT{i:08d}",
            rng.choice(all_keys),
            rng.choices(EVENT_TYPES, weights=EVENT_WEIGHTS, k=1)[0],
            rand_date(rng, 90),
            rng.choice(CAMPAIGN_IDS),
        ])
        if i and i % 250000 == 0:
            log(f"  events: {i}/{n}")
    w.close()
    log(f"engagement_events done in {time.time()-t0:.1f}s")


def gen_audience(outdir: Path, total: int, n_dupes: int, n_unsub: int,
                 active_keys, unsub_keys, emails, rng, chunk_size: int) -> dict:
    """campaign_audience part-files with planted defects (a) and (b). NO parity defect."""
    n_clean = total - n_dupes - n_unsub
    if n_clean <= 0:
        sys.exit("audience size too small for requested defect counts")
    if n_unsub > len(unsub_keys):
        sys.exit(f"not enough unsubscribed subscribers ({len(unsub_keys)}) to plant {n_unsub}")

    clean = rng.sample(active_keys, n_clean)
    planted_unsub = rng.sample(unsub_keys, n_unsub)
    base = clean + planted_unsub
    # duplicates: re-add keys that are already in the audience
    planted_dupes = rng.sample(base, n_dupes)
    rows = base + planted_dupes
    rng.shuffle(rows)

    t0 = time.time()
    w = ChunkedCsvWriter(outdir, "campaign_audience",
                         ["audience_row_id", "subscriber_key", "email", "country", "added_date"], chunk_size)
    for i, key in enumerate(rows):
        w.writerow([f"ROW{i:07d}", key, emails[key], rng.choice(COUNTRIES), rand_date(rng, 30)])
    w.close()
    log(f"campaign_audience done in {time.time()-t0:.1f}s")
    return {
        "total_rows": len(rows),
        "unique_subscriber_keys": len(set(rows)),
        "planted_duplicate_rows": n_dupes,
        "planted_unsubscribed_members": n_unsub,
        "parity_defect": "NOT planted - create live in demo",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subscribers", type=int, default=1_000_000)
    ap.add_argument("--events", type=int, default=1_500_000)
    ap.add_argument("--audience", type=int, default=200_000)
    ap.add_argument("--dupes", type=int, default=8_000)
    ap.add_argument("--unsub-in-audience", type=int, default=5_000)
    ap.add_argument("--unsub-rate", type=float, default=0.05)
    ap.add_argument("--chunk-size", type=int, default=100_000,
                    help="max rows per CSV part-file (default 100k, ~7MB)")
    ap.add_argument("--events-chunk-size", type=int, default=None,
                    help="override chunk size for engagement_events only")
    ap.add_argument("--outdir", default="output")
    ap.add_argument("--small", action="store_true", help="10k/15k/2k smoke-test sizes")
    args = ap.parse_args()

    if args.small:
        args.subscribers, args.events, args.audience = 10_000, 15_000, 2_000
        args.dupes, args.unsub_in_audience = 80, 50

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    fake = Faker()
    Faker.seed(SEED)

    pool = build_name_pool(fake)
    active, unsub, emails = gen_subscribers(outdir, args.subscribers, args.unsub_rate, pool, rng, args.chunk_size)
    gen_events(outdir, args.events, active + unsub, rng,
               args.events_chunk_size or args.chunk_size)
    stats = gen_audience(outdir, args.audience, args.dupes, args.unsub_in_audience,
                         active, unsub, emails, rng, args.chunk_size)

    manifest = {
        "generated_at": NOW.isoformat(),
        "seed": SEED,
        "subscribers": {"rows": args.subscribers, "unsubscribed_rate": args.unsub_rate,
                        "unsubscribed_count": len(unsub)},
        "engagement_events": {"rows": args.events},
        "campaign_audience": stats,
        "chunk_size": args.chunk_size,
        "sfmc_import_note": "Use audience_row_id as DE primary key so duplicate subscriber_keys survive import. "
                            "Import part 001 first, then remaining parts with 'Add and Update' (never Overwrite).",
    }
    with open(outdir / "defects_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    log("defects_manifest.json written")
    log("DONE")


if __name__ == "__main__":
    main()
