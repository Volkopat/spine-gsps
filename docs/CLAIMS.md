# Claims ledger

Every number that may appear in the paper, with its provenance. Nothing enters a
manuscript unless it has a row here.

Status codes:

- **MEASURED** run in this project, on this hardware, reproducible by the listed command
- **PENDING** the experiment is defined and running or scheduled, no number yet
- **LITERATURE** taken from a cited source, never presented as ours
- **RETIRED** previously believed, now known wrong. Kept so it cannot creep back.

Hardware for every MEASURED row unless stated: one NVIDIA GeForce RTX 5090 Laptop
GPU, 24463 MiB, sm_120, driver 610.74. Python 3.10.20, torch 2.8.0+cu128,
nnunetv2 2.4.2, pydicom 3.0.2, highdicom 0.28.1. Pins in `env/requirements.lock`.

---

## A. Conformance of presentation states and segmentations

| # | Claim | Status | Source |
|---|---|---|---|
| A1 | The 38 GSPS objects emitted by the deployed pipeline score 7 required-attribute errors and 6 out-of-IOD attributes each. 0 of 38 pass. | MEASURED | `python -m spinelab.gsps.validate <dir> --pattern _GSPS`. `results/gsps_conformance_baseline.md` |
| A2 | The seven are `FileMetaInformationGroupLength`, `FileMetaInformationVersion`, `InstanceNumber`, `PresentationPixelSpacing`, `SeriesNumber`, `StudyID`, `Laterality`. | MEASURED | same |
| A3 | `Laterality` is a Type 2C conditional that `dciodvfy` cannot evaluate for an unpaired body part. Absence is correct; zero length draws a worse diagnostic. | MEASURED | same, plus the verbatim second diagnostic |
| A4 | Our conformant GSPS variants score 1 error, the `Laterality` conditional, and 0 out-of-IOD attributes. | MEASURED | `results/gsps_variants.md` |
| A5 | Our from-scratch GSPS built on public data scores the same, with an empty other-diagnostics section. | MEASURED | `python -m spinelab.gsps.build`, `results/public_gsps_validation.json` |
| A6 | DICOM SEG objects score **0 errors and 0 out-of-IOD attributes**, **6 of 6** in the released validation file (three cases plus three colour variants). An earlier orchestrator run validated 12 objects with the same result. The 12 was also confusable with the 12 *segments* each object carries; state the run. | MEASURED | `results/seg_writer_validation.json` (n_files 6); orchestrator run in `results/orchestrator_verification.md` |
| A7 | Generated CT instances score 0 and 0 as `CTImage`. The released validation file covers **933 of 933 instances across three cases**, not a sample. An earlier orchestrator run sampled 12 of 722 with the same result. The full-coverage figure is the stronger one and supersedes the sample. | MEASURED | `results/public_dicom_validation.json` (n_files 933); sample in `results/orchestrator_verification.md` |
| A8 | **SEG is strictly more conformant than GSPS at its best.** | MEASURED | A4 versus A6 |

## B. The three colour routes

**This section was substantially wrong and was rewritten on 2026-07-31 after an
adversarial review.** The original claim, that text colour is outside the GSPS IOD
while line colour is inside it, confused a validator diagnostic with the standard.
See G12. The corrected finding is a three-way gap between standard, tooling and
validator, which is a stronger result than the one it replaces.

