"""Major revision, step 3: the analyses the reviewers asked for, from the step-1 rows.

  A. Unmatched vertebrae (reviewer 3 point 2; reviewer 4). The 396 predictions with no
     ground-truth centroid within 20 mm were excluded from every AUC. Three readings:
       as_published   matched only (1845), the published population
       worst_case     every unmatched prediction counted as WRONG (2241)
       best_case      every unmatched prediction counted as CORRECT (2241)
       absent_level   unmatched predictions whose assigned level does not exist anywhere in
                      the ground-truth volume counted as wrong; the other unmatched excluded
  B. Reference methods (reviewer 4): three label-free scores a site could compute without
     the model's internals: inverse channel entropy, mask-volume regularity against
     neighbouring vertebrae, inter-centroid spacing regularity.
  C. The FLAG, not the confidence (reviewer 4): the deployed geometric flag (in-sample
     pooled z > 1.5, exactly as shipped) and the leave-one-out variant, on the public CT,
     with sensitivity, specificity, PPV, NPV and firing rate per vertebra and per study,
     each with a case-clustered interval; and the AUC of the confidence actually displayed
     (shipped readout times the flag's penalty multiplier).
  D. Selection of the best of nine arms (reviewer 4, "winner's curse"): the best arm chosen
     on one half of the cases and scored on the other, over E1's 40 case-halving folds.

Every interval is a 2000-repetition case-level bootstrap (percentile), the same protocol as the
published Table 5. Output: results/rev1_stats.json.

Usage (spinelab env):
    python scripts/rev1_stats.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))
import e1_ablation as E1  # noqa: E402
from spinelab.outliers import spline as SP  # noqa: E402
from spinelab.paths import RESULTS  # noqa: E402

REPS = 2000
SEED = 20261014


def boot_idx(cases: np.ndarray, reps: int = REPS, seed: int = SEED):
    """Case-level bootstrap index sets, generated once and shared by every statistic so all
    intervals in this file are computed on the same resamples."""
    uniq = sorted(set(cases.tolist()))
    by = {c: np.where(cases == c)[0] for c in uniq}
    rng = np.random.default_rng(seed)
    for _ in range(reps):
        pick = rng.integers(0, len(uniq), len(uniq))
        yield np.concatenate([by[uniq[i]] for i in pick])


def auc_with_ci(score: np.ndarray, wrong: np.ndarray, cases: np.ndarray) -> dict:
    ok = ~np.isnan(score)
    s, w, c = score[ok], wrong[ok], cases[ok]
    a = E1._auc_fast(s, w)
    d = []
    for sel in boot_idx(c):
        v = E1._auc_fast(s[sel], w[sel])
        if v == v:
            d.append(v)
    return {"auc": float(a), "lo": float(np.percentile(d, 2.5)), "hi": float(np.percentile(d, 97.5)),
            "n": int(ok.sum()), "n_wrong": int(w.sum())}


def rate_with_ci(num_mask: np.ndarray, den_mask: np.ndarray, cases: np.ndarray) -> dict:
    """A proportion num/den over vertebrae with a case-clustered percentile interval."""
    den = den_mask.sum()
    p = float(num_mask[den_mask].mean()) if den else float("nan")
    d = []
    for sel in boot_idx(cases):
        dm = den_mask[sel]
        if dm.sum():
            d.append(float(num_mask[sel][dm].mean()))
    return {"value": p, "lo": float(np.percentile(d, 2.5)), "hi": float(np.percentile(d, 97.5)),
            "num": int((num_mask & den_mask).sum()), "den": int(den)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows", default=str(RESULTS / "rev1_rows.json"))
    ap.add_argument("--out", default=str(RESULTS / "rev1_stats.json"))
    a = ap.parse_args(argv)
    D = json.load(open(a.rows))
    R, ARMS = D["rows"], D["arms"]
    cases = np.array([r["case"] for r in R])
    matched = np.array([r["matched"] for r in R])
    wrong_m = np.array([bool(r["wrong"]) if r["matched"] else False for r in R])
    absent = np.array([not r["name_in_gt"] for r in R])
    out: dict = {"n_rows": len(R), "n_matched": int(matched.sum()), "n_unmatched": int((~matched).sum()),
                 "n_cases": len(set(cases.tolist())), "bootstrap": {"reps": REPS, "unit": "case", "seed": SEED}}

    # ---------------- A. unmatched vertebrae ----------------
    pops = {
        "as_published": (matched, wrong_m),
        "worst_case": (np.ones(len(R), bool), np.where(matched, wrong_m, True)),
        "best_case": (np.ones(len(R), bool), np.where(matched, wrong_m, False)),
        "absent_level": (matched | (~matched & absent), np.where(matched, wrong_m, True)),
    }
    A = {}
    for pname, (inc, w) in pops.items():
        A[pname] = {"n": int(inc.sum()), "n_wrong": int(w[inc].sum())}
        for k in ARMS:
            s = np.array([r["arms"][k] for r in R], dtype=float)
            A[pname][k] = auc_with_ci(s[inc], w[inc], cases[inc])
        print("A %-13s n=%4d wrong=%4d  " % (pname, A[pname]["n"], A[pname]["n_wrong"]) +
              "  ".join("%s %.3f" % (k[:10], A[pname][k]["auc"]) for k in ARMS))
    # the matched-only AUC under the label-free phase, against the published E1 phase
    A["phase_note"] = {k: {"label_free_phase": A["as_published"][k]["auc"],
                           "e1_phase": float(E1._auc_fast(np.array([r["arms_e1_phase"][k] for r in R], float)[matched],
                                                          wrong_m[matched]))} for k in ARMS}
    # what the excluded predictions look like under the shipped readout
    ship = np.array([r["arms"]["parity_region_deployed"] for r in R], dtype=float)
    um_abs = ~matched & absent
    A["unmatched_profile"] = {
        "unmatched": int((~matched).sum()),
        "unmatched_level_absent_from_volume": int(um_abs.sum()),
        "unmatched_level_present_but_beyond_20mm": int((~matched & ~absent).sum()),
        "shipped_confidence_median_unmatched_absent": float(np.nanmedian(ship[um_abs])),
        "shipped_confidence_median_matched_correct": float(np.nanmedian(ship[matched & ~wrong_m])),
        "shipped_confidence_median_matched_wrong": float(np.nanmedian(ship[matched & wrong_m])),
        "unmatched_absent_with_shipped_confidence_ge_0.8": int((um_abs & (ship >= 0.8)).sum()),
        "unmatched_absent_flagged_by_deployed_check": int((um_abs & np.array([r["deployed_flag"] for r in R])).sum()),
    }
    out["A_unmatched"] = A

    # ---------------- B. reference methods ----------------
    B = {}
    for ref in ("ref_entropy_inv", "ref_volume_regularity", "ref_spacing_regularity"):
        s = np.array([r[ref] for r in R], dtype=float)
        B[ref] = {p: auc_with_ci(s[inc], w[inc], cases[inc])
                  for p, (inc, w) in pops.items() if p in ("as_published", "worst_case")}
        print("B %-24s published %.3f [%.3f, %.3f]   worst-case %.3f [%.3f, %.3f]" % (
            ref, B[ref]["as_published"]["auc"], B[ref]["as_published"]["lo"], B[ref]["as_published"]["hi"],
            B[ref]["worst_case"]["auc"], B[ref]["worst_case"]["lo"], B[ref]["worst_case"]["hi"]))
    out["B_reference_methods"] = B

    # ---------------- C. the flag itself ----------------
    C = {}
    for fname in ("deployed_flag", "loo_flag"):
        f = np.array([r[fname] for r in R], dtype=bool)
        checked = np.array([r["deployed_checked"] for r in R], dtype=bool) if fname == "deployed_flag" \
            else np.isfinite(np.array([r["loo_z"] for r in R], float))
        Cf = {}
        for pname, (inc, w) in (("as_published", pops["as_published"]), ("worst_case", pops["worst_case"])):
            den = inc
            Cf[pname] = {
                "firing_rate": rate_with_ci(f, den, cases),
                "sensitivity": rate_with_ci(f, den & w, cases),
                "specificity": rate_with_ci(~f, den & ~w, cases),
                "ppv": rate_with_ci(w, den & f, cases),
                "npv": rate_with_ci(~w, den & ~f, cases),
                "not_checked": int((den & ~checked).sum()),
            }
        # per study: fraction of cases with at least one flag
        uc = sorted(set(cases.tolist()))
        Cf["studies_flagged"] = {"num": int(sum(f[cases == c].any() for c in uc)), "den": len(uc)}
        C[fname] = Cf
        p = Cf["as_published"]
        print("C %-13s fires %.3f  sens %.3f [%.3f,%.3f]  spec %.3f  PPV %.3f [%.3f,%.3f]  NPV %.3f  studies %d/%d" % (
            fname, p["firing_rate"]["value"], p["sensitivity"]["value"], p["sensitivity"]["lo"], p["sensitivity"]["hi"],
            p["specificity"]["value"], p["ppv"]["value"], p["ppv"]["lo"], p["ppv"]["hi"], p["npv"]["value"],
            Cf["studies_flagged"]["num"], Cf["studies_flagged"]["den"]))
    # the confidence actually displayed: shipped readout times the penalty multiplier
    z = np.array([r["deployed_z"] for r in R], dtype=float)
    mult = np.where(np.isfinite(z) & (z > SP.DEPLOYED_Z_THRESHOLD),
                    np.maximum(SP.DEPLOYED_PENALTY_FLOOR, 1 - (z - SP.DEPLOYED_Z_THRESHOLD) * SP.DEPLOYED_PENALTY_SLOPE), 1.0)
    shown = ship * mult
    C["displayed_confidence_auc"] = {p: auc_with_ci(shown[inc], w[inc], cases[inc])
                                     for p, (inc, w) in pops.items() if p in ("as_published", "worst_case")}
    C["deployed_z_as_score_auc"] = {p: auc_with_ci(-z[inc], w[inc], cases[inc])
                                    for p, (inc, w) in pops.items() if p in ("as_published", "worst_case")}
    print("C displayed confidence AUC %.3f [%.3f, %.3f]; deployed z as a score %.3f" % (
        C["displayed_confidence_auc"]["as_published"]["auc"], C["displayed_confidence_auc"]["as_published"]["lo"],
        C["displayed_confidence_auc"]["as_published"]["hi"], C["deployed_z_as_score_auc"]["as_published"]["auc"]))
    out["C_flag"] = C

    # ---------------- D. selecting the best of nine ----------------
    mc = cases[matched]
    uniq = sorted(set(mc.tolist()))
    S = {k: np.array([r["arms"][k] for r in R], float)[matched] for k in ARMS}
    wm = wrong_m[matched]
    held, chosen = [], []
    for rep in range(20):
        r2 = np.random.default_rng(90000 + rep)
        pick = set(r2.permutation(len(uniq))[: len(uniq) // 2].tolist())
        fit = np.array([uniq.index(c) in pick for c in mc])
        for am, bm in ((fit, ~fit), (~fit, fit)):
            best = max(ARMS, key=lambda k: E1._auc_fast(S[k][am], wm[am]))
            chosen.append(best)
            held.append(E1._auc_fast(S[best][bm], wm[bm]))
    in_best = max(ARMS, key=lambda k: E1._auc_fast(S[k], wm))
    out["D_selection"] = {"in_sample_best_arm": in_best, "in_sample_best_auc": float(E1._auc_fast(S[in_best], wm)),
                          "selected_heldout_mean": float(np.mean(held)), "selected_heldout_sd": float(np.std(held, ddof=1)),
                          "folds": len(held), "times_chosen": {k: chosen.count(k) for k in ARMS if chosen.count(k)}}
    print("D best-of-nine: in sample %s %.3f; chosen on half, scored on the other: mean %.3f sd %.3f; chosen %s" % (
        in_best, out["D_selection"]["in_sample_best_auc"], out["D_selection"]["selected_heldout_mean"],
        out["D_selection"]["selected_heldout_sd"], out["D_selection"]["times_chosen"]))

    Path(a.out).write_text(json.dumps(out, indent=1))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
