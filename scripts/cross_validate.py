"""Cross-validate presentation states against two independent validators.

Comment 1 of an adversarial review established that a dciodvfy diagnostic is evidence
about dciodvfy's IOD tables, not about the standard. Reading PS3.3 settled the
question. This adds the empirical half: a second, independent validator.

  dciodvfy   David Clunie, dicom3tools. General IOD validator.
  dcmpschk   DCMTK. Checker written specifically for presentation states.

Where two reference validators disagree about the same object, neither can be quoted
as "the standard says". Where they agree, the finding is robust to the choice of tool.
"""
from __future__ import annotations

import argparse
import glob
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spinelab.paths import DCIODVFY, TOOLS  # noqa: E402

DCMPSCHK = next(iter(glob.glob(str(TOOLS / "dcmtk" / "**" / "dcmpschk.exe"),
                               recursive=True)), None)


def run_dciodvfy(p: Path) -> tuple[int, int]:
    """Return (required-attribute errors, distinct out-of-IOD tags)."""
    r = subprocess.run([str(DCIODVFY), str(p)], capture_output=True, text=True,
                       errors="replace")
    out = r.stdout + r.stderr
    miss = {m for m in re.findall(r"Missing attribute Type \S+ \S+ Element=<([^>]+)>", out)}
    noniod = {m for m in re.findall(r"not present in standard DICOM IOD - \((0x[0-9a-fA-F]{4},0x[0-9a-fA-F]{4})\)", out)}
    return len(miss), len(noniod)


def run_dcmpschk(p: Path) -> tuple[str, list[str]]:
    """Return (verdict, messages)."""
    if not DCMPSCHK:
        return ("unavailable", [])
    r = subprocess.run([DCMPSCHK, str(p)], capture_output=True, text=True,
                       errors="replace")
    out = (r.stdout + r.stderr).splitlines()
    msgs = [l.split(":", 1)[-1].strip() for l in out
            if l.startswith(("W:", "E:")) and "Testing:" not in l
            and "Test passed" not in l and "Test failed" not in l]
    verdict = "PASS" if any("Test passed" in l for l in out) else (
        "FAIL" if any("Test failed" in l for l in out) else "?")
    return verdict, msgs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("targets", nargs="+")
    ap.add_argument("--pattern", default=None)
    a = ap.parse_args(argv)

    files: list[Path] = []
    for t in a.targets:
        p = Path(t)
        files.extend(sorted(p.rglob("*.dcm")) if p.is_dir() else [p])
    if a.pattern:
        files = [f for f in files if a.pattern in f.name]
    if not files:
        print("no files matched")
        return 1

    print("dciodvfy : %s" % DCIODVFY)
    print("dcmpschk : %s\n" % (DCMPSCHK or "NOT FOUND"))
    print("%-46s %-24s %-10s %s" % ("object", "dciodvfy", "dcmpschk", "agree?"))
    print("-" * 100)

    disagree = 0
    for f in files:
        err, noniod = run_dciodvfy(f)
        verdict, msgs = run_dcmpschk(f)
        dciod = "%d err, %d out-of-IOD" % (err, noniod)
        # dciodvfy "clean" means no required-attribute errors beyond the unevaluable
        # Laterality conditional, and no out-of-IOD attributes.
        dciod_ok = (err <= 1 and noniod == 0)
        ps_ok = (verdict == "PASS")
        agree = "yes" if dciod_ok == ps_ok else "**NO**"
        if agree != "yes":
            disagree += 1
        print("%-46s %-24s %-10s %s" % (f.name[:46], dciod, verdict, agree))
        for m in msgs[:2]:
            print("%-46s %s" % ("", "  dcmpschk: " + m[:60]))

    print("\n%d of %d objects where the two validators disagree" % (disagree, len(files)))
    if disagree:
        print("Where they disagree, neither can be quoted as 'the standard says'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