| # | Claim | Status | Source |
|---|---|---|---|
| B1 | **The standard permits per-object colour on both text and graphic objects.** PS3.3 C.10.5, the Graphic Annotation Module, which is in the GSPS IOD: `TextStyleSequence` (0070,0231) **Type 3**, `LineStyleSequence` (0070,0232) **Type 3**, `FillStyleSequence` (0070,0233) **Type 3**. | VERIFIED against the primary standard | dicom.nema.org PS3.3 sect_C.10.5 |
| B2 | `GraphicLayerRecommendedDisplayCIELabValue` (0070,0401), Graphic Layer Module, is also in the IOD and validates clean. | MEASURED | variant `colour_layer_iod` |
| B3 | **`dciodvfy` accepts the line route and rejects the text route, though both are Type 3 in the same module.** The text variant draws 6 "not present in standard DICOM IOD" warnings; the line variant draws 0. | MEASURED | variants `colour_text_outofiod`, `colour_line_iod` |
| B3a | **The asymmetry is inside the validator, not the standard.** `ShadowStyle` (0070,0244) is flagged when it sits in `TextStyleSequence` and passes when it sits in `LineStyleSequence`, in the same object. The standard defines it in both macros. | MEASURED | same |
| B3b | `dciodvfy` closes with "Dicom dataset contains attributes not present in standard DICOM IOD, this is a Standard Extended SOP Class", which asserts extension rather than non-conformance. Quoting it as a conformance failure overstates it. | MEASURED, verbatim | same |
| B3c | Ruled out: the attributes are correctly nested. `TextColorCIELabValue` sits inside `TextStyleSequence`, not directly on the text object, so this is not a misplacement the validator was right to reject. | MEASURED | pydicom inspection of the emitted object |
| B4 | The deployed pipeline carries its per-vertebra flag on the text route. That route is standard-conformant but is rejected by the reference validator and cannot be written by the reference library. | MEASURED | `results/gsps_conformance_baseline.md` |
| B4a | **Attribute name correction.** (0070,0251) is `Pattern On Color CIELab Value`, **not** "Line Color CIELab Value", which does not exist in DICOM. The code constant `TAG_LINE_COLOR` was misnamed throughout and set the same tag twice in `_line_style`. | MEASURED | pydicom data dictionary |
| B5 | The `LineStyleSequence` macro has ten Type 1 attributes and `dciodvfy` enforces all ten. | MEASURED | caught omitting four of them |
| B6 | `highdicom` 0.28.1 can write GSPS: `hd.pr.GrayscaleSoftcopyPresentationState`, SOP class in `pr.SOP_CLASS_UIDS`. | MEASURED | `results/seg_writer.md`, re-verified |
| B7 | `highdicom` contains **zero** occurrences of `TextStyleSequence`, `LineStyleSequence`, `TextColorCIELabValue`, `LineColorCIELabValue`. Its only GSPS colour route is layer level. | MEASURED | grep over the installed package, re-verified |
| B8 | Therefore per-vertebra colour in a conformant GSPS writable with standard tooling **requires one graphic layer per vertebra**. | MEASURED | follows from B1, B2, B7 |
| B9 | We are not aware of a published study comparing GSPS against DICOM SEG rendering support across viewers. | LITERATURE, softened per review Comment 3.8. The earlier form quoted an exact PubMed count that an external reviewer could not reproduce, so it is now stated as a claim about our search rather than about the literature. | search recorded in the recon workflow |
| B10 | **Storage, measured not cited.** Conformant GSPS 12 KB, mean 11.1 KB over nine variants. DICOM SEG mean 15,501 KB over three objects, range 11,243 to 19,542. Ratio of means about **1300 to 1**. | MEASURED | `results/storage_comparison.md` |
| B10a | B10 is NOT like-for-like: a segmentation carries voxel extents across hundreds of frames, a presentation state carries a label and a two-point line per vertebra. The difference is information content, not overhead. The defensible claim is scoped to the task of conveying per-vertebra labels with a flag. | MEASURED, with the caveat stated | same |
| B11 | `highdicom` **0.28.1 is a real released artefact**, listed by `pip index versions` as both available and latest, and is what is installed. | MEASURED | review Comment 8 asserted this version does not exist; it does |
| B3d | **PS3.2 defines Standard Extended SOP Class.** Section 7.3 gives the rules, verbatim: a SOP class that "shall be a proper super set of one Standard SOP Class", "may include Standard and/or Private Type 3 Attributes beyond those defined in the IOD on which it is based", and shall "use the same UID as the Standard SOP Class on which it is based". So `dciodvfy`'s closing diagnostic names a conformant category. **That sentence is claimed, and an earlier version of this row wrongly withdrew it.** PS3.2 states verbatim: "IODs from a Standard Extended SOP Class may be freely exchanged between DICOM implementations since implementations unfamiliar with the additional Type 3 Attributes would simply ignore them." I had asserted this belonged to Specialized SOP Classes instead; it does not, and PS3.2 says close to the opposite of them, since a Specialized SOP Class carries a different UID. See G19. | VERIFIED against the primary standard | dicom.nema.org PS3.2 sect_7.3 |
| B16 | **IHE AIR does not place presentation states out of scope**, which an earlier draft claimed. AIR Revision 1.3, 8 August 2025, states verbatim: "This profile also does not address encoding results that lack machine-readable semantics (e.g., using Secondary Captures, or Softcopy Presentation States). Implementations that support such encodings as a fallback in addition to the methods required in this profile may refer to the IHE Consistent Presentation of Images Profile for some guidance." The profile's explicit out-of-scope list covers data flow, scheduling, non-imaging data and interactive use, and does not name presentation states. | VERIFIED against the primary document | `IHE_RAD_Suppl_AIR.pdf`, Rev. 1.3, line 265 |
| B12 | **A second, independent validator disagrees.** DCMTK's `dcmpschk`, written specifically for presentation states, **passes** the text colour route that `dciodvfy` rejects. Across nine variants the two agree on seven and disagree on exactly the two that use text colour. | MEASURED | `scripts/cross_validate.py` |
| B13 | Both validators agree on genuine defects: each independently fails the `asis` variants, `dcmpschk` naming the cause as `instanceNumber absent or empty in presentation state`. | MEASURED | same |
| B14 | **The conformance defects stop rendering.** `dcmp2pgm`, the reference GSPS renderer, refuses the `asis` variants and produces no output. | MEASURED | `results/render_matrix.md` |
| B14a | **Isolated to one attribute.** Restoring only `InstanceNumber`, changing nothing else, makes the object render, byte identical to the conformant variant. The deployed pipeline's 38 objects all lack it while rendering correctly in their target viewer. | MEASURED | same |
| B15 | **`dcmp2pgm` draws no GSPS annotations at all.** Removing all 19 annotation items leaves the rendered bitmap byte identical; displacing all 57 objects by 120 px leaves it byte identical. The renderer applies the greyscale pipeline and ignores the Graphic Annotation Module. | MEASURED | `results/render_annotation_probe.md` |
| B15a | The 237,376 differing pixels are the **greyscale pipeline**, not annotations. They span **100.0 percent of rows** (1119 of 1119) at 41.4 percent of pixels, and applying the presentation state collapses the image from **256 distinct grey levels to 16**. That is the VOI LUT, the shutter and the displayed area. | MEASURED | same |
| B15b | **Byte-identical output across the three colour routes is therefore true by construction, not a finding.** A renderer that draws no annotations cannot draw them in different colours. The earlier reading is retired as G17. | MEASURED | same |
| B15c | **The corrected, and stronger, statement.** The DCMTK toolchain offers no scriptable renderer that draws GSPS annotations. `dcmp2pgm` ignores them; DICOMscope draws them and is a Java GUI. A practitioner has no headless, reproducible way to verify what their annotations will look like using the reference toolkit. | MEASURED, plus DCMTK's own documentation | same |

