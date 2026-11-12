# Forecasts Roblox's up-and-coming chart: place-by-place top-10 probabilities for the next 72 hours.
# main.py — Roblox up-and-coming forecast (make.fun roblox-up-and-coming-forecast-01)
# Python 3.13, stdlib only, deterministic, no network.
import json
import math
import os
from datetime import datetime, timedelta, timezone
from statistics import median

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR") or "/input"
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"


def band(rank):
    if rank <= 10:
        return rank
    if rank <= 15:
        return "11-15"
    if rank <= 20:
        return "16-20"
    if rank <= 30:
        return "21-30"
    if rank <= 50:
        return "31-50"
    return "51+"


def parse_at(s):
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def load_reads(path):
    reads = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                reads.append(json.loads(line))
    reads.sort(key=lambda r: parse_at(r["at"]))
    return reads


def build_tables(reads, maxm):
    n = len(reads)
    tables = {}
    for m in range(1, maxm + 1):
        cases = {}
        hits = {}
        placed = {}
        for i in range(n - m):
            cur = reads[i]["up_and_coming"]
            nxt = sorted(reads[i + m]["up_and_coming"], key=lambda g: g["rank"])[:10]
            top_place = {g["universe_id"]: k for k, g in enumerate(nxt, start=1)}
            for g in cur:
                b = band(g["rank"])
                uid = g["universe_id"]
                cases[b] = cases.get(b, 0) + 1
                k = top_place.get(uid)
                if k is not None:
                    hits[b] = hits.get(b, 0) + 1
                    pb = placed.setdefault(b, {})
                    pb[k] = pb.get(k, 0) + 1
        tbl = {}
        for b in set(cases) | set(placed):
            p_in = (hits.get(b, 0) + 0.5) / (cases.get(b, 0) + 1.0)
            pb = placed.get(b, {})
            tot = sum(pb.values())
            dist = {k: (pb.get(k, 0) + 1.0) / (tot + 10.0) for k in range(1, 11)}
            tbl[b] = (p_in, dist)
        tables[m] = tbl
    return tables


def horizon_weights(read_hours):
    nmax = math.ceil(72.0 / read_hours) + 1
    raw = {}
    for m in range(1, nmax + 1):
        raw[m] = min(72.0, m * read_hours) - (m - 1) * read_hours
    total = sum(raw.values())
    if total <= 0:
        raw = {m: 1.0 for m in raw}
        total = float(len(raw))
    return {m: w / total for m, w in raw.items()}, nmax


def main():
    reads = load_reads(os.path.join(INPUT_DIR, "history.ndjson"))
    n = len(reads)

    gaps = [
        (parse_at(b["at"]) - parse_at(a["at"])).total_seconds() / 3600.0
        for a, b in zip(reads, reads[1:])
    ]
    recent_gaps = gaps[-20:]
    read_hours = median(recent_gaps) if recent_gaps else 1.0
    if read_hours <= 0:
        read_hours = 1.0

    maxm = max(1, min(n - 1, max(12, round(20.0 / read_hours))))
    tables = build_tables(reads, maxm)
    weights, nmax = horizon_weights(read_hours)

    last = sorted(reads[-1]["up_and_coming"], key=lambda g: g["rank"])
    max_rank = max(g["rank"] for g in last)
    prev = {}
    if n >= 2:
        prev = {g["universe_id"]: g["rank"] for g in reads[-2]["up_and_coming"]}

    DEFAULT = (0.5, {k: 0.1 for k in range(1, 11)})
    created = {}
    for r in reversed(reads):
        det = r.get("details")
        if not det:
            continue
        for uid, d in det.items():
            if uid not in created and isinstance(d, dict) and d.get("created"):
                created[int(uid)] = parse_at(d["created"])
    age_limit_days = timedelta(days=28)
    start_ts = parse_at(reads[-1]["at"])

    acc = {}
    for g in last:
        uid = g["universe_id"]
        rank = g["rank"]
        pr = prev.get(uid, rank)
        r_eff = round(rank - 0.4 * (pr - rank))
        r_eff = max(1, min(r_eff, max_rank))
        b = band(r_eff)
        c = created.get(uid)
        for h, w in weights.items():
            p_in, dist = tables[min(h, maxm)].get(b, DEFAULT)
            age_f = 1.0
            if c is not None and c + age_limit_days < start_ts + timedelta(hours=h):
                age_f = 0.02
            for k in range(1, 11):
                row = acc.setdefault(k, {})
                row[uid] = row.get(uid, 0.0) + w * p_in * age_f * dist[k]

    probabilities = []
    for k in range(1, 11):
        rows = sorted(acc.get(k, {}).items(), key=lambda t: (-t[1], t[0]))
        rows = [(u, p) for u, p in rows if p >= 0.0002]
        if rows:
            tot = sum(p for _, p in rows)
            if tot > 0.9:
                rows = [(u, p * 0.9 / tot) for u, p in rows]
        for u, p in rows:
            probabilities.append({"universe_id": u, "place": k, "p": round(p, 6)})

    top10 = [g["universe_id"] for g in last[:10]]
    forecast = {"probabilities": probabilities, "top10": top10}

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "forecast.json"), "w", encoding="utf-8") as f:
        json.dump(forecast, f, separators=(",", ":"))


if __name__ == "__main__":
    main()
