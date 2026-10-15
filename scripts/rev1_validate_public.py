"""Major revision: one provenance for the nine-variant table.

The published Table 2 put validator counts from the nine CLINICAL-derived re-encodings
(runs/gsps_variants, built from one delivered object) beside renderer results from the nine
PUBLIC reconstructions (runs/public_gsps_v3, built on VerSe sub-verse502). The two sets share
variant names but not content: the clinical as-is copies keep every defect of the delivered
object, the public as-is reconstructions reproduce only some. Reviewer 4 asked for the errors of
the as-is encoding to be stated relative to the control, which needs both on the same object.

This runs every tool on the public set only, so the revised table has one provenance and touches
no clinical data:
  dciodvfy (dicom3tools)  distinct attributes reported absent, distinct out-of-IOD tags
  dcmpschk (DCMTK 3.7.0)  pass or fail, and the named cause
  dcmp2pgm (DCMTK 3.7.0)  rendered or refused on the referenced public slice

Usage (spinelab env):
    python scripts/rev1_validate_public.py --pstate-dir <runs/public_gsps_v3> --image <...0217.dcm>
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spinelab.gsps import validate as V  # noqa: E402
from spinelab.paths import RESULTS, TOOLS  # noqa: E402

BIN = next(iter(glob.glob(str(TOOLS / "dcmtk" / "**" / "bin"), recursive=True)), None)


def dcmtk(tool: str, *args) -> tuple[int, str]:
    r = subprocess.run([str(Path(BIN) / (tool + ".exe"))] + [str(a) for a in args],
                       capture_output=True, text=True, errors="replace")
    return r.returncode, (r.stdout + r.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pstate-dir", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--json", default=str(RESULTS / "rev1_public_variants.json"))
    a = ap.parse_args(argv)
    out = {"dciodvfy": str(V.DCIODVFY), "dcmtk_bin": BIN, "variants": {}}
    for f in sorted(Path(a.pstate_dir).glob("*.dcm")):
        tag = f.stem.split("__")[-1]
        rec = V.run_one(f)
        missing = sorted({m["element"] for m in (rec.get("missing") or [])})
        noti = rec.get("not_in_iod") or []
        # dciodvfy reports one record per occurrence (114 on the text-colour variants, one per
        # text object); the table counts distinct tags, as the published tables did
        noti_distinct = sorted({str(x.get("tag")) + " " + str(x.get("name")) for x in noti if isinstance(x, dict)})
        code, log = dcmtk("dcmpschk", f)
        # dcmpschk exits 0 either way and reports its verdict on a warning line
        psk_fail = "Test failed" in log
        cause = [l[2:].strip() for l in log.splitlines()
                 if l.startswith("W:") and "Testing:" not in l and "Test failed" not in l
                 and "Test passed" not in l][:2]
        with tempfile.TemporaryDirectory() as td:
            pgm = Path(td) / "out.pgm"
            rc, rlog = dcmtk("dcmp2pgm", "--pstate", f, a.image, pgm)
            rendered = pgm.exists() and pgm.stat().st_size > 0
            rcause = [l.strip() for l in rlog.splitlines() if l.startswith(("E:", "F:"))][:2]
        out["variants"][tag] = {"dciodvfy_absent": missing, "dciodvfy_absent_n": len(missing),
                                "dciodvfy_not_in_iod_distinct": noti_distinct,
                                "dciodvfy_not_in_iod_n": len(noti_distinct),
                                "dcmpschk": "fails" if psk_fail else "passes", "dcmpschk_cause": cause,
                                "dcmp2pgm": "renders" if rendered else "refused", "dcmp2pgm_exit": rc,
                                "dcmp2pgm_cause": rcause}
        v = out["variants"][tag]
        print("%-24s absent %d %s | out-of-IOD %d | dcmpschk %s %s | dcmp2pgm %s %s" % (
            tag, v["dciodvfy_absent_n"], missing, v["dciodvfy_not_in_iod_n"], v["dcmpschk"], cause[:1],
            v["dcmp2pgm"], rcause[:1]))
    Path(a.json).write_text(json.dumps(out, indent=1))
    print("wrote", a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