## C. Geometry

| # | Claim | Status | Source |
|---|---|---|---|
| C1 | NIfTI to DICOM CT conversion round-trips to a max world-coordinate error of 4.55e-12 mm, with 0 of 189,267,968 voxels mismatched and 0 HU error. pydicom and SimpleITK/GDCM agree. | MEASURED | `--roundtrip --simpleitk`, `results/orchestrator_verification.md` |
| C2 | On an axial series the vertebrae span 215 mm along the slice normal, so no single axial slice can contain them. Sagittal reformat brings the mean absolute offset to 4.6 mm. | MEASURED | `results/public_gsps_geometry.md` |
| C3 | A single-slice GSPS therefore presupposes a sagittal or reformatted acquisition. | MEASURED | follows from C2 |
| C4 | VerSe composition: 60 axial, 56 isotropic, 15 sagittal, 71 unlabelled, of 202. | MEASURED | filename census |

## D. The confidence score, experiment E1

| # | Claim | Status | Source |
|---|---|---|---|
| D1 | Both step models are region-based nnU-Net, `regions_class_order` present, no background channel, so per-region sigmoid channel i carries class `regions_class_order[i]`. Step 1 has 9 channels, step 2 has 11. | MEASURED | checkpoint `dataset.json`, and `nnUNetPredictor.label_manager.foreground_regions` |
| D2 | Channel 8 is `sacrum` and channel 9 is `canal`, which the deployed `json_generator.py` prints as `vertebrae_type_3` and `vertebrae_type_4`. All eleven printed names are wrong. | MEASURED | same |
| D3 | The retired region mapping reads the **sacrum** channel for every lumbar vertebra and the **canal** channel for the sacrum. | MEASURED | `python -m spinelab.confidence.channels` |
| D4 | Anatomical parity does not determine the channel: the model's alternation follows detection order. Measured instance, T7 (odd) on the even channel at 0.963 against 0.0006 on the odd channel. | MEASURED | batch case record |
| D5 | **FINAL, 155 cases, 2241 predicted, 1845 matched within 20 mm, 373 wrong.** No channel-selection rule produces a usable flag. All nine arms fall between 0.427 and 0.581, and a ceiling given the labels and honestly held out reaches 0.570. The provisional claim this replaces is retired as G15. | MEASURED | `python scripts/e1_ablation.py --run-dir runs/verse_batch_01` |

