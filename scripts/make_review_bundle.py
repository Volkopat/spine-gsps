"""Assemble the adversarial review bundle, redacting on the way out.

The reviewer is external. The clinical cohort is aycan's and is not ours to distribute,
so nothing that could relink a study to a patient may leave this machine. Three things
in the results tree would:

  - a real StudyInstanceUID from a clinical study, which under HIPAA Safe Harbor is an
    identifier in its own right,
  - the `pat_NNNN` folder pseudonyms, which are a code in aycan's system rather than a
    de-identification,
  - absolute paths that name the private tree.

Standard DICOM UIDs under 1.2.840.10008 are constants, not identifiers, and are kept.

Raw validator JSON derived from the 38 clinical objects is excluded outright rather
than redacted: it is a per-attribute dump over a clinical dataset, and confidently
sanitising 400 KB of it is a worse bet than shipping the .md summary that carries the
same numbers. The exclusion is recorded in the manifest so the reviewer knows it exists
and can ask for it through aycan.

Usage:  python scripts/make_review_bundle.py [--out DIR]
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# --- what goes in, in the order the reviewer should read it -------------------
DOCS = [
    # The IJMI package is the live submission and goes first. The SPIE artefacts are
    # retained as background only: that venue is out, see docs/TARGET.md.
    ("01_SUBMISSION_ijmi.md", "docs/ijmi/submission.md"),
    ("02_claims_ledger.md", "docs/CLAIMS.md"),
    ("03_READ_FIRST_review_packet.md", "docs/REVIEW_PACKET.md"),
    ("04_venue_decision_and_date.md", "docs/TARGET.md"),
    ("05_ijmi_requirements.md", "docs/ijmi_requirements.md"),
    ("06_ai_disclosure.md", "docs/AI_DISCLOSURE.md"),
    ("07_background_manuscript_superseded.md", "docs/manuscript.md"),
]

# Raw validator output over the 38 CLINICAL objects. Not redacted, not shipped.
EXCLUDE_JSON = {
    "gsps_conformance_baseline.json":
        "per-attribute validator dump over the 38 clinical GSPS objects",
    "gsps_variants_validation.json":
        "per-attribute validator dump over clinical-derived colour-route variants",
}

# --- redaction ----------------------------------------------------------------
STANDARD_UID = re.compile(r"^1\.2\.840\.10008\.")
UID = re.compile(r"\b\d+(?:\.\d+){4,}\b")

# Case insensitive, and covers the ANON_PAT_XXXX form that appears as a PatientName
# value in the deployed objects. A first version matched only lowercase `pat_XXXX` with
# word boundaries and let every ANON_PAT_XXXX through, which the self check missed
# because it used the same regex. It now uses a different one.
PAT = re.compile(r"\b(?:ANON[_-]?)?pat[_-](\d+)\b", re.I)

# Literal roots first. A general Windows-path regex either stops at the space in
# "Spine Labeling" and leaks the tail, or swallows the rest of the line. Naming the
# roots is exact, and leaves the readable relative part intact for the reviewer.
PRIVATE_ROOTS = [
    r"<path>",
    r"<path>",
    r"<path>",
    r"<path>",
    r"<path>",
]
ABS = re.compile(r"[A-Za-z]:\\+(?:[^\s\"'`|\\]+\\+)*[^\s\"'`|\\]*", re.I)
PRIVATE_HINT = re.compile(r"Spine Labeling|test_api|refined_gsps|_TRASH|_spine_extract",
                          re.I)
# what the self check refuses to let out, deliberately written independently
LEAK = [
    # (?<![\d.]) matters: without it the engine re-enters a standard UID one character
    # in, so 1.2.840.10008.5.1.4.1.1.11.1 reports its own tail as a leak.
    ("clinical UID",
     re.compile(r"(?<![\d.])(?!1\.2\.840\.10008)\d+(?:\.\d+){4,}(?![\d.])")),
    ("cohort pseudonym", re.compile(r"pat[_-]?\d{3,}", re.I)),
    ("local drive path", re.compile(r"[A-Za-z]:[\\/]+Radiology", re.I)),
]


class Redactor:
    """Stable pseudonyms, so the same UID reads as the same object across files."""

    def __init__(self):
        self.uids: dict[str, str] = {}
        self.pats: dict[str, str] = {}
        self.counts: Counter = Counter()

    def _uid(self, m):
        u = m.group(0)
        if STANDARD_UID.match(u):
            return u                      # a DICOM constant, not an identifier
        if u not in self.uids:
            self.uids[u] = "<clinical-uid-%02d>" % (len(self.uids) + 1)
        self.counts["StudyInstanceUID or similar"] += 1
        return self.uids[u]

    def _pat(self, m):
        k = m.group(1)
        if k not in self.pats:
            self.pats[k] = "<case-%02d>" % (len(self.pats) + 1)
        self.counts["pat_NNNN cohort pseudonym"] += 1
        return self.pats[k]

    def _abs(self, m):
        p = m.group(0)
        if not PRIVATE_HINT.search(p):
            return p                      # a public or tooling path, keep it
        self.counts["absolute path into the private tree"] += 1
        tail = p.replace("\\", "/").rstrip("/").split("/")[-1]
        return "<private>/" + tail

    def apply(self, text: str) -> str:
        for root in PRIVATE_ROOTS:            # longest first, see the list order
            for form in (root, root.replace("\\", "/"), root.replace("\\", "\\\\")):
                if form in text:
                    self.counts["absolute path into the private tree"] += \
                        text.count(form)
                    text = text.replace(form, "<private>")
        text = ABS.sub(self._abs, text)
        text = UID.sub(self._uid, text)
        return PAT.sub(self._pat, text)


def _field_counts():
    """Word and character counts for the three hard-limited SPIE fields.

    Hardcoded in an earlier version as 298/126/758 while the actual fields were
    299/147/763. All three were inside their limits, so nothing would have been
    rejected, but a manifest that misreports numbers a reviewer can check in ten
    seconds is worse than one that omits them.
    """
    p = REPO / "docs" / "spie2027" / "SUBMISSION.md"
    if not p.exists():
        return (0, 0, 0)
    t = p.read_text(encoding="utf-8")

    def blk(a, b):
        i = t.index(a)
        j = t.index(b, i)
        return "\n".join(l.lstrip("> ").rstrip()
                          for l in t[i + len(a):j].splitlines()
                          if l.strip().startswith(">")).replace("**", "")

    a = len(re.findall(r"\S+",
                       blk("## 3. Abstract for technical review, 200 to 300 words",
                           "## 4. Summary for the program")))
    s = len(re.findall(r"\S+",
                       blk("## 4. Summary for the program, 50 to 150 words",
                           "## 5. Speaker biography")))
    b = len(blk("## 5. Speaker biography, 1000 characters maximum",
                "## 6. Disclosure"))
    return (a, s, b)


def _ijmi_counts():
    """Body and abstract word counts for the submission, measured not asserted.

    Same lesson as _field_counts above, one venue later. IJMI's body limit is 3000
    words and its abstract limit is 300, both confirmed on the live guide for
    authors on 2026-07-31. Tables are excluded from the body count by Elsevier
    convention, so table rows are dropped before counting; the structured-abstract
    headings are dropped for the same reason.
    """
    p = REPO / "docs" / "ijmi" / "submission.md"
    if not p.exists():
        return (0, 0)
    t = p.read_text(encoding="utf-8")

    def words(s):
        s = re.sub(r"^\|.*$", "", s, flags=re.M)
        return len(re.findall(r"\S+", re.sub(r"\*\*|\*|`|#", "", s)))

    body = words(t[t.index("## 1. Introduction"):
                   t.index("## Declaration of competing interest")])
    # Two defensible abstract counts, and reporting only one is how the manifest
    # and the review packet came to disagree: 291 excludes the bold structured
    # headings, 296 includes them. Report both and test the larger.
    m = re.search(r"## Abstract\n(.*?)\n## ", t, re.S)
    bare = words(re.sub(r"\*\*.*?\*\*", "", m.group(1))) if m else 0
    full = words(m.group(1)) if m else 0
    return (body, bare, full)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO.parent / "review_round4_ijmi"))
    args = ap.parse_args(argv)

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "figures").mkdir(parents=True)
    (out / "measurements").mkdir(parents=True)
    (out / "data").mkdir(parents=True)

    red = Redactor()
    written: list[tuple[str, int]] = []

    # In the repo the supplemental sits at docs/spie2027/ and reaches figures with
    # ../../results/figures/. In the bundle it sits at the root and figures are at
    # figures/. Left alone, the only figure in the 5 August artefact silently fails to
    # resolve at PDF build time, which is the worst kind of break: the markdown looks
    # fine and the figure is simply absent from the PDF.
    IMG = re.compile(r"(!\[[^\]]*\]\()[^)]*?figures/([^)]+)(\))")

    def emit(dest: Path, src: Path, redact=True):
        t = src.read_text(encoding="utf-8", errors="replace")
        t = red.apply(t) if redact else t
        t = IMG.sub(lambda m: m.group(1) + "figures/" + m.group(2) + m.group(3), t)
        dest.write_text(t, encoding="utf-8")
        written.append((str(dest.relative_to(out)).replace("\\", "/"),
                        dest.stat().st_size))

    for name, rel in DOCS:
        p = REPO / rel
        if not p.exists():
            print("  MISSING %s" % rel)
            continue
        emit(out / name, p)

    # The submission cites four figures, renumbered from six. Shipping the other two
    # invites a reviewer to look for Figures 5 and 6 that the paper does not have.
    CITED = {"fig6_instance_number": "Figure1_instance_number",
             "fig5_masking": "Figure2_residual_estimator",
             "fig4_channel_ablation": "Figure3_nine_arm_ablation",
             "fig3_public_pair": "Figure4_delivered_records"}
    figs = [f for f in sorted((REPO / "results" / "figures").glob("*"))
            if f.stem in CITED]
    for f in figs:
        dest = out / "figures" / (CITED[f.stem] + f.suffix)
        shutil.copy2(f, dest)
        written.append(("figures/" + dest.name, f.stat().st_size))

    for p in sorted((REPO / "results").glob("*.md")):
        emit(out / "measurements" / p.name, p)

    for p in sorted((REPO / "results").glob("*.json")):
        if p.name in EXCLUDE_JSON:
            continue
        emit(out / "data" / p.name, p)

    # --- manifest -------------------------------------------------------------
    lines = [
        "# IJMI submission package, for adversarial review",
        "",
        "Read `01_READ_FIRST_review_packet.md` first. It names where I think this is",
        "weakest and lists what I have already been wrong about.",
        "",
        "## What changed this round",
        "",
        "**Your concern N21 was right and it was the only blocking item.** Figure 3 drew",
        "the **naive** confidence intervals while its caption promised the **clustered**",
        "ones, and the consequence was the bad one: the shipped rule's naive interval is",
        "[0.395, 0.458], entirely left of the chance line, so the picture asserted *below",
        "chance*, which is exactly the claim ledger row D5g exists to refuse. It now draws",
        "the clustered interval [0.342, 0.516] as the primary bar with the naive one",
        "thinner inside it, on an axis extended to 0.32 so nothing is clipped, and both",
        "intervals are named in the legend. `make_figures.py` now refuses to draw the",
        "panel at all if any arm lacks a clustered interval rather than falling back.",
        "",
        "**All four figures were regenerated without burned-in captions.** Elsevier",
        "typesets captions from the manuscript, so a caption inside the artwork is a",
        "second copy that cannot be copy-edited and goes stale silently. Three of the four",
        "had shipped as byte-identical renames carrying the previous round's captions, two",
        "of them repeating text the ledger had already retired. Rasters are flattened to",
        "RGB.",
        "",
        "**Figure 3's caption no longer generalises.** \"All indistinguishable from",
        "chance\" was false for three of the nine arms by our own clustered intervals: six",
        "contain 0.5, three do not, at 0.576 to 0.581. The caption now says *none of them",
        "usable*, which is both true and the claim the paper needs, and the body states",
        "the six-three split. The panel title carried the same overstatement and is fixed",
        "with it.",
        "",
        "**The abstract limit was checked before cutting, and no cut was needed.** IJMI's",
        "live guide, retrieved 2026-07-31, sets 300 words. The abstract is 296.",
        "",
        "**The retired claims inside `measurements/` are now marked.** G17, G18, B16 and",
        "B9 were still stated flat in four write-ups that this bundle hands to a reviewer.",
        "Each superseded passage now carries an inline retraction naming its ledger entry,",
        "rather than being deleted.",
        "",
        "Earlier retractions still stand: G12 (text colour is not outside the GSPS IOD),",
        "G15 (the provisional ablation claim), G16 (an in-sample ceiling read as",
        "headroom), G17 (the renderer draws no annotations), and G20 (the arm labelled",
        "\"the deployed rule\" was not the deployed rule; the real one is the worst of the",
        "nine).",
        "",
        "## Contents",
        "",
        "| file | what it is |",
        "|---|---|",
        "| `01_SUBMISSION_ijmi.md` | **the artefact actually under review.** Body %d words against a 3000 limit; abstract %d excluding the structured headings and %d including them, against 300 |"
        % _ijmi_counts(),
        "| `02_claims_ledger.md` | every number, its status, and the command that produces it. Twenty-one retired claims in section G |",
        "| `03_READ_FIRST_review_packet.md` | cover note: reading order, how to verify, where I think it breaks |",
        "| `04_venue_decision_and_date.md` | why IJMI, why not SPIE, and the submission date |",
        "| `05_ijmi_requirements.md` | the limits this was built against, with retrieval dates |",
        "| `06_ai_disclosure.md` | superseded SPIE-era draft, retained for provenance. The live declaration is in the submission |",
        "| `07_background_manuscript_superseded.md` | the long-form argument the 3000-word body could not carry |",
        "| `figures/` | **four** figures, PDF and PNG, numbered as the manuscript cites them, no burned-in captions |",
        "| `measurements/` | the write-up behind each claim |",
        "| `data/` | the result files the figures and claims are computed from |",
        "",
        "## What is deliberately not here",
        "",
        "| excluded | why |",
        "|---|---|",
    ]
    for k, why in sorted(EXCLUDE_JSON.items()):
        lines.append("| `results/%s` | %s. Clinical data is aycan's and is not mine to distribute. The .md summary in `measurements/` carries the same counts |" % (k, why))
    lines += [
        "| the 1735 clinical DICOM objects | private, never released |",
        "| the model checkpoints | upstream TotalSpineSeg released weights, not redistributable here |",
        "| the 35 GB VerSe dataset | public, fetch with `scripts/fetch_verse.py` |",
        "",
        "## Redaction applied to everything above",
        "",
        "Automated, by `scripts/make_review_bundle.py`, not by a manual pass:",
        "",
    ]
    if red.counts:
        for k, n in red.counts.most_common():
            lines.append("- %d occurrences of %s, replaced with a stable pseudonym" % (n, k))
    else:
        lines.append("- nothing matched, which is itself worth checking")
    lines += [
        "",
        "DICOM standard UIDs under `1.2.840.10008` are constants and are kept verbatim.",
        "The same clinical UID reads as the same pseudonym in every file, so the",
        "cross-references still work.",
        "",
        "## How to verify rather than trust me",
        "",
        "```",
        "git clone <the harness>            # code only, no data",
        "python -m pytest tests -q          # 267 tests",
        "python scripts/e1_ablation.py --run-dir <run>",
        "python scripts/make_figures.py     # every figure, from data/*.json",
        "```",
        "",
        "Use the project interpreter. Under a different environment `test_e1_oracles.py`",
        "cannot import `nibabel`, skips as a single module-level skip, and the suite",
        "silently reports 249 instead of 267 without erroring.",
        "",
        "No metric in the paper is computed by code written for the purpose of computing",
        "that metric. Conformance is scored by `dciodvfy`, an independent third-party",
        "validator. Vertebral identification is scored by the VerSe organisers' own",
        "`eval_utilities.py`, vendored rather than reimplemented.",
        "",
        "## File listing",
        "",
        "| path | KB |",
        "|---|---:|",
    ]
    for rel, size in sorted(written):
        lines.append("| `%s` | %.1f |" % (rel, size / 1024))

    (out / "00_MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    zp = out.parent / (out.name + ".zip")
    if zp.exists():
        zp.unlink()
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(out.parent))

    print("bundle  %s" % out)
    print("zip     %s  (%.1f MB)" % (zp, zp.stat().st_size / 1024 / 1024))
    print("files   %d  plus the manifest" % len(written))
    print("\nredacted:")
    for k, n in red.counts.most_common():
        print("  %4d  %s" % (n, k))
    if red.uids:
        print("\ndistinct clinical UIDs pseudonymised: %d" % len(red.uids))
    if red.pats:
        print("distinct cohort pseudonyms replaced  : %d" % len(red.pats))

    # Last line of defence, using LEAK rather than the redaction regexes. Checking with
    # the same pattern that did the removal cannot catch a pattern that is too narrow,
    # which is exactly how ANON_PAT_XXXX got through the first version.
    bad = []
    for p in sorted(out.rglob("*")):
        if not p.is_file() or p.suffix in (".png", ".pdf"):
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        for name, pat in LEAK:
            for m in pat.finditer(t):
                bad.append("%s: %s %r" % (p.name, name, m.group(0)[:60]))
    if bad:
        print("\nSELF CHECK FAILED, do not send. %d leaks:" % len(bad))
        for b in bad[:25]:
            print("  " + b)
        return 1
    print("\nself check passed: no clinical UID, no cohort pseudonym, no local path")
    return 0


if __name__ == "__main__":
    sys.exit(main())
