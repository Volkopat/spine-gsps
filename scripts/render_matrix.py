"""Measure whether a presentation state actually renders, using the reference renderer.

The paper's weakest structural point is that it is about delivering annotations to
viewers and measures no viewer. A cross-viewer study needs a human at a screen, but one
important part does not: DCMTK ships `dcmp2pgm`, which applies a presentation state to
an image and writes the rendered bitmap. That is the reference implementation of GSPS
rendering, and it can be diffed.

Three questions this answers without any human judgement:

1. **Does the annotation render at all?** Compare the bitmap rendered with the
   presentation state against the bitmap rendered from the image alone. Identical means
   the overlay was dropped.
2. **Does the colour route change anything?** Compare bitmaps across the layer, line
   and text colour variants. Identical means the renderer ignores the distinction the
   paper spends its container half on.
3. **Do the conformance defects stop rendering?** Compare the as-is variants, which are
   missing required attributes, against the conformant ones.

Note the output is PGM, which is greyscale. A Grayscale Softcopy Presentation State is
greyscale by name and by IOD, so a conformant greyscale renderer has nowhere to put a
colour. If all three colour routes render identically that is not a bug in the renderer,
it is the point.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spinelab.paths import RUNS, TOOLS  # noqa: E402

DCMP2PGM = next(iter(glob.glob(str(TOOLS / "dcmtk" / "**" / "dcmp2pgm.exe"),
                               recursive=True)), None)


def render(image: Path, pstate: Path | None, out: Path) -> tuple[bool, str]:
    cmd = [DCMP2PGM]
    if pstate is not None:
        cmd += ["--pstate", str(pstate)]
    cmd += [str(image), str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    msg = (r.stdout + r.stderr).strip().splitlines()
    return out.exists() and out.stat().st_size > 0, " | ".join(m[:70] for m in msg[:2])


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "-"


def nonzero_diff(a: Path, b: Path) -> int:
    """Count differing bytes in the pixel payload, a crude but sufficient measure."""
    if not (a.exists() and b.exists()):
        return -1
    da, db = a.read_bytes(), b.read_bytes()
    n = min(len(da), len(db))
    return sum(1 for i in range(n) if da[i] != db[i]) + abs(len(da) - len(db))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", required=True, help="the referenced source instance")
    ap.add_argument("--pstate-dir", required=True)
    ap.add_argument("--out", default=str(RUNS / "render_matrix"))
    a = ap.parse_args(argv)

    if not DCMP2PGM:
        print("dcmp2pgm not found under %s" % TOOLS)
        return 2
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    image = Path(a.image)

    print("renderer : %s" % DCMP2PGM)
    print("image    : %s\n" % image.name)

    base = out / "_baseline.pgm"
    ok, msg = render(image, None, base)
    print("baseline, no presentation state: %s  %s" % (
        "rendered %d bytes" % base.stat().st_size if ok else "FAILED", msg))
    if not ok:
        return 1

    rows = []
    for ps in sorted(Path(a.pstate_dir).glob("*.dcm")):
        o = out / (ps.stem + ".pgm")
        ok, msg = render(image, ps, o)
        rows.append({
            "variant": ps.stem.split("__")[-1],
            "rendered": ok,
            "bytes": o.stat().st_size if ok else 0,
            "sha": digest(o),
            "diff_vs_baseline": nonzero_diff(base, o) if ok else -1,
            "msg": msg,
        })

    print("\n%-26s %-9s %10s %18s %s" % ("variant", "rendered", "bytes",
                                         "bytes differing", "sha16"))
    print("-" * 92)
    for r in rows:
        print("%-26s %-9s %10d %18s %s" % (
            r["variant"], "yes" if r["rendered"] else "NO", r["bytes"],
            r["diff_vs_baseline"] if r["diff_vs_baseline"] >= 0 else "n/a", r["sha"]))
        if r["msg"]:
            print("%-26s   %s" % ("", r["msg"][:80]))

    print("\n--- interpretation ---")
    drawn = [r for r in rows if r["diff_vs_baseline"] > 0]
    print("variants that changed the rendered bitmap: %d of %d" % (len(drawn), len(rows)))

    shas = {}
    for r in rows:
        shas.setdefault(r["sha"], []).append(r["variant"])
    print("\ndistinct rendered outputs: %d" % len(shas))
    for sha, names in shas.items():
        print("  %s  %s" % (sha, ", ".join(sorted(names))))
    if len(shas) == 1:
        print("\nALL variants render identically. The renderer is indifferent to the")
        print("colour route, so the container distinction is invisible downstream of it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
