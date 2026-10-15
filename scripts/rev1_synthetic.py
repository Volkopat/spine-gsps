"""Major revision, step 4: ROC and precision-recall for both residual estimators, on the
synthetic chains, and the four-level-region residual in millimetres.

Reviewer 4: "Please provide ROC/PR curves for both estimators"; "what was the control designed
to detect?"; "pixel and mm units are mixed up". The published synthetic results (Table 4) are
operating points at z > 1.5. Here every vertebra in every injected study is scored by the
continuous statistic of each estimator, so the whole curve is visible:

  in_sample   the deployed pooled z of the in-sample residual (what shipped)
  loo         the same pooling of the leave-one-out residual (what was specified)
  in_sample_mm, loo_mm   the raw residuals in millimetres, unstandardised, to separate the
                         estimator from the study-level z pooling applied to it

Positives are the vertebrae an injection actually moved off their own position
(`SyntheticStudy.perturbed`); negatives are every vertebra of the SAME studies before the
injection, which are correct by construction. This is the paired design of the published
Table 4, so a curve at the diagonal means the statistic does not distinguish an erroneous
vertebra from a correct one in the same anatomy.
Population: the published 432 studies with 0.5 mm centroid noise, the realistic case, and the
four published injections, of which the lateral 10 mm displacement is the positive control: it
moves one centroid off the curve without relabelling anything, which is the one error a
distance-to-curve residual can see in principle, so an estimator that cannot see it cannot see
anything.

Also: the in-sample residual of vertebrae in regions of exactly four levels, against all other
regional vertebrae, in millimetres (the published text quoted pixels).

Usage (spinelab env):
    python scripts/rev1_synthetic.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
from spinelab.outliers import spline as SP  # noqa: E402
from spinelab.paths import RESULTS  # noqa: E402


def roc_pr(scores: np.ndarray, pos: np.ndarray) -> dict:
    ok = np.isfinite(scores)
    s, y = scores[ok], pos[ok]
    order = np.argsort(-s, kind="mergesort")
    s, y = s[order], y[order]
    P, N = int(y.sum()), int((~y).sum())
    # thresholds at every distinct value
    distinct = np.r_[np.where(np.diff(s))[0], s.size - 1]
    tp = np.cumsum(y)[distinct]
    fp = np.cumsum(~y)[distinct]
    tpr = np.r_[0.0, tp / P]
    fpr = np.r_[0.0, fp / N]
    prec = np.r_[1.0, tp / np.maximum(tp + fp, 1)]
    auc = float(np.trapz(tpr, fpr))
    ap = float(np.sum((tpr[1:] - tpr[:-1]) * prec[1:]))
    # the operating point the deployment used, z > 1.5
    op = s > SP.DEPLOYED_Z_THRESHOLD
    return {"auc": auc, "average_precision": ap, "prevalence": P / (P + N), "n_pos": P, "n_neg": N,
            "at_z_1p5": {"tpr": float(op[y].mean()), "fpr": float(op[~y].mean()),
                         "ppv": float(y[op].mean()) if op.any() else float("nan")},
            "curve": {"fpr": [round(float(v), 5) for v in fpr[:: max(1, fpr.size // 400)]],
                      "tpr": [round(float(v), 5) for v in tpr[:: max(1, tpr.size // 400)]],
                      "recall": [round(float(v), 5) for v in tpr[:: max(1, tpr.size // 400)]],
                      "precision": [round(float(v), 5) for v in prec[:: max(1, prec.size // 400)]]}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(RESULTS / "rev1_synthetic.json"))
    a = ap.parse_args(argv)
    pop = SP.build_population(0.5, 12)
    out = {"n_studies": len(pop), "noise_mm": 0.5, "injections": {}}
    for label, make in SP.default_injections().items():
        zs, zl, rs, rl, pos = [], [], [], [], []
        for st in pop:
            try:
                bad = make(st)
            except ValueError:
                continue
            for r in SP.fit_instrumented(bad.centers, bad.pixel_spacing_mm, SP.DEPLOYED_CONFIG):
                if r.name in bad.perturbed:
                    zs.append(r.z)
                    zl.append(r.z_loo)
                    rs.append(r.residual_mm)
                    rl.append(r.loo_residual_mm)
                    pos.append(True)
            for r in SP.fit_instrumented(st.centers, st.pixel_spacing_mm, SP.DEPLOYED_CONFIG):
                zs.append(r.z)
                zl.append(r.z_loo)
                rs.append(r.residual_mm)
                rl.append(r.loo_residual_mm)
                pos.append(False)
        pos = np.array(pos)
        out["injections"][label] = {"in_sample": roc_pr(np.array(zs, float), pos),
                                    "loo": roc_pr(np.array(zl, float), pos),
                                    "in_sample_mm": roc_pr(np.array(rs, float), pos),
                                    "loo_mm": roc_pr(np.array(rl, float), pos)}
        i, l = out["injections"][label]["in_sample"], out["injections"][label]["loo"]
        print("%-26s prev %.3f | in-sample AUC %.3f AP %.3f (z>1.5 tpr %.3f fpr %.3f) | LOO AUC %.3f AP %.3f (tpr %.3f fpr %.3f)" % (
            label, i["prevalence"], i["auc"], i["average_precision"], i["at_z_1p5"]["tpr"], i["at_z_1p5"]["fpr"],
            l["auc"], l["average_precision"], l["at_z_1p5"]["tpr"], l["at_z_1p5"]["fpr"]))
        print("%-26s            raw mm: in-sample AUC %.3f AP %.3f | LOO AUC %.3f AP %.3f" % (
            "", out["injections"][label]["in_sample_mm"]["auc"], out["injections"][label]["in_sample_mm"]["average_precision"],
            out["injections"][label]["loo_mm"]["auc"], out["injections"][label]["loo_mm"]["average_precision"]))

    # four-level regions, in millimetres, on the clean noisy population
    four, other = [], []
    for st in pop:
        for r in SP.fit_instrumented(st.centers, st.pixel_spacing_mm, SP.DEPLOYED_CONFIG):
            if r.fit_scope != "region" or not np.isfinite(r.residual_mm):
                continue
            (four if r.region_size == 4 else other).append(r.residual_mm)
    out["four_level_regions"] = {"n_four": len(four), "n_other": len(other),
                                 "mean_residual_mm_four": float(np.mean(four)),
                                 "mean_residual_mm_other": float(np.mean(other)),
                                 "spacings_mm": list(SP.SPACINGS_MM)}
    print("four-level regions: in-sample residual mean %.4f mm (n=%d) against %.4f mm elsewhere (n=%d)" % (
        np.mean(four), len(four), np.mean(other), len(other)))
    Path(a.out).write_text(json.dumps(out, indent=1))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
