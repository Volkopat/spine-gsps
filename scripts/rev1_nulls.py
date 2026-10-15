"""Major revision, step 2: permutation nulls that respect the data's dependence.

Reviewer 3 (point 3) and reviewer 4 both note that the published null shuffled the
wrong/right labels across all 1845 matched vertebrae, which breaks the clustering of
vertebrae within cases and the variation of error rate by level, and that a p of 1/1001 from
1000 random permutations is a Monte Carlo p-value, not an exact one. Reviewer 4 adds that the
held-out ceiling (0.570) was set against the in-sample null, when the reference for a held-out
value is the held-out procedure run on no signal, which should sit near 0.5.

Three nulls, all running the identical coordinate-ascent search E1 used (E1._ascend):

  within_case    labels permuted among the vertebrae of each case, so every case keeps its
                 number of errors. The in-sample per-level ceiling is recomputed per draw.
  within_level   labels permuted among vertebrae of the same anatomical level, so every level
                 keeps its error rate. Same statistic.
  heldout        labels permuted within case, then the full held-out procedure E1 used
                 (20 random case halvings, fitted on one half, scored on the other, both
                 directions, 40 folds) is run and its mean held-out AUC recorded. This is the
                 reference distribution for the observed held-out 0.570.
  heldout_level  the same held-out procedure with labels permuted within level, which keeps
                 each level's error rate and so measures how much of the held-out value a
                 mapping can earn from level base rates alone.

Monte Carlo p-values are (1 + number of draws >= observed) / (1 + draws), reported as such.
Every draw is written out, so the distributions can be re-examined without re-running.

Usage (spinelab env; uses all cores but two):
    python scripts/rev1_nulls.py [--reps 1000] [--heldout-reps 200]
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))
import e1_ablation as E1  # noqa: E402
from spinelab.paths import RESULTS  # noqa: E402

G: dict = {}


def _load(rows_path: str) -> dict:
    d = json.load(open(rows_path))
    rows = [r for r in d["rows"] if r["matched"]]
    m = np.array([r["chan_conf"] for r in rows], dtype=float)
    w = np.array([bool(r["wrong"]) for r in rows])
    levels = sorted({r["name"] for r in rows})
    li = np.array([levels.index(r["name"]) for r in rows], dtype=np.int64)
    cases = np.array([r["case"] for r in rows])
    uniq = sorted(set(cases.tolist()))
    groups_case = [np.where(cases == c)[0] for c in uniq]
    groups_level = [np.where(li == k)[0] for k in range(len(levels))]
    return {"m": m, "w": w, "li": li, "nl": len(levels), "cases": cases, "uniq": uniq,
            "gc": groups_case, "gl": groups_level}


def _init(rows_path: str) -> None:
    G.update(_load(rows_path))


def _permute(w: np.ndarray, groups, rng) -> np.ndarray:
    p = w.copy()
    for g in groups:
        if g.size > 1:
            p[g] = w[g][rng.permutation(g.size)]
    return p


def heldout_mean(m, w, li, nl, cases, uniq, split_reps=20) -> float:
    """E1's held-out protocol exactly: rng 90000+rep picks half the cases, fit on one half,
    score on the other, both directions."""
    held = []
    for rep in range(split_reps):
        r2 = np.random.default_rng(90000 + rep)
        pick = set(r2.permutation(len(uniq))[: len(uniq) // 2].tolist())
        fit = np.array([uniq.index(c) in pick for c in cases])
        for am, bm in ((fit, ~fit), (~fit, fit)):
            _fa, mp_ = E1._ascend(m[am], w[am], li[am], nl, m.shape[1])
            if mp_ is None:
                continue
            hb = E1._auc_fast(m[bm][np.arange(int(bm.sum())), mp_[li[bm]]], w[bm])
            if hb == hb:
                held.append(float(hb))
    return float(np.mean(held)) if held else float("nan")


def _job(args):
    kind, seed = args
    rng = np.random.default_rng(seed)
    m, w, li, nl = G["m"], G["w"], G["li"], G["nl"]
    if kind == "within_case":
        a, _ = E1._ascend(m, _permute(w, G["gc"], rng), li, nl, m.shape[1])
        return kind, float(a)
    if kind == "within_level":
        a, _ = E1._ascend(m, _permute(w, G["gl"], rng), li, nl, m.shape[1])
        return kind, float(a)
    if kind == "heldout":
        return kind, heldout_mean(m, _permute(w, G["gc"], rng), li, nl, G["cases"], G["uniq"])
    if kind == "heldout_level":
        return kind, heldout_mean(m, _permute(w, G["gl"], rng), li, nl, G["cases"], G["uniq"])
    raise ValueError(kind)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows", default=str(RESULTS / "rev1_rows.json"))
    ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--heldout-reps", type=int, default=200)
    ap.add_argument("--out", default=str(RESULTS / "rev1_nulls.json"))
    a = ap.parse_args(argv)

    D = _load(a.rows)
    t0 = time.time()
    obs_in, _ = E1._ascend(D["m"], D["w"], D["li"], D["nl"], D["m"].shape[1])
    obs_held = heldout_mean(D["m"], D["w"], D["li"], D["nl"], D["cases"], D["uniq"])
    print("observed in-sample %.4f, held-out mean %.4f (%.0f s)" % (obs_in, obs_held, time.time() - t0))

    jobs = [("within_case", 1_000_000 + i) for i in range(a.reps)]
    jobs += [("within_level", 2_000_000 + i) for i in range(a.reps)]
    jobs += [("heldout", 3_000_000 + i) for i in range(a.heldout_reps)]
    jobs += [("heldout_level", 4_000_000 + i) for i in range(a.heldout_reps)]
    draws = {"within_case": [], "within_level": [], "heldout": [], "heldout_level": []}
    n = max(1, (os.cpu_count() or 4) - 2)
    with mp.Pool(n, initializer=_init, initargs=(a.rows,)) as pool:
        for i, (k, v) in enumerate(pool.imap_unordered(_job, jobs, chunksize=1)):
            draws[k].append(v)
            if (i + 1) % 100 == 0:
                print("  %d/%d draws (%.0f min)" % (i + 1, len(jobs), (time.time() - t0) / 60), flush=True)

    def summ(v, obs):
        v = np.array([x for x in v if x == x])
        return {"reps": int(v.size), "mean": float(v.mean()), "sd": float(v.std(ddof=1)),
                "p95": float(np.quantile(v, 0.95)), "max": float(v.max()), "observed": float(obs),
                "monte_carlo_p": float((1 + (v >= obs).sum()) / (1 + v.size)),
                "draws": [round(float(x), 6) for x in sorted(v)]}
    out = {"observed_in_sample": float(obs_in), "observed_heldout_mean": float(obs_held),
           "within_case": summ(draws["within_case"], obs_in),
           "within_level": summ(draws["within_level"], obs_in),
           "heldout_within_case": summ(draws["heldout"], obs_held),
           "heldout_within_level": summ(draws["heldout_level"], obs_held),
           "note": "Monte Carlo p = (1 + draws >= observed) / (1 + draws). Not exact."}
    Path(a.out).write_text(json.dumps(out, indent=1))
    for k in ("within_case", "within_level", "heldout_within_case", "heldout_within_level"):
        s = out[k]
        print("%-20s reps %4d  mean %.4f  p95 %.4f  max %.4f  observed %.4f  MC p %.4f"
              % (k, s["reps"], s["mean"], s["p95"], s["max"], s["observed"], s["monte_carlo_p"]))
    print("wrote", a.out, "in %.0f min" % ((time.time() - t0) / 60))
    return 0


if __name__ == "__main__":
    sys.exit(main())
