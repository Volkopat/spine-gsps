"""Revision, Route 2: the deployed emitter, unmodified, run on public cases.

The submitted version measured the presentation states the deployed service emitted on
clinical examinations. The revision rests every result on public data instead. The container
findings are properties of the service's code, not of any patient, so they are reproduced by
running that code itself, `generate_gsps_4.py` exactly as deployed (outer repository commit
9bb5648, `test_api/`), on public VerSe cases. Nothing in the emitter is edited; this script only
builds the two inputs it reads, in the format the deployed pipeline wrote them:

  dicom_base_dir/pat_<case>/...            a DICOM series of the case's central sagittal slices,
                                           converted from the public NIfTI by our converter
  output_dir/pat_<case>/<series>/json/2d_spine_per-instance-sop.json
                                           per SOPInstanceUID, per vertebra, a bounding box
                                           [[min_x, min_y], [max_x, max_y]] in pixels and a
                                           confidence in percent, the format of the deployed
                                           json_generator.py

Boxes come from the case's own step-2 segmentation (same grid as the CT), each labelled
voxel mapped to the DICOM plane through its world coordinate. Names are the batch run's level
assignment. Confidence is the shipped readout (`parity_region_deployed`, 3-D formula), times 100.
The deployed pipeline's JSON came from a 2-D per-slice stage that is not part of this harness;
its geometry is approximated here, and only its format is reproduced.

The emitter is then run once, under the analysis environment (pydicom 3.0.2, which like the
deployment writes no file meta group length or version), and writes one presentation state per
case plus anonymised copies of the slices, and its own log, which records every penalty.

Usage (spinelab env):
    python scripts/rev2_deployed_on_public.py --run-dir <runs/verse_batch_01> --work <runs/rev2_deployed_public>
        [--slices 40] [--limit N]
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np
import pydicom

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spinelab.confidence import channels as CH  # noqa: E402
from spinelab.io import nifti_to_dicom as N2D  # noqa: E402
from spinelab.paths import DATASETS, RESULTS  # noqa: E402

OUTER = Path(__file__).resolve().parents[2]          # the private baseline repository
EMITTER_COMMIT = "9bb5648"


def fetch_emitter(dst: Path) -> dict:
    dst.mkdir(parents=True, exist_ok=True)
    out = {}
    for name in ("generate_gsps_4.py", "config.py"):
        src = subprocess.run(["git", "show", "%s:test_api/%s" % (EMITTER_COMMIT, name)], cwd=str(OUTER),
                             capture_output=True, check=True).stdout
        (dst / name).write_bytes(src)
        out[name] = hashlib.sha256(src).hexdigest()
    return out


def lr_axis(affine) -> int:
    codes = nib.aff2axcodes(affine)
    return [i for i, c in enumerate(codes) if c in ("L", "R")][0]


def build_case(case: str, verts: list[dict], shipped: dict, data_dir: Path, seg_dir: Path,
               dicom_root: Path, out_root: Path, n_slices: int) -> dict | None:
    ct_p = glob.glob(str(data_dir / (case + "*_ct.nii.gz")))
    seg_p = seg_dir / (case + "_step2_output.nii.gz")
    if not ct_p or not seg_p.exists():
        return None
    ct, seg = nib.load(ct_p[0]), nib.load(str(seg_p))
    if ct.shape != seg.shape or np.abs(ct.affine - seg.affine).max() > 1e-3:
        return {"case": case, "skipped": "segmentation grid differs from CT"}
    ax = lr_axis(ct.affine)
    sd = np.asarray(seg.dataobj).astype(np.int16)
    lab2name = {int(v["label"]): CH.normalise(v.get("name", "")) for v in verts if v.get("label") is not None}
    lab2name = {k: v for k, v in lab2name.items() if v}
    if not lab2name:
        return {"case": case, "skipped": "no named vertebrae"}
    # centre the crop on the spine along the left-right axis
    idx = np.nonzero(np.isin(sd, list(lab2name)))
    if idx[0].size == 0:
        return {"case": case, "skipped": "no labelled voxels"}
    c = int(round(float(np.median(idx[ax]))))
    lo = max(0, c - n_slices // 2)
    hi = min(ct.shape[ax], lo + n_slices)
    sl = [slice(None)] * 3
    sl[ax] = slice(lo, hi)
    ct_c, seg_c = ct.slicer[tuple(sl)], seg.slicer[tuple(sl)]
    series = "SAG_CT"
    sdir = dicom_root / ("pat_" + case) / series
    # Some VerSe volumes store Hounsfield units as floating point, which the converter refuses
    # to quantise silently. Round to whole units here, explicitly: a sub-unit change that touches
    # neither the boxes, which come from the segmentation, nor any attribute that is scored.
    hu = np.rint(np.asarray(ct_c.dataobj, dtype=np.float64)).astype(np.int16)
    ct_c = nib.Nifti1Image(hu, ct_c.affine)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / (case + "_ct.nii.gz")
        nib.save(ct_c, str(tmp))
        rec = N2D.write_series(tmp, sdir, subject=case, slice_axis=ax)
    # read the series back: geometry per instance
    inst = []
    for f in sorted(sdir.glob("*.dcm")):
        d = pydicom.dcmread(str(f), stop_before_pixels=True)
        inst.append({"sop": str(d.SOPInstanceUID), "ipp": np.array([float(x) for x in d.ImagePositionPatient]),
                     "iop": np.array([float(x) for x in d.ImageOrientationPatient]),
                     "ps": [float(x) for x in d.PixelSpacing], "rows": int(d.Rows), "cols": int(d.Columns),
                     "n": int(getattr(d, "InstanceNumber", 0) or 0)})
    inst.sort(key=lambda r: r["n"])
    X, Y = inst[0]["iop"][:3], inst[0]["iop"][3:]
    nrm = np.cross(X, Y)
    pos = np.array([float(np.dot(nrm, r["ipp"])) for r in inst])
    # every labelled voxel of the crop, to LPS world coordinates
    sc = np.asarray(seg_c.dataobj).astype(np.int16)
    vi = np.array(np.nonzero(np.isin(sc, list(lab2name))))
    labs = sc[tuple(vi)]
    ras = (seg_c.affine[:3, :3] @ vi + seg_c.affine[:3, 3:4])
    lps = ras * np.array([[-1.0], [-1.0], [1.0]])
    k = np.abs(np.dot(nrm, lps)[None, :] - pos[:, None]).argmin(axis=0)
    data = {}
    for j, r in enumerate(inst):
        on = k == j
        if not on.any():
            data[r["sop"]] = {}
            continue
        rel = lps[:, on] - r["ipp"][:, None]
        col = np.dot(X, rel) / r["ps"][1]
        row = np.dot(Y, rel) / r["ps"][0]
        lb = labs[on]
        frame = {}
        for L in np.unique(lb):
            m = lb == L
            name = lab2name.get(int(L))
            if not name or m.sum() < 20:
                continue
            frame["vertebrae_" + name] = {
                "coords": [[float(col[m].min()), float(row[m].min())], [float(col[m].max()), float(row[m].max())]],
                "confidence": float(100.0 * shipped.get(name, 0.0)),
            }
        data[r["sop"]] = frame
    jdir = out_root / ("pat_" + case) / series / "json"
    jdir.mkdir(parents=True, exist_ok=True)
    (jdir / "2d_spine_per-instance-sop.json").write_text(json.dumps(
        {"image_dimensions": [inst[0]["cols"], inst[0]["rows"]], "data": data}))
    return {"case": case, "slices": len(inst), "lr_axis": ax, "crop": [lo, hi],
            "frames_with_vertebrae": sum(1 for v in data.values() if v)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--rows", default=str(RESULTS / "rev1_rows.json"))
    ap.add_argument("--slices", type=int, default=40)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args(argv)
    run, work = Path(a.run_dir), Path(a.work)
    rows = json.load(open(a.rows))["rows"]
    shipped = {}
    for r in rows:
        shipped.setdefault(r["case"], {})[r["name"]] = r["arms"]["parity_region_deployed"]
    cases = sorted(shipped)[: a.limit] if a.limit else sorted(shipped)
    prov = {"emitter_commit": EMITTER_COMMIT, "emitter_sha256": fetch_emitter(work / "emitter"),
            "pydicom": pydicom.__version__, "slices_per_case": a.slices, "cases": []}
    for i, case in enumerate(cases):
        cj = json.load(open(run / "cases" / (case + ".json")))
        try:
            rec = build_case(case, cj.get("vertebrae") or [], shipped[case], DATASETS / "verse_4skx2",
                             run / "seg", work / "dicom", work / "output", a.slices)
        except Exception as exc:                      # recorded, never silently dropped
            rec = {"case": case, "failed": "%s: %s" % (type(exc).__name__, exc)}
        prov["cases"].append(rec)
        print("[%3d/%d] %s %s" % (i + 1, len(cases), case, rec), flush=True)
    # run the deployed emitter, unmodified, from its own directory
    em = work / "emitter"
    r = subprocess.run([sys.executable, "generate_gsps_4.py", "--output_dir", str(work / "output"),
                        "--dicom_base_dir", str(work / "dicom"), "--gsps_output_dir", str(work / "gsps")],
                       cwd=str(em), capture_output=True, text=True, errors="replace")
    prov["emitter_exit"] = r.returncode
    prov["emitter_tail"] = (r.stdout + r.stderr).splitlines()[-3:]
    prov["presentation_states"] = len(list((work / "gsps").rglob("*_GSPS.dcm")))
    (work / "provenance.json").write_text(json.dumps(prov, indent=1, default=str))
    print("emitter exit %d, %d presentation states" % (r.returncode, prov["presentation_states"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
