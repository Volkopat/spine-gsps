# Venue decision and submission date

**Decided 2026-07-31.** Supersedes the SPIE Medical Imaging 2027 plan.

## The decision

| | |
|---|---|
| **Primary** | **International Journal of Medical Informatics** (IJMI), Elsevier, ISSN 1386-5056 |
| **Fallback** | Journal of Imaging Informatics in Medicine (JIIM), Springer, formerly J Digit Imaging |
| **Article type** | full original research, **not** a short technical communication |
| **Target submission date** | **Monday 14 September 2026** |
| Complementary, not a substitute | SIIM 2027, Nashville, 17 to 19 June 2027, abstracts around mid-December 2026 |

## Why SPIE is out

The author will not travel to Vancouver. SPIE's policy, verified verbatim on the live
manuscript-guidelines page: **"Papers and posters not presented at the event will not be
published in the Proceedings of SPIE."** The only sanctioned remedy is a substitute
presenter, "a coauthor or colleague who is attending", and this paper is sole author by
decision, with two colleagues at the operator excluded on ICMJE grounds. There is
no remote, virtual or publication-only route.

**Nothing was submitted to SPIE, and nothing will be.** That is deliberate: a no-show
after the programme is finalised is logged in the presenting author's record and SPIE
describes it as unprofessional. Submitting and relying on remembering to withdraw is pure
downside.

## Why IJMI over JIIM, when JIIM's scope fits better

JIIM's guidelines give explicit precedence to validation and implementation papers over
algorithm papers, which describes this paper almost exactly, and its scope names DICOM and
IHE directly. That advantage is real but a matter of degree.

Against it: the author already has a separate sole-author manuscript under review at JIIM
(JDIM-D-26-02896, on an unrelated Florence-2 de-identification pipeline). Editorial pools
in DICOM standards work are small, so the same handling editor and plausibly overlapping
reviewers would see both sole-authored papers on adjacent topics at the same time. One
negative reaction then propagates across both. Two papers at two journals is also a
broader record than two at one.

IJMI's scope covers standardisation, systems integration and interoperability, and it
states that "Short technical communications concerning (solved) problems in implementing
or using existing information systems are welcome", so the fit is close behind rather than
distant. The diversification is worth the small scope penalty.

**If IJMI desk-rejects, go to JIIM within the week.** Do not sit on it.

## Article type: full original research

Not a short technical communication. IJMI states short communications are "not intended
for incomplete studies or abbreviated versions of full research articles", and this paper
has three independent findings, a methods section, six figures, a 1000-repetition
permutation null and a held-out ceiling. The short-communication framing fits the
`InstanceNumber` result alone, which is one section.

## The date, and why it needs to exist

SPIE's 5 August deadline was the only hard external date on the calendar. Journals take
rolling submissions, so nothing now compels this to get finished. Almost every step of
this project has moved when a deadline pushed it and not otherwise.

**Monday 14 September 2026.** Six and a half weeks from the decision, before the autumn
semester takes the time.

| by | what | why it is in this slot |
|---|---|---|
| 8 Aug | N9, cluster-adjusted confidence intervals | the only compute item, and the claim it changes is in the abstract |
| 15 Aug | N17 `parity_name` identity; N6 test count; N18 five citations | each can change what the paper says, so they precede writing |
| 29 Aug | restructure for no page limit; bank `results/viewer_bench.md` | the four-page limit was the only reason this was deferred |
| 5 Sep | N13, N14, N15, N16; IJMI reference style; Highlights | mechanical |
| **14 Sep** | **submit** | |

N9 and N17 are first because they are the two items that could change a claim rather than
a sentence. Everything after them is writing.

## What the pivot costs

Almost nothing. Every artefact except one carries over unchanged: the manuscript, the
claims ledger, the figures, 267 tests, the released harness, and every correction from
three adversarial review rounds including the PS3.2 reversal, the sigmoid pass, and G17,
G18 and G19.

The single artefact that existed only to satisfy SPIE's abstract form is the page-limited
2-to-4-page supplemental at `docs/spie2027/supplemental.md`. Its content is not wasted,
since it is the tightest existing statement of the argument and is a good basis for the
journal abstract and for a structured summary, but its **format constraint is dead** and
the hours spent cutting it to four pages bought nothing.

What is genuinely lost is the forcing function. Hence the date above.

## What becomes possible

The four-page limit was the stated reason for deferring:

- `results/viewer_bench.md`, 24.7 KB of measured, reproducible, human-free work with zero
  ledger rows: Orthanc 1.12.11 accepts and indexes all 38 non-conformant objects, 38 of
  38; `storescu` succeeds over the DICOM network path; QIDO-RS and WADO-RS return every
  colour route intact including the one `dciodvfy` rejects. Its own conclusion is that if
  a viewer shows no colour, the archive and the transport are ruled out.
- Proper separate treatment of the `InstanceNumber` result and the annotation probe,
  rather than sharing a section.
- The four-level-region finding, the z-threshold sweep, and the silent-skip finding, all
  currently confined to `results/`.

## What becomes blocking that was not

Journal review is slower, more thorough and more statistical than a conference abstract
screen.

- **N9**, unclustered confidence intervals. 1845 vertebrae from 155 cases, about twelve
  per case. The held-out split is by case, correctly; the intervals are not. The claim at
  risk is "the improvement from repairing the mapping is 0.065 with intervals that barely
  fail to overlap", which probably does not survive adjustment. The headline negative
  finding does not depend on it.
- **N17**, whether the arm labelled "the live server's rule" reproduces the deployed
  function. `results/tests.md` reads the deployed `confidence_calculator.py` as restarting
  parity at C1, T1 and L1, agreeing on all seven cervical levels and disagreeing on all
  seventeen from T1 down. If the arm does not reproduce that, the paper's central
  narrative loses its anchor.
