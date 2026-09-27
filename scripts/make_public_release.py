"""Build the public code release that the paper's Data availability statement cites.

This is NOT `git push` of the working repository. Two things in the working tree
must not be published, and rewriting HEAD would not remove them from history:

  - `results/gsps_conformance_baseline.json` and `results/gsps_variants_validation.json`
    are raw per-attribute validator dumps over the 38 CLINICAL objects. The project
    already refuses to hand these to an external reviewer, so they cannot go public
    either. Their .md summaries carry the same counts and do ship.
  - `ANON_PAT_XXXX` / `pat_XXXX` is the deployed anonymiser's own pseudonym for one
    patient. It is a code in the operator's system rather than a de-identification,
    and it appears inside quoted validator output that IS part of a finding. The
    quote is kept, the code is not.

Also excluded: the SPIE-era working drafts under `docs/spie2027/`, which are dead
with the venue and name individuals in internal correspondence, and the scratch
files. Submission-planning documents, venue-specific build scripts and
correspondence with editors are not part of the harness and are not published.

Scanned before it is written: a scan that runs over the OUTPUT, with patterns
written separately from the redactor, so a redactor bug cannot pass its own check.

Usage:  python scripts/make_public_release.py [--out DIR]
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

EXCLUDE_EXACT = {
    "results/gsps_conformance_baseline.json",
    "results/gsps_variants_validation.json",
    ".scratch_intro_section.md",
}
EXCLUDE_PREFIX = ("docs/spie2027/", ".scratch/")

# Applied to text content on the way out.
SUBS = [
    # the operator's own pseudonym for one patient, kept legible as a shape
    (re.compile(r"ANON[_-]?PAT[_-]?\d+", re.I), "ANON_PAT_XXXX"),
    (re.compile(r"\bpat[_-]\d{3,}\b", re.I), "pat_XXXX"),
    # individuals named in an authorship-exclusion rationale
    (re.compile(r"two colleagues at the operator"),
     "two colleagues at the operator"),
    (re.compile(r"[name withheld]|[name withheld]"), "[name withheld]"),
]
PRIVATE_ROOTS = [
    r"<path>",
    r"<path>",
    r"<path>",
    r"<path>",
    r"<path>",
]

# Written independently of SUBS, on purpose.
LEAK = [
    ("cohort pseudonym", re.compile(r"(?:ANON.?PAT.?|pat[_-])\d{3,}", re.I)),
    ("named individual", re.compile(r"[name withheld]|[name withheld]", re.I)),
    ("private drive path", re.compile(r"[A-Za-z]:[\\/]{1,2}Radiology", re.I)),
    ("non-standard UID", re.compile(
        r"(?<![\d.])(?!1\.2\.840\.10008|1\.2\.826\.0\.1\.3680043|1\.2\.276\.0\.16)"
        r"\d+(?:\.\d+){4,}(?![\d.])")),
]

TEXT_EXT = {".py", ".md", ".txt", ".toml", ".yml", ".yaml", ".json", ".cfg",
            ".ps1", ".lock", ".gitignore", ""}

LICENSE = """MIT License

Copyright (c) 2026 Digvijay Patil

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

# Kept out of LICENSE: GitHub's licence detector reads any trailing prose as a
# modification and labels the repository "Other" instead of MIT.
NOTICE = """Third-party code
================

The VerSe evaluation code under `src/spinelab/eval/` is vendored from
github.com/anjany/verse and carries its own MIT licence, reproduced alongside
it. It is used byte-identically rather than reimplemented, so that vertebral
identification in the accompanying article is scored by the benchmark
organisers' own code and not by ours.
"""

# Zenodo takes its metadata from the GitHub account unless the repository says
# otherwise, so the first archived version was credited to the account handle
# rather than to the author. These two files fix that for every future release.
ZENODO_JSON = """{
  "title": "spine-gsps: evaluation harness for a deployed DICOM spine-labelling service",
  "description": "Evaluation harness accompanying the article \\"Separating conformance from trustworthiness: an end-to-end audit, and five checks, for an AI result delivered into a clinical archive\\". Every number in the article has a row in docs/CLAIMS.md recording its status, the command that produces it, and its source, including twenty-one retired claims.",
  "license": "mit",
  "upload_type": "software",
  "creators": [
    {
      "name": "Patil, Digvijay",
      "affiliation": "University at Buffalo School of Management, Buffalo, NY, USA",
      "orcid": "0009-0003-6878-1712"
    }
  ],
  "keywords": [
    "DICOM", "health information interoperability", "artificial intelligence governance",
    "grayscale softcopy presentation state", "conformance", "quality assurance"
  ]
}
"""

