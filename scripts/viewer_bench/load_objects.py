"""Push DICOM objects into the bench Orthanc and report accept or reject.

This measures the first and hardest of the four outcome levels in SCORING.md
without a human looking at a screen: does the archive take the object at all.
An archive or viewer refusing a Presentation State is a real, citable result, and
it is the only level of the matrix that is fully automatable.

What it does per file:

  1. POST the raw bytes to <orthanc>/instances with Content-Type application/dicom.
  2. Classify the reply into ACCEPTED, DUPLICATE, REJECTED or ERROR.
  3. For anything Orthanc kept, read it back over the REST API to confirm the
     object is really indexed and not merely acknowledged, and record the parent
     study and series so a human can find it in a viewer.
  4. Print per viewer deep links for the human rendering pass, which this script
     does NOT perform.

Usage:
    python load_objects.py <dir-or-file> [more...] \
        [--url http://localhost:8142] [--pattern _GSPS] [--json out.json]

Exit code is 0 if every object was accepted or already stored, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

try:
    import pydicom
except ImportError:  # pydicom only labels the table, it is not required
    pydicom = None

DEFAULT_URL = "http://localhost:8142"
OHIF_STANDALONE = "http://localhost:3110"

# Outcome vocabulary. Mirrors SCORING.md level 3 versus levels 0 to 2.
ACCEPTED = "ACCEPTED"
DUPLICATE = "DUPLICATE"
REJECTED = "REJECTED"
ERROR = "ERROR"

# The three colour routes under test, see results/gsps_variants.md. Checked on
# readback because an archive silently dropping an out-of-IOD attribute would
# otherwise be mistaken for a viewer that ignores it.
COLOUR_TAGS = {
    "0070,0241": "text colour, NOT in the GSPS IOD",
    "0070,0251": "line colour, in the IOD",
    "0070,0401": "layer colour, in the IOD",
}


def local_facts(path: Path) -> dict:
    """Read the few tags that make the report legible. Never fatal."""
    out = {"sop_class_uid": None, "sop_class": None, "modality": None,
           "study_uid": None, "series_uid": None, "sop_instance_uid": None,
           "read_error": None}
    if pydicom is None:
        out["read_error"] = "pydicom not installed"
        return out
    try:
        ds = pydicom.dcmread(str(path), stop_before_pixels=True, force=True)
        uid = ds.get("SOPClassUID")
        out["sop_class_uid"] = str(uid) if uid else None
        out["sop_class"] = getattr(uid, "name", None)
        out["modality"] = str(ds.get("Modality") or "") or None
        out["study_uid"] = str(ds.get("StudyInstanceUID") or "") or None
        out["series_uid"] = str(ds.get("SeriesInstanceUID") or "") or None
        out["sop_instance_uid"] = str(ds.get("SOPInstanceUID") or "") or None
    except Exception as exc:  # a file we cannot parse is still worth POSTing
        out["read_error"] = "%s: %s" % (type(exc).__name__, exc)
    return out


def post_one(session: requests.Session, base: str, path: Path,
             timeout: float) -> dict:
    """POST one file. Returns the raw facts, no interpretation beyond verdict."""
    rec = {"file": str(path), "name": path.name,
           "bytes": path.stat().st_size, "verdict": None,
           "http_status": None, "orthanc_status": None,
           "orthanc_id": None, "parent_study": None, "parent_series": None,
           "message": None, "raw_response": None, "verified": None}
    rec.update(local_facts(path))

    body = path.read_bytes()
    try:
        resp = session.post(base + "/instances", data=body,
                            headers={"Content-Type": "application/dicom"},
                            timeout=timeout)
    except requests.RequestException as exc:
        rec["verdict"] = ERROR
        rec["message"] = "transport: %s: %s" % (type(exc).__name__, exc)
        return rec

    rec["http_status"] = resp.status_code
    text = resp.text
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    rec["raw_response"] = text[:2000]

    if payload is None:
        rec["verdict"] = REJECTED if resp.status_code >= 400 else ERROR
        rec["message"] = "non JSON reply: " + text[:300].replace("\n", " ")
        return rec

    if resp.status_code >= 400:
        rec["verdict"] = REJECTED
        # Orthanc error bodies carry Message, plus Details when it has more.
        parts = [str(payload.get(k)) for k in ("Message", "Details")
                 if payload.get(k)]
        rec["message"] = " | ".join(parts) or json.dumps(payload)[:300]
        return rec

    rec["orthanc_status"] = payload.get("Status")
    rec["orthanc_id"] = payload.get("ID")
    rec["parent_study"] = payload.get("ParentStudy")
    rec["parent_series"] = payload.get("ParentSeries")
    if rec["orthanc_status"] == "AlreadyStored":
        rec["verdict"] = DUPLICATE
    elif rec["orthanc_status"] == "Success":
        rec["verdict"] = ACCEPTED
    else:
        rec["verdict"] = ERROR
        rec["message"] = "unexpected Status %r" % (rec["orthanc_status"],)
    return rec


def _tags_present(node, wanted: set, found: set) -> None:
    """Recursively note which of `wanted` tag keys occur anywhere, sequences
    included. Orthanc's ?short tag dump nests sequence items as lists of dicts."""
    if isinstance(node, dict):
        for key, val in node.items():
            if key in wanted:
                found.add(key)
            _tags_present(val, wanted, found)
    elif isinstance(node, list):
        for item in node:
            _tags_present(item, wanted, found)


