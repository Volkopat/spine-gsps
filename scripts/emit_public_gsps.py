"""Emit GSPS objects from scratch on PUBLIC data, removing the clinical dependency.

Every GSPS variant so far was re-emitted from an existing clinical object, which
means the E5 artifact cannot be released. This builds one from nothing: a public
VerSe case converted to DICOM CT, annotated with that case's own predicted vertebra
levels and corrected confidences from the batch run.

The coordinate chain, which is where this silently goes wrong:

  batch JSON  centroid_world_ras_mm, RAS, millimetres
  ->  negate x and y                RAS to LPS, because DICOM patient space is LPS
  ->  per slice inverse of          P(r,c) = IPP + c*dCol*X + r*dRow*Y
      the DICOM image plane         where IOP = [X(3), Y(3)] and
                                    PixelSpacing = [dRow, dCol]
  ->  choose the slice whose        offset along the plane normal X cross Y
      normal offset is smallest     is nearest zero
  ->  pixel row, column             what a GSPS text object and polyline need

Confidence displayed is the parity_sequence_phased arm, the only channel selection
rule measured to carry signal (AUC 0.865 preliminary against 0.418 for the mapping
that produced every published number). So the public object carries the CORRECTED
confidence, not the one the deployed system shows.

Self check, printed every run: how many vertebrae project inside the image bounds.
A coordinate chain error shows up immediately as points landing outside, which is
exactly the failure a visual check would miss on a single slice.

Usage:
  python scripts/emit_public_gsps.py --case sub-verse508_dir-ax --out <path>\\runs\\public_gsps
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

import numpy as np
import pydicom

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spinelab.confidence import channels as CH  # noqa: E402
from spinelab.gsps import writer as W  # noqa: E402
from spinelab.paths import DATASETS, RUNS  # noqa: E402


def conf_from_channel(ch: dict, n_voxels: int) -> float:
    return (0.20 * float(ch.get("mean", 0.0))
            + 0.50 * float(ch.get("p95", 0.0))
            + 0.30 * min(1.0, float(ch.get("n_gt_0p7", 0)) / max(1, n_voxels)))


def phased_confidences(verts: list[dict]) -> list[dict]:
    """Order along the column, estimate the alternation phase, score each vertebra."""
    ordered = sorted([v for v in verts if v.get("centroid_world_ras_mm")],
                     key=lambda v: -float(v["centroid_world_ras_mm"][2]))
    best_off, best_tot = 0, -1.0
    for off in (0, 1):
        tot = 0.0
        for i, v in enumerate(ordered):
            try:
                ci = CH.channel_parity(CH.normalise(v.get("name", "")), ordinal=i + off)
            except Exception:
                continue
            tot += float((v.get("channels") or {}).get(str(ci), {}).get("mean", 0.0))
        if tot > best_tot:
            best_off, best_tot = off, tot
    out = []
    for i, v in enumerate(ordered):
        name = CH.normalise(v.get("name", ""))
        try:
            ci = CH.channel_parity(name, ordinal=i + best_off)
            c = conf_from_channel((v.get("channels") or {}).get(str(ci), {}),
                                  int(v.get("n_voxels") or 1))
        except Exception:
            continue
        out.append({"name": name, "conf": c,
                    "world_ras": np.asarray(v["centroid_world_ras_mm"], float)})
    return out


def load_series(series_dir: Path) -> list[pydicom.Dataset]:
    ds = []
    for f in sorted(glob.glob(str(series_dir / "*.dcm"))):
        ds.append(pydicom.dcmread(f, stop_before_pixels=True))
    if not ds:
        raise SystemExit("no DICOM instances in %s" % series_dir)
    return ds


def project(world_lps: np.ndarray, inst: pydicom.Dataset):
    """Return (row, col, normal_offset_mm) of a patient point on this instance."""
    iop = np.asarray(inst.ImageOrientationPatient, float)
    X, Y = iop[:3], iop[3:]                     # col dir, row dir
    ipp = np.asarray(inst.ImagePositionPatient, float)
    d_row, d_col = (float(inst.PixelSpacing[0]), float(inst.PixelSpacing[1]))
    n = np.cross(X, Y)
    n = n / (np.linalg.norm(n) or 1.0)
    d = world_lps - ipp
    return float(d @ Y / d_row), float(d @ X / d_col), float(d @ n)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--run-dir", default=str(RUNS / "verse_batch_01"))
    ap.add_argument("--series-root", default=str(RUNS / "public_dicom"))
    ap.add_argument("--out", default=str(RUNS / "public_gsps"))
    ap.add_argument("--flag-below", type=float, default=0.35,
                    help="mark a vertebra as flagged when its confidence is below this")
    args = ap.parse_args(argv)

    stem = args.case
    cj = Path(args.run_dir) / "cases" / (stem + ".json")
    if not cj.exists():
        raise SystemExit("no batch record at %s" % cj)
    rec = json.loads(cj.read_text())
    if not str(rec.get("status", "")).startswith("ok"):
        raise SystemExit("case status is %r, need an ok case" % rec.get("status"))

    verts = phased_confidences(rec.get("vertebrae") or [])
    print("case            : %s" % stem)
    print("vertebrae scored : %d" % len(verts))
    if not verts:
        raise SystemExit("no scorable vertebrae")

    # public DICOM series, converting on demand
    series_dir = Path(args.series_root) / stem
    if not glob.glob(str(series_dir / "*.dcm")):
        nii = list(DATASETS.glob("verse_4skx2/%s_ct.nii.gz" % stem))
        if not nii:
            raise SystemExit("no VerSe NIfTI for %s" % stem)
        print("converting NIfTI to DICOM, this takes a minute...")
        # subprocess, not os.system: on Windows os.system re-parses the string
        # through cmd.exe and mangles a quoted interpreter path, failing with
        # "The filename, directory name, or volume label syntax is incorrect."
        import subprocess

        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        cp = subprocess.run(
            [sys.executable, "-m", "spinelab.io.nifti_to_dicom", str(nii[0]),
             "--out", str(args.series_root)],
            env=env, capture_output=True, text=True)
        if cp.returncode != 0:
            print(cp.stdout[-2000:])
            print(cp.stderr[-2000:])
            raise SystemExit("NIfTI to DICOM conversion failed, rc=%d" % cp.returncode)
    insts = load_series(series_dir)
    print("series instances : %d, %s x %s" % (
        len(insts), insts[0].Rows, insts[0].Columns))

    # RAS to LPS
    lps = [{"name": v["name"], "conf": v["conf"],
            "p": np.array([-v["world_ras"][0], -v["world_ras"][1], v["world_ras"][2]])}
           for v in verts]

    # pick the instance minimising total absolute normal offset over all vertebrae
    best, best_cost = None, None
    for inst in insts:
        cost = 0.0
        for v in lps:
            cost += abs(project(v["p"], inst)[2])
        if best_cost is None or cost < best_cost:
            best, best_cost = inst, cost
    rows, cols = int(best.Rows), int(best.Columns)
    print("chosen instance  : InstanceNumber %s, mean |normal offset| %.1f mm"
          % (best.get("InstanceNumber"), best_cost / len(lps)))

    inside = 0
    anns = []
    for v in lps:
        r, c, off = project(v["p"], best)
        ok = (0 <= r < rows) and (0 <= c < cols)
        inside += int(ok)
        anns.append({"name": v["name"], "conf": v["conf"], "row": r, "col": c,
                     "normal_mm": off, "inside": ok})

    print("\nSELF CHECK: vertebrae projecting inside the %dx%d image: %d/%d"
          % (rows, cols, inside, len(anns)))
    for a in anns:
        print("  %-7s conf %5.1f%%  row %7.1f col %7.1f  normal %8.1f mm  %s"
              % (a["name"], 100 * a["conf"], a["row"], a["col"], a["normal_mm"],
                 "" if a["inside"] else "OUTSIDE IMAGE"))
    if inside == 0:
        print("\nEVERY point fell outside the image. The coordinate chain is wrong.")
        print("Most likely the RAS to LPS flip or the row/column axis assignment.")
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "case": stem, "series_dir": str(series_dir),
        "instance": str(best.SOPInstanceUID),
        "rows": rows, "columns": cols,
        "inside": inside, "total": len(anns),
        "confidence_arm": "parity_sequence_phased",
        "annotations": [{k: (float(x) if isinstance(x, (int, float, np.floating)) else x)
                         for k, x in a.items()} for a in anns],
    }
    (out / (stem + "_annotations.json")).write_text(json.dumps(payload, indent=2))
    print("\nwrote %s" % (out / (stem + "_annotations.json")))
    print("\nNOTE: this writes the annotation geometry and the corrected confidences.")
    print("Emitting the GSPS objects themselves reuses spinelab.gsps.writer, which")
    print("currently re-emits variants of an EXISTING object. Wiring a from scratch")
    print("build path is the remaining step and is deliberately not faked here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