CITATION_CFF = """cff-version: 1.2.0
message: "If you use this software, please cite the article it accompanies."
title: "spine-gsps: evaluation harness for a deployed DICOM spine-labelling service"
version: 1.0.2
license: MIT
authors:
  - family-names: Patil
    given-names: Digvijay
    orcid: "https://orcid.org/0009-0003-6878-1712"
    affiliation: "University at Buffalo School of Management, Buffalo, NY, USA"
preferred-citation:
  type: article
  title: "Separating conformance from trustworthiness: an end-to-end audit, and five checks, for an AI result delivered into a clinical archive"
  authors:
    - family-names: Patil
      given-names: Digvijay
      orcid: "https://orcid.org/0009-0003-6878-1712"
  year: 2026
"""

README = """# spine-gsps

Evaluation harness for *"Separating conformance from trustworthiness: an end-to-end audit, and five checks, for an AI result delivered into a clinical archive."*

Every number in the article has a row in [`docs/CLAIMS.md`](docs/CLAIMS.md)
giving its status, the command that produces it, and its source file. That
ledger also records **twenty-one claims that were retired**, several of them
asserted confidently before measurement contradicted them. It is the honest
guide to how this analysis fails.

## What this is

Three measurements on one deployed DICOM service:

1. **Conformance and delivery.** All 38 presentation states the service emitted
   fail two independent validators and are refused by the reference renderer,
   while the archive indexes every one, DICOMweb returns them intact, and the
   target viewer displayed them. Nothing in the delivery path detected it.
2. **A nine-arm ablation of the quality flag.** Only the rule choosing which
   per-region sigmoid channel to read varies. All nine land between 0.427 and
   0.581 AUC. The rule that actually shipped is the **worst of the nine**, and
   its case-clustered interval contains 0.5.
3. **The geometric consistency check.** Specified as leave-one-out, implemented
   in sample on its normal path, so the spline absorbs the displacement it
   exists to detect.

## Running it

```
python -m spinelab.paths                        # check every store resolves
python -m pytest tests -q                       # 267 tests, the factual constraints
python -m spinelab.confidence.channels          # channel table vs the checkpoints
python -m spinelab.gsps.validate <dir>          # dciodvfy over a DICOM directory
python -m spinelab.eval.verse --self-check      # the scorer against known answers
python -m spinelab.outliers.spline --validate   # the synthetic evaluation
python scripts/e1_ablation.py --run-dir <run>   # ablation, ceilings, null
python scripts/make_figures.py                  # every figure, from results/*.json
```

Pins are frozen in `env/requirements.lock`. `nnunetv2==2.4.2` must be installed
explicitly: current `totalspineseg` no longer depends on it, and without it the
checkpoints will not deserialise.

**No metric in the article is computed by code written for the purpose of
computing that metric.** Conformance is scored by `dciodvfy` (dicom3tools).
Vertebral identification is scored by the VerSe organisers' own
`eval_utilities.py`, vendored rather than reimplemented.

## What is not here, and why

- **The clinical material.** The 38 delivered objects and the retrospective
  cohort they came from derive from patient examinations. The written permission
  obtained covers research use, publication of these findings and release of this
  code, not redistribution of patient data. The raw per-attribute validator dumps
  over those objects are withheld for the same reason; the `.md` write-ups in
  `results/` carry the same counts.
- **The model checkpoints.** They are the openly released upstream TotalSpineSeg
  weights, obtainable from release r20241005 at
  github.com/neuropoly/totalspineseg. They were not trained here.
- **The public datasets.** VerSe 2019 and 2020, 202 cases, by anonymous download
  from OSF (osf.io/nqjyw, osf.io/t98fz) under CC BY-SA 4.0.

## Licence

MIT, see `LICENSE`. The vendored VerSe evaluation code carries its own.
"""


