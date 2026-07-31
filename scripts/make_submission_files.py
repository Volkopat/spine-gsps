"""Produce the files that actually get uploaded to IJMI's submission system.

`docs/ijmi/submission.md` is the single source of truth. It is not submittable:
Editorial Manager wants a manuscript document, Highlights as their own file with
"highlights" in the name, and figures as individual files. This script derives
all of them from the one markdown so they cannot drift apart.

It REFUSES to emit anything if an unresolved placeholder is still in the text.
The repository URL and the Zenodo DOI are placeholders until the code is pushed
and the archive minted, and a submitted manuscript that cites a repository which
does not exist is worse than a late submission.

Usage:  python scripts/make_submission_files.py [--out DIR] [--allow-placeholders]
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "docs" / "ijmi" / "submission.md"
FIGDIR = REPO / "results" / "figures"

# Figure N in the manuscript -> the stem that builds it. Held here rather than
# inferred, because round four shipped three figures as byte-identical renames
# and nobody noticed until a reviewer hashed them.
FIGURES = [
    (1, "fig6_instance_number"),
    (2, "fig5_masking"),
    (3, "fig4_channel_ablation"),
    (4, "fig3_public_pair"),
]

# Text that exists to talk to me, or to the editor, and must not reach a reviewer.
INTERNAL = [
    re.compile(r"^\*Submitted as a separate file\..*?\*$", re.M),
    re.compile(r"^\*Editorial note\..*?\*$", re.M | re.S),
]

# Anything matching these means the manuscript is not finished.
PLACEHOLDERS = [
    ("repository URL", re.compile(r"ORG-PLACEHOLDER")),
    ("Zenodo DOI", re.compile(r"zenodo\.X+", re.I)),
    ("generic marker", re.compile(r"\bTODO\b|\bTBD\b|\bXXXX+\b")),
]


def _split(md: str):
    """Return (front_matter, highlights_block, rest_without_highlights)."""
    i = md.index("## Highlights")
    j = md.index("## Summary Table")
    front = md[:i]
    highlights = md[i:j]
    rest = md[j:]
    # the "---" separator that preceded Highlights is now dangling
    front = re.sub(r"\n---\s*\n\s*$", "\n", front)
    return front, highlights, rest


def _clean(s: str) -> str:
    for rx in INTERNAL:
        s = rx.sub("", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip() + "\n"


def _docx(md_text: str, out: Path, title: str):
    """No --standalone and no title metadata.

    With them, pandoc stamps a Title-styled paragraph from the metadata ahead of
    the document, so the manuscript opened with the word "Manuscript" and the
    real title appeared underneath it as a heading. Each block already carries
    its own top-level heading; let that be the title.
    """
    import pypandoc
    out.parent.mkdir(parents=True, exist_ok=True)
    pypandoc.convert_text(
        md_text, "docx", format="markdown+pipe_tables-abbreviations",
        outputfile=str(out), extra_args=["--wrap=none"])
    _strip_nbsp(out)
    return out.stat().st_size


def _strip_nbsp(path: Path) -> int:
    """Replace U+00A0 with a plain space inside the .docx.

    Pandoc puts a non-breaking space after an abbreviation, so every "et al."
    in the reference list gets one. Typographically that is correct, but
    Editorial Manager parses reference strings and a non-breaking space is not
    what its parser expects. Disabling the `abbreviations` extension did not
    remove them, so rewrite the package: a .docx is a zip of XML.
    """
    import zipfile
    with zipfile.ZipFile(path) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    n = 0
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for info, data in items:
            if info.filename.endswith(".xml"):
                nb = " ".encode("utf-8")
                n += data.count(nb)
                data = data.replace(nb, b" ")
            z.writestr(info, data)
    tmp.replace(path)
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(REPO.parent / "IJMI_submission"))
    ap.add_argument("--allow-placeholders", action="store_true",
                    help="emit DRAFT files anyway, for checking layout only")
    a = ap.parse_args(argv)

    md = SRC.read_text(encoding="utf-8")

    found = [(what, rx.findall(md)) for what, rx in PLACEHOLDERS]
    found = [(w, h) for w, h in found if h]
    if found and not a.allow_placeholders:
        print("REFUSING to build. Unresolved placeholders in the manuscript:\n")
        for what, hits in found:
            print("  %-16s %s" % (what, ", ".join(sorted(set(hits)))))
        print("\nBoth live in the Data availability statement. Resolve them, or")
        print("re-run with --allow-placeholders to inspect layout only.")
        return 1

    # Clear the CONTENTS, not the directory. Removing the directory itself fails
    # with WinError 32 whenever any shell has it as its working directory, which
    # is exactly what happens when you are looking at the output between builds.
    out = Path(a.out)
    for child in sorted(out.glob("*"), reverse=True) if out.exists() else []:
        try:
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        except PermissionError:
            # Word holds an exclusive lock on an open .docx. Say so, rather than
            # emitting a traceback that looks like a bug in the build.
            print("CANNOT WRITE: %s is open in another program (Word locks an open\n"
                  ".docx). Close it and re-run; nothing has been changed."
                  % child.name)
            raise SystemExit(1)
    (out / "figures").mkdir(parents=True, exist_ok=True)

    draft = "DRAFT_" if found else ""
    front, highlights, rest = _split(md)

    # --- 1. the manuscript -------------------------------------------------
    manuscript = _clean(front + "\n" + rest)
    n = _docx(manuscript, out / (draft + "Manuscript.docx"), "Manuscript")
    print("  Manuscript.docx           %6.1f KB" % (n / 1024))

    # --- 2. Highlights, own file, "highlights" in the name per the guide ---
    hl = _clean(highlights).replace("## Highlights", "# Highlights", 1)
    n = _docx(hl, out / (draft + "Highlights.docx"), "Highlights")
    bullets = [l.strip()[2:] for l in hl.splitlines() if l.strip().startswith("- ")]
    print("  Highlights.docx           %6.1f KB   %d bullets, longest %d chars"
          % (n / 1024, len(bullets), max(len(b) for b in bullets)))

    # --- 3. figures, vector where we have it -------------------------------
    for num, stem in FIGURES:
        for ext in ("pdf", "png"):
            s = FIGDIR / ("%s.%s" % (stem, ext))
            if not s.exists():
                print("  MISSING %s" % s)
                return 1
            d = out / "figures" / ("Figure%d.%s" % (num, ext))
            shutil.copy2(s, d)
        print("  figures/Figure%d.pdf+.png            from %s" % (num, stem))

    # --- 4. the checklist IJMI requires as supplementary material ----------
    appf = md[md.index("## Appendix F."):md.index("## Appendix G.")]
    appf = appf.replace("## Appendix F. Reporting-guideline statement",
                        "# Machine Learning checklist and reporting-guideline statement\n\n"
                        "*Supplementary material accompanying the manuscript "
                        "\"Separating conformance from trustworthiness\". This reproduces "
                        "Appendix F of the manuscript as a standalone file, per the "
                        "journal's requirement that the checklist be submitted as "
                        "supplementary material.*")
    n = _docx(_clean(appf), out / (draft + "Supplementary_ML_checklist.docx"),
              "Machine Learning checklist")
    print("  Supplementary_ML_checklist.docx  %6.1f KB" % (n / 1024))

    print("\n  %s" % out)
    if found:
        print("\n  DRAFT ONLY. Placeholders still present, do not upload.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
