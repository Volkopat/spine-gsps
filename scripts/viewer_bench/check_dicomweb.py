"""Ask the bench Orthanc, over DICOMweb, what the browser viewers will actually see.

load_objects.py proves the archive accepted an object. That is not the same as the
object being discoverable and intact on the path a web viewer uses. OHIF, and the
Orthanc OHIF plugin, consume QIDO-RS and WADO-RS metadata, which is a different
code path from Orthanc's native REST API. An out-of-IOD attribute could survive
one and be dropped by the other, and if that happened we would misread it as the
viewer ignoring the colour.

So this checks three things, per series:

  1. QIDO-RS lists the series at all, and with which Modality.
  2. WADO-RS metadata returns it.
  3. Which of the three colour routes are still present in that metadata.

It renders nothing and it scores no viewer. It only fixes the transport as a
variable so the human rendering pass can be attributed to the viewer.

Usage:
    python check_dicomweb.py [--url http://localhost:8142] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys

import requests

DEFAULT_URL = "http://localhost:8142"

# Keyword form, which is how DICOMweb JSON names top level attributes.
COLOUR_TAGS = {
    "00700241": "text colour, NOT in the GSPS IOD",
    "00700251": "line colour, in the IOD",
    "00700401": "layer colour, in the IOD",
}
SHORT = {"00700241": "text", "00700251": "line", "00700401": "layer"}


def _tags_present(node, wanted: set, found: set) -> None:
    """Recursive scan of DICOMweb JSON. Sequence items sit under "Value"."""
    if isinstance(node, dict):
        for key, val in node.items():
            if key in wanted:
                found.add(key)
            _tags_present(val, wanted, found)
    elif isinstance(node, list):
        for item in node:
            _tags_present(item, wanted, found)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--modality", default=None,
                    help="only series of this Modality, e.g. PR")
    ap.add_argument("--json", dest="out", default=None)
    args = ap.parse_args(argv)

    base = args.url.rstrip("/")
    dw = base + "/dicom-web"
    s = requests.Session()

    try:
        studies = s.get(dw + "/studies", timeout=30).json()
    except Exception as exc:
        print("cannot reach DICOMweb at %s: %s" % (dw, exc))
        return 2
    print("QIDO-RS /studies returned %d study/studies" % len(studies))

    records = []
    for st in studies:
        study_uid = st.get("0020000D", {}).get("Value", [None])[0]
        r = s.get("%s/studies/%s/series" % (dw, study_uid), timeout=60)
        series = r.json() if r.status_code == 200 else []
        print("\nstudy %s\n  QIDO-RS /series HTTP %d, %d series"
              % (study_uid, r.status_code, len(series)))
        for se in series:
            series_uid = se.get("0020000E", {}).get("Value", [None])[0]
            modality = (se.get("00080060", {}).get("Value", [None])[0]) or "?"
            n_inst = (se.get("00201209", {}).get("Value", [None])[0])
            if args.modality and modality != args.modality:
                continue
            m = s.get("%s/studies/%s/series/%s/metadata"
                      % (dw, study_uid, series_uid), timeout=120)
            found: set = set()
            if m.status_code == 200:
                _tags_present(m.json(), set(COLOUR_TAGS), found)
            desc = (se.get("0008103E", {}).get("Value", [""]) or [""])[0]
            rec = {
                "study_uid": study_uid, "series_uid": series_uid,
                "modality": modality, "instances": n_inst,
                "series_description": desc,
                "metadata_http": m.status_code,
                "colour_tags_in_dicomweb_metadata": sorted(found),
            }
            records.append(rec)
            print("    %-3s  n=%-3s  meta HTTP %-3d  colour %-16s  %s"
                  % (modality, n_inst, m.status_code,
                     ",".join(SHORT.get(c, c) for c in sorted(found)) or "-",
                     desc[:40]))

    if args.out:
        from pathlib import Path
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(
            {"dicomweb_root": dw, "n_series": len(records),
             "records": records}, indent=2))
        print("\nwrote %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
