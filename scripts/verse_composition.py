"""Characterise the VerSe cohort before running anything on it.

Two purposes:

1. Establish what is in the evaluation set, so the identification rate can be
   reported per level and per field of view rather than as one opaque average.
   VerSe field of view varies enormously, from cervical only to whole spine, and a
   bare mean over cases is not interpretable.

2. Predict, from ground truth alone, how many cases the pipeline is structurally
   unable to get right. Two limitations were read out of the recovered level
   assignment code (see results/level_assignment.md):
     - T13 cannot be produced at all, and VerSe labels it as 28.
     - If no landmark disc is in the field of view, the algorithm writes no output
       and does not flag it.
   Knowing the size of both populations in advance stops us attributing a
   structural limitation to segmentation quality after the fact.

VerSe label convention, verbatim from the OSF readme:
  1-7 C1-C7 | 8-19 T1-T12 | 20-25 L1-L6 | 26 sacrum | 27 coccyx | 28 T13
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys
from pathlib import Path

import nibabel as nib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spinelab.paths import DATASETS, RESULTS  # noqa: E402

NAME = {}
for i in range(1, 8):
    NAME[i] = "C%d" % i
for i in range(8, 20):
    NAME[i] = "T%d" % (i - 7)
for i in range(20, 26):
    NAME[i] = "L%d" % (i - 19)
NAME[26] = "sacrum"
NAME[27] = "coccyx"
NAME[28] = "T13"

# The four landmark discs the algorithm anchors on, in its configured priority
# order (inference_logic.py:151, selected_disc_landmarks=[2, 5, 3, 4]).
#
# A disc sits between two vertebrae, so presence of BOTH neighbours in the ground
# truth is a proxy for that disc being inside the field of view. This is a proxy,
# not a measurement: the pipeline predicts discs from the image, so a disc can be
# in the image even when a neighbouring structure is unlabelled.
#
# IMPORTANT: VerSe deliberately does not label the sacrum. Its readme states
# "26,27: sacrum, cocygis - not labeled in this dataset". So requiring both
# neighbours can NEVER detect the L5-S landmark, and a strict count reports 0
# percent availability for it as an artifact of the annotation convention rather
# than a fact about the images. We therefore report two counts:
#   strict  both neighbours labelled
#   lenient the superior neighbour labelled, which for L5-S means L5 present
# The lenient count is the honest upper bound on landmark availability, and the
# truth for L5-S lies between them.
LANDMARK_DISCS = [
    # name, superior neighbour, inferior neighbour, inferior_is_labelled_in_verse
    ("C2-C3", 2, 3, True),
    ("L5-S", 24, 26, False),
    ("C7-T1", 7, 8, True),
    ("T12-L1", 19, 20, True),
]


def region_of(v: int) -> str:
    if 1 <= v <= 7:
        return "C"
    if 8 <= v <= 19 or v == 28:
        return "T"
    if 20 <= v <= 25:
        return "L"
    return "S"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    d = Path(args.dir) if args.dir else DATASETS / "verse_4skx2"
    masks = sorted(glob.glob(str(d / "*seg-vert_msk.nii.gz")))
    if not masks:
        print("no masks found in %s" % d)
        return 1
    print("cohort: %s" % d)
    print("cases : %d\n" % len(masks))

    rows = []
    level_count = collections.Counter()
    for mp in masks:
        stem = os.path.basename(mp).split("_seg-vert")[0]
        img = nib.load(mp)
        m = np.asanyarray(img.dataobj).round().astype(np.int16)
        present = sorted(int(v) for v in np.unique(m) if v > 0)
        for v in present:
            level_count[v] += 1
        zooms = tuple(round(float(z), 3) for z in img.header.get_zooms()[:3])
        ctd = glob.glob(str(d / (stem + "*ctd.json")))
        n_ctd = 0
        if ctd:
            j = json.load(open(ctd[0]))
            n_ctd = len([e for e in j if isinstance(e, dict) and "label" in e])
        rows.append({
            "case": stem,
            "n_levels": len(present),
            "levels": present,
            "regions": "".join(sorted({region_of(v) for v in present},
                                      key="CTLS".index)),
            "has_T13": 28 in present,
            "has_L6": 25 in present,
            "has_sacrum": 26 in present,
            "shape": tuple(int(x) for x in m.shape),
            "zooms": zooms,
            "n_centroids": n_ctd,
            "landmarks_strict": [nm for nm, a, b, lab in LANDMARK_DISCS
                                 if a in present and b in present],
            "landmarks_lenient": [nm for nm, a, b, lab in LANDMARK_DISCS
                                  if a in present and (b in present or not lab)],
        })

    n = len(rows)
    print("=" * 76)
    print("STRUCTURAL LIMITATIONS, predicted from ground truth alone")
    print("=" * 76)
    t13 = [r for r in rows if r["has_T13"]]
    l6 = [r for r in rows if r["has_L6"]]
    nolm_s = [r for r in rows if not r["landmarks_strict"]]
    nolm_l = [r for r in rows if not r["landmarks_lenient"]]
    print("cases containing T13 (label 28), which the algorithm cannot produce:")
    print("  %d/%d (%.1f%%)  %s" % (len(t13), n, 100.0 * len(t13) / n,
                                    [r["case"] for r in t13][:8]))
    print("cases containing L6 (label 25), which it CAN produce:")
    print("  %d/%d (%.1f%%)  %s" % (len(l6), n, 100.0 * len(l6) / n,
                                    [r["case"] for r in l6][:8]))
    print("\ncases with NO landmark disc in the field of view, predicted to yield no")
    print("output at all. Two bounds because VerSe does not label the sacrum:")
    print("  strict  %d/%d (%.1f%%)  %s" % (
        len(nolm_s), n, 100.0 * len(nolm_s) / n, [r["case"] for r in nolm_s][:6]))
    print("  lenient %d/%d (%.1f%%)  %s" % (
        len(nolm_l), n, 100.0 * len(nolm_l) / n, [r["case"] for r in nolm_l][:6]))
    print("  The lenient bound is the one to quote. The strict bound overstates the")
    print("  problem because it can never find L5-S.")
    print("\nlandmark availability by disc:")
    print("  %-8s %-14s %-14s %s" % ("disc", "strict", "lenient", "between"))
    for nm, a, b, lab in LANDMARK_DISCS:
        cs = sum(1 for r in rows if nm in r["landmarks_strict"])
        cl = sum(1 for r in rows if nm in r["landmarks_lenient"])
        note = "" if lab else "   <- sacrum unlabelled in VerSe, strict is meaningless"
        print("  %-8s %3d/%d (%5.1f%%) %3d/%d (%5.1f%%)  %s and %s%s"
              % (nm, cs, n, 100.0 * cs / n, cl, n, 100.0 * cl / n,
                 NAME[a], NAME.get(b, "sacrum"), note))
    lmc = collections.Counter(len(r["landmarks_lenient"]) for r in rows)
    print("\nnumber of available landmarks per case (lenient):")
    for k in sorted(lmc):
        print("  %d landmark(s): %2d cases  %s" % (k, lmc[k], "#" * lmc[k]))

    print("\n" + "=" * 76)
    print("FIELD OF VIEW")
    print("=" * 76)
    rc = collections.Counter(r["regions"] for r in rows)
    print("region coverage:")
    for k, v in rc.most_common():
        print("  %-6s %3d cases (%5.1f%%)" % (k, v, 100.0 * v / n))
    nl = [r["n_levels"] for r in rows]
    nl_s = sorted(nl)
    print("\nannotated levels per case: min=%d p25=%d median=%d p75=%d max=%d mean=%.1f"
          % (nl_s[0], nl_s[n // 4], nl_s[n // 2], nl_s[3 * n // 4], nl_s[-1],
             float(np.mean(nl))))
    print("total annotated vertebrae in cohort: %d" % sum(nl))
    mism = [r for r in rows if r["n_centroids"] != r["n_levels"]]
    print("cases where centroid count differs from mask label count: %d" % len(mism))
    for r in mism[:5]:
        print("  %-22s mask=%d centroids=%d" % (r["case"], r["n_levels"], r["n_centroids"]))

    print("\n" + "=" * 76)
    print("LEVEL PREVALENCE, the denominator for any per level rate")
    print("=" * 76)
    for v in sorted(level_count):
        c = level_count[v]
        print("  %-7s %3d/%d (%5.1f%%) %s" % (NAME.get(v, "?%d" % v), c, n,
                                              100.0 * c / n, "#" * int(c * 40 / n)))
    print("\nLevels appearing in under 10 percent of cases cannot support a stable")
    print("per level rate. Report those separately or pool them, and never quote a")
    print("bare macro average over levels with this prevalence skew.")

    print("\n" + "=" * 76)
    print("VOXEL GEOMETRY")
    print("=" * 76)
    zc = collections.Counter(r["zooms"] for r in rows)
    print("distinct voxel spacings: %d" % len(zc))
    for k, v in zc.most_common(8):
        print("  %-26s %d cases" % (str(k), v))
    iso = sum(1 for r in rows if len(set(r["zooms"])) == 1)
    print("isotropic cases: %d/%d" % (iso, n))
    print("\nThe model was trained at 1.0 mm isotropic. Anisotropy here reaches")
    print("%.2f mm through plane, so resampling behaviour matters."
          % max(max(r["zooms"]) for r in rows))

    out = Path(args.out) if args.out else RESULTS / "verse_composition.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "cohort": str(d), "n_cases": n,
        "n_with_T13": len(t13), "n_with_L6": len(l6),
        "n_without_landmark_strict": len(nolm_s), "n_without_landmark_lenient": len(nolm_l),
        "total_annotated_vertebrae": sum(nl),
        "level_prevalence": {NAME.get(k, str(k)): v for k, v in sorted(level_count.items())},
        "cases": rows,
    }, indent=2, default=str))
    print("\nwrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
