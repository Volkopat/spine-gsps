"""Revision, Route 2: measure what the deployed emitter wrote on public cases.

Reads the output of `rev2_deployed_on_public.py` and applies to it every instrument the
submitted version applied to the clinical objects, plus the ones reviewer 4 asked for:

  conformance   dciodvfy (absent attributes, out-of-IOD tags) and dcmpschk (verdict and cause)
                on every presentation state
  rendering     DCMTK dcmp2pgm and dcm4che dcm2jpg, each applying the presentation state to the
                slice it references, and a repair ablation on every object: InstanceNumber
                restored, PresentationPixelSpacing restored, both restored, to see which
                attribute decides the refusal
  delivery      every presentation state and its referenced slice over C-STORE to Orthanc and
                to dcm4chee-arc-light, then found over QIDO-RS, retrieved over WADO-RS and
                compared element by element with the file sent
  the flag      from the emitter's own log: vertebrae with a confidence, penalties, and studies
                with at least one penalty, per case; and the largest logged z

Everything here is public data. Output: results/rev2_deployed_public.json.

Usage (spinelab env; both archives running for --archives; Java on JAVA_HOME for dcm2jpg):
    python scripts/rev2_measure_deployed_public.py --work <runs/rev2_deployed_public>
        --dcm4che <dir> --commons-cli <jar> --storescu <exe> [--archives orthanc,dcm4chee]
"""
from __future__ import annotations

import argparse
import glob
import math
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pydicom
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))
from spinelab.gsps import validate as V  # noqa: E402
from spinelab.paths import RESULTS, TOOLS  # noqa: E402
import rev1_archives as ARC  # noqa: E402

BIN = next(iter(glob.glob(str(TOOLS / "dcmtk" / "**" / "bin"), recursive=True)), None)


def dcmtk(tool, *args):
    r = subprocess.run([str(Path(BIN) / (tool + ".exe"))] + [str(a) for a in args],
                       capture_output=True, text=True, errors="replace")
    return r.returncode, r.stdout + r.stderr


def referenced_image(ps_path: Path) -> Path | None:
    ds = pydicom.dcmread(str(ps_path), stop_before_pixels=True)
    uid = str(ds.ReferencedSeriesSequence[0].ReferencedImageSequence[0].ReferencedSOPInstanceUID)
    for f in ps_path.parent.glob("*.dcm"):
        if f == ps_path or f.name.endswith("_GSPS.dcm"):
            continue
        if str(pydicom.dcmread(str(f), stop_before_pixels=True).SOPInstanceUID) == uid:
            return f
    return None


def repaired(src: Path, dst: Path, instance_number: bool, spacing: bool) -> None:
    ds = pydicom.dcmread(str(src))
    if instance_number:
        ds.InstanceNumber = 1
    if spacing:
        ref = pydicom.dcmread(str(referenced_image(src)), stop_before_pixels=True)
        ds.DisplayedAreaSelectionSequence[0].PresentationPixelSpacing = [float(x) for x in ref.PixelSpacing]
    ds.save_as(str(dst))


def render_dcmtk(ps: Path, img: Path) -> bool:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "o.pgm"
        dcmtk("dcmp2pgm", "--pstate", ps, img, out)
        return out.exists() and out.stat().st_size > 0


def render_dcm4che(java_cmd: list[str], ps: Path, img: Path) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "o.png"
        subprocess.run(java_cmd + ["-F", "PNG", "--ps", str(ps), str(img), str(out)],
                       capture_output=True, text=True, errors="replace")
        if not (out.exists() and out.stat().st_size > 0):
            return False, "-"
        a = np.asarray(Image.open(out).convert("L"))
        return True, hashlib.sha256(a.tobytes()).hexdigest()[:16]