| arm | AUC | naive 95% | **clustered 95%** | common 1828 |
|---|---:|---|---|---:|
| `region_retired`, published rule | 0.516 | [0.483, 0.549] | **[0.479, 0.553]** | 0.519 |
| `parity_name`, continuous anatomical parity, **a rule nobody shipped** | 0.572 | [0.539, 0.606] | **[0.480, 0.661]** | 0.572 |
| `parity_region_deployed`, **THE RULE THAT SHIPPED** | 0.427 | [0.395, 0.458] | **[0.342, 0.516]** | 0.425 |
| `parity_sequence`, uncalibrated | 0.481 | [0.449, 0.514] | **[0.398, 0.562]** | 0.481 |
| `parity_sequence_inverted`, global sign flip | 0.488 | [0.456, 0.521] | **[0.413, 0.574]** | 0.486 |
| `parity_sequence_phased`, best arm | 0.581 | [0.547, 0.614] | **[0.531, 0.641]** | 0.579 |
| `mapping_free_top1` | 0.576 | [0.543, 0.609] | **[0.523, 0.636]** | 0.575 |
| `mapping_free_margin` | 0.486 | [0.453, 0.519] | **[0.435, 0.536]** | 0.486 |
| `argmax_mean` | 0.579 | [0.545, 0.612] | **[0.527, 0.639]** | 0.579 |

Ceilings, all chosen **with** the labels, so each is quoted in sample and held out.
Held out means fitted on half the **cases** and scored on the other half, both
directions, 20 repetitions giving 40 folds. Split by case, not by vertebra, because
vertebrae within a case are correlated.

| ceiling | in sample | held out (40 folds) | what it is |
|---|---:|---:|---|
| `best_fixed_channel` | 0.566 (channel 5) | **0.550** (sd 0.044) | exact: exhaustive over all 11 channels on all 1845 vertebrae |
| `best_name_mapping` | 0.635 (26 levels) | **0.570** (sd 0.033) | coordinate ascent, 11 starts, over an 11^26 space. **Not** a bound |
| `best_name_mapping` on **shuffled labels**, 1000 reps | 0.594 mean, 0.611 p95, **0.629 max** | n/a | the same search with all signal destroyed |

| # | Claim | Status | Source |
|---|---|---|---|
| D5a | **The channel mapping bug is real but correcting it does not produce a usable flag.** The published rule scores 0.516 and the best arm 0.581, an improvement of 0.065. **The 'intervals that barely fail to overlap' reading is withdrawn**: under case-level clustering the paired delta spans zero, D5j. | MEASURED | same |
| D5b | **The limit is not the mapping, and this now survives a held-out test.** A per-level channel mapping fitted with the labels reaches 0.635 in sample, which looks like real headroom. It is not: held out on unseen cases it is worth **0.570**, which is *below* `parity_sequence_phased` at 0.581. The exact fixed-channel ceiling drops 0.566 to **0.550** under the same treatment. No channel-selection rule, including one given the answers, beats the rules already deployed. | MEASURED | same |
| D5c | **Why the in-sample ceiling must not be quoted, stated precisely.** The identical search on **shuffled** labels, where no signal exists by construction, reaches **0.594 mean, 0.611 p95, 0.629 max over 1000 repetitions**. So most of the in-sample 0.635 is reproducible from nothing: it is dominated by the optimism of fitting 26 free parameters to 1845 points. | MEASURED, `E1_NULL_REPS=1000` | same |
| D5c-i | **The excess above the null is nonetheless real.** No permutation of 1000 reached 0.635, the maximum being 0.629, so the exact permutation p is (0+1)/(1000+1) = **0.001**, the smallest attainable at this rep count. The search therefore does find genuine structure. An earlier phrasing of D5c and G16 called the 0.635 "almost entirely" and "pure" optimism; the first is defensible, the second was too strong, and both are replaced by this row. | MEASURED | p follows from max alone: if no draw reaches the observed value, p = 1/(N+1) whatever the rest of the distribution is |
| D5c-ii | **The real structure does not generalise, which is the finding.** Fitted with the labels and scored on unseen cases the same mapping is worth **0.570**, below `parity_sequence_phased` at 0.581. Significant and useless are not in tension here: the search reliably finds level-specific structure in the data it is fitted on, and that structure does not transfer. | MEASURED | 40 folds, split by case |
| D5c-prev | **Superseded.** The earlier `best_per_level` (0.536) was reported as a bound and was not one, which showed as it landing below `parity_name`. It maximised the within-level AUC and reported the global AUC of that choice, and it dropped levels that were all-correct or all-wrong. Both defects fixed; see commit `f82ca2c`. Retained here because the ledger records what was claimed, not only what survives. | RETIRED | `tests/test_e1_oracles.py` now asserts the properties whose absence exposed it |
| D5d | Per-case phase estimation does real work and is **not** a global sign flip: uncalibrated 0.481, globally inverted 0.488, per-case phased 0.581. The estimated phase varies across cases, 105 at offset 1 and 40 at offset 0. The reviewer's inference that it was a disguised sign error rested on the n=18 numbers, which were noise. | MEASURED | same |
| D5e | Arms scored on different populations are not comparable, so every arm is also scored on the **1828** vertebrae where all eight are defined. The ranking is unchanged, so it is not an artefact of `parity_name` dropping its 17 undefined cases. | MEASURED | same |
| D5f | **The arm previously labelled the deployed rule was not the deployed rule.** `parity_name` uses continuous anatomical parity. The deployed `utils/confidence_calculator.py::get_vertebra_channel` restarts parity at C1, T1 and L1, so the two pick a different channel for **1665 of 1845 vertebrae, 90.2 percent**, agreeing only on C1 to C7 and SACRUM. Added as the ninth arm `parity_region_deployed`. See G20. | MEASURED | `channels.channel_region_restart`, pinned independently by `tests/test_channels.py` |
| D5g | **The rule that shipped is the worst of the nine**, AUC 0.427, naive [0.395, 0.458]. Its **clustered** interval **[0.342, 0.516] contains 0.5**, so the correct statement is *indistinguishable from chance*, NOT *below chance*. The naive interval would have supported the stronger claim and the stronger claim would have been wrong. | MEASURED | same |
| D5h | **The range in the paper is now 0.427 to 0.581 across nine arms**, not 0.481 to 0.581 across eight. | MEASURED | same |
| D5i | **Intervals now respect clustering.** 1845 vertebrae come from 155 cases, about twelve each, sharing a patient, a scanner, a field of view and one pass of the same model. Hanley and McNeil assume independence, so the naive interval was too narrow. A 2000-repetition case-level cluster bootstrap widens every interval by 1.12 to 2.78 times. The held-out split already resampled CASES for this reason; the intervals did not, which is the inconsistency review caught. | MEASURED | `cluster_bootstrap` in `scripts/e1_ablation.py` |
| D5j | **The repair's effect is not separable at this sample size.** Paired delta, best arm minus published rule: **[-0.004, 0.144], P(delta <= 0) = 0.032**. It crosses zero. | MEASURED | same |
| D6 | Per-vertebra level accuracy on matched vertebrae, out-of-distribution CT: **79.8 percent** (1472 of 1845). | MEASURED | same |
| D7 | **17.7 percent** of predicted vertebrae (396 of 2241) fall beyond the 20 mm tolerance and cannot be scored. Verification bias remains, but is far smaller than the provisional 42 percent. | MEASURED | same |