def verify_one(session: requests.Session, base: str, rec: dict,
               timeout: float) -> None:
    """Read the stored object back. Acknowledged is not the same as indexed."""
    oid = rec.get("orthanc_id")
    if not oid:
        return
    try:
        r = session.get("%s/instances/%s" % (base, oid), timeout=timeout)
        if r.status_code != 200:
            rec["verified"] = "readback HTTP %d" % r.status_code
            return
        meta = r.json()
        t = session.get("%s/instances/%s/tags?short" % (base, oid),
                        timeout=timeout)
        sop_class = None
        if t.status_code == 200:
            tags = t.json()
            sop_class = tags.get("0008,0016")
            found: set = set()
            _tags_present(tags, set(COLOUR_TAGS), found)
            rec["colour_tags_after_readback"] = sorted(found)
        rec["verified"] = "indexed"
        rec["stored_sop_class_uid"] = sop_class
        rec["stored_index_in_series"] = meta.get("IndexInSeries")
        if (rec.get("sop_class_uid") and sop_class
                and sop_class != rec["sop_class_uid"]):
            rec["verified"] = "SOP class changed on ingest: %s" % sop_class
    except requests.RequestException as exc:
        rec["verified"] = "readback failed: %s" % exc


def collect(targets: list[str], pattern: str | None) -> list[Path]:
    files: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            files.extend(sorted(x for x in p.rglob("*") if x.is_file()))
        elif p.is_file():
            files.append(p)
        else:
            print("skipping, not found: %s" % t)
    if pattern:
        files = [f for f in files if pattern in f.name]
    return files


def viewer_links(base: str, study_uids: list[str]) -> list[str]:
    """Deep links for the human rendering pass. Not exercised by this script."""
    out = []
    for uid in study_uids:
        out.append("study %s" % uid)
        out.append("  stone      %s/stone-webviewer/index.html?study=%s"
                   % (base, uid))
        out.append("  ohif plug  %s/ohif/viewer?StudyInstanceUIDs=%s"
                   % (base, uid))
        out.append("  ohif alone %s/viewer?StudyInstanceUIDs=%s"
                   % (OHIF_STANDALONE, uid))
        out.append("  volview    %s/volview/index.html" % base)
        out.append("  explorer   %s/ui/app/" % base)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="+", help="files or directories")
    ap.add_argument("--url", default=DEFAULT_URL,
                    help="Orthanc base URL, default %s" % DEFAULT_URL)
    ap.add_argument("--pattern", default=None,
                    help="only files whose name contains this, e.g. _GSPS")
    ap.add_argument("--user", default=None)
    ap.add_argument("--password", default=None)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--json", dest="out", default=None,
                    help="write the full records here")
    ap.add_argument("--no-links", action="store_true",
                    help="suppress the per viewer deep link block")
    args = ap.parse_args(argv)

    base = args.url.rstrip("/")
    session = requests.Session()
    if args.user:
        session.auth = (args.user, args.password or "")

    try:
        sysinfo = session.get(base + "/system", timeout=10).json()
    except Exception as exc:
        print("cannot reach Orthanc at %s: %s" % (base, exc))
        print("bring the bench up first:  docker compose up -d")
        return 2
    print("Orthanc %s, API %s, name %r at %s"
          % (sysinfo.get("Version"), sysinfo.get("ApiVersion"),
             sysinfo.get("Name"), base))

    files = collect(args.targets, args.pattern)
    if not files:
        print("no files matched")
        return 1
    print("pushing %d object(s)\n" % len(files))

    recs = []
    for f in files:
        rec = post_one(session, base, f, args.timeout)
        if rec["verdict"] in (ACCEPTED, DUPLICATE):
            verify_one(session, base, rec, args.timeout)
        recs.append(rec)

    short = {"0070,0241": "text", "0070,0251": "line", "0070,0401": "layer"}
    width = max(len(r["name"]) for r in recs)
    header = ("%-*s  %-9s  %-4s  %-8s  %-15s  %s"
              % (width, "object", "verdict", "http", "readback",
                 "colour tags", "orthanc id or error"))
    print("=" * len(header))
    print(header)
    print("=" * len(header))
    for r in recs:
        detail = r.get("orthanc_id") or ""
        if r["verdict"] in (REJECTED, ERROR):
            detail = (r.get("message") or "")[:60]
        colours = r.get("colour_tags_after_readback")
        ctxt = ",".join(short.get(c, c) for c in colours) if colours else "-"
        print("%-*s  %-9s  %-4s  %-8s  %-15s  %s"
              % (width, r["name"], r["verdict"], r["http_status"],
                 (r.get("verified") or "-")[:8], ctxt, detail))

    counts = {}
    for r in recs:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print("\n" + ", ".join("%s %d" % (k, counts[k]) for k in sorted(counts)))

    studies = []
    for r in recs:
        u = r.get("study_uid")
        if u and u not in studies:
            studies.append(u)
    if studies and not args.no_links:
        print("\n" + "=" * 76)
        print("DEEP LINKS for the human rendering pass, NOT tested by this script")
        print("=" * 76)
        for line in viewer_links(base, studies):
            print(line)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({
            "orthanc": {"url": base, "version": sysinfo.get("Version"),
                        "api_version": sysinfo.get("ApiVersion")},
            "n_files": len(recs), "counts": counts, "records": recs,
        }, indent=2))
        print("\nwrote %s" % args.out)

    bad = counts.get(REJECTED, 0) + counts.get(ERROR, 0)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
