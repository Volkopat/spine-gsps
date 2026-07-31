"""Does `dcmp2pgm` actually draw GSPS annotations, or only the greyscale pipeline?

Round two review, concern N1. Both deliverables state that the reference renderer draws
the annotations and discards only their colour, inferring that from 237,376 bytes
differing between a render with a presentation state and one without. The reviewer
points out that `dcmp2pgm`'s own documentation says textual and graphical annotations
will NOT be visible in its output, because those are drawn by DICOMscope, the Java GUI
layered on the same DCMTK classes. If the reviewer is right, those differing bytes are
the VOI LUT, shutter, displayed area and spatial transforms, and our sentence is false.

This is exactly the inference pattern the ledger exists to catch: a specific mechanism
read off an aggregate signal without isolating it. So isolate it.

Three tests, in increasing directness:

  A. STRIP. Render the object, then render the same object with only
     GraphicAnnotationSequence removed and every greyscale attribute left identical.
     Byte-identical output means the annotations are not drawn.

  B. LOCALISE. Compare the with-pstate render against the no-pstate baseline and ask
     WHERE the differing pixels are. Annotations are sparse, thin and localised near
     the graphic coordinates. A greyscale pipeline change is dense and global. A
     row-occupancy histogram separates these two without ambiguity.

  C. MOVE. Render the object with every annotation displaced by a large offset. If the
     renderer draws annotations, moving them moves the differing pixels.

Usage:
  python scripts/render_annotation_probe.py --image <referenced instance> \
      --pstate <a conformant GSPS referencing it>
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import subprocess
import sys
from pathlib import Path

import numpy as np
import pydicom

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spinelab.paths import RUNS, TOOLS  # noqa: E402

DCMP2PGM = next(iter(glob.glob(str(TOOLS / "dcmtk" / "**" / "dcmp2pgm.exe"),
                               recursive=True)), None)

TAG_GRAPHIC_ANNOTATION = (0x0070, 0x0001)
TAG_GRAPHIC_OBJECT = (0x0070, 0x0009)
TAG_TEXT_OBJECT = (0x0070, 0x0008)
TAG_GRAPHIC_DATA = (0x0070, 0x0022)
TAG_ANCHOR = (0x0070, 0x0014)
TAG_BOUNDING_TLHC = (0x0070, 0x0010)
TAG_BOUNDING_BRHC = (0x0070, 0x0011)


def render(image: Path, pstate: Path | None, out: Path) -> bool:
    cmd = [DCMP2PGM]
    if pstate is not None:
        cmd += ["--pstate", str(pstate)]
    cmd += [str(image), str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stderr.strip():
        for line in r.stderr.strip().splitlines():
            print("      renderer: %s" % line.strip())
    return out.exists() and out.stat().st_size > 0


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def read_pgm(p: Path) -> np.ndarray:
    """Minimal binary PGM reader. Header is 3 whitespace-separated tokens after P5."""
    raw = p.read_bytes()
    tok, i, vals = [], 2, []
    while len(vals) < 3:
        while i < len(raw) and raw[i:i + 1].isspace():
            i += 1
        if raw[i:i + 1] == b"#":
            while i < len(raw) and raw[i:i + 1] != b"\n":
                i += 1
            continue
        j = i
        while j < len(raw) and not raw[j:j + 1].isspace():
            j += 1
        vals.append(int(raw[i:j]))
        i = j
    i += 1
    w, h, maxv = vals
    dt = np.uint8 if maxv < 256 else np.dtype(">u2")
    a = np.frombuffer(raw[i:i + w * h * np.dtype(dt).itemsize], dtype=dt)
    return a.reshape(h, w).astype(np.int32)


def seq(ds, tag):
    """The items of a sequence, or an empty list. ds.get returns a DataElement."""
    if tag not in ds:
        return []
    v = ds[tag].value
    return list(v) if v is not None else []


def strip_annotations(src: Path, dst: Path) -> int:
    ds = pydicom.dcmread(str(src))
    n = len(seq(ds, TAG_GRAPHIC_ANNOTATION))
    if TAG_GRAPHIC_ANNOTATION in ds:
        del ds[TAG_GRAPHIC_ANNOTATION]
    ds.save_as(str(dst), enforce_file_format=True)
    return n


def displace_annotations(src: Path, dst: Path, dx: float, dy: float) -> int:
    ds = pydicom.dcmread(str(src))
    moved = 0
    for item in seq(ds, TAG_GRAPHIC_ANNOTATION):
        for g in seq(item, TAG_GRAPHIC_OBJECT):
            if TAG_GRAPHIC_DATA in g:
                d = list(g[TAG_GRAPHIC_DATA].value)
                g[TAG_GRAPHIC_DATA].value = [
                    (v + (dx if k % 2 == 0 else dy)) for k, v in enumerate(d)]
                moved += 1
        for t in seq(item, TAG_TEXT_OBJECT):
            for tag in (TAG_ANCHOR, TAG_BOUNDING_TLHC, TAG_BOUNDING_BRHC):
                if tag in t:
                    d = list(t[tag].value)
                    t[tag].value = [(v + (dx if k % 2 == 0 else dy))
                                    for k, v in enumerate(d)]
                    moved += 1
    ds.save_as(str(dst), enforce_file_format=True)
    return moved


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", required=True)
    ap.add_argument("--pstate", required=True)
    ap.add_argument("--out", default=str(RUNS / "render_annotation_probe"))
    a = ap.parse_args(argv)

    if not DCMP2PGM:
        print("dcmp2pgm not found under %s" % TOOLS)
        return 2
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    image, pstate = Path(a.image), Path(a.pstate)
    print("renderer : %s" % DCMP2PGM)
    print("image    : %s" % image.name)
    print("pstate   : %s" % pstate.name)

    ds = pydicom.dcmread(str(pstate))
    items = seq(ds, TAG_GRAPHIC_ANNOTATION)
    n_layers = len(items)
    n_graphic = sum(len(seq(i, TAG_GRAPHIC_OBJECT)) for i in items)
    n_text = sum(len(seq(i, TAG_TEXT_OBJECT)) for i in items)
    print("           %d annotation items, %d graphic objects, %d text objects"
          % (n_layers, n_graphic, n_text))

    p_base = out / "baseline_no_pstate.pgm"
    p_full = out / "with_pstate.pgm"
    p_strip_ds = out / "pstate_no_annotations.dcm"
    p_strip = out / "with_pstate_stripped.pgm"
    p_move_ds = out / "pstate_displaced.dcm"
    p_move = out / "with_pstate_displaced.pgm"

    print("\n--- rendering ---")
    ok_b = render(image, None, p_base)
    ok_f = render(image, pstate, p_full)
    stripped = strip_annotations(pstate, p_strip_ds)
    ok_s = render(image, p_strip_ds, p_strip)
    moved = displace_annotations(pstate, p_move_ds, 120.0, 120.0)
    ok_m = render(image, p_move_ds, p_move)
    if not all((ok_b, ok_f, ok_s, ok_m)):
        print("a render produced no output, cannot conclude")
        return 1
    print("  baseline no pstate      %s" % sha(p_base))
    print("  with pstate             %s" % sha(p_full))
    print("  pstate, %2d annotation items removed  %s" % (stripped, sha(p_strip)))
    print("  pstate, %2d objects displaced 120 px  %s" % (moved, sha(p_move)))

    A = read_pgm(p_base)
    F = read_pgm(p_full)
    S = read_pgm(p_strip)
    M = read_pgm(p_move)

    d_pstate = int((A != F).sum())
    d_strip = int((F != S).sum())
    d_move = int((F != M).sum())
    tot = A.size

    print("\n--- test A: does removing the annotations change anything? ---")
    print("  pixels differing, baseline vs with pstate : %d of %d (%.1f%%)"
          % (d_pstate, tot, 100.0 * d_pstate / tot))
    print("  pixels differing, with vs annotations removed : %d" % d_strip)
    print("  pixels differing, with vs annotations moved   : %d" % d_move)

    print("\n--- test B: WHERE do the pstate pixels differ? ---")
    diff = (A != F)
    rows = diff.sum(axis=1)
    occupied = int((rows > 0).sum())
    print("  image %d x %d" % (A.shape[1], A.shape[0]))
    print("  rows containing any difference : %d of %d (%.1f%%)"
          % (occupied, A.shape[0], 100.0 * occupied / A.shape[0]))
    if occupied:
        print("  mean differing pixels per occupied row : %.1f of %d (%.1f%%)"
              % (rows[rows > 0].mean(), A.shape[1],
                 100.0 * rows[rows > 0].mean() / A.shape[1]))
    print("  distinct grey levels, baseline %d, with pstate %d"
          % (len(np.unique(A)), len(np.unique(F))))

    print("\n=== VERDICT ===")
    drawn = d_strip > 0 or d_move > 0
    if drawn:
        print("  The renderer DOES draw annotations: removing or moving them changes")
        print("  the output. The current sentence stands, cite this diff.")
    else:
        print("  The renderer does NOT draw annotations. Removing every annotation and")
        print("  displacing every object BOTH leave the rendered bitmap byte identical.")
        print("  The %d differing pixels between baseline and with-pstate are the" % d_pstate)
        print("  greyscale pipeline (VOI LUT, shutter, displayed area), not annotations.")
        print("  The claim 'the labels and leader lines are drawn' is FALSE and the")
        print("  byte-identical result across colour routes is true by construction.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
