# IJMI submission requirements

Target venue per `TARGET.md`. **Source: the author's reviewer, 2026-07-31.** Their
caveats are preserved verbatim rather than smoothed away, because several items were
recovered from indexed snippets rather than the live page: ScienceDirect blocks automated
retrieval of both the guide for authors and the open-access page, which is why this file
exists rather than a fetched copy.

Everything marked **RECONFIRM** must be checked on the live page before submission, with
the retrieval date recorded here.

---

## The two items that change the work, not just the formatting

### 1. Scope: this must not read as an imaging paper

IJMI's sister-journal boundary text excludes "papers related to signal processing,
**imaging**, medical devices, or communication networks ... unless they combine
knowledge-intensive approaches involving ontologies."

A GSPS conformance paper reads as imaging unless it is framed otherwise. The framing that
is squarely in scope, and which the paper genuinely supports:

- **interoperability and standards conformance**, which is what the five-authority
  disagreement and the archive/transport measurements actually are
- **AI implementation and governance**, which is what the quality-flag ablation is

Both are named IJMI priority areas. IJMI states it prioritises "implementation fidelity,
measurable clinical/population impact ... over algorithmic novelty alone", which is this
paper's position exactly.

**Action: send a short pre-submission scope enquiry to the Editor-in-Chief,
Heimar de Fatima Marin, before writing.** A desk rejection on scope costs weeks; the
enquiry costs an email. This decision has to be made before the rewrite, not after,
because it determines the title, the abstract and the introduction.

### 2. The AI disclosure must be split in two, and Elsevier's placement is the reverse of SPIE's

This project's `docs/AI_DISCLOSURE.md` was written to SPIE's rule, which puts AI
disclosure in Materials and Methods. Elsevier splits it:

| what | where | Elsevier's rule |
|---|---|---|
| prose and manuscript preparation | a dedicated section **at the end of the manuscript, immediately above References** | titled "Declaration of Generative AI and AI-assisted technologies in the writing process" |
| **AI used to write code and run analyses** | **Methods**, with tool, version and developer | "AI use in the research process should be declared and described in detail in the methods section, if relevant" |

Verbatim template Elsevier supplies for the writing declaration:

> "During the preparation of this work, the author(s) used [NAME OF TOOL / SERVICE] in
> order to [REASON]. After using this tool/service, the author(s) reviewed and edited the
> content as needed and take(s) full responsibility for the content of the published
> article."

Carve-out, verbatim: "Basic checks of grammar, spelling and punctuation do not need a
declaration statement. However, when an AI tool makes substantive changes to sentence
structure or organization of a part of the text, this should be disclosed."

**This is a bisection, not a relocation.** Most of what this project's disclosure
describes is research-process use: the harness, the emitters, the analysis scripts and the
test suite were largely AI-written. That half belongs in Methods on the merits, and it is
the half that supports rather than undermines the paper, because the three control
mechanisms already documented (independent third-party validators, the vendored VerSe
scorer, and the claims ledger) are the answer to "how do you know the tool did not
fabricate this".

**RECONFIRM** the exact section title on IJMI's live guide: Elsevier's central policy says
"in the writing process", the ScienceDirect guide wording is "in the manuscript
preparation process". The placement is unambiguous either way.

---

## Article type

**Original Research Article.** Confirmed against IJMI's own definitions.

| type | verbatim scope | fit |
|---|---|---|
| Original research articles | "original quantitative studies reporting novel findings on the design, deployment, evaluation, or governance of health information technologies in real-world clinical settings" | **this one** |
| Implementation reports | "structured around the five dimensions of a deployed system"; **3,000-word limit**, mandatory SQUIRE 2.0 checklist | poor fit: a conformance measurement is not a deployment lifecycle, and the cap is prohibitive |
| Short communications | "not intended for incomplete studies or **abbreviated versions of full research articles**" | explicitly barred |
| Review, Letters, Editorials | editorials by invitation only | no |