## E. The spline outlier detector, experiment E2

| # | Claim | Status | Source |
|---|---|---|---|
| E1 | The deployed residual is **in sample** for regions of four or more levels. True leave one out applies only to regions of one to three, and then against a global spline. The abstract's "leave-one-out" description is wrong for the normal path. | MEASURED | `results/spline_detector_verified.md` |
| E2 | The in-sample residual is flat at roughly 0.2 mm across a 0 to 80 mm true displacement. The leave-one-out residual tracks displacement, 0.553 to 78.553 mm. | MEASURED | synthetic, 432 studies per condition |
| E3 | Paired injection: a single-level shift is flagged at its own site 5.1 percent against a 22.7 percent control. **Worse than chance.** | MEASURED | same |
| E4 | Whole-column off-by-one scores 97.0 percent against a 97.0 percent control. Zero discrimination. | MEASURED | same |
| E5 | False positives on error-free chains: 7.4 percent per vertebra, 91.7 percent of studies. Closely reproduces the 11.1 percent and 97.4 percent measured on real shipped output. | MEASURED | same, plus the GSPS colour census |
| E6 | A 3.0 mm minimum-residual guard removes all false positives and all detections. A magnitude guard silences an in-sample detector rather than fixing it. | MEASURED | same |
| E7 | For ddof=0 pooling the algebraic bound is sqrt(n-1), about 4.12 at n=18. The observed z of 651.46 comes from the 0.1 px standard-deviation floor. | MEASURED | logs plus derivation |
| E8 | True leave one out detects 75.0 percent at 40 mm and 100.0 percent at 80 mm, against 2.1 and 7.6 percent for the deployed rule, at a cost of 50.0 percent endpoint false positives. | MEASURED | same |

## F. Provenance and attribution

| # | Claim | Status | Source |
|---|---|---|---|
| F1 | The vertebral level assignment is upstream TotalSpineSeg code: 289 of 307 substantive lines, 94 percent, appear verbatim in `totalspineseg/utils/iterative_label.py`. It must be attributed, not claimed. | MEASURED | `results/level_assignment.md` |
| F2 | `region_max_sizes` permits six lumbar levels, so L6 is representable, but thoracic max equals default at 12, so **T13 cannot be produced**. | MEASURED, from code structure; empirical confirmation pending | same |
| F3 | When no landmark disc is found the algorithm writes no output and does not flag it. | MEASURED | same, plus `step1_no_landmark` in the batch |
| F4 | Output range is C1 to L6 plus sacrum, not C1 to L5 as the abstract states. | MEASURED | same |

