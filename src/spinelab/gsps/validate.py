"""Run dciodvfy over a set of DICOM objects and aggregate its verdicts.

dciodvfy is David Clunie's IOD validator from dicom3tools. It is an independent
third party scorer, which is why we use it instead of trusting our own reading
of PS3.3. Nothing here interprets conformance itself.

Usage:
    python -m spinelab.gsps.validate <dir-or-file> [more...] [--json out.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    from ..paths import DCIODVFY
except Exception:  # importable standalone, for example from a bare checkout
    DCIODVFY = Path(os.environ.get("SPINELAB_DCIODVFY", "dciodvfy.exe"))

# dciodvfy line shapes we care about.
RE_MISSING = re.compile(
    r"^Error - Missing attribute Type (?P<type>\S+) \S+ "
    r"Element=<(?P<elem>[^>]+)> Module=<(?P<module>[^>]+)>")
RE_NOT_IN_IOD = re.compile(
    r"^Warning - Attribute is not present in standard DICOM IOD - "
    r"\((?P<tag>0x[0-9a-fA-F]{4},0x[0-9a-fA-F]{4})\) (?P<vr>\S+) (?P<name>.+?)\s*$")
RE_ERROR_OTHER = re.compile(r"^Error - (?P<msg>.+?)\s*$")
RE_WARN_OTHER = re.compile(r"^Warning - (?P<msg>.+?)\s*$")
# dciodvfy announces the IOD it matched on a line of its own, as a bare
# CamelCase token with no punctuation, for example "GrayscaleSoftcopyPresentationState"
# or simply "Segmentation". An earlier version of this pattern required the name to
# contain PresentationState, Storage, Image or IOD, which meant every SEG object was
# reported as "(unrecognised)" even though dciodvfy had recognised it perfectly well.
# Match the shape of the line instead of enumerating IOD names.
RE_IOD = re.compile(r"^(?P<iod>[A-Z][A-Za-z0-9]{3,})\s*$")


def run_one(path: Path) -> dict:
    """Validate a single file. Returns a structured record."""
    proc = subprocess.run(
        [str(DCIODVFY), str(path)],
        capture_output=True, text=True, errors="replace")
    lines = (proc.stdout + "\n" + proc.stderr).splitlines()

    rec = {
        "file": str(path),
        "iod": None,
        "missing": [],       # required attributes absent
        "not_in_iod": [],    # attributes present that the IOD does not define
        "other_errors": [],
        "other_warnings": [],
        "exit_code": proc.returncode,
    }
    for ln in lines:
        ln = ln.rstrip()
        if not ln:
            continue
        m = RE_MISSING.match(ln)
        if m:
            rec["missing"].append({
                "type": m.group("type"), "element": m.group("elem"),
                "module": m.group("module")})
            continue
        m = RE_NOT_IN_IOD.match(ln)
        if m:
            rec["not_in_iod"].append({
                "tag": m.group("tag").lower(), "vr": m.group("vr"),
                "name": m.group("name")})
            continue
        m = RE_IOD.match(ln)
        if m and rec["iod"] is None:
            rec["iod"] = m.group("iod")
            continue
        m = RE_ERROR_OTHER.match(ln)
        if m:
            rec["other_errors"].append(m.group("msg"))
            continue
        m = RE_WARN_OTHER.match(ln)
        if m:
            rec["other_warnings"].append(m.group("msg"))
    return rec


def collect(targets: list[str]) -> list[Path]:
    files: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.dcm")))
        elif p.is_file():
            files.append(p)
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("targets", nargs="+", help="files or directories")
    ap.add_argument("--pattern", default=None,
                    help="only files whose name contains this, e.g. _GSPS")
    ap.add_argument("--json", dest="out", default=None, help="write records here")
    args = ap.parse_args(argv)

    if not DCIODVFY.exists():
        print("dciodvfy not found at %s. Set SPINELAB_DCIODVFY." % DCIODVFY)
        return 2

    files = collect(args.targets)
    if args.pattern:
        files = [f for f in files if args.pattern in f.name]
    if not files:
        print("no files matched")
        return 1

    print("validating %d file(s) with %s\n" % (len(files), DCIODVFY.name))
    recs = [run_one(f) for f in files]

    miss = collections.Counter()
    noniod = collections.Counter()
    iods = collections.Counter()
    clean = 0
    for r in recs:
        iods[r["iod"] or "(unrecognised)"] += 1
        if not r["missing"] and not r["other_errors"]:
            clean += 1
        # Count FILES affected, not occurrences. A missing Type 1 inside a
        # sequence macro is reported once per item, so counting raw occurrences
        # produced impossible tallies like "68/9".
        for key in {"Type %-3s %-28s %s" % (m["type"], m["element"], m["module"])
                    for m in r["missing"]}:
            miss[key] += 1
        seen = {(n["tag"], n["name"]) for n in r["not_in_iod"]}
        for tag, name in seen:
            noniod["%s %s" % (tag, name)] += 1

    n = len(recs)
    print("=" * 84)
    print("IOD recognised as")
    print("=" * 84)
    for k, v in iods.most_common():
        print("  %-52s %d/%d" % (k, v, n))

    print("\n" + "=" * 84)
    print("ERRORS: required attributes absent  (count = files affected of %d)" % n)
    print("=" * 84)
    if not miss:
        print("  none")
    for k, v in sorted(miss.items(), key=lambda x: (-x[1], x[0])):
        print("  %-64s %d/%d" % (k, v, n))

    print("\n" + "=" * 84)
    print("OUT OF IOD: attributes present that this IOD does not define")
    print("=" * 84)
    if not noniod:
        print("  none")
    for k, v in sorted(noniod.items(), key=lambda x: (-x[1], x[0])):
        print("  %-64s %d/%d" % (k, v, n))

    other = collections.Counter()
    for r in recs:
        for m in set(r["other_errors"]):
            other["ERROR   " + m[:72]] += 1
        for m in set(r["other_warnings"]):
            if "not present in standard DICOM IOD" in m:
                continue
            other["warning " + m[:72]] += 1
    print("\n" + "=" * 84)
    print("OTHER DIAGNOSTICS")
    print("=" * 84)
    if not other:
        print("  none")
    for k, v in sorted(other.items(), key=lambda x: (-x[1], x[0])):
        print("  %-72s %d/%d" % (k, v, n))

    print("\n" + "=" * 84)
    print("files with zero errors: %d/%d" % (clean, n))
    print("=" * 84)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(
            {"validator": str(DCIODVFY), "n_files": n, "records": recs}, indent=2))
        print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