Note that the aims-and-scope sentence recovered earlier, "Short technical communications
concerning (solved) problems in implementing or using existing information systems are
welcome", maps to the **Short communications** type in the submission system. It is a
genuine invitation but it is not this paper.

## Manuscript

| item | requirement | status |
|---|---|---|
| structure | IMRaD: Introduction, Methods, Results, Discussion, Conclusions | |
| abstract | **"a concise and factual abstract which does not exceed 300 words"**, verbatim | **CONFIRMED on the live guide, retrieved 2026-07-31.** Not 250. Ours is 296 excluding the bold headings and needs no cut. The earlier "Elsevier's general ceiling is 250" was a guess and would have cost content for nothing |
| structured abstract | required "by means of appropriate headings"; the guide prescribes **no specific heading set**, only that the abstract state the purpose, outline procedures, include main findings with effect sizes and statistical significance, and give principal conclusions | **CONFIRMED 2026-07-31.** Our headings satisfy all four |
| keywords | 1 to 7, English; MeSH not mandated | **CONFIRMED 2026-07-31.** Ours is 6 |
| references | Elsevier numbered / Vancouver, in order of appearance | journal-wide cap not verified |
| Highlights | **optional**, 3 to 5 bullets, max 85 characters each including spaces, separate file | |
| graphical abstract | **optional**, 531 x 1328 px (h x w) or proportionally larger, readable at 5 x 13 cm | general-purpose generative AI must not create it |
| Highlights, measured | 5 bullets, longest 81 characters | **CONFIRMED 2026-07-31** against "3 to 5 bullet points, each a maximum of 85 characters, including spaces" |
| figures | TIFF/EPS/PDF; line art >=1000 dpi, combination >=500, halftone >=300. **Colour free online** | **DONE.** Four cited figures, PDF (vector) plus 300 dpi PNG, flattened to RGB, captions not burned in |
| word count | **3000 words on the body**, stated in the AI clause below; abstract, references, tables, legends excluded by Elsevier convention | **CONFIRMED 2026-07-31.** Body is 2992. Guarded by `tests/test_docs_consistency.py` so it cannot drift silently |

### Articles on artificial intelligence, quoted from the live guide 2026-07-31

> "Authors of articles on studies on Artificial Intelligence, Machine Learning,
> Natural Language Processing and related topics, are required to add relevant
> information as appendix (considering the limit of 3,000 words on the body of the
> manuscript) to allow for better assessment, transparency and reproducibility.
> Authors must complete and submit IJMI's Machine Learning checklist as supplementary
> material at the submission process. **Manuscripts not conforming to these
> requirements may be returned without review.**"

> "The manuscripts must adhere to the recognized standards such as TRIPOD+AI for
> prediction models, DECIDE-AI for early-stage clinical evaluation, SPIRIT-AI for
> trial protocols, PROBAST-AI for bias assessment in prediction model studies, and
> CONSORT-AI for clinical trials evaluating AI interventions."

| | |
|---|---|
| content | **DONE.** Appendix F answers the checklist item by item and argues, with reasons, that none of the five named standards applies, because no prediction model is developed, derived, updated or validated. The ablation varies a fixed post-hoc readout of an unchanged, openly released network |
| artefact | **OPEN, and a desk-rejection trigger.** The checklist must be uploaded as a **separate supplementary file**. Appendix F is not that file. Obtain IJMI's own checklist template at submission time and transcribe Appendix F into it |
| risk | If a handling editor decides TRIPOD+AI *does* apply, that is a substantial addition rather than an attachment. Appendix F's non-applicability argument is the thing to have a reviewer attack |
| LaTeX | accepted, `elsarticle` class. "Format Word files in a single-column layout. Double-column formatting is only permitted for LaTeX submissions." | |

## Declarations, all required

- **Declaration of competing interest.** Ours is affirmative, not the "none" boilerplate:
  the work was done while employed at aycan, the submitting affiliation is University at
  Buffalo, and the pipeline under study is aycan's. Mirror it in Editorial Manager and the
  cover letter.