## G. Retired claims

| # | Claim | Why retired |
|---|---|---|
| G1 | "Confidence separated broken cases (0.12) from acceptable (0.28 to 0.31)." | The score was computed from the sacrum channel for lumbar levels. In-sample AUC is 0.478 image level, 0.528 per vertebra. Void regardless of splitting. |
| G2 | "Processing averaged 100 seconds per study on a single 24 GB GPU." | Untraceable. A transcription of a third-party README table. No timing instrumentation exists anywhere in the project. |
| G3 | "Leave-one-out residuals." | The normal path is in sample. See E1. |
| G4 | "First end-to-end DICOM-in / DICOM-out spine labelling with vendor-neutral PACS rendering." | Four independent prior systems, two FDA cleared. |
| G5 | "Chen et al. 2025, SpineCheck" as a mislabel-detection comparator. | Does not exist. The real SpineCheck is Ilkhan et al., Informatics 2025;12(4):140, a scoliosis Cobb-angle platform. |
| G6 | VerSe published means of 94.3 and 96.6 percent. | Those are the best single algorithms. Across-algorithm means are 61.6 +/- 43.6 and 72.8 +/- 39.96 percent. **Verified 2026-07-31 against the primary source**, Table 5 of arXiv:2001.09193v4, which prints "2019 61.4 +/-44.5 83.3 +/-30.7 61.6 +/-43.6 82.4 +/-31.6" and "2020 77.7 +/-35.7 93.9 +/-21.0 72.8 +/-39.96 94.4 +/-17.5" for Public/Hidden by All/Top-5. Note v2 does not contain them: it is the VerSe19-only version, so checking the wrong arXiv version would have falsely condemned a correct number. |
| G7 | "torch 2.8.0+cu128 cannot run on Tesla P40." | `sm_61` is in the compiled arch list. The release note covers sm50 to sm60. |
| G8 | "Leave-one-out leverage over-flags region endpoints in the deployed detector." | True only under real leave one out, 50.0 percent. The deployed in-sample path flags interior points more, 9.7 versus 2.5 percent. |
| G9 | The 558-image rating pass as radiologist validation. | One observer, one 59 minute session, median 2.37 s per image, unrandomised order, filenames visible, comments are keystroke artifacts. Describe as a developer screening pass. |
| G10 | "The trained checkpoints are this project's own training run." | Wrong. They are the upstream released TotalSpineSeg weights, trained on a Compute Canada cluster on an A100. Inferred from `dataset.txt` and `progress.png`, which ship inside the released model folder and are upstream's records. See H2a. |
| G11 | "The spline outlier detector does not work." | Too coarse, and it misattributes the failure. The **design** is leave one out residuals on regional splines, and that design works: 75.0 percent detection at 40 mm and 100.0 percent at 80 mm. The **shipped implementation** computes an in-sample residual for regions of four or more levels, which is what cannot work. The correct statement is that the implementation deviates from the design. See E1 and E8. |
| G12 | **"Text colour is not in the GSPS IOD, while line and layer colour are."** The paper's headline container claim. | **Wrong.** PS3.3 C.10.5 lists `TextStyleSequence`, `LineStyleSequence` and `FillStyleSequence` all as Type 3 in the Graphic Annotation Module, which is in the GSPS IOD. I treated a `dciodvfy` warning as evidence about the standard when it is evidence about the validator's IOD tables. Caught by adversarial review, then verified against dicom.nema.org. The corrected finding is in B1 to B4a and is stronger: the standard permits per-object colour, the reference library cannot write it, and the reference validator rejects one of the two routes it permits. |
| G13 | "Line Color CIELab Value (0070,0251)." | No such attribute exists. (0070,0251) is `Pattern On Color CIELab Value`. Misnamed in the code, the ledger, the manuscript and the supplemental. |
| G14 | Describing `PresentationPixelSpacing` (0070,0101) flatly among "required attributes absent". | It is **Type 1C** in the Displayed Area module, conditional on `PresentationSizeMode` being TRUE SIZE. Precision matters in a paper whose credibility rests on attribute-level accuracy. |
| G15 | **"Varying only channel selection moves flag validity from below chance to usable."** Carried in the SPIE abstract, the supplemental and the manuscript. | **Wrong, and contradicted by the completed run.** It rested on 18 of 202 cases, where `parity_sequence_phased` read 0.865 against `region_retired` at 0.418. On all 155 scorable cases the same two arms read 0.581 and 0.516. The provisional gap was noise from 18 cases. The corrected and durable finding is the reverse: the mapping bug is real and provable from the checkpoint's own labels, and repairing it does **not** yield a usable flag. See D5, D5a and D5b. This is the third time in this project that an early partial sample produced a confident claim that the full run destroyed, which is the reason the ledger exists. |
| G16 | The in-sample label-informed ceiling of 0.635 as evidence of headroom. | Not headroom: the identical search on **shuffled** labels reaches 0.594 on average over 1000 repetitions, so most of the figure is the optimism of fitting 26 parameters to 1845 points, and held out the mapping is worth 0.570. **This row previously said the number was "search optimism" full stop, which overstated it in the other direction.** No permutation of 1000 reached 0.635, so the exact permutation p is 0.001 and the excess above the null is real. The precise statement is D5c, D5c-i and D5c-ii: the structure is genuine, and it does not generalise. |
| G17 | **"The annotations themselves render, so the labels and leader lines are drawn. Only the colour is discarded."** Carried in both deliverables after the 2026-07-31 rendering measurement. | **Wrong.** A specific mechanism inferred from an aggregate signal without isolating it, which is the fourth time in this project and the exact failure mode this ledger exists to catch. Isolating it takes one command: deleting every annotation, and separately displacing every annotation by 120 px, both leave the bitmap byte identical. The 237,376 pixels are the VOI LUT, and the decisive tell was available all along, 256 grey levels becoming 16. Caught by round two adversarial review reading `dcmp2pgm`'s documentation, which states that annotations are not visible in its output. The corrected finding is in B15 to B15c and is stronger. |
| G18 | **Figure 3's two panel titles.** Left: "all levels correct". Right: "two anatomically impossible placements", with the points coloured `CRIT if conf < 0.35 else GOOD` and a code comment asserting that "correctly placed versus impossible are exactly good versus critical". | **Both wrong, and the right panel argued the opposite of this paper's own section 3.3.** For the right-hand case the ground truth holds C1 to T6 only: **eight** of twelve assigned names are levels absent from the volume, seven carrying confidence 0.82 to 0.96 and drawn as if correct, while the flag fired on two, one of which (T1) is a level that IS present. The colour was a confidence threshold relabelled as anatomy. For the left-hand case, C7 and SACRUM are absent from the ground-truth mask, so 17 of 19 names match and "all correct" is unverified. Found by an adversarial figure audit; the numbers here were re-derived directly from the annotation records and the VerSe GT cache. |
| G19 | **"PS3.2 does not say Standard Extended objects may be freely exchanged; that sentence belongs to Specialized SOP Classes."** Asserted in ledger row B3d, as a correction to an adversarial reviewer who had it right. | **Wrong, and it withdrew the strongest sentence available.** PS3.2 3.11.3 states: "IODs from a Standard Extended SOP Class may be freely exchanged between DICOM implementations since implementations unfamiliar with the additional Type 3 Attributes would simply ignore them." Of Specialized SOP Classes PS3.2 says close to the reverse, since they carry a different UID. Two notes on how this was found, because both matter. The reviewer supplied the sentence but cited it to section 7.3, where it is not; three separate queries against 7.3 returned nothing, and only a phrase search located it in 3.11.3, the Definitions chapter. Their quoted wording was also slightly off, "implementations that do not recognize" for "implementations unfamiliar with". So the substance was theirs and the citation is corrected here. This is the second time in this project that a claim about the standard was made from a paraphrase rather than the text, after G12. |
| G21 | **Four of the eleven references were wrong**, in ways only a check against the primary record finds. Ref 2 and ref 10 had truncated titles that removed what the paper was about. Ref 10 named **Rhee DJ** as second author where the record says **Nguyen C**, and carried no volume or pages. Ref 4 and ref 11 had **titles that were paraphrased or invented from the acronym**: VERIDAH is "solving enumeration anomaly aware vertebra labeling across imaging sequences", not "vertebra identification and hallucination-free labelling". | **Corrected 2026-07-31.** Each of the eleven checked against PubMed, the publisher DOI or the arXiv abstract page, not against a search summary. Verified correct as written: 1, 5, 6, 7, 8, 9. This is the same failure as G5, where a comparator was cited that did not exist: writing what a title plausibly says instead of what it says. |
| G20 | **"The live server's `confidence_calculator.py` uses the CORRECT parity mapping."** Asserted in `CLAUDE.md` finding 2 and in two places in these notes, and carried into the paper as the label "the deployed rule" on the `parity_name` arm. | **Wrong.** `get_vertebra_channel` reads the integer inside the vertebra's own name and tests its parity, so counting restarts at C1, T1 and L1: C7 and T1 collide, and the rule is wrong from T1 downwards, not just for the lumbar spine. Measured as `parity_region_deployed`: **AUC 0.427, the worst of the nine**, clustered interval containing chance. `tests/test_channels.py::test_the_deployed_confidence_calculator_restarts_parity_at_each_region` has asserted this since the suite was written and its docstring says so outright; it passed on every run of the suite while the paper carried the contradicting label. Nothing catches a wrong label except reading it. ("Passed 262 times" stood here until round four. Nobody ever counted the runs, and it was the suite size at the time, not a tally. A rhetorical number is still a number.) |

