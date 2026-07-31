"""Scratch probe: (1) the true deployed per-region parity arm, (2) case-level
cluster bootstrap intervals. Not a deliverable; written to quantify N9 and N17."""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from spinelab.confidence import channels as CH  # noqa: E402
from spinelab.paths import DATASETS  # noqa: E402
import e1_ablation as E  # noqa: E402

RUN = Path(r"<path>\runs\verse_batch_01")
DATA = DATASETS / "verse_4skx2"
TOL = 20.0


def deployed_rule(name: str) -> int:
    """utils/confidence_calculator.py::get_vertebra_channel, verbatim in effect."""
    s = CH.normalise(name)
    if s.startswith("S"):
        return 8
    return 6 if int(s[1:]) % 2 == 1 else 7


def load():
    rows = []
    for cf in sorted(glob.glob(str(RUN / "cases" / "*.json"))):
        try:
            j = json.load(open(cf))
        except Exception:
            continue
        if not str(j.get("status", "")).startswith("ok"):
            continue
        verts = j.get("vertebrae") or []
        if not verts:
            continue
        stem = j.get("case") or Path(cf).stem
        masks = glob.glob(str(DATA / (stem + "*seg-vert_msk.nii.gz")))
        if not masks:
            continue
        gt = E.gt_centroids_world(Path(masks[0]), RUN / "_gt_centroid_cache")
        if not gt:
            continue
        ordered = sorted([v for v in verts if v.get("centroid_world_ras_mm")],
                         key=lambda v: -float(v["centroid_world_ras_mm"][2]))
        for seq_idx, v in enumerate(ordered):
            name = CH.normalise(v.get("name", ""))
            if not name:
                continue
            c = np.asarray(v["centroid_world_ras_mm"], dtype=np.float64)
            best, bestd = None, 1e18
            for gname, gc in gt.items():
                d = float(np.linalg.norm(gc - c))
                if d < bestd:
                    best, bestd = gname, d
            if best is None or bestd > TOL:
                continue
            rows.append({"case": stem, "name": name, "wrong": best != name,
                         "seq": seq_idx, "v": v})
    return rows


def auc(s, w):
    s = np.asarray(s, float); w = np.asarray(w, bool)
    ok = ~np.isnan(s)
    s, w = s[ok], w[ok]
    pos, neg = s[w], s[~w]
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    from scipy.stats import rankdata
    r = rankdata(np.concatenate([pos, neg]))
    return float((r[:pos.size].sum() - pos.size * (pos.size + 1) / 2.0)
                 / (pos.size * neg.size))


def main():
    rows = load()
    cases = sorted({r["case"] for r in rows})
    print("cases %d  vertebrae %d  wrong %d"
          % (len(cases), len(rows), sum(r["wrong"] for r in rows)))
    per = [sum(1 for r in rows if r["case"] == c and r["wrong"]) for c in cases]
    tot = [sum(1 for r in rows if r["case"] == c) for c in cases]
    print("vertebrae per case: mean %.1f  min %d  max %d"
          % (np.mean(tot), min(tot), max(tot)))
    print("cases with 0 wrong: %d of %d ; cases with ALL wrong: %d"
          % (sum(1 for p in per if p == 0), len(cases),
             sum(1 for p, t in zip(per, tot) if p == t)))

    # phase, per case, exactly as the shipped script does it
    for c in cases:
        crows = [r for r in rows if r["case"] == c]
        totals = {}
        for off in (0, 1):
            t = 0.0
            for r in crows:
                ch = r["v"].get("channels") or {}
                try:
                    ci = CH.channel_parity(r["name"], ordinal=r["seq"] + off)
                except Exception:
                    continue
                t += float(ch.get(str(ci), {}).get("mean", 0.0))
            totals[off] = t
        b = max(totals, key=totals.get)
        for r in crows:
            r["phase"] = b

    ARMS = ["region_retired", "parity_name", "parity_sequence_phased",
            "mapping_free_top1", "argmax_mean"]
    S = {}
    for a in ARMS:
        S[a] = np.array([
            (lambda x: np.nan if x is None else x)(
                E._arm_score_one(a, r, (r["v"].get("channels") or {}),
                                 int(r["v"].get("n_voxels") or 1)))
            for r in rows], dtype=float)
    # the real deployed rule
    dep = []
    for r in rows:
        ch = r["v"].get("channels") or {}
        try:
            ci = deployed_rule(r["name"])
        except Exception:
            dep.append(np.nan); continue
        dep.append(E.conf_from_channel(ch.get(str(ci), {}),
                                       int(r["v"].get("n_voxels") or 1)))
    S["parity_region_restart_DEPLOYED"] = np.array(dep, dtype=float)

    w = np.array([r["wrong"] for r in rows], bool)
    caseid = np.array([cases.index(r["case"]) for r in rows])

    print("\npoint AUC")
    for a, s in S.items():
        print("  %-34s %.4f" % (a, auc(s, w)))

    # how often does the deployed rule pick a different channel than parity_name?
    diff = 0
    for r in rows:
        try:
            if deployed_rule(r["name"]) != CH.channel_parity(r["name"]):
                diff += 1
        except Exception:
            pass
    print("\nvertebrae where deployed rule != parity_name arm: %d of %d (%.1f%%)"
          % (diff, len(rows), 100.0 * diff / len(rows)))

    # cluster bootstrap by case
    rng = np.random.default_rng(0)
    B = 2000
    idx_by_case = [np.where(caseid == i)[0] for i in range(len(cases))]
    keys = list(S.keys())
    boot = {k: [] for k in keys}
    boot["delta_best_minus_published"] = []
    for _ in range(B):
        pick = rng.integers(0, len(cases), len(cases))
        sel = np.concatenate([idx_by_case[i] for i in pick])
        ww = w[sel]
        if ww.sum() == 0 or (~ww).sum() == 0:
            continue
        vals = {}
        for k in keys:
            vals[k] = auc(S[k][sel], ww)
            boot[k].append(vals[k])
        boot["delta_best_minus_published"].append(
            vals["parity_sequence_phased"] - vals["region_retired"])
    print("\ncase-level cluster bootstrap, %d reps" % B)
    for k in keys + ["delta_best_minus_published"]:
        v = np.array(boot[k], float)
        v = v[~np.isnan(v)]
        print("  %-34s  point %s  95%% [%.3f, %.3f]  width %.3f"
              % (k,
                 ("%.3f" % auc(S[k], w)) if k in S else "  n/a",
                 np.percentile(v, 2.5), np.percentile(v, 97.5),
                 np.percentile(v, 97.5) - np.percentile(v, 2.5)))
    d = np.array(boot["delta_best_minus_published"], float)
    print("  P(delta <= 0) = %.3f" % float((d <= 0).mean()))


if __name__ == "__main__":
    main()
