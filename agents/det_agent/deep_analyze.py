"""Deep per-day analysis of a run.

Shows per-day cover, revenue, cash, util, walkout patterns and computes
implied per-cover revenue, daily margin, and identifies missed-revenue days
(util 1.0 + walkouts = capacity-bound = missed sales).

Usage:
  python -m agents.det_agent.deep_analyze [run.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def analyze(data: dict) -> None:
    results = data["results"]
    print("\n" + "=" * 100)
    print("  DEEP ANALYSIS — per-scenario insights")
    print("=" * 100)

    # Per-scenario aggregates
    by_scen: dict[str, list[dict]] = {}
    for r in results:
        by_scen.setdefault(r["scenario"], []).append(r)

    for scen, games in by_scen.items():
        avg_score = sum(g.get("score", 0) for g in games) / len(games)
        print(f"\n  📊 {scen} — avg score {avg_score:+,.0f}")
        for g in games:
            log = g.get("days_log", [])
            if not log:
                continue
            seed = g["seed"]
            covers = [d.get("cov", 0) or 0 for d in log]
            revs = [d.get("rev", 0) or 0 for d in log]
            cash_traj = [d.get("cash", 0) or 0 for d in log]
            util = [d.get("util", 0) or 0 for d in log]
            walk_days = sum(1 for d in log if d.get("walk") in ("Some", "Many"))
            walk_many_days = sum(1 for d in log if d.get("walk") == "Many")
            cap_bound = sum(1 for u in util if u >= 0.95)
            avg_cov = sum(covers) / max(1, len(covers))
            avg_rev = sum(revs) / max(1, len(revs))
            per_cover = avg_rev / max(1, avg_cov)
            score = g.get("score", 0)
            print(f"    seed {seed}: score={score:+8.0f}  covers_avg={avg_cov:>5.0f}  "
                  f"rev/cover={per_cover:>5.2f}  walk_days={walk_days:>2} (Many={walk_many_days})  "
                  f"cap_bound_days={cap_bound:>2}")
            # Top walkout days (where we missed revenue)
            many = [(d["d"], d["cov"], d["wx"]) for d in log if d.get("walk") == "Many"]
            if many:
                samp = ", ".join(f"d{d}({c}cov,{wx})" for d, c, wx in many[:5])
                print(f"      Many walkout days: {samp}")
            # Best days
            top_revs = sorted([(d.get("d",0), d.get("rev",0), d.get("cov",0)) for d in log],
                             key=lambda x: -x[1])[:3]
            print(f"      top revenue: {', '.join(f'd{d}(rev{r:.0f},c{c})' for d,r,c in top_revs)}")

    # Aggregate diagnostics
    print("\n" + "=" * 100)
    print("  OPPORTUNITY ANALYSIS")
    print("=" * 100)
    cap_bound_days = 0
    walk_days_total = 0
    total_days = 0
    rev_per_cover_avg = 0
    rev_per_cover_n = 0
    for r in results:
        log = r.get("days_log", [])
        for d in log:
            total_days += 1
            if (d.get("util", 0) or 0) >= 0.95:
                cap_bound_days += 1
            if d.get("walk") in ("Some", "Many"):
                walk_days_total += 1
            cov = d.get("cov") or 0
            rev = d.get("rev") or 0
            if cov > 0:
                rev_per_cover_avg += rev / cov
                rev_per_cover_n += 1
    print(f"  Total game-days analyzed: {total_days}")
    print(f"  Capacity-bound days (util>=95%): {cap_bound_days} ({100*cap_bound_days/total_days:.1f}%)")
    print(f"  Walkout days (Some/Many): {walk_days_total} ({100*walk_days_total/total_days:.1f}%)")
    if rev_per_cover_n:
        print(f"  Avg revenue/cover: €{rev_per_cover_avg/rev_per_cover_n:.2f}")


def main():
    if len(sys.argv) >= 2:
        path = Path(sys.argv[1])
        data = json.loads(path.read_text())
    else:
        files = sorted(Path("eval_runs").glob("run-*.json"))
        if not files:
            print("No runs found.")
            sys.exit(1)
        path = files[-1]
        data = json.loads(path.read_text())
    print(f"Analyzing: {path}")
    analyze(data)


if __name__ == "__main__":
    main()
