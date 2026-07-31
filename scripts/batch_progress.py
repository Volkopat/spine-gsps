"""Report progress of a batch run without touching it."""
from __future__ import annotations

import collections
import glob
import json
import os
import statistics
import sys

rd = sys.argv[1] if len(sys.argv) > 1 else r"<path>\runs\verse_batch_01"
total = int(sys.argv[2]) if len(sys.argv) > 2 else 202

files = sorted(glob.glob(os.path.join(rd, "cases", "*.json")))
status = collections.Counter()
nverts, wall = [], []
for p in files:
    try:
        j = json.load(open(p))
    except Exception:
        status["unreadable"] += 1
        continue
    status[j.get("status", "?")] += 1
    if j.get("n_vertebrae"):
        nverts.append(j["n_vertebrae"])
    if j.get("wall_seconds"):
        wall.append(j["wall_seconds"])

n = len(files)
print("case JSONs written: %d / %d  (%.1f%%)" % (n, total, 100.0 * n / total))
print()
for k, v in status.most_common():
    print("  %-24s %4d  (%5.1f%%)" % (k, v, 100.0 * v / max(1, n)))

if nverts:
    print("\nvertebrae per labelled case: n=%d mean=%.1f min=%d max=%d"
          % (len(nverts), statistics.mean(nverts), min(nverts), max(nverts)))
if wall:
    med = statistics.median(wall)
    print("wall clock per case: mean=%.0f s  median=%.0f s  max=%.0f s"
          % (statistics.mean(wall), med, max(wall)))
    rem = max(0, total - n)
    print("remaining %d cases, roughly %.1f h at the median rate" % (rem, rem * med / 3600.0))

log = os.path.join(rd, "run_log.jsonl")
if os.path.exists(log):
    with open(log) as fh:
        lines = [ln for ln in fh if ln.strip()]
    print("\nrun_log.jsonl entries: %d" % len(lines))
