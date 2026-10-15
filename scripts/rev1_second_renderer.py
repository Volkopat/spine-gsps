"""Major revision: a second, independently written renderer.

Reviewer 4: "single renderer". The published rendering results rest on DCMTK's dcmp2pgm (C++).
This repeats them with dcm4che's dcm2jpg (Java, a separate code base and a separate presentation
state implementation), applying each of the nine public presentation-state variants to the same
public source slice, and repeats the annotation probe: every graphic annotation deleted, and
separately every annotation displaced by 120 px. If the bitmap is unchanged by either probe, the
renderer does not draw annotations, and it then speaks only to whether the object loads and to
its greyscale pipeline.

All inputs are public (VerSe sub-verse502, sagittal reformat, CC BY-SA 4.0). Nothing clinical.

Usage (spinelab env; Java 17+ on JAVA_HOME):
    python scripts/rev1_second_renderer.py --image <runs/public_dicom_sag/.../sub-verse502_dir-iso_0217.dcm>
        --pstate-dir <runs/public_gsps_v3> --dcm4che <tools/dcm4che/dcm4che-5.34.1>
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pydicom
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spinelab.paths import RESULTS, RUNS  # noqa: E402


def run(cmd: list[str], env=None) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", env=env, shell=False)
    return r.returncode, (r.stdout + r.stderr).strip()


def pixel_hash(p: Path) -> tuple[str, int]:
    if not p.exists() or p.stat().st_size == 0:
        return "-", 0
    a = np.asarray(Image.open(p).convert("L"))
    return hashlib.sha256(a.tobytes()).hexdigest()[:16], int(len(np.unique(a)))


def strip_or_shift(src: Path, dst: Path, mode: str) -> int:
    """Delete every graphic annotation item, or displace every graphic and text anchor by 120
    px, and write a copy. Returns the number of items touched."""
    ds = pydicom.dcmread(str(src))
    n = 0
    if "GraphicAnnotationSequence" in ds:
        if mode == "delete":
            for it in ds.GraphicAnnotationSequence:
                for key in ("GraphicObjectSequence", "TextObjectSequence"):
                    if key in it:
                        n += len(getattr(it, key))
                        delattr(it, key)
        else:
            for it in ds.GraphicAnnotationSequence:
                for g in it.get("GraphicObjectSequence", []):
                    pts = [float(v) + 120.0 for v in g.GraphicData]
                    g.GraphicData = pts
                    n += 1
                for t in it.get("TextObjectSequence", []):
                    for k in ("AnchorPoint", "BoundingBoxTopLeftHandCorner", "BoundingBoxBottomRightHandCorner"):
                        if k in t:
                            setattr(t, k, [float(v) + 120.0 for v in getattr(t, k)])
                    n += 1
    ds.save_as(str(dst), enforce_file_format=False)
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", required=True)
    ap.add_argument("--pstate-dir", required=True)
    ap.add_argument("--dcm4che", required=True)
    ap.add_argument("--commons-cli", required=True, help="commons-cli-1.4.jar")
    ap.add_argument("--out", default=str(RUNS / "rev1_second_renderer"))
    ap.add_argument("--json", default=str(RESULTS / "rev1_second_renderer.json"))
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    # Java is called directly with the toolkit's own classpath rather than through the .bat
    # launcher, which breaks on a space in the install path. One substitution: dcm2jpg's --ps
    # option fails in dcm4che 5.31.2, 5.33.1 and 5.34.1 alike with "FileInputStream cannot be
    # cast to File" at Dcm2Jpg.java:352, because the bundled commons-cli (1.6 and later) returns
    # an open stream for an existing-file option where the tool expects a File. commons-cli
    # 1.4, the last release returning a File, is put on the classpath in its place (SHA-1
    # c51c00206bb913cd8612b24abd9fa98ae89719b1, as published on Maven Central). Nothing else in
    # the toolkit is touched.
    home = Path(a.dcm4che)
    java = str(Path(os.environ.get("JAVA_HOME", "")) / "bin" / "java")
    cli = Path(a.commons_cli)
    cp = os.pathsep.join([str(cli), str(home / "etc" / "dcm2jpg")] +
                         [str(p) for p in sorted((home / "lib").glob("*.jar")) if "commons-cli" not in p.name])
    base = [java, "-cp", cp, "org.dcm4che3.tool.dcm2jpg.Dcm2Jpg"]
    env = dict(os.environ)
    ver = run(base + ["-V"], env)[1].splitlines()[:1]

    def render(ps: Path | None, dst: Path):
        cmd = base + ["-F", "PNG"]
        if ps is not None:
            cmd += ["--ps", str(ps)]
        cmd += [str(a.image), str(dst)]
        if dst.exists():
            dst.unlink()
        code, msg = run(cmd, env)
        h, levels = pixel_hash(dst)
        return {"exit": code, "written": dst.exists() and dst.stat().st_size > 0, "pixel_sha256_16": h,
                "distinct_grey_levels": levels, "message": " | ".join(msg.splitlines()[-2:])[:300]}

    res = {"renderer": "dcm4che dcm2jpg", "version": ver, "image": Path(a.image).name, "variants": {}}
    res["baseline_no_pstate"] = render(None, out / "_baseline.png")
    for ps in sorted(Path(a.pstate_dir).glob("*.dcm")):
        tag = ps.stem.split("__")[-1]
        res["variants"][tag] = render(ps, out / (tag + ".png"))
        v = res["variants"][tag]
        print("%-24s exit %s  written %-5s  %s  levels %s  %s" % (tag, v["exit"], v["written"], v["pixel_sha256_16"],
                                                              v["distinct_grey_levels"], v["message"][:90]))
    # annotation probe on one conformant variant
    src = next(Path(a.pstate_dir).glob("*conformant_trueid.dcm"))
    probe = {}
    for mode in ("delete", "shift"):
        dst = out / ("_probe_%s.dcm" % mode)
        n = strip_or_shift(src, dst, mode)
        probe[mode] = dict(render(dst, out / ("_probe_%s.png" % mode)), items_touched=n)
    probe["unmodified"] = res["variants"].get("conformant_trueid")
    res["annotation_probe"] = probe
    same_del = probe["delete"]["pixel_sha256_16"] == probe["unmodified"]["pixel_sha256_16"]
    same_shift = probe["shift"]["pixel_sha256_16"] == probe["unmodified"]["pixel_sha256_16"]
    res["draws_annotations"] = not (same_del and same_shift)
    print("annotation probe: deleted %s, shifted %s -> draws annotations: %s" % (
        "identical" if same_del else "DIFFERENT", "identical" if same_shift else "DIFFERENT", res["draws_annotations"]))
    Path(a.json).write_text(json.dumps(res, indent=1))
    print("wrote", a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
