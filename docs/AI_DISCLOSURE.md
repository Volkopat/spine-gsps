# AI assistance disclosure

> **SUPERSEDED, retained for provenance. Do not submit this file.**
>
> This is the SPIE-era working draft. The venue is now IJMI, and the live
> disclosure is split across two places in `docs/ijmi/submission.md`, per
> Elsevier's rule that the two kinds of use are declared separately:
>
> - **Methods 2.5, "AI use in the research process"**, for the tool's role in
>   writing code, running experiments and analysing output.
> - **"Declaration of generative AI in scientific writing", above the reference
>   list**, for the tool's role in preparing the prose.
>
> The instruction below to insert the whole disclosure as a Methods subsection
> is SPIE's rule and is **wrong for IJMI**, which wants the writing declaration
> above References. The SPIE policy quotations, the note about the Lena test
> image and item 4 of the author notes are all dead with the venue.
>
> Two errors are left standing in the text below rather than corrected, because
> a provenance record that has been quietly tidied is not a provenance record:
> it says "softmax channel" where the models are region based and use per-region
> sigmoids (retired as part of the sigmoid pass), and it opens a sentence with the
> retired-claim count in lower case, which is the visible end of a find-and-replace
> that did not read what it was replacing. The count itself is kept current, because
> a test enforces it against the ledger.

Drafted to satisfy SPIE's AI-assisted content and authorship policy, retrieved
2026-07-30 from the Manuscript Guidelines and Policies page. The governing text,
verbatim:

> "AI systems and large language models (LLMs) cannot be listed as authors of a
> manuscript."

> When AI tools contribute to "generation, analysis, processing, interpretation, or
> presentation of research findings," authors must "provide sufficient methodological
> detail to allow reviewers and readers to understand the role of the tool."

> "Use of AI solely for language editing, grammar correction, translation, or
> stylistic refinement does not normally require description in the Methods section."

> "SPIE follows COPE guidance that authors are fully responsible for all content in
> their manuscript, regardless of the tools used in its creation."

**The narrow exception does not apply to this work.** AI assistance extended well
beyond language editing, into code authorship, experiment execution, analysis, and
draft preparation. A Methods disclosure with real methodological detail is therefore
required, not an acknowledgement line.

---

## Text for the Methods section

Insert as a subsection, suggested position after the validation subsection so a
reader encounters it before the results.

> ### Use of AI tools
>
> Analysis code, evaluation harness code, and the initial drafts of this manuscript
> were produced with the assistance of a large language model coding agent (Anthropic
> Claude, Opus 5, accessed through Claude Code during July 2026). Its role is
> described here in the detail SPIE's policy requires, since it extended beyond
> language editing.
>
> **What the tool did.** It wrote the evaluation harness released with this paper,
> including the validator wrapper, the presentation state and segmentation writers,
> the NIfTI to DICOM converter, the batch inference runner, the channel selection
> ablation, and the synthetic evaluation of the geometric consistency check. It
> executed those programs, tabulated their output, performed the source-code audit of
> the deployed pipeline reported in Sections 3.2 and 4.5, and produced the first draft
> of this manuscript.
>
> **What the tool did not do.** It did not select the research question, decide which
> claims to make, or approve any figure or number for publication. It has no access to
> the clinical cohort beyond the pseudonymised derived statistics described in Section
> 6. It is not an author and is not accountable for the content.
>
> **How its output was controlled.** Three mechanisms, adopted because the tool
> produced errors that would otherwise have entered the manuscript.
>
> First, all conformance is scored by an independent third-party validator
> (`dciodvfy`, dicom3tools) and all vertebral identification by the benchmark
> organisers' own code, vendored rather than reimplemented. No metric in this paper is
> computed by code the tool wrote for the purpose of computing that metric.
>
> Second, a regression suite of 267 tests encodes the project's factual constraints,
> including that the softmax channel table agrees with the model checkpoints' own
> label definition. That suite detected two defects in tool-written code that had
> already been committed: an ordinal table that assigned two adjacent vertebrae to the
> same softmax channel, and a DICOM value-representation overrun that pydicom reports
> only as a warning and would have produced silently non-conformant objects.
>
> Third, every quantitative claim is recorded in a provenance ledger released with the
> code, marking it as measured here, taken from the literature, or retired. twenty-one
> claims are recorded as retired, including two carried over from an earlier abstract
> by the author and one citation that does not exist as previously described. The
> ledger exists because tool-assisted analysis produced several plausible intermediate
> conclusions that later measurement contradicted; those are documented rather than
> silently dropped.
>
> The author has verified every claim in this manuscript against the released code and
> data and is fully responsible for its content.

## Notes for the author before submission

1. **Verify the disclosure is accurate.** It states you verified every claim. Do that
   before submitting it, since the statement is itself a claim you are accountable
   for.
2. **The provenance ledger should be released**, not just cited. It is the strongest
   available evidence that the tool's output was controlled rather than trusted, and
   it converts an integrity liability into a methodological strength.
3. **Do not soften this.** A reviewer who suspects undisclosed AI use and finds a
   thorough disclosure will read the rest more generously. The reverse is also true.
   Academ-AI and comparable projects specifically document undisclosed use, and this
   work would be easy to identify given the code release.
4. **Check journal policy separately** if any part is later submitted to a journal.
   SPIE permits proceedings content to be expanded into a journal submission, but
   journal AI policies differ and are typically stricter about disclosure placement.
5. The policy prohibits AI authorship, which is not at issue here, and requires
   accountability, which rests entirely with you.

## One further SPIE requirement noticed while retrieving this

SPIE prohibits the Lena/Lenna test image and reserves the right to refuse manuscripts
containing it. Not relevant to this work, recorded for completeness.
