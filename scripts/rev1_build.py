"""Major revision, step 1: one row per PREDICTED vertebra, all 2241 of them.

The E1 ablation (scripts/e1_ablation.py) built these rows in memory and kept only the 1845
that matched a ground-truth centroid within the 20 mm VerSe tolerance; the per-vertebra table
was never written. Both reviewers ask what happens to the 396 that did not match (reviewer 3,
point 2; reviewer 4, "17.7 percent cannot be scored"), and reviewer 4 asks for the deployed
FLAG, not only the confidence, to be scored on the public data. Everything needed is already on
disk: per-vertebra channel statistics for every prediction in runs/verse_batch_01/cases, and
ground-truth centroids in runs/verse_batch_01/_gt_centroid_cache. This script writes the table
once so every later analysis reads the same rows.

Per row:
  case, name, seq (detection order, superior to inferior), phase (label-free, estimated
  per case over ALL its predictions), matched, gt (nearest ground-truth level), dist_mm,
  wrong (None when unmatched), name_in_gt (does the assigned level exist anywhere in the
  ground-truth volume), the nine arm scores, three label-free reference scores, and the
  deployed geometric flag computed exactly as shipped.

Positive control: the nine arm AUCs on the matched rows, with the phase estimated as E1
estimated it (matched rows only), must reproduce results/e1_ablation.json exactly. The script
refuses to write if they do not.

Usage (spinelab env):
    python scripts/rev1_build.py --run-dir <runs/verse_batch_01> [--out results/rev1_rows.json]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

import nibabel as nib
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))
import e1_ablation as E1  # noqa: E402
from spinelab.confidence import channels as CH  # noqa: E402
from spinelab.outliers import spline as SP  # noqa: E402
from spinelab.paths import DATASETS, RESULTS  # noqa: E402

ARMS = ["region_retired", "parity_name", "parity_region_deployed", "parity_sequence",
        "parity_sequence_inverted", "parity_sequence_phased", "mapping_free_top1",
        "mapping_free_margin", "argmax_mean"]


def estimate_phase(rows: list[dict]) -> int:
    """E1's label-free phase estimate: whichever offset puts more probability on the
    selected parity channel. Uses channel probabilities only, never the labels."""
    totals = {}
    for off in (0, 1):
        tot = 0.0
        for r in rows:
            chans = r["v"].get("channels") or {}
            try:
                ci = CH.channel_parity(r["name"], ordinal=r["seq"] + off)
            except Exception:
                continue
            tot += float(chans.get(str(ci), {}).get("mean", 0.0))
        totals[off] = tot
    return max(totals, key=totals.get)


def neighbour_ratio_score(vals: list[float]) -> list[float]:
    """Regularity of a quantity along the detected column: minus the absolute log ratio of
    each value to the median of its up-to-two neighbours on each side. 0 is perfectly
    regular; more negative is less regular. Higher means 'more trustworthy', the same
    direction as a confidence."""
    out = []
    for i, v in enumerate(vals):
        nb = [vals[j] for j in range(max(0, i - 2), min(len(vals), i + 3)) if j != i]
        nb = [x for x in nb if x > 0]
        if v <= 0 or not nb:
            out.append(float("nan"))
            continue
        out.append(-abs(float(np.log(v / float(np.median(nb))))))
    return out


def spacing_score(cents: list[np.ndarray]) -> list[float]:
    """Inter-centroid spacing regularity: for each vertebra, the worse of its two gaps to
    the adjacent detections, as minus the absolute log ratio to the case's median gap."""
    if len(cents) < 3:
        return [float("nan")] * len(cents)
    gaps = [float(np.linalg.norm(cents[i + 1] - cents[i])) for i in range(len(cents) - 1)]
    med = float(np.median(gaps))
    out = []
    for i in range(len(cents)):
        g = []
        if i > 0:
            g.append(gaps[i - 1])
        if i < len(gaps):
            g.append(gaps[i])
        out.append(-max(abs(float(np.log(max(x, 1e-6) / med))) for x in g))
    return out


