"""Major revision: the delivery path on two archives, every object over C-STORE.

Reviewer 4: "single (tolerant) archive ... single object for C-STORE. At least a second archive
is required." The published delivery results rest on Orthanc 1.12.11, with C-STORE tried on one
delivered object only. This sends every public object, the nine presentation-state variants
(seven conformant, two as-is reproductions of the delivered encoding) and their referenced CT
series, to two archives that share no code, over the DICOM network path (DCMTK storescu), then
reads each one back over DICOMweb (QIDO-RS to find it, WADO-RS to retrieve it) and compares the
retrieved dataset with the file sent, element by element:

  orthanc    Orthanc 1.12.11, a fresh container with no persistent volume
  dcm4chee   dcm4chee-arc-light 5.35.1 (scripts/second_archive/docker-compose.yml)

Recorded per object and archive: the C-STORE response status, whether QIDO-RS finds it, whether
WADO-RS returns it, which top-level elements differ between sent and retrieved, and whether every
colour attribute of the object's route survives (Text Style, Line Style and Graphic Layer
CIELab values). All inputs are public (VerSe sub-verse502, CC BY-SA 4.0). Nothing clinical.

Usage (spinelab env; both archives running):
    python scripts/rev1_archives.py --pstate-dir <runs/public_gsps_v3>
        --series-dir <runs/public_dicom_sag/sub-verse502_dir-iso> --storescu <dcmtk/bin/storescu.exe>
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import re
import subprocess
import sys
from email import message_from_bytes
from pathlib import Path

import pydicom
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spinelab.paths import RESULTS  # noqa: E402

ARCHIVES = {
    "orthanc": {"aet": "ORTHANCR1", "port": 4343, "rs": "http://localhost:8143/dicom-web",
                "version_url": "http://localhost:8143/system"},
    "dcm4chee": {"aet": "DCM4CHEE", "port": 11212, "rs": "http://localhost:8180/dcm4chee-arc/aets/DCM4CHEE/rs",
                 "version_url": None},
}
COLOUR_TAGS = {0x00700241: "TextColorCIELabValue", 0x00700251: "PatternOnColorCIELabValue",
               0x00700401: "GraphicLayerRecommendedDisplayCIELabValue"}


def walk_tags(ds) -> set[int]:
    out = set()
    for el in ds.iterall():
        out.add(int(el.tag))
    return out


def store(storescu: str, aet: str, port: int, f: Path) -> dict:
    r = subprocess.run([storescu, "-v", "-aec", aet, "localhost", str(port), str(f)],
                       capture_output=True, text=True, errors="replace")
    log = r.stdout + r.stderr
    m = re.search(r"Received Store Response \(([^)]*)\)", log)
    warn = [l.strip() for l in log.splitlines() if l.startswith("W:")]
    return {"exit": r.returncode, "response": m.group(1) if m else None, "warnings": warn[:3],
            "association_accepted": "Association Accepted" in log}


def retrieve(rs: str, ds) -> dict:
    q = requests.get(rs + "/instances", params={"SOPInstanceUID": ds.SOPInstanceUID},
                     headers={"Accept": "application/dicom+json"}, timeout=60)
    found = q.status_code == 200 and bool(q.text.strip()) and len(q.json()) > 0
    out = {"qido_status": q.status_code, "qido_found": found}
    w = requests.get("%s/studies/%s/series/%s/instances/%s" % (rs, ds.StudyInstanceUID, ds.SeriesInstanceUID,
                                                              ds.SOPInstanceUID),
                     headers={"Accept": 'multipart/related; type="application/dicom"'}, timeout=120)
    out["wado_status"] = w.status_code
    if w.status_code != 200:
        return out
    ctype = w.headers.get("Content-Type", "")
    msg = message_from_bytes(("Content-Type: %s\r\n\r\n" % ctype).encode() + w.content)
    parts = [p.get_payload(decode=True) for p in msg.walk() if p.get_content_type() == "application/dicom"]
    if not parts:
        out["wado_parts"] = 0
        return out
    got = pydicom.dcmread(io.BytesIO(parts[0]), force=True)
    out["wado_parts"] = len(parts)
    sent_top = {int(e.tag) for e in ds}
    got_top = {int(e.tag) for e in got}
    changed = [int(e.tag) for e in ds if int(e.tag) in got_top and e.tag != 0x7FE00010
               and e.VR != "SQ" and got[e.tag].value != e.value]
    out["top_level_removed"] = ["%08X" % t for t in sorted(sent_top - got_top)]
    out["top_level_added"] = ["%08X" % t for t in sorted(got_top - sent_top)]
    out["top_level_changed"] = ["%08X" % t for t in sorted(changed)]
    st, gt = walk_tags(ds), walk_tags(got)
    out["colour_sent"] = [n for t, n in COLOUR_TAGS.items() if t in st]
    out["colour_retrieved"] = [n for t, n in COLOUR_TAGS.items() if t in gt]
    out["colour_intact"] = out["colour_sent"] == out["colour_retrieved"]
    out["nested_tags_lost"] = ["%08X" % t for t in sorted(st - gt) if t not in sent_top][:20]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pstate-dir", required=True)
    ap.add_argument("--series-dir", required=True)
    ap.add_argument("--storescu", required=True)
    ap.add_argument("--archives", default="orthanc,dcm4chee")
    ap.add_argument("--json", default=str(RESULTS / "rev1_archives.json"))
    a = ap.parse_args(argv)
    ps = sorted(Path(a.pstate_dir).glob("*.dcm"))
    series = sorted(Path(a.series_dir).glob("*.dcm"))
    res = {"objects": {"presentation_states": len(ps), "ct_instances": len(series)}, "archives": {}}
    for name in a.archives.split(","):
        cfg = ARCHIVES[name]
        A = {"config": {k: v for k, v in cfg.items() if k != "version_url"}}
        if cfg["version_url"]:
            try:
                A["version"] = requests.get(cfg["version_url"], timeout=10).json().get("Version")
            except Exception:
                A["version"] = None
        # the referenced series first, so a presentation state never arrives before its image
        ct = [store(a.storescu, cfg["aet"], cfg["port"], f) for f in series]
        A["ct_store"] = {"sent": len(ct), "success": sum(1 for r in ct if r["response"] == "Success"),
                         "responses": sorted({str(r["response"]) for r in ct})}
        A["presentation_states"] = {}
        for f in ps:
            tag = f.stem.split("__")[-1]
            ds = pydicom.dcmread(str(f))
            s = store(a.storescu, cfg["aet"], cfg["port"], f)
            r = retrieve(cfg["rs"], ds)
            A["presentation_states"][tag] = {"cstore": s, "dicomweb": r}
            print("%-9s %-24s C-STORE %-10s QIDO %-5s WADO %s colour %s->%s removed %s changed %s" % (
                name, tag, s["response"], r.get("qido_found"), r.get("wado_status"), r.get("colour_sent"),
                r.get("colour_retrieved"), r.get("top_level_removed"), r.get("top_level_changed")))
        A["summary"] = {
            "cstore_success": sum(1 for v in A["presentation_states"].values() if v["cstore"]["response"] == "Success"),
            "qido_found": sum(1 for v in A["presentation_states"].values() if v["dicomweb"].get("qido_found")),
            "wado_ok": sum(1 for v in A["presentation_states"].values() if v["dicomweb"].get("wado_status") == 200),
            "colour_intact": sum(1 for v in A["presentation_states"].values() if v["dicomweb"].get("colour_intact")),
            "of": len(ps)}
        print(name, "summary", A["summary"], "CT", A["ct_store"])
        res["archives"][name] = A
    Path(a.json).write_text(json.dumps(res, indent=1))
    print("wrote", a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