def _safe_output_location(out: Path) -> bool:
    """Refuse to build inside another repository's working tree.

    The first version defaulted the output next to the harness, which put it
    inside the PRIVATE baseline repository. An earlier run then deleted the
    release's own `.git`, so the next `git add -A` walked up the tree and
    committed 105 files of release output into the private repo. Nothing was
    lost, but the fix is to make the layout incapable of it rather than to
    remember. Nothing about a public release should live inside a private tree.
    """
    if (out / ".git").is_dir():
        return True                     # its own repository, fine
    for parent in [out] + list(out.parents):
        if (parent / ".git").exists() and parent != out:
            print("REFUSING: %s sits inside the git working tree at %s.\n"
                  "A public release must not be built inside another repository:\n"
                  "a stray `git add -A` there commits it to the wrong history.\n"
                  "Pass --out with a path outside it." % (out, parent))
            return False
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(REPO.parent.parent / "spine-gsps-public"))
    a = ap.parse_args(argv)
    if not _safe_output_location(Path(a.out)):
        return 1
    # Clear the contents but keep `.git`, so re-running updates the release in
    # place rather than orphaning the repository that is about to be pushed.
    # git objects are read-only on Windows, so rmtree over them fails WinError 5.
    out = Path(a.out)
    had_git = (out / ".git").is_dir()
    out.mkdir(parents=True, exist_ok=True)
    # dict.fromkeys, not list concatenation: on Windows glob("*") already
    # matches dotfiles, so adding glob(".*") deletes .gitignore twice.
    for child in dict.fromkeys(list(out.glob("*")) + list(out.glob(".*"))):
        if child.name == ".git":
            continue
        shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink()
    # The release repository has now been destroyed twice while this script was
    # being written, and both times it was noticed only when a later push failed
    # with "not a git repository". Once the history is gone the next `git init`
    # silently starts an unrelated repository, so fail here instead.
    if had_git and not (out / ".git").is_dir():
        print("ABORTING: %s/.git existed before this build and does not now.\n"
              "The release history has been destroyed. Restore it with:\n"
              "  cd %s && git init -b main && git remote add origin <url>\n"
              "  git fetch origin && git reset --soft origin/main && git add -A"
              % (out, out))
        return 1

    tracked = subprocess.run(["git", "ls-files"], cwd=str(REPO),
                             capture_output=True, text=True).stdout.split()
    kept, skipped, redactions = [], [], 0

    for rel in tracked:
        if rel in EXCLUDE_EXACT or rel.startswith(EXCLUDE_PREFIX):
            skipped.append(rel)
            continue
        src, dst = REPO / rel, out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix.lower() in TEXT_EXT:
            t = src.read_text(encoding="utf-8")
            for root in PRIVATE_ROOTS:
                for form in (root, root.replace("\\", "/"), root.replace("\\", "\\\\")):
                    if form in t:
                        redactions += t.count(form)
                        t = t.replace(form, "<path>")
            for rx, rep in SUBS:
                t, k = rx.subn(rep, t)
                redactions += k
            dst.write_text(t, encoding="utf-8")
        else:
            shutil.copy2(src, dst)
        kept.append(rel)

    # figures are build products, not tracked, but the article cites them
    figs = REPO / "results" / "figures"
    if figs.exists():
        shutil.copytree(figs, out / "results" / "figures", dirs_exist_ok=True)
        kept += ["results/figures/" + p.name for p in sorted(figs.iterdir())]

    (out / "LICENSE").write_text(LICENSE, encoding="utf-8")
    (out / "NOTICE").write_text(NOTICE, encoding="utf-8")
    (out / ".zenodo.json").write_text(ZENODO_JSON, encoding="utf-8")
    (out / "CITATION.cff").write_text(CITATION_CFF, encoding="utf-8")
    (out / "README.md").write_text(README, encoding="utf-8")

    print("  kept    %d files" % len(kept))
    print("  skipped %d:" % len(skipped))
    for s in sorted(skipped):
        print("            %s" % s)
    print("  %d redactions applied" % redactions)

    # --- scan the OUTPUT, with patterns written apart from the redactor ----
    bad = []
    for p in sorted(out.rglob("*")):
        if not p.is_file() or p.suffix.lower() in (".png", ".pdf"):
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for name, rx in LEAK:
            for m in rx.finditer(t):
                bad.append("%s :: %s :: %s" % (p.relative_to(out), name, m.group(0)[:48]))
    if bad:
        print("\n  SCAN FAILED, %d finding(s), release NOT safe:" % len(bad))
        for b in bad[:25]:
            print("    " + b)
        return 1
    print("\n  independent scan passed: no pseudonym, no named individual,")
    print("  no private path, no non-standard UID")
    print("\n  %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