def sagittal_px(case_json: dict, nifti_path: Path | None, world: np.ndarray) -> tuple[float, float, float]:
    """Project a world RAS centroid onto the sagittal plane, in pixels of the case's own
    in-plane spacing, so the deployed 2-D check sees what it saw in deployment: (A-P, S-I)
    on one sagittal slice. Returns (x_px, y_px, spacing_mm)."""
    sp = 1.0
    if nifti_path is not None:
        try:
            z = nib.load(str(nifti_path)).header.get_zooms()[:3]
            sp = float(np.mean(sorted(z)[:2]))
        except Exception:
            sp = 1.0
    # image x to the right across columns = anterior-posterior; y down rows = superior to
    # inferior. Signs do not matter to a distance-to-curve residual.
    return float(-world[1] / sp), float(-world[2] / sp), sp


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--out", default=str(RESULTS / "rev1_rows.json"))
    a = ap.parse_args(argv)
    run_dir = Path(a.run_dir)
    data_dir = Path(a.data_dir) if a.data_dir else DATASETS / "verse_4skx2"

    rows, cases = [], {}
    for cf in sorted(glob.glob(str(run_dir / "cases" / "*.json"))):
        j = json.load(open(cf))
        if not str(j.get("status", "")).startswith("ok") or not (j.get("vertebrae") or []):
            continue
        stem = j.get("case") or os.path.basename(cf).replace(".json", "")
        masks = glob.glob(str(data_dir / (stem + "*seg-vert_msk.nii.gz")))
        if not masks:
            continue
        gt = E1.gt_centroids_world(Path(masks[0]), run_dir / "_gt_centroid_cache")
        if not gt:
            continue
        imgs = [p for p in glob.glob(str(data_dir / (stem + "*.nii.gz"))) if "seg" not in os.path.basename(p)]
        ordered = sorted([v for v in j["vertebrae"] if v.get("centroid_world_ras_mm")],
                         key=lambda v: -float(v["centroid_world_ras_mm"][2]))
        crow = []
        for seq, v in enumerate(ordered):
            name = CH.normalise(v.get("name", ""))
            if not name:
                continue
            c = np.asarray(v["centroid_world_ras_mm"], dtype=np.float64)
            best, bestd = None, 1e18
            for g, gc in gt.items():
                d = float(np.linalg.norm(gc - c))
                if d < bestd:
                    best, bestd = g, d
            matched = best is not None and bestd <= E1.MATCH_TOLERANCE_MM
            crow.append({"case": stem, "name": name, "seq": seq, "matched": matched,
                         "gt": best if matched else None, "nearest_gt": best,
                         "dist_mm": bestd, "wrong": (best != name) if matched else None,
                         "name_in_gt": name in gt, "v": v, "world": c})
        if not crow:
            continue
        cases[stem] = {"img": imgs[0] if imgs else None}
        # label-free phase over all predictions, and E1's matched-only phase for the control
        ph_all = estimate_phase(crow)
        m = [r for r in crow if r["matched"]]
        ph_e1 = estimate_phase(m) if m else ph_all
        # reference scores, label-free, in detection order
        nv = [float(r["v"].get("n_voxels") or 0) for r in crow]
        vol = neighbour_ratio_score(nv)
        spc = spacing_score([r["world"] for r in crow])
        # deployed geometric flag on the sagittal projection
        cen, spacing = [], 1.0
        for r in crow:
            x, y, spacing = sagittal_px(j, Path(imgs[0]) if imgs else None, r["world"])
            cen.append((r["name"], x, y))
        tr = SP.deployed_trace(cen)
        inst = {q.name: q for q in SP.fit_instrumented(cen, pixel_spacing_mm=spacing, cfg=SP.LOO_CONFIG)}
        for i, r in enumerate(crow):
            r["phase"] = ph_all
            r["phase_e1"] = ph_e1
            r["ref_volume_regularity"] = vol[i]
            r["ref_spacing_regularity"] = spc[i]
            mf = r["v"].get("mapping_free") or {}
            r["ref_entropy_inv"] = float(mf["entropy_inv"]) if mf.get("entropy_inv") is not None else float("nan")
            z = tr.z.get(r["name"])
            r["deployed_z"] = float(z) if z is not None else float("nan")
            r["deployed_checked"] = z is not None
            r["deployed_flag"] = bool(z is not None and z > SP.DEPLOYED_Z_THRESHOLD)
            q = inst.get(r["name"])
            r["loo_z"] = float(q.z_loo) if q is not None else float("nan")
            r["loo_resid_mm"] = float(q.loo_residual_mm) if q is not None else float("nan")
            r["insample_resid_mm"] = float(q.residual_mm) if q is not None else float("nan")
            r["loo_flag"] = bool(q is not None and q.flag(SP.LOO_CONFIG))
            r["pixel_spacing_mm"] = spacing
        rows.extend(crow)

    # ---- arm scores: under E1's phase for the control, under the label-free phase for use
    def score(r, kind, phase_key):
        rr = dict(r, phase=r[phase_key])
        s = E1._arm_score_one(kind, rr, (r["v"].get("channels") or {}), int(r["v"].get("n_voxels") or 1))
        return float("nan") if s is None else float(s)

    matched = [r for r in rows if r["matched"]]
    prev = json.loads((RESULTS / "e1_ablation.json").read_text())["arms"]
    bad = []
    for k in ARMS:
        s = np.array([score(r, k, "phase_e1") for r in matched])
        w = np.array([bool(r["wrong"]) for r in matched])
        auc = E1._auc_fast(s, w)
        if abs(auc - prev[k]["auc"]) > 1e-9:
            bad.append((k, auc, prev[k]["auc"]))
    print("rows %d, matched %d, unmatched %d, cases %d" % (len(rows), len(matched), len(rows) - len(matched), len(cases)))
    if bad:
        print("POSITIVE CONTROL FAILED, refusing to write:", bad)
        return 1
    print("positive control: all nine arm AUCs reproduce results/e1_ablation.json exactly")

    out = []
    for r in rows:
        o = {k: r[k] for k in ("case", "name", "seq", "matched", "gt", "nearest_gt", "dist_mm", "wrong",
                               "name_in_gt", "phase", "phase_e1", "ref_volume_regularity",
                               "ref_spacing_regularity", "ref_entropy_inv", "deployed_z", "deployed_checked",
                               "deployed_flag", "loo_z", "loo_resid_mm", "insample_resid_mm", "loo_flag",
                               "pixel_spacing_mm")}
        o["n_voxels"] = int(r["v"].get("n_voxels") or 0)
        # the deployed confidence formula on each of the 11 output channels, which is what
        # the label-informed per-level ceilings search over (E1._score_matrix)
        cd, nv = (r["v"].get("channels") or {}), int(r["v"].get("n_voxels") or 1)
        o["chan_conf"] = [E1.conf_from_channel(cd[str(c)], nv) if str(c) in cd else float("nan")
                          for c in range(11)]
        o["arms"] = {k: score(r, k, "phase") for k in ARMS}
        o["arms_e1_phase"] = {k: score(r, k, "phase_e1") for k in ARMS}
        out.append(o)
    Path(a.out).write_text(json.dumps({"n_rows": len(out), "arms": ARMS, "rows": out}, indent=1, default=float))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