def dcmpschk_named(plog: str) -> list[str]:
    """Every problem dcmpschk names: the attributes it reports missing, and its
    presentation-state messages. Its first warning line is a file meta notice, not a cause."""
    out = set()
    for l in plog.splitlines():
        if "Affected attribute:" in l:
            out.add(l.split("Affected attribute:")[1].strip())
        elif l.startswith("W: ") and ("presentation state" in l or "instanceNumber" in l):
            out.add(l[3:].strip())
    return sorted(out)


def flag_census(log: Path) -> dict:
    blocks, cur = [], None
    zs = []
    for l in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if "Processing series:" in l:
            if cur:
                blocks.append(cur)
            cur = {"n": 0, "pen": 0, "gsps": 0, "z": []}
            continue
        if cur is None:
            continue
        m = re.search(r"Extracted confidence for (\d+) vertebrae", l)
        if m:
            cur["n"] = int(m.group(1))
        m = re.search(r"Penalty for \S+: z-score=([\d.]+)", l)
        if m:
            cur["pen"] += 1
            cur["z"].append(float(m.group(1)))
            zs.append(float(m.group(1)))
        if "Creating GSPS" in l:
            cur["gsps"] += 1
    if cur:
        blocks.append(cur)
    g = [b for b in blocks if b["gsps"]]
    # z pooled over every residual including the tested one is bounded by sqrt(n - 1)
    over = sum(1 for b in g if b["z"] and max(b["z"]) > math.sqrt(max(b["n"] - 1, 1)) + 1e-9)
    top = max((b for b in g if b["z"]), key=lambda b: max(b["z"]), default=None)
    return {"studies": len(g), "studies_with_a_penalty": sum(1 for b in g if b["pen"]),
            "vertebrae_with_confidence": sum(b["n"] for b in g), "penalties": sum(b["pen"] for b in g),
            "max_logged_z": max(zs) if zs else None,
            "max_logged_z_study_n": top["n"] if top else None,
            "max_logged_z_study_bound": round(math.sqrt(top["n"] - 1), 4) if top else None,
            "studies_over_their_bound": over}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", required=True)
    ap.add_argument("--dcm4che", required=True)
    ap.add_argument("--commons-cli", required=True)
    ap.add_argument("--storescu", required=True)
    ap.add_argument("--archives", default="")
    ap.add_argument("--reuse-archives", action="store_true",
                    help="carry the archive round trips over from the existing output file, recorded as such, "
                         "instead of storing every object a second time")
    ap.add_argument("--json", default=str(RESULTS / "rev2_deployed_public.json"))
    a = ap.parse_args(argv)
    work = Path(a.work)
    home = Path(a.dcm4che)
    java = str(Path(os.environ.get("JAVA_HOME", "")) / "bin" / "java")
    cp = os.pathsep.join([str(a.commons_cli), str(home / "etc" / "dcm2jpg")] +
                         [str(p) for p in sorted((home / "lib").glob("*.jar")) if "commons-cli" not in p.name])
    jcmd = [java, "-cp", cp, "org.dcm4che3.tool.dcm2jpg.Dcm2Jpg"]

    import datetime
    out = {"work": "runs/" + work.name, "measured_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "objects": [], "summary": {}}
    ps_files = sorted(work.joinpath("gsps").rglob("*_GSPS.dcm"))
    for i, ps in enumerate(ps_files):
        img = referenced_image(ps)
        rec = V.run_one(ps)
        absent = sorted({m["element"] for m in (rec.get("missing") or [])})
        oiod = sorted({str(x.get("tag")) for x in (rec.get("not_in_iod") or []) if isinstance(x, dict)})
        _, plog = dcmtk("dcmpschk", ps)
        named = dcmpschk_named(plog)
        o = {"case": ps.parent.parent.name.replace("pat_", ""), "absent": absent, "out_of_iod": len(oiod),
             "dcmpschk_fails": "Test failed" in plog, "dcmpschk_named": named,
             "dcmp2pgm": render_dcmtk(ps, img), "dcm2jpg": render_dcm4che(jcmd, ps, img)[0]}
        with tempfile.TemporaryDirectory() as td:
            for tag, inst, sp in (("plus_instance_number", True, False), ("plus_pixel_spacing", False, True),
                                  ("plus_both", True, True)):
                f = Path(td) / (tag + ".dcm")
                repaired(ps, f, inst, sp)
                o["dcmp2pgm_" + tag] = render_dcmtk(f, img)
        out["objects"].append(o)
        if (i + 1) % 20 == 0:
            print("  %d/%d measured" % (i + 1, len(ps_files)), flush=True)

    objs = out["objects"]
    seven = ["FileMetaInformationGroupLength", "FileMetaInformationVersion", "InstanceNumber", "Laterality",
             "PresentationPixelSpacing", "SeriesNumber", "StudyID"]
    out["summary"] = {
        "presentation_states": len(objs),
        "all_seven_absent": sum(1 for o in objs if o["absent"] == seven),
        "absent_sets": sorted({",".join(o["absent"]) for o in objs}),
        "out_of_iod_six": sum(1 for o in objs if o["out_of_iod"] == 6),
        "dciodvfy_pass": sum(1 for o in objs if not o["absent"]),
        "dcmpschk_fail": sum(1 for o in objs if o["dcmpschk_fails"]),
        "dcmpschk_named_sets": {k: sum(1 for o in objs if " | ".join(o["dcmpschk_named"]) == k)
                                for k in sorted({" | ".join(o["dcmpschk_named"]) for o in objs})},
        "dcmp2pgm_renders": sum(1 for o in objs if o["dcmp2pgm"]),
        "dcm2jpg_renders": sum(1 for o in objs if o["dcm2jpg"]),
        "dcmp2pgm_renders_plus_instance_number": sum(1 for o in objs if o["dcmp2pgm_plus_instance_number"]),
        "dcmp2pgm_renders_plus_pixel_spacing": sum(1 for o in objs if o["dcmp2pgm_plus_pixel_spacing"]),
        "dcmp2pgm_renders_plus_both": sum(1 for o in objs if o["dcmp2pgm_plus_both"]),
    }
    out["flag"] = flag_census(work / "emitter" / "gsps_generation.log")
    print("summary", json.dumps(out["summary"], indent=1))
    print("flag", out["flag"])

    if a.reuse_archives and not a.archives:
        prev = json.loads(Path(a.json).read_text())
        out["archives"] = prev["archives"]
        out["archives_carried_over_from"] = (prev.get("archives_carried_over_from") or prev.get("measured_at") or
                                             datetime.datetime.fromtimestamp(Path(a.json).stat().st_mtime)
                                             .isoformat(timespec="seconds"))
    if a.archives:
        out["archives"] = {}
        for name in a.archives.split(","):
            cfg = ARC.ARCHIVES[name]
            A = {"cstore": 0, "qido": 0, "wado": 0, "colour_intact": 0, "unaltered": 0, "ref_cstore": 0}
            for ps in ps_files:
                img = referenced_image(ps)
                A["ref_cstore"] += int(ARC.store(a.storescu, cfg["aet"], cfg["port"], img)["response"] == "Success")
                s = ARC.store(a.storescu, cfg["aet"], cfg["port"], ps)
                r = ARC.retrieve(cfg["rs"], pydicom.dcmread(str(ps)))
                A["cstore"] += int(s["response"] == "Success")
                A["qido"] += int(bool(r.get("qido_found")))
                A["wado"] += int(r.get("wado_status") == 200)
                A["colour_intact"] += int(bool(r.get("colour_intact")))
                A["unaltered"] += int(r.get("top_level_removed") == [] and r.get("top_level_changed") == [])
            A["of"] = len(ps_files)
            out["archives"][name] = A
            print(name, A)
    Path(a.json).write_text(json.dumps(out, indent=1))
    print("wrote", a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
