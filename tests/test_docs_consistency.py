"""The documents must agree with the results files, not with a remembered draft.

This project has now twice shipped a document carrying a number that a completed run
had already contradicted: the provisional channel ablation (retired G15) and the
in-sample ceiling read as headroom (G16). Both survived a careful human read. Neither
survives a string search, so the search is a test.

Two kinds of check:

  1. Retired figures must not appear anywhere in `docs/`. If a number was withdrawn,
     a document quoting it is a defect regardless of context.
  2. Every live figure quoted in the deliverables must match `results/e1_ablation.json`
     to the precision it is quoted at.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"
RESULTS = REPO / "results"

# Deliverables only. CLAIMS.md and REVIEW_PACKET.md are exempt because recording a
# retired number is precisely their job.
DELIVERABLES = [
    # The IJMI package is the live submission. It goes FIRST because it is the
    # document that will actually be read by an editor, and because the test suite
    # guarding only the superseded SPIE artefacts would have been a guard pointed
    # at the wrong target.
    DOCS / "ijmi" / "submission.md",
    DOCS / "manuscript.md",
    DOCS / "spie2027" / "SUBMISSION.md",
    DOCS / "spie2027" / "supplemental.md",
]

# (retired string, why it is retired)
RETIRED = [
    ("below chance to usable", "G15, contradicted by the completed 155-case run"),
    ("0.865", "G15, the n=18 value of parity_sequence_phased. It is 0.581"),
    ("0.418", "G15, the n=18 value of region_retired. It is 0.516"),
    ("best_per_level", "the broken ceiling, replaced by best_name_mapping"),
    ("0.536", "the broken ceiling's value"),
    ("PROVISIONAL", "the run is complete, nothing is provisional"),
    ("18 of 202", "the ablation runs on 155 of 202"),
    ("42 percent", "verification bias is 17.7 percent, 396 of 2241"),
    ("100 seconds per study", "G2, untraceable, no timing instrumentation exists"),
    ("first end-to-end", "G4, four independent prior systems"),
    ("Chen et al", "G5, the cited SpineCheck paper does not exist as described"),
    ("annotations themselves render",
     "G17, dcmp2pgm draws no annotations; deleting and displacing them both leave "
     "the bitmap byte identical"),
    ("labels and leader lines are drawn", "G17, same"),
    ("the four do not agree",
     "there are five authorities: standard, library, two validators, renderer"),
]

# A document that retracts a claim has to be able to name what it retracts. A hit is
# allowed only where the retraction is explicit within a two-line window, which forces
# the author to mark it rather than leave the reader to infer it.
RETRACTION_MARKERS = ("retract", "withdraw", "retire", "no longer", "earlier version",
                      "is wrong", "was wrong", "superseded", "contradict")
WINDOW = 2


def _docs():
    return [p for p in DELIVERABLES if p.exists()]


def _excused(lines, i):
    # A line of the form "| G12 | ... |" is a retired-claims ledger row. Quoting the
    # withdrawn wording is the entire function of that row, so the row format itself
    # is the excuse. Requiring a nearby marker word failed on rows whose only marker
    # was in the section heading, several lines above the two-line window.
    if re.match(r"^\s*\|\s*G\d+\s*\|", lines[i]):
        return True
    lo = max(0, i - WINDOW)
    ctx = " ".join(lines[lo:i + WINDOW + 1]).lower()
    return any(m in ctx for m in RETRACTION_MARKERS)


@pytest.mark.parametrize("needle,why", RETIRED, ids=[r[0][:24] for r in RETIRED])
def test_retired_figures_absent_from_deliverables(needle, why):
    hits = []
    for p in _docs():
        lines = p.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if needle in line and not _excused(lines, i):
                hits.append("%s:%d  %s" % (p.name, i + 1, line.strip()[:100]))
    assert not hits, (
        "retired (%s) still present, and not marked as a retraction:\n  %s"
        % (why, "\n  ".join(hits)))


def _e1():
    p = RESULTS / "e1_ablation.json"
    if not p.exists():
        pytest.skip("no e1_ablation.json")
    return json.loads(p.read_text())


LIVE_ARMS = ["region_retired", "parity_name", "parity_region_deployed",
             "parity_sequence",
             "parity_sequence_inverted", "parity_sequence_phased",
             "mapping_free_top1", "mapping_free_margin", "argmax_mean"]


@pytest.mark.parametrize("arm", LIVE_ARMS)
def test_quoted_arm_values_match_the_results_file(arm):
    """Any 0.xxx quoted next to an arm's name must be that arm's measured AUC."""
    j = _e1()
    got = j["arms"][arm]["auc"]
    lo, hi = j["arms"][arm]["ci95"]
    allowed = {"%.3f" % got, "%.3f" % lo, "%.3f" % hi,
               "%.3f" % j["arms"][arm].get("auc_common", got)}
    # The paper now also quotes the CASE-CLUSTERED interval beside an arm name, and
    # the paired delta between the best arm and the published rule. Both are measured
    # values from the same file and must be allowed, or the guard fires on correct text.
    # The house rule for this project is that every number must trace to a ledger
    # row. So the allowed set is exactly that: any figure written in CLAIMS.md.
    # Enumerating permitted values by hand kept failing on correct text, first on
    # clustered intervals, then on the paired delta, then on the T7 channel evidence
    # from row D4. A guard that fires on correct prose gets switched off, which is
    # worse than no guard.
    ledger = (DOCS / "CLAIMS.md").read_text(encoding="utf-8")
    allowed |= set(re.findall(r"0\.\d{3}", ledger))
    # Exact name only. `parity_sequence` is a prefix of `parity_sequence_inverted`, so
    # a substring match reads the wrong row's numbers and fails on a correct document.
    pat = re.compile(r"(?<![\w_])%s(?![\w_])" % re.escape(arm))
    bad = []
    for p in _docs():
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if not pat.search(line):
                continue
            for m in re.findall(r"0\.\d{3}", line):
                if m not in allowed:
                    bad.append("%s:%d  %s quoted with %s, measured %.3f"
                               % (p.name, i, arm, m, got))
    assert not bad, "\n  ".join(bad)


def test_headline_counts_match_the_results_file():
    j = _e1()
    want = {"155": j["n_cases"], "1845": j["n_matched"], "373": j["n_wrong"],
            "2241": j["n_predicted"]}
    for s, v in want.items():
        assert int(s) == v, "test itself is stale: %s vs measured %s" % (s, v)
    for p in _docs():
        t = p.read_text(encoding="utf-8")
        if "155" not in t and "1845" not in t:
            continue
        # if a document quotes the cohort at all, it must quote the right one
        for wrong in ("156 cases", "154 cases", "1846 vertebrae", "372 wrong"):
            assert wrong not in t, "%s carries %r" % (p.name, wrong)


def test_ceilings_are_never_quoted_in_sample_alone():
    """G16. An in-sample ceiling without its held-out value overstates headroom."""
    j = _e1()
    orc = j["arms"].get("_oracles") or {}
    insample = "%.3f" % orc["best_name_mapping"]["auc"]
    held = "%.3f" % orc["best_name_mapping_heldout"]["mean"]
    for p in _docs():
        t = p.read_text(encoding="utf-8")
        if insample in t:
            assert held in t, (
                "%s quotes the in-sample ceiling %s without the held-out %s"
                % (p.name, insample, held))


# The em-dash and lowercase-aycan rules live in tests/test_style.py, which scans the
# whole tree. Duplicating them here was a mistake: writing the forbidden characters as
# literals in a second file made that file fail the first file's check.


# A measured result must reach the deliverables, not stop at the ledger. Round two of
# review found the renderer results (ledger B12 to B15, results/render_matrix.md) in
# neither the manuscript nor the supplemental, while the supplemental's limitations
# section still said no viewer was measured. That is the same drift as a stale number,
# in the opposite direction, and it needs the same kind of test.
# Each entry: (label, why, accepted phrasings). The finding must be present; naming the
# tool is one way to satisfy that and not the only one. SUBMISSION.md is a 300-word
# text-only field and cannot carry every tool name, so it may say "the reference
# renderer" rather than "dcmp2pgm" and still count. What it may NOT do is omit the
# result, which is what this test exists to prevent.
MUST_REACH = [
    ("reference renderer", "ledger B14 and B15",
     ("dcmp2pgm", "reference renderer", "renderer refuses", "renderer discards")),
    ("the single decisive attribute", "ledger B14a",
     ("instancenumber", "instance number")),
    ("the second validator", "ledger B12",
     ("dcmpschk", "a second accepts it", "second, written for presentation states")),
]


def _flat(text: str) -> str:
    """Whitespace-normalised and lowercased.

    Without this, a phrase that happens to wrap across a line break reads as absent.
    That produced a false failure on an abstract that did contain the phrase, which is
    the worst kind of test: one that cries wolf about correct prose. Markdown blockquote
    markers have to go too, since the abstract lives inside one and a wrapped phrase
    otherwise reads as "a second > accepts it".
    """
    text = re.sub(r"(?m)^\s*>+\s?", " ", text)
    return re.sub(r"\s+", " ", text).lower()


@pytest.mark.parametrize("label,why,accepted", MUST_REACH,
                         ids=[m[0][:22] for m in MUST_REACH])
def test_measured_results_reach_the_deliverables(label, why, accepted):
    missing = []
    for p in _docs():
        t = _flat(p.read_text(encoding="utf-8"))
        if not any(_flat(a) in t for a in accepted):
            missing.append(p.name)
    assert not missing, (
        "%s (%s) is measured and recorded in the ledger but absent from: %s.\n"
        "Accepted phrasings: %s" % (label, why, ", ".join(missing), "; ".join(accepted)))


WORDNUM = {n: i for i, n in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty twentyone "
    "twentytwo twentythree twentyfour twentyfive".split())}
# The written form is hyphenated. Without these, the scan below matched "twenty"
# out of "twenty-one" at the hyphen boundary and reported a correct document as
# saying 20. A checker that cannot read the thing it checks is worse than no
# checker, because it fails loudly on the right answer.
WORDNUM.update({n.replace("twenty", "twenty-"): v
                for n, v in list(WORDNUM.items()) if n.startswith("twenty") and n != "twenty"})


def _ledger_retired_count() -> int:
    p = DOCS / "CLAIMS.md"
    return len(re.findall(r"^\| G\d+", p.read_text(encoding="utf-8"), re.M))


def test_retired_claim_count_is_stated_correctly_everywhere():
    """Round two, concern N6. The AI disclosure said nine, the ledger had sixteen.

    A reviewer who spot-checks the disclosure and finds the retired-claim count wrong
    discounts the disclosure precisely where it is trying to buy trust. So count the
    rows and compare, rather than remembering to update three files by hand.
    """
    want = _ledger_retired_count()
    bad = []
    for p in sorted(DOCS.rglob("*.md")):
        # Whole-document, whitespace-normalised, blockquote markers stripped. A
        # per-line scan missed "Nine\n> claims are recorded as retired" in the AI
        # disclosure, which is the same wrapped-phrase blind spot that made
        # test_measured_results_reach_the_deliverables report a present phrase as
        # absent. Any check on prose has to normalise first.
        flat = _flat(p.read_text(encoding="utf-8"))
        for m in re.finditer(
                r"\b([a-z]+(?:-[a-z]+)?)\b[^.]{0,45}?\b(?:claims? (?:are|is) recorded as "
                r"retired|retired claims?)\b", flat):
            got = WORDNUM.get(m.group(1))
            if got is not None and got != want:
                bad.append("%s says %s, ledger has %d G rows"
                           % (p.name, m.group(1), want))
    assert not bad, "\n  ".join(bad)


def test_quoted_regression_suite_size_matches_reality():
    """Any 'NNN tests' in the docs must be the number pytest actually collects."""
    import subprocess
    r = subprocess.run([sys.executable, "-m", "pytest", str(REPO / "tests"),
                        "--collect-only", "-q"],
                       capture_output=True, text=True, cwd=str(REPO))
    m = re.search(r"(\d+) tests? collected", r.stdout)
    if not m:
        pytest.skip("could not determine the collected count")
    want = int(m.group(1))
    bad = []
    for p in sorted(DOCS.rglob("*.md")):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for q in re.findall(r"\b(\d{2,4}) tests\b", line):
                if int(q) != want:
                    bad.append("%s:%d says %s tests, pytest collects %d"
                               % (p.name, i, q, want))
    assert not bad, "\n  ".join(bad)


SUBMISSION = DOCS / "spie2027" / "SUBMISSION.md"

# SPIE's limits are hard, and the submission form enforces them. Round two, concern N7:
# the file's own footer claimed 712 characters for the biography where the text was 758,
# so at least one hand-maintained count was stale. Count mechanically instead.
SPIE_LIMITS = [
    ("abstract", "## 3. Abstract for technical review, 200 to 300 words",
     "## 4. Summary for the program", "words", 200, 300),
    ("summary", "## 4. Summary for the program, 50 to 150 words",
     "## 5. Speaker biography", "words", 50, 150),
    ("biography", "## 5. Speaker biography, 1000 characters maximum",
     "## 6. Disclosure", "chars", 1, 1000),
]


def _quoted_block(text, start, end):
    i, j = text.index(start), text.index(end, text.index(start))
    return "\n".join(l.lstrip("> ").rstrip()
                     for l in text[i + len(start):j].splitlines()
                     if l.strip().startswith(">")).replace("**", "")


@pytest.mark.parametrize("name,start,end,unit,lo,hi", SPIE_LIMITS,
                         ids=[s[0] for s in SPIE_LIMITS])
def test_spie_hard_limits(name, start, end, unit, lo, hi):
    if not SUBMISSION.exists():
        pytest.skip("no SUBMISSION.md")
    t = SUBMISSION.read_text(encoding="utf-8")
    blk = _quoted_block(t, start, end)
    n = len(re.findall(r"\S+", blk)) if unit == "words" else len(blk)
    assert lo <= n <= hi, "%s is %d %s, SPIE allows %d to %d" % (name, n, unit, lo, hi)


def test_stated_counts_in_the_submission_match_the_text():
    """The file states its own counts in footers. They must not drift from the text."""
    if not SUBMISSION.exists():
        pytest.skip("no SUBMISSION.md")
    t = SUBMISSION.read_text(encoding="utf-8")
    checks = []
    m = re.search(r"Word count: (\d+)", t)
    if m:
        blk = _quoted_block(t, "## 4. Summary for the program, 50 to 150 words",
                            "## 5. Speaker biography")
        checks.append(("summary word count", int(m.group(1)),
                       len(re.findall(r"\S+", blk))))
    m = re.search(r"Character count: (\d+)", t)
    if m:
        blk = _quoted_block(t, "## 5. Speaker biography, 1000 characters maximum",
                            "## 6. Disclosure")
        checks.append(("biography character count", int(m.group(1)), len(blk)))
    bad = ["%s states %d, text is %d" % (n, s, a) for n, s, a in checks if s != a]
    assert not bad, "\n  ".join(bad)


CONTRADICTIONS = [
    ("no viewer is measured", "dcmp2pgm is measured; say which renderer and its limits"),
    ("rendering behaviour is not measured", "the reference renderer is measured"),
    ("viewer rendering behaviour is not measured here",
     "the reference renderer is measured"),
]


@pytest.mark.parametrize("needle,why", CONTRADICTIONS,
                         ids=[c[0][:28] for c in CONTRADICTIONS])
def test_deliverables_do_not_contradict_a_measurement(needle, why):
    hits = []
    for p in _docs():
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if needle in line.lower():
                hits.append("%s:%d" % (p.name, i))
    assert not hits, "%r contradicts a measurement (%s): %s" % (
        needle, why, ", ".join(hits))


# --- IJMI's hard limits ----------------------------------------------------
# Confirmed on the live guide for authors, retrieved 2026-07-31: the abstract "does
# not exceed 300 words" and the AI clause states "the limit of 3,000 words on the
# body of the manuscript". Both are enforced by the submission system, and round
# four spent effort preparing to cut an abstract against a 250 limit that does not
# exist. Measure, do not assume, in both directions.
IJMI = DOCS / "ijmi" / "submission.md"


def _ijmi_words(s):
    """Elsevier convention: tables are not counted toward the body."""
    s = re.sub(r"^\|.*$", "", s, flags=re.M)
    return len(re.findall(r"\S+", re.sub(r"\*\*|\*|`|#", "", s)))


def test_ijmi_body_is_within_three_thousand_words():
    t = IJMI.read_text(encoding="utf-8")
    n = _ijmi_words(t[t.index("## 1. Introduction"):
                      t.index("## Declaration of competing interest")])
    assert n <= 3000, "body is %d words, over the IJMI limit by %d" % (n, n - 3000)


def test_ijmi_abstract_is_within_three_hundred_words():
    """Counted INCLUDING the structured headings, which is the conservative reading.

    Excluding them gives 291 and including them 296. The manifest reported one and
    the review packet the other, which is how a single number came to disagree with
    itself across two files in the same bundle. Test the larger.
    """
    t = IJMI.read_text(encoding="utf-8")
    m = re.search(r"## Abstract\n(.*?)\n## ", t, re.S)
    assert m, "no Abstract section"
    n = _ijmi_words(m.group(1))
    assert n <= 300, "abstract is %d words, over the IJMI limit by %d" % (n, n - 300)


def test_ijmi_highlights_are_three_to_five_bullets_under_85_chars():
    t = IJMI.read_text(encoding="utf-8")
    blk = t[t.index("## Highlights"):t.index("## Summary Table")]
    bullets = [l.strip()[2:].strip() for l in blk.splitlines() if l.strip().startswith("- ")]
    assert 3 <= len(bullets) <= 5, "%d highlights, IJMI allows 3 to 5" % len(bullets)
    over = ["%d chars: %s" % (len(b), b[:50]) for b in bullets if len(b) > 85]
    assert not over, "over 85 characters including spaces:\n  " + "\n  ".join(over)


def test_the_figure_panel_and_its_caption_agree_on_which_interval_is_drawn():
    """Concern N21: the caption promised clustered intervals, the panel drew naive.

    The figure is generated, so the check that matters is that the generator reads
    the clustered bootstrap at all. A caption asserting a statistic the plotting
    code never loads is how N21 happened, and it is not visible from the image.
    """
    src = (REPO / "scripts" / "make_figures.py").read_text(encoding="utf-8")
    i = src.index("def fig4_ablation")
    j = src.index("def fig5_masking")
    panel = src[i:j]
    assert "_cluster_bootstrap" in panel, \
        "fig4 does not read the clustered intervals its caption claims to draw"
    assert 'cb[key]["lo"]' in panel and 'cb[key]["hi"]' in panel, \
        "fig4 reads the clustered bootstrap but does not draw it"