## H. Data and permissions

| # | Item | Status |
|---|---|---|
| H1 | VerSe 2019 and 2020, CC BY-SA 4.0, anonymous OSF download. 202 of 202 cases on disk, 34.07 GB. | MEASURED, clean of TotalSpineSeg training data |
| H2 | SPIDER, spine-generic, whole-spine and MRSpineSeg are in **upstream TotalSpineSeg's** training data and must never be used as held-out sets. | MEASURED from the upstream training manifest |
| H2a | The checkpoints are the **upstream released TotalSpineSeg weights**, not locally trained. `fold_0/debug.json` records `hostname ng20104.narval.calcul.quebec`, a Digital Research Alliance of Canada cluster used by NeuroPoly, on an `NVIDIA A100-SXM4-40GB` with `torch 2.3.1` and 1000 epochs. The deployment machine was a Debian 11 box with dual Tesla P40. Upstream publishes this exact artefact at `neuropoly/totalspineseg/releases/download/r20241005/`. | MEASURED |
| H2b | Consequence for clearance: the weights are openly released upstream, so the channel-selection ablation runs public weights on public data with our own analysis and needs no third-party clearance. | follows from H2a |
| H3 | aycan clinical cohort, 558 rated images, 80 patients. Research use **permitted by aycan in writing**, held in the author's email, reported 2026-07-31. | CLOSED, **on the author's report**. The thread has not been seen by this ledger, and the artefact is the email itself. This is the basis for the permission sentence in Methods 2.1 and for the Data availability statement. No venue considered here collects the document; see H5c. |
| H3a | **Four distinct permissions, not one.** (1) data use, the 558 images; (2) **publishing the findings about the deployed pipeline**; (3) code and IP release, work authored as an employee; (4) affiliation and authorship. | **All four reported granted in writing 2026-07-31**, held in email. |
| H3b | **The system under study is a deployed pipeline, not a released product.** An internal service integrated with a viewer, not a cleared or shipped product feature. Confirmed by the author 2026-07-31. Consequence for wording: describe it as a deployed pipeline or service throughout, never as a product, and reserve "defect" for the specific technical sense of non-conformance against an IOD. | CONFIRMED by the author |
| H3c | **Sole author.** No co-author meets ICMJE criteria for this work. | CONFIRMED by the author 2026-07-31 |
| H4a | **Affiliation is University at Buffalo School of Management**, ORCID 0009-0003-6878-1712, work performed while at aycan. aycan is a competing-interest declaration, not the submitting affiliation. | CONFIRMED by the author 2026-07-30 |
| H5 | **SPIE requires the clearance attestation at ABSTRACT stage, not only at manuscript stage.** Abstract Submission Guidelines, verbatim: authors must verify that "all clearances, authorizations, and licenses needed for **submission and publication** of this paper have been obtained and all reused work is properly cited." The manuscript guidelines add "Company or government clearance must be finalized at the time of submission" and advise allowing **a minimum of 60 days**. | VERIFIED on the live SPIE pages 2026-07-30 |
| H5a | Consequence: the reading that the 5 August gate covers only data use, with the rest deferrable to the 27 January manuscript, **does not hold.** The August attestation covers publication, not just review. | follows from H5 |
| H5b | **SPIE collects no clearance document at either stage.** Both are attestations made in the submission form; there is no upload field. The written permission exists to protect the author, not to satisfy a form. Email is a sufficient written record. | VERIFIED on the live SPIE pages 2026-07-30 |
| H5c | **Archive the permission thread outside any aycan mailbox.** | **CLOSED 2026-07-31, author's decision, no action taken.** IJMI uploads nothing. Guide for authors, verbatim: "Written consents must be retained by the authors. They should not be provided to this journal unless this is specifically requested in exceptional circumstances, for example, when a legal issue arises." SPIE was the same, an attestation with no upload field (H5b), so no venue this project has considered collects the document. Residual risk, stated rather than mitigated: the same guide says the journal "reserves the right to request additional evidence", and the author is a former employee whose access to that mailbox can lapse. If it is ever requested and the mailbox is gone, the artefact is gone. That trade is the author's to make and has been made. |
| H4 | TotalSegmentator MRI cannot score level assignment: its `total_mr` label set groups the spine into one `vertebrae` class. | MEASURED from the authoritative class map |
