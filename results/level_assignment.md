# The vertebral level assignment algorithm: provenance and failure modes

Established 2026-07-30 by reading the recovered server source at
`<path>\app\inference_core\` and comparing it against the
installed upstream `totalspineseg` package.

## Provenance: the algorithm is upstream TotalSpineSeg, not original work

The RSNA 2026 abstract states, in Materials and Methods: "Iterative labeling
anchors on landmark discs to assign levels (C1-L5, sacrum)." That sentence
describes upstream code.

Measured overlap. Substantive lines, meaning lines over 25 characters with
comments stripped, that appear **verbatim** in
`totalspineseg/utils/iterative_label.py`:

| recovered file | verbatim in upstream |
|---|---|
| `iterative_labeling_main.py` | 171/179 (96%) |
| `iterative_labeling_landmarks.py` | 29/31 (94%) |
| `iterative_labeling_components_sort.py` | 35/36 (97%) |
| `iterative_labeling_merging.py` | 33/39 (85%) |
| `iterative_labeling_components_base.py` | 21/22 (95%) |
| **total** | **289/307 (94%)** |

Upstream ships this as one 54.4 KB file. The recovered version is the same code
split across five modules. The magic defaults are identical in both:
`region_max_sizes=[5, 12, 6, 1]` and `region_default_sizes=[5, 12, 5, 1]`.

**Consequence for the paper.** The level assignment must be attributed to
TotalSpineSeg (Warszawer et al., neuropoly) and described as used, not as
contributed. The RSNA novelty page already said the pipeline "does not claim
segmentation novelty", but the Methods sentence reads as though the iterative
labelling were part of this system's own machinery. It is not. Combined with
VERIDAH (arXiv:2601.14066) having already published TotalSpineSeg at 94.24 percent
subject-level labelling accuracy on MRI, there is nothing left to claim on this
axis. The contribution has to be the delivery layer and the QA layer.

## How it actually works

1. Derive the canal centerline and a mask anterior to it
   (`_get_canal_centerline_indices`, `_get_mask_aterior_to_canal`).
2. Extract superior-to-inferior sorted connected components separately for discs
   (combined into one class) and for vertebrae (`_get_si_sorted_components`).
3. Merge vertebra components sharing a label, then absorb extra labels into
   adjacent vertebrae.
4. Anchor: `_get_landmark_output_labels` finds which sorted disc component is a
   known landmark disc. Priority order is configured in `inference_logic.py:151`
   as `selected_disc_landmarks=[2, 5, 3, 4]`, which given step 1's label map means
   **C2-C3 first, then L5-S, then C7-T1, then T12-L1**.
5. Propagate outward from the anchor, filling disc slots from
   `region_max_sizes` per region, and map disc outputs to vertebra outputs.
6. Interleave vertebrae and discs by superior-inferior position, with swap
   heuristics at `iterative_labeling_main.py:315-335` that reorder the sequence
   when two discs or two vertebrae land adjacent.

## Failure modes, read from the code

**T13 cannot be produced.** `region_max_sizes=[5, 12, 6, 1]` against
`region_default_sizes=[5, 12, 5, 1]` gives the lumbar region one slot more than
its default, which is how L6 (lumbarisation, sacralisation) is representable. The
thoracic region has max equal to default at 12, so there is no spare slot and no
T13. This matters directly for the VerSe evaluation, because **VerSe explicitly
labels T13 as value 28** and VerSe'20 contains such cases. On those cases the
pipeline is structurally unable to produce the correct answer, independent of
segmentation quality.

Caveat on this claim: I derived the slot-to-level correspondence from the code
structure rather than by running it. It should be confirmed empirically on a VerSe
T13 case once the batch runner exists. Flagged rather than asserted.

**Partial field of view produces no output at all.**
`_get_landmark_output_labels` raises `ValueError("At least one of the landmarks
must be in the segmentation or localizer")` when no landmark disc is found.
`_iterative_label` catches that, prints `Error: <path>, <msg>`, deletes any
existing output file, and **returns without writing anything**
(`iterative_labeling_main.py:157-160`). So a study whose field of view excludes
all four landmark discs is silently skipped, not flagged. A lumbar-only study
missing L5-S, or a mid-thoracic study, would hit this.

There is a `default_superior_disc` fallback that assigns the topmost disc a fixed
label when set above zero, which converts the failure into a guess. It is not set
in `cfg/config.yml`, so on the deployed configuration the failure mode is the
silent skip.

**Range is C1 to L6 plus sacrum, not C1 to L5.** The abstract says C1-L5. Because
the lumbar region permits six levels, the actual output range includes L6.

## What this changes

- Attribute the level assignment to TotalSpineSeg in Methods.
- Report the T13 limitation before a reviewer finds it, and exclude or separately
  analyse VerSe T13 cases rather than letting them silently depress the
  identification rate for the wrong reason.
- The silent-skip behaviour on absent landmarks is a genuine deployment finding
  and worth reporting: a QA layer that never fires because no output was produced
  is a real gap in an AI-results pipeline, and it is the kind of thing the paper's
  quality-assurance framing is well placed to discuss.
