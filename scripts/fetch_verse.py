"""Download a VerSe subset from OSF.

VerSe (Sekuboyina et al., Medical Image Analysis 73:102166, 2021) is CC BY-SA 4.0
and served anonymously from OSF. It is the only public spine set that gives all
three properties we need: named vertebral levels, the challenge organiser's own
scorer, and a published leaderboard for comparison.

Note it is CT while the model is MRI trained, so results are out of distribution
by construction. That is a stated limitation, not an accident.

OSF components:
  VerSe'19 subject based   https://osf.io/jtfa5/
  VerSe'20 MICCAI series   https://osf.io/b2wxj/
  VerSe'20 subject based   https://osf.io/4skx2/

Each subject directory holds three files we care about:
  *_ct.nii.gz            the image
  *_seg-vert_msk.nii.gz  voxel mask, integer value IS the anatomical level
  *_seg-subreg_ctd.json  per vertebra centroid landmarks

Label convention, verbatim from the OSF readme:
  1-7 C1-C7 | 8-19 T1-T12 | 20-25 L1-L6 | 26,27 sacrum,coccyx (unlabelled) | 28 T13

Usage:
  python scripts/fetch_verse.py --component 4skx2 --limit 40
  python scripts/fetch_verse.py --component 4skx2 --limit 0     # everything
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

OSF_API = "https://api.osf.io/v2"
UA = {"User-Agent": "spinelab-verse-fetch/0.1"}
WANT_SUFFIX = ("_ct.nii.gz", "_seg-vert_msk.nii.gz", "_seg-subreg_ctd.json")


def get_json(url: str, tries: int = 6) -> dict:
    """OSF rate limits anonymous callers. A 429 needs a long, escalating wait,
    not the short retry that works for transient network errors."""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                out = json.loads(r.read().decode())
            time.sleep(0.35)   # be a polite client, the walk is hundreds of calls
            return out
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                wait = 30 * (i + 1)
                print("   HTTP 429 rate limited, waiting %ds" % wait)
                time.sleep(wait)
                continue
            raise
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))
            print("   retry %d after %s" % (i + 1, type(e).__name__))
    raise RuntimeError("unreachable")


def walk(node_url: str, depth: int = 0, max_depth: int = 4) -> list[dict]:
    """Depth first walk of an OSF storage tree, returning file entries."""
    out: list[dict] = []
    url = node_url
    while url:
        page = get_json(url)
        for item in page.get("data", []):
            attrs = item.get("attributes", {})
            kind = attrs.get("kind")
            name = attrs.get("name")
            if kind == "file":
                out.append({
                    "name": name,
                    "size": attrs.get("size") or 0,
                    "path": attrs.get("materialized_path") or name,
                    "download": item.get("links", {}).get("download"),
                })
            elif kind == "folder" and depth < max_depth:
                sub = item.get("relationships", {}).get("files", {}).get(
                    "links", {}).get("related", {}).get("href")
                if sub:
                    out.extend(walk(sub, depth + 1, max_depth))
        url = page.get("links", {}).get("next")
    return out


def download(url: str, dest: Path, expect: int = 0) -> bool:
    if dest.exists() and (expect == 0 or dest.stat().st_size == expect):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    tmp.replace(dest)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--component", default="4skx2",
                    help="OSF component id: 4skx2, b2wxj, jtfa5, 923ap")
    ap.add_argument("--out", default=None, help="destination root")
    ap.add_argument("--limit", type=int, default=40,
                    help="max subjects, 0 for all")
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--rewalk", action="store_true",
                    help="force a fresh OSF tree walk instead of reusing manifest.json")
    args = ap.parse_args(argv)

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from spinelab.paths import DATASETS

    out = Path(args.out) if args.out else DATASETS / ("verse_" + args.component)
    out.mkdir(parents=True, exist_ok=True)

    manifest = out / "manifest.json"

    # Reuse a previous walk when possible. Walking the tree costs hundreds of API
    # calls and OSF answers with HTTP 429 if you do it twice in quick succession,
    # which is exactly how the first attempt died.
    if manifest.exists() and not args.rewalk:
        cached = json.loads(manifest.read_text())
        # A manifest written by an earlier --limit run holds only that subset. Reusing
        # it for --limit 0 silently downloads the subset and reports success, which is
        # exactly what happened on 2026-07-30. Refuse to trust a partial manifest when
        # the caller asked for everything.
        if cached.get("files") and not cached.get("full_walk") and args.limit == 0:
            print("cached manifest at %s is NOT a full walk (%d subjects) and you asked"
                  % (manifest, len(cached.get("subjects", []))))
            print("for all subjects. Re-walking rather than silently returning a subset.")
        elif cached.get("files"):
            print("reusing cached manifest: %s" % manifest)
            print("title     : %s" % cached.get("title"))
            print("full walk : %s" % bool(cached.get("full_walk")))
            todo = cached["files"]
            keys = cached.get("subjects", [])
            if args.limit:
                keys = keys[:args.limit]
                todo = [f for f in todo if f["name"].split("_")[0] in set(keys)]
            total = sum(f["size"] for f in todo)
            print("selected %d subjects, %d files, %.2f GB" % (
                len(keys), len(todo), total / (1 << 30)))
            if args.list_only:
                return 0
            return _fetch(todo, out, total)

    print("component : %s" % args.component)
    node = get_json("%s/nodes/%s/" % (OSF_API, args.component))
    attrs = node["data"]["attributes"]
    print("title     : %s" % attrs.get("title"))
    print("public    : %s" % attrs.get("public"))
    if not attrs.get("public"):
        print("component is not public, aborting")
        return 1

    prov = get_json("%s/nodes/%s/files/" % (OSF_API, args.component))
    root = None
    for p in prov.get("data", []):
        rel = p.get("relationships", {}).get("files", {}).get(
            "links", {}).get("related", {}).get("href")
        if rel:
            root = rel
            break
    if not root:
        print("no storage provider found")
        return 1

    print("walking storage tree, this takes a minute...")
    files = walk(root)
    print("total files listed: %d" % len(files))

    wanted = [f for f in files if f["name"].endswith(WANT_SUFFIX)]
    print("files matching %s: %d" % (WANT_SUFFIX, len(wanted)))

    # group by subject so we only take complete triples
    subjects: dict[str, list[dict]] = {}
    for f in wanted:
        sub = f["name"].split("_")[0]
        subjects.setdefault(sub, []).append(f)
    complete = {k: v for k, v in subjects.items()
                if any(x["name"].endswith("_ct.nii.gz") for x in v)
                and any(x["name"].endswith("_seg-vert_msk.nii.gz") for x in v)}
    print("subjects with image and mask: %d of %d" % (len(complete), len(subjects)))

    keys = sorted(complete)
    if args.limit:
        keys = keys[:args.limit]
    todo = [f for k in keys for f in complete[k]]
    total = sum(f["size"] for f in todo)
    print("selected %d subjects, %d files, %.2f GB" % (
        len(keys), len(todo), total / (1 << 30)))

    # Persist the FULL walk so a later run with a different --limit can reuse it.
    manifest.write_text(json.dumps(
        {"component": args.component, "title": attrs.get("title"),
         "license": "CC BY-SA 4.0", "full_walk": True,
         "n_subjects_available": len(complete),
         "subjects": sorted(complete),
         "files": [f for k in sorted(complete) for f in complete[k]]}, indent=2))
    print("wrote %s (full walk, %d subjects available)" % (manifest, len(complete)))

    if args.list_only:
        return 0
    return _fetch(todo, out, total)


def _fetch(todo: list[dict], out: Path, total: int) -> int:
    got = skipped = failed = 0
    done_bytes = 0
    for i, f in enumerate(todo, 1):
        dest = out / f["name"]
        try:
            if download(f["download"], dest, f["size"]):
                got += 1
            else:
                skipped += 1
            done_bytes += f["size"]
        except Exception as e:
            failed += 1
            print("  FAIL %s: %s: %s" % (f["name"], type(e).__name__, e))
            continue
        if i % 10 == 0 or i == len(todo):
            print("  %d/%d  new=%d cached=%d failed=%d  %.2f/%.2f GB" % (
                i, len(todo), got, skipped, failed, done_bytes / (1 << 30),
                total / (1 << 30)))

    print("\ndone. new=%d cached=%d failed=%d into %s" % (got, skipped, failed, out))
    return 1 if failed and not got else 0


if __name__ == "__main__":
    sys.exit(main())