- **CRediT authorship contribution statement**, required even for a sole author.
- **Data availability**, citing VerSe with its persistent identifier, plus the code
  repository **with a DOI**. Mint one via Zenodo. Avoid "available on request".
- **Funding**, using Elsevier's "Formatting of funding sources".
- **Ethics.** Public de-identified benchmark data, descriptive statistics, no patient
  contact: a brief "not human-subjects research, no IRB required" statement with its
  rationale is the expected form, not an approval number.
- **Nothing about permission or consent is uploaded.** Confirmed on the live guide,
  retrieved 2026-07-31, verbatim: *"Written consents must be retained by the authors.
  They should not be provided to this journal unless this is specifically requested in
  exceptional circumstances, for example, when a legal issue arises. Only then should
  you provide copies of the consents, or evidence that all relevant consents were
  obtained."* The aycan research-use permission is therefore **retained, not
  submitted**, and the decision not to export it out of the aycan mailbox is recorded
  with its residual risk at ledger H5c. The guide does add that the journal *"reserves
  the right to request additional evidence"*, which is the whole of the exposure.
- **The AI declaration**, per the split above.

## The AI/ML checklist expectation, and how to pre-empt it

IJMI is prescriptive about reporting guidelines and requires, verbatim, that AI/ML/NLP
studies complete **IJMI's Machine Learning checklist** and adhere to "TRIPOD+AI for
prediction models, DECIDE-AI for early-stage clinical evaluation, SPIRIT-AI for trial
protocols, PROBAST-AI ..., and CONSORT-AI".

This paper develops no model and runs no trial, so most of those do not apply. But it does
ablate a deployed AI quality flag, so a reviewer may reasonably expect a checklist.
**Pre-empt it**: supply the ML checklist items that do apply and state briefly why
TRIPOD+AI and CONSORT-AI do not, rather than leaving a reviewer to raise it.

**RECONFIRM**: whether STARE-HI, STROBE or EQUATOR are named. Unverified.

## Mechanics

| | |
|---|---|
| submission system | Editorial Manager; email submission not accepted |
| peer review | single-blind; authors may suggest and oppose reviewers |
| Editor-in-Chief | Heimar de Fatima Marin, Federal University of Sao Paulo |
| plausible handling editors | Georgiou, Liaw or Zhou on interoperability/standards/clinical informatics. **RECONFIRM** current assignments before naming anyone |
| APC, gold OA | USD 3,160 excluding taxes; a third-party index said 3,210. **The personalised OACS quote at submission governs.** **RECONFIRM** |
| subscription route | **no author fee** |
| preprints | permitted before and during review. **RECONFIRM** no journal-specific restriction |
| decision times, acceptance rate | **COULD NOT BE VERIFIED.** Journal Insights blocks automated retrieval. Check journalinsights.elsevier.com/journals/1386-5056 and record the date |
| 2026-27 special issues | none found on standards, interoperability or AI governance. Check the Calls for Papers tab |

## Cover letter

Disclose:

- the earlier, different RSNA 2026 abstract on the same underlying system, which was
  rejected. Not a prior publication and no bar.
- that an abstract was prepared for SPIE Medical Imaging 2027 and **not submitted**.
- that the work is not under consideration elsewhere.
- code and data availability.

**Do not mention** the unrelated JIIM manuscript. It is a different paper; the
dual-submission prohibition applies only to the same work, and raising it invites a
question that does not exist.

## If IJMI declines

Per `TARGET.md`, JIIM is the fallback. The rewrite cost is bounded and known:

1. declarations reformat into Springer's single "Statements and Declarations" block
2. **the AI disclosure moves back into Methods**, since Springer places LLM documentation
   there and does not require declaring AI-assisted copy editing at all
3. Springer numbered reference style
4. no word cap to trim to

JAMIA Open behind that: Research and Applications is capped at 4,000 words excluding
acknowledgements and references, structured abstract 250 words with headings Objective /
Materials and Methods / Results / Discussion / Conclusion, 4 tables, 6 figures, and a
required "Background and Significance" section. Gold OA only.
