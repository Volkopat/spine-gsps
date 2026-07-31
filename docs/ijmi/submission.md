# Separating conformance from trustworthiness: an end-to-end audit, and five checks, for an AI result delivered into a clinical archive

**Digvijay Patil**

University at Buffalo School of Management, Buffalo, NY, USA

ORCID 0009-0003-6878-1712

Correspondence: Digvijay Patil, University at Buffalo School of Management, Buffalo, NY, USA.

---

## Highlights

*Submitted as a separate file. Five bullets, each within 85 characters including spaces.*

- All 38 objects a deployed AI service delivered failed independent validation.
- Archive and DICOMweb accepted all 38; the target viewer displayed them anyway.
- Its per-vertebra quality flag fired on 97.4% of the studies it delivered.
- Nine readings of one model output span 0.427 to 0.581 AUC; the worst one shipped.
- Conformance and trustworthiness fail separately; the service monitored neither.

---

## Summary Table

**What was already known on the topic**

- Automated delivery of AI results into clinical archives is in commercial use, and the IHE AI Results profile names softcopy presentation states as an encoding that lacks machine-readable semantics and does not address them.
- Quality signals that accompany AI results are normally validated as a property of the model, on the data the model was developed on, rather than as a property of the service that delivers them.

**What this study added to our knowledge**

- All 38 objects a deployed service delivered failed independent validation with seven required-attribute errors each, yet the archive indexed every one, DICOMweb returned them intact, and the viewer they were built against displayed them, so nothing in the delivery path detected it.
- The accompanying per-vertebra quality flag fired on 97.4 percent of delivered studies, and nine readings of the same model output spanned 0.427 to 0.581 AUC, the rule that shipped being the worst of the nine and indistinguishable from chance.

*Editorial note. If the editor requires flat bullets rather than the two headings, retain the two bullets under "What this study added" and add: "When no landmark is found the service writes no output and raises no flag, so its quality layer is silent exactly where it is most needed."*

---

## Abstract

**Background.** Artificial intelligence (AI) results arrive in clinical archives as standardised objects whose conformance, and whose embedded quality signal, are trusted rather than measured.

**Objective.** To measure both independently in a deployed clinical AI service and its quality flag.

**Methods.** We audited 38 unmodified DICOM presentation states, from real clinical studies, that a deployed service returned into a clinical archive: conformance by two independent third-party validators, ingestion into an open-source archive, DICOMweb retrieval, and reference-renderer loading. The flag was scored on 1845 vertebrae in 155 public benchmark cases, out of distribution by modality, varying only how the score was read from the sigmoid outputs, across nine arms with case-clustered intervals, and on 432 synthetic studies under paired error injection.

**Results.** Neither validator passed any object: all 38 carried the same seven required-attribute errors, and the reference renderer refused every one. The archive ingested all 38, DICOMweb returned them, and in deployment they rendered in their target viewer: nothing in the delivery path detected it. The flag fired on 37 of 38 studies (97.4 percent) and 11.1 percent of vertebrae, its check measuring the residual in sample on its normal path; an injected single-level error was flagged at its own site in 5.1 percent of studies against a 22.7 percent paired control. Nine readings of one model output gave AUC 0.427 to 0.581, none usable: the shipped rule scored worst, its case-clustered interval 0.342 to 0.516 containing 0.5, indistinguishable from chance, and the best gained 0.065 over the published rule, an interval spanning zero.

**Conclusions.** Conformance and trustworthiness are independent properties of a delivered AI result: acceptance by archive, transport and viewer is no evidence of either. We give five checks a receiving health system can run on its own delivery path, each derived from a measurement reported here.

---

## Keywords

Health information interoperability; Health information standards; DICOM; Artificial intelligence governance; Quality assurance, health care; Clinical information systems

---

## 1. Introduction

Health systems increasingly receive artificial intelligence output not as a report or a screen but as a standardised object: a DICOM instance returned into the picture archiving and communication system (PACS), indexed by the archive and drawn by whichever viewer the clinician opens. Result delivery of this kind is already in commercial use, including in products with regulatory clearance [1,2]. Two properties of the delivered object then decide what the receiving site actually gets: whether it conforms to the standard it claims to speak, and whether the quality signal it carries can be trusted at the point of use. The first is an interoperability question, the second one of AI governance, and the accuracy of the model behind the object answers neither.

A presentation state is a natural carrier for a result drawn over a series already held in the archive, because it requires no segmentation support in the receiving system. The IHE AI Results profile, Revision 1.3 of 8 August 2025 [3], converges instead on Structured Reporting and Segmentation, stating that it "does not address encoding results that lack machine-readable semantics (e.g., using Secondary Captures, or Softcopy Presentation States)". Presentation states are contemplated as a fallback, not excluded: the profile's explicit out-of-scope list does not name them.

Container and contents are independent properties, and a service can satisfy either while failing the other. We examine one deployed service, internal and integrated with a commercial viewer, not a cleared product. We follow the 38 presentation states it emitted through validation, delivery and rendering, and test its per-object quality flag on public benchmark data and on synthetic chains with injected errors of known size.

We contribute three measurements: how five authorities disagree on encoding a per-object flag; a controlled ablation separating a model-interface defect from model accuracy, with case-clustered intervals, a permutation null and a held-out ceiling; and a paired synthetic characterisation showing that the consistency check's estimator, not its threshold, governs whether it can respond at all. From these we derive five checks a receiving site can run on its own delivery path (Table 5). Priority is claimed for no component: not presentation-state emission, not per-object quality estimation, and not the level assignment, upstream code [4], 289 of 307 substantive lines verbatim.

## 2. Methods

### 2.1 Setting and materials

The system under study is an internal deployed service, integrated with a commercial viewer, returning annotated results to a clinical archive as DICOM Grayscale Softcopy Presentation States; its 38 emitted objects, from real clinical studies, are examined exactly as the service wrote them, and every defect reported was already in the delivered files (Appendix A.0). aycan, which operated the service, permitted this examination and its publication in writing; the analysis uses object metadata and derived statistics only, and is not human-subjects research. The public substrate is VerSe 2019 and 2020 [5], 202 cases from OSF (nqjyw, t98fz) under CC BY-SA 4.0. No model was trained or modified here: the checkpoints are the openly released upstream TotalSpineSeg weights [4] and the level assignment is upstream code, 94 percent verbatim, attributed rather than claimed. Those weights declare MR as their only training modality and the public cases are CT, so every public-data result is out of distribution by construction and bounds robustness rather than the deployment. Datasets present in upstream training data (SPIDER, spine-generic, whole-spine, MRSpineSeg) were excluded. Public volumes were converted from NIfTI to DICOM by our own converter, whose world-coordinate round trip, in Appendix E, checks the conversion and is not a finding.

### 2.2 Conformance, delivery and rendering

Conformance is never adjudicated by us. Every object is scored by dciodvfy (dicom3tools, snapshot 20260701065818), an independent third-party validator, and cross-checked against DCMTK 3.7.0 dcmpschk, a second independent validator written specifically for presentation states. The identification rate is scored by the benchmark organisers' own code, vendored with its licence rather than reimplemented. The analysis code around those two is ours, and is released.

Rendering is measured rather than inspected: bitmaps from dcmp2pgm, DCMTK's reference headless renderer, are hashed and diffed, so a rendering claim rests on a hash, not a screen. What it draws is established by probe: every annotation item is deleted, and separately displaced, and the bitmap re-hashed. Delivery is measured against Orthanc 1.12.11, over its REST API with read-back and over QIDO-RS and WADO-RS retrieval, with the DICOM network path checked separately by storescu. Library capability is tested against the installed highdicom 0.28.1 package [6], not its documentation. The three colour routes are emitted in isolation and in combination, with annotation content held byte identical across variants.

### 2.3 Quality-signal ablation

All nine arms are scored from one batch run, so the pipeline and its segmentations are fixed and only the confidence rule varies. Seven keep the deployed confidence formula and change only which output channel it reads, among them the shipped rule and the rule behind the published numbers; two mapping-free arms drop the name-to-channel mapping entirely, scoring the top channel's mean and the top-1 minus top-2 margin. One estimates the model's alternation phase per case from the probabilities alone, using no labels. Both step models are region-based, so the network applies a per-region sigmoid [7]: the channels are independent probabilities that do not sum to one, two alone reaching 1.87 on one measured vertebra. With no categorical distribution to normalise [8], the channel is a free interface decision, which is what makes the question well posed.

The outcome label is ground-truth correctness, not a human rating: a vertebra is wrong when the nearest ground-truth centroid within the organisers' 20 mm tolerance carries a different level, their rule applied in our code to centroids recomputed from the released masks. Discrimination is AUC with naive and case-clustered 95 percent intervals, the latter from a 2000-repetition bootstrap resampling cases rather than vertebrae, because the 1845 scored vertebrae come from 155 cases. Label-informed ceilings, exhaustive over channels and coordinate ascent over per-level mappings, are quoted in sample and held out: fitted on half the cases, scored on the other half, both directions, 20 repetitions giving 40 folds. The same search is repeated on shuffled labels, 1000 repetitions, giving its null and an exact permutation p.

### 2.4 Geometric consistency check

The check is implemented twice, as deployed and as specified. The deployed arm is reverse engineered from source, verified against a trace of the original, and instrumented to emit the residual separately from the confidence it is multiplied into. Evaluation is on 432 synthetic studies with known ground truth, in a paired design: each rate is measured on the same studies before and after a known error is injected, so the control is the same population. The masking analysis is the median over 144 studies per displacement step, not the full 432. The synthetic design bounds what the estimator can detect in principle, not a clinical rate.

### 2.5 AI use in the research process

The harness, emitters, analysis scripts and tests were largely written by a large language model coding agent (Claude Opus 5, Anthropic, used through Claude Code, July 2026). Three controls make its output checkable: the two independent validators, the vendored benchmark scorer, and a released claims ledger tying every number to its command. Manuscript-preparation use is declared separately.

## 3. Results

### 3.1 What the health system received

None of the 38 presentation states the deployed service emitted passed independent validation. Each carried the same seven attributes the validator scores as absent, five required and two conditional, plus six it places outside the information object definition (Table 1). The validator calls those six an extension, a Standard Extended SOP Class; the seven absences are not.

Delivery was measured at every hop (Table 1). Orthanc 1.12.11 indexed all 38 over REST and accepted an emitted object again over C-STORE; QIDO-RS and WADO-RS returned every one with its colour route intact. All 38 rendered correctly in their target viewer, on the deployment's operating record rather than a measurement here. A second validator, dcmpschk, also failed all 38, on a further attribute. Acceptance and conformance were fully dissociated, and nothing in the delivery path reported the difference.

Refusal isolates to a single attribute. A reconstruction of the deployed encoding on public data, lacking InstanceNumber (0020,0013), is refused outright by the reference renderer, which writes zero bytes and names that attribute. Restoring that one Type 1 attribute and nothing else makes it render, byte identical to a from-scratch conformant object, SHA-256 prefix 5ea1ecb666bc6382 (Figure 1).

Other object classes validate clean, and our own emitter is not exempt (Table 1).

### 3.2 Why consulting the authorities does not resolve it

Encoding a per-object flag has no single correct answer, because the five authorities an implementer would consult disagree (Table 2).

The standard permits every route. PS3.3 C.10.5, the Graphic Annotation Module of the presentation state IOD, lists TextStyleSequence (0070,0231), LineStyleSequence (0070,0232) and FillStyleSequence (0070,0233) each as Type 3.

The reference library writes none of them. highdicom 0.28.1 [6] emits presentation states, but none of the three sequences appears in its code, only in the machine-readable standard tables the package ships, and the sole CIELab colour attribute its presentation state code sets is GraphicLayerRecommendedDisplayCIELabValue (0070,0401), at layer level.

The two validators disagree, in both directions. dciodvfy rejects the text route that dcmpschk accepts, and the asymmetry is demonstrably internal to the validator rather than a property of the standard: ShadowStyle (0070,0244) is flagged inside TextStyleSequence and passes inside LineStyleSequence in one and the same object, though the standard defines it in both macros.

The reference renderer cannot answer the question at all, because it draws no annotations. Deleting all 19 annotation items, and separately displacing all 57 objects by 120 px, each leave the rendered bitmap byte identical.

Two consequences: the reference toolkit offers no headless, reproducible way to verify what an annotation will show, and per-object colour writable with standard tooling requires one graphic layer per annotated object.

### 3.3 What the clinician received, and why the check could not fire

The per-vertebra quality flag fired on 37 of the 38 studies the service emitted, 97.4 percent, and on 11.1 percent of vertebrae. A flag that fires on almost every study carries almost no information at the point of use, and no basis for treating one study differently from another.

The cause is the estimator, not the threshold (Table 3, Figure 2). The check is specified as leave-one-out residuals against regional splines but implemented in sample for regions of four or more levels, the normal path, so the spline is fitted through the displaced point and absorbs it. The reported residual is flat at roughly 0.2 mm across a 0 to 80 mm true displacement, while a leave-one-out residual on the same data tracks that displacement, 0.553 to 78.553 mm. One subcase is worse than masked: a region of exactly four levels gives a cubic spline just enough freedom to interpolate it, so the in-sample residual collapses to a mean of 0.027 px against 0.552 px elsewhere and the pooled z can never reach the threshold, leaving those levels unchecked entirely.

Paired injection shows the consequence: a single-level shift is flagged at its own site 5.1 percent of the time against a 22.7 percent paired control, worse than chance. On error-free chains the deployed rule flags 7.4 percent of vertebrae and 91.7 percent of studies, reproducing from synthetic data alone the 11.1 percent and 97.4 percent measured on the emitted objects. A 3.0 mm minimum-residual guard removes every false positive and every detection, so the obvious first fix silences the check rather than repairing it.

Two bounds. Computed as specified the residual detects nothing at displacements of 20 mm or less, reaching 75.0 percent only at 40 mm and 100.0 percent at 80 mm, and flagging every error-free study in doing so. And a single-level relabel moves centroids along the column, not off it, so it is invisible to a distance-to-curve residual under either estimator: 0.0 percent at the injected site against a 0.0 percent control.

### 3.4 Whether the flag carries information at all

Nine readings of the same model output were scored on the 155 public cases that produced a result: of 2241 predicted vertebrae, 1845 matched within the benchmark's 20 mm tolerance and 373 carried a wrong level. Only the rule choosing which per-region sigmoid channel to read varied. All nine fall between 0.427 and 0.581 in area under the curve (Table 4, Figure 3). All nine read the same output on the same out-of-distribution material, so the comparison is internal and the values are not a deployment estimate.

The rule that shipped, parity restarted at each anatomical region, is the worst of the nine at 0.427, and its case-clustered interval [0.342, 0.516] contains 0.5, so the readout the service actually used is indistinguishable from chance. Six of the nine arms have clustered intervals containing 0.5; the three that do not, at 0.576 to 0.581, remain far below any threshold at which a per-vertebra flag would be actionable. The published rule scores 0.516 and the best arm 0.581, but their paired difference, [-0.004, 0.144] with P(delta <= 0) = 0.032, crosses zero, so the repair's effect is not separable at this sample size.

Fitting the readout with the labels does not rescue it (Table 4): the best per-level mapping reaches 0.635 in sample but 0.570 held out, below the best rule already available. The same search on shuffled labels reaches 0.594 mean over 1000 repetitions, so the exact permutation p for the in-sample value is 0.001. The structure is genuine and does not generalise.

Figure 4 shows the per-study consequence: on the failure case 8 of 12 assigned names are levels absent from the volume, 7 carrying confidence 0.82 to 0.96, while the flag fired on 2, one of them a level that is present.

### 3.5 When the pipeline produces nothing

A third failure mode delivers nothing and reports nothing. When the labelling stage finds no landmark to anchor to, it writes no output, deletes any existing output file, and does not flag the event, so no quality layer can fire on that study and the failure is silent to every downstream monitor. This path was taken in 47 of 202 public cases, 23.3 percent, on CT with a model whose declared training input is MRI, so it is out of distribution by construction: it bounds robustness and is not a deployment rate. A default_superior_disc fallback that would turn the silent skip into a guess is in the code and not enabled in the deployed configuration.

## 4. Discussion

The constraint on encoding such a signal is not the standard alone but the intersection of the standard, the reference library, two reference validators and the reference renderer, which do not agree, so no implementer could resolve it from the specification alone. Conformance and trustworthiness are then independent properties of the same delivered object, and this deployment monitored neither. Acceptance carried no information about either: archive, DICOMweb, the DICOM network path and the target viewer all took the 38 objects that two independent validators failed and the reference renderer refused to load. A health system that infers correctness from successful delivery is inferring nothing. The independence runs both ways: a fully conformant object carrying a flag indistinguishable from chance would look no different to the archive, the transport or the display.

A flag that fires on 97.4 percent of studies and 11.1 percent of vertebrae is not a safety signal. It is alert fatigue in a standards-conformant wrapper, and the clinician who dismisses it on every case is reading it correctly. The failure sits in the estimator, not the threshold: a check that fits its reference curve through the point under test absorbs the displacement it exists to detect, so no threshold sweep recovers it, and the one magnitude guard that removes every false positive removes every detection with it. Thresholds are what a deployment tunes; the estimator decides whether there is anything to tune. The same layer fails silently in the other direction: where no landmark disc is found, the service writes no output and raises no flag.

Presentation states carrying point markers have been pushed into a production PACS before [9]; carrying per-object identity together with a per-object quality value is a different demand on the same IOD. Netherton et al. [10] built a learned per-vertebra quality signal, since validated externally; ours is complementary and cautionary, showing how a signal read from the model's own output channels fails. Labelling accuracy is settled [11] and is not contested here.

What generalises is the method, not the incidence rate (Table 5).

**Limitations.** The container findings are 38 objects from one service and one archive, and the validator disagreement is measured on nine encodings of one annotation set. The public substrate is out of distribution by construction, so the 23.3 percent no-output rate bounds robustness, not deployment. Verification bias affects every AUC, since 17.7 percent of predicted vertebrae cannot be scored, and the synthetic work bounds an estimator, not a clinical rate. The one renderer measured draws no annotations, so it speaks to whether an object loads, not to what is drawn; rendering in the target viewer is reported from deployment, and no human scored a viewport. The repair effect crosses zero at this sample size and is not claimed. Appendix G records every claim retired here, because such a study should be judged on what its author discarded as well as on what survived.

## 5. Conclusions

An AI result can be delivered, accepted and rendered end to end while failing every conformance check applied to it, and no component of the delivery path will say so. The quality signal attached to that result can fire on 97.4 percent of studies while the confidence it carries is indistinguishable from chance, and neither fact is visible from the object, from its rendering, or from the model's accuracy. Conformance and trustworthiness must therefore be measured separately, by independent tools, and reported as properties of the health system rather than as metrics of the model.

---

## Declaration of competing interest

The author declares the following interests. The submitting affiliation is University at Buffalo School of Management, Buffalo, NY, USA. The service studied here is an internal deployment of aycan Medical Systems LLC; the author worked on that deployment while employed at aycan and is no longer employed there. aycan granted, in writing on 31 July 2026, permission for research use of the clinical material, for publication of the findings reported here, for release of the analysis code, and for the authorship and affiliation stated above. That permission was granted for findings that are critical of aycan's own internal service, and the author records it as a deliberate act of transparency by the operator rather than as a formality: a vendor that allows an unflattering audit of its own deployment to be published, with its code, is doing what this article argues the field should do. The service is an internal deployment integrated with a commercial viewer. It is not a cleared or released product, and nothing in this article should be read as a statement about a regulated device. The commercial viewer referred to in the deployment description is a third-party product; this work does not benchmark it, does not compare it against any alternative, and does not evaluate its diagnostic performance, and no endorsement is implied or received. Two points are owed to that vendor. First, it rendered all 38 objects correctly despite their conformance defects, which is the behaviour a clinical viewer should have: refusing to display would have withheld a result from the reader rather than surfacing a defect, and tolerance of imperfect input is a virtue in a viewer even though it is the reason the defects went unnoticed. Second, the emitted objects declare that vendor in Manufacturer and ManufacturerModelName. **Those values were written by the deployed pipeline, not by that vendor's software.** Every conformance defect reported in this article belongs to the emitting pipeline, and no conclusion about that vendor's products should be drawn from any measurement here. The segmentation checkpoints are openly released upstream weights rather than proprietary artefacts, and every quantitative claim rests on public benchmark data, those openly released weights, the output of independent third-party validators, or direct counts over the objects the deployed service itself emitted. The author declares no other financial or non-financial competing interests.

## CRediT authorship contribution statement

**Digvijay Patil:** Conceptualization, Methodology, Software, Validation, Formal analysis, Investigation, Resources, Data curation, Writing - original draft, Writing - review & editing, Visualization, Project administration.

Digvijay Patil is the sole author, performed all of the work reported, and takes full responsibility for its content. No other individual meets the ICMJE criteria for authorship of this work. No generative AI tool is listed as an author; the use that was made of one is declared in Methods, section 2.5, and immediately above the References.

## Funding

This research did not receive any specific grant from funding agencies in the public, commercial, or not-for-profit sectors.

## Ethics

This work is not human subjects research, and no institutional review board approval was sought. The public benchmark data are de-identified and are used under their published licence. The clinical material consists of DICOM objects emitted by an already-deployed service, analysed in pseudonymised form, together with derived summary statistics from a retrospective cohort. No individual was contacted, no intervention or interaction with any individual took place, and no prospective research was conducted. The unit of analysis throughout is the delivered object and its machine-generated annotation record, not the patient: no individual-level clinical finding is reported, and every clinical result is reported as an aggregate count. On that basis the activity does not involve human subjects as defined at 45 CFR 46.102(e), so institutional review board approval was not required.

## Data availability

The public benchmark data are the VerSe 2019 and VerSe 2020 collections, 202 cases in total, obtained by anonymous download from the Open Science Framework, osf.io/nqjyw and osf.io/t98fz, under CC BY-SA 4.0. Vertebral identification is scored with the benchmark organisers' own evaluation code, vendored byte-identically under its MIT licence rather than reimplemented.

The evaluation harness, the exact validator invocations, the presentation-state and segmentation writers, the channel-selection ablation, the generator for the synthetic evaluation, and the claims ledger recording the provenance and status of every number in this article, including every claim retired during the work, are released under the MIT licence at https://github.com/Volkopat/spine-gsps and archived at https://doi.org/10.5281/zenodo.21728405, a concept identifier that always resolves to the latest archived version; the version underlying this article is tag v1.0.1. The release is a curated snapshot rather than the working history: the raw per-attribute validator dumps over the 38 clinical objects are withheld, because they are a per-attribute record over patient examinations, and the summary write-ups released in their place carry the same counts.

The segmentation checkpoints are not redistributed with this work. They are the openly released upstream TotalSpineSeg weights and are obtainable from the upstream release r20241005 at https://github.com/neuropoly/totalspineseg.

The clinical material, both the delivered presentation states and the retrospective cohort they came from, cannot be released, because it derives from patient examinations and the written permission obtained covers research use, publication of these findings and release of the analysis code, not redistribution of patient data. The commands that produced every claim drawn from it are listed with the released code, so each measurement can be repeated on any equivalent set of delivered objects.

## Declaration of Generative AI and AI-assisted technologies in the writing process

During the preparation of this work, the author used Anthropic Claude (Opus 5, Anthropic PBC), accessed through Claude Code, in order to draft and restructure manuscript prose and to check the text against the journal's formatting requirements. After using this tool, the author reviewed and edited the content as needed and takes full responsibility for the content of the published article.

Use of the same tool in the research process, covering code authorship, execution of the analyses and tabulation of their output, is declared with tool, version and developer in Methods, section 2.5, together with the three controls that make it checkable, and is not repeated here.

---

## References

1. Son Y, Joo B, Park M, Ahn SJ, Kim S, Lee HS. Real-world use of PACS-integrated automated spine numbering in MRI. Clin Imaging. 2026;132:110744.
2. Sung J, Chang PD, Ayobi A, et al. Multicenter, multinational, and multivendor validation of an artificial intelligence application for acute cervical spine fracture detection on CT. Diagnostics. 2026;16(2):194. doi:10.3390/diagnostics16020194
3. IHE Radiology Technical Framework Supplement: AI Results (AIR). Revision 1.3, Trial Implementation. IHE International; 8 August 2025.
4. Warszawer Y, Molinier N, Valosek J, et al. TotalSpineSeg: robust spine segmentation and labeling across multiple MRI contrasts. Proc Int Soc Magn Reson Med. 2025;33:0624. The software release used here is r20241005, github.com/neuropoly/totalspineseg. No peer-reviewed journal version was located as of 31 July 2026.
5. Sekuboyina A, Husseini ME, Bayat A, et al. VerSe: a vertebrae labelling and segmentation benchmark for multi-detector CT images. Med Image Anal. 2021;73:102166.
6. Bridge CP, Gorman C, Pieper S, et al. Highdicom: a Python library for standardized encoding of image annotations and machine learning model outputs in pathology and radiology. J Digit Imaging. 2022;35(6):1719-1737.
7. Isensee F, Jaeger PF, Kohl SAA, Petersen J, Maier-Hein KH. nnU-Net: a self-configuring method for deep learning-based biomedical image segmentation. Nat Methods. 2021;18(2):203-211.
8. Mehrtash A, Wells WM, Tempany CM, Abolmaesumi P, Kapur T. Confidence calibration and predictive uncertainty estimation for deep medical image segmentation. IEEE Trans Med Imaging. 2020;39(12):3868-3878.
9. Dikici E, Bigelow M, Prevedello LM, White RD, Erdal BS. Integrating AI into radiology workflow: levels of research, production, and feedback maturity. J Med Imaging. 2020;7(1):016502.
10. Netherton TJ, Nguyen C, Cardenas CE, et al. An automated treatment planning framework for spinal radiation therapy and vertebral-level second check. Int J Radiat Oncol Biol Phys. 2022;114(3):516-528.
11. Moller H, Schoen H, Graf R, et al. VERIDAH: solving enumeration anomaly aware vertebra labeling across imaging sequences. arXiv:2601.14066. 2026.

---

## Figure captions

**Figure 1.** One Type 1 attribute decides whether the reference renderer accepts the object at all. (a) The delivered encoding, which dcmp2pgm refuses, writing zero bytes and emitting `instanceNumber absent or empty in presentation state`. (b) The same object with only InstanceNumber (0020,0013) restored, which renders. (c) A from-scratch conformant object built by our own emitter. Panels (b) and (c) are byte identical, SHA-256 prefix 5ea1ecb666bc6382, computed at figure-build time from the files on disk rather than quoted. All 38 objects the deployed service emitted lack this attribute, and all 38 nonetheless rendered correctly in the commercial viewer they were built against, which is the dissociation the paper reports. This result concerns whether the object is accepted at all, which is upstream of annotation drawing, and is therefore unaffected by the withdrawal of the earlier annotation-rendering claim recorded in Appendix G.

**Figure 2.** An in-sample residual absorbs the displacement it exists to detect. Upper panel: reported residual against true displacement of one level. The deployed in-sample curve is flat at roughly 0.2 mm across 0 to 80 mm, while the true leave-one-out residual tracks the diagonal from 0.553 to 78.553 mm. Lower panel: the deployed flag rate on the same axis, collapsing to 3.5 percent at 20 mm and 2.1 percent at 40 mm, which is the band a single-level mislabel occupies. Both curves are the median over 144 synthetic studies per displacement step, drawn from a population of 432 synthetic studies with known ground truth. Synthetic data establishes what the estimator can and cannot do in principle; it is not a clinical rate.

**Figure 3.** Nine readings of one model output, none of them usable. Above the divider, the nine channel-selection arms with AUC for separating wrong from correct levels; the case-clustered 95 percent interval from a 2000-repetition case-level bootstrap is the primary interval, with the naive interval drawn thinner behind it. The arm behind the published numbers and the arm that actually shipped are marked; the shipped arm is the worst of the nine at 0.427, and its clustered interval contains 0.5. Below the divider, the two label-informed ceilings, each drawn as a connected pair of its in-sample and held-out value, against the shuffled-label null band (mean 0.594, maximum 0.629 over 1000 repetitions). The divider exists because the two groups have different nulls: 0.50 for the unfitted rules, and the shuffled-label distribution for the fitted ceilings.

**Figure 4.** What the flag did on two delivered annotation records, both from public VerSe data under CC BY-SA 4.0. Marker fill encodes whether the assigned level exists in the ground-truth volume and outline colour encodes whether the quality flag fired, so the two facts are separable and hue is never the only encoding; the greyscale background is rendered at reduced contrast because the subject of the figure is the annotation record, not the image. Left: a contiguous 19-level labelling in which 17 of the 19 assigned names appear in the ground-truth mask, so C7 and SACRUM are unscoreable rather than known wrong. Right: a case whose ground truth holds C1 to T6 only, where 8 of 12 assigned names are levels absent from the volume, 7 of them carrying confidence 0.82 to 0.96, while the flag fired on 2, one of which is a level that is present. Neither panel checks position within the 20 mm identification tolerance, because these records carry no world coordinate.

---

## Table captions

**Table 1.** Conformance and delivery by object class. Conformance scored by dciodvfy (dicom3tools snapshot 20260701065818) and cross-checked by DCMTK 3.7.0 dcmpschk; errors are distinct attributes the validator reports as absent per object, and out-of-IOD counts distinct tags it reports as not belonging to the information object definition. Delivery measured against Orthanc 1.12.11.

| object class | n | errors per object | out-of-IOD | passing | archive accepts, REST | archive accepts, C-STORE | QIDO-RS and WADO-RS return with colour intact | dcmpschk | reference renderer loads |
|---|---:|---:|---:|---:|---|---|---|---|---|
| delivered presentation states | 38 | 7 | 6 | 0 of 38 | 38 of 38 | tested on 1 object, accepted | 38 of 38 | 0 passed, 38 failed | refused |
| conformant presentation states, public | 9 | 1 (7 variants) | 0 (7 variants) | 0 of 9 | 9 of 9 | tested on 1 object, accepted | 9 of 9 | 7 passed, 2 failed | 7 of 9 load |
| Segmentation, public | 6 | 0 | 0 | 6 of 6 | not tested | not tested | not tested | not applicable | not applicable |
| generated CT instances | 933 | 0 | 0 | 933 of 933 | 40 of 41 accepted, 1 duplicate | not tested | 1 series of 40 instances | not applicable | not applicable |

*Footnotes.* (a) The single error on the conformant emitter is Laterality, a Type 2C conditional the validator cannot evaluate for an unpaired body part; absence is correct, and a zero-length value draws a worse diagnostic. (b) PresentationPixelSpacing (0070,0101) is Type 1C in the Displayed Area module, conditional on PresentationSizeMode being TRUE SIZE, and must not be described flatly as a required attribute absent. (c) The 6 of 6 Segmentation and 933 of 933 CT figures are the released full-coverage validation files and supersede earlier orchestrator samples. (d) Of the nine public variants, seven are conformant by design and two are deliberate as-is reproductions of the delivered encoding; the as-is pair carries the errors and the out-of-IOD attributes, and is what the renderer refuses. (e) dcmpschk names the same Type 1C cause on the 38 delivered objects as dcmp2pgm does on the as-is reconstruction, verbatim in Appendix A.

**Table 2.** Three routes for encoding a per-object colour flag, against the five authorities an implementer would consult. Every cell except the PS3.3 column is a measurement rather than our reading of the standard.

| route | attribute | PS3.3 C.10.5 type | highdicom 0.28.1 writes it | dciodvfy | dcmpschk | dcmp2pgm draws it |
|---|---|---|---|---|---|---|
| graphic layer | Graphic Layer Recommended Display CIELab Value (0070,0401) | Type 3 | yes | accepts | accepts | no annotations drawn |
| line style | Pattern On Color CIELab Value (0070,0251), inside Line Style Sequence (0070,0232) | Type 3 | no | accepts | accepts | no annotations drawn |
| text style | Text Color CIELab Value (0070,0241), inside Text Style Sequence (0070,0231) | Type 3 | no | rejects | accepts | no annotations drawn |

*Footnotes.* (a) PS3.2 section 3.11.3, verbatim: "IODs from a Standard Extended SOP Class may be freely exchanged between DICOM implementations since implementations unfamiliar with the additional Type 3 Attributes would simply ignore them." (b) dciodvfy's closing diagnostic on the delivered objects, verbatim: "Dicom dataset contains attributes not present in standard DICOM IOD, this is a Standard Extended SOP Class", which asserts extension rather than non-conformance. (c) The rejection is internal to the validator: ShadowStyle (0070,0244) is flagged inside Text Style Sequence and accepted inside Line Style Sequence in the same object, although the standard defines it in both macros. (d) The attributes are correctly nested, Text Color CIELab Value sitting inside Text Style Sequence rather than directly on the text object, so this is not a misplacement the validator was right to reject. (e) The renderer column is a third state, neither pass nor fail: dcmp2pgm draws no graphic annotations at all, so it cannot answer the colour question.

**Table 3.** The geometric consistency check, three panels, each stating its own n. Synthetic studies with known ground truth; paired, so each rate is measured on the same studies before and after injection.

*Panel A. Masking. Median over 144 studies per displacement step.*

| true displacement (mm) | in-sample residual (mm) | leave-one-out residual (mm) | deployed detects | detects under the specification |
|---:|---:|---:|---:|---:|
| 0.0 | 0.212 | 0.553 | 21.5% | 0% |
| 1.0 | 0.265 | 1.171 | 27.8% | 0% |
| 5.0 | 0.290 | 4.923 | 23.6% | 0% |
| 10.0 | 0.239 | 9.903 | 22.9% | 0% |
| 20.0 | 0.235 | 19.843 | 3.5% | 0% |
| 40.0 | 0.153 | 39.532 | 2.1% | 75.0% |
| 80.0 | 0.118 | 78.553 | 7.6% | 100.0% |

*Panel B. Paired injection, 432 studies. Detection at the injected site, with the paired control on the same studies in parentheses.*

| injected error | flagged at its own site (paired control) |
|---|---|
| single-level shift | 5.1% (22.7%) |
| adjacent swap | 11.3% (22.7%) |
| whole-column off by one | 97.0% (97.0%) |
| lateral 10 mm, positive control | 23.1% (22.7%) |

*Panel C. False positives on error-free chains, 432 studies, 6156 vertebrae.*

| rule | per vertebra | per study |
|---|---:|---:|
| deployed, in sample | 7.4% | 91.7% |
| guarded at 3.0 mm minimum residual | 0.0% | 0.0% |
| true leave one out | 15.1% | 100.0% |

*Footnotes.* (a) Equal values in Panel B mean zero discrimination; the whole-column row is identical to its control. (b) The deployed 7.4 percent per vertebra and 91.7 percent per study closely reproduce the 11.1 percent and 97.4 percent measured on real delivered output, which is independent synthetic confirmation of a production observation. (c) The 3.0 mm guard removes every false positive and every detection. (d) Under true leave one out the false positives concentrate at region endpoints, 50.0 percent there against 0.0 percent in the interior. (e) Across a z sweep from 1.00 to 4.00 no threshold separates detection from its paired control; see Appendix D. (f) Panel A is 144 studies per step, not 432.

**Table 4.** The channel-selection ablation. 155 cases, 2241 predicted vertebrae, 1845 matched within the benchmark's 20 mm identification tolerance, 373 carrying a wrong level. Pipeline, segmentation and confidence formula are identical across every row of Panel A; only the rule that selects which output channel the score reads changes.

*Panel A. Nine arms. Clustered intervals from a 2000-repetition case-level bootstrap.*

| arm | what it is | AUC | naive 95% CI | clustered 95% CI |
|---|---|---:|---|---|
| region_retired | channel from the first letter of the level name (PUBLISHED) | 0.516 | [0.483, 0.549] | [0.479, 0.553] |
| parity_name | parity of the anatomical name, continuous | 0.572 | [0.539, 0.606] | [0.480, 0.661] |
| parity_region_deployed | parity restarted at each anatomical region (SHIPPED) | 0.427 | [0.395, 0.458] | [0.342, 0.516] |
| parity_sequence | parity of position in the model's detected sequence | 0.481 | [0.449, 0.514] | [0.398, 0.562] |
| parity_sequence_inverted | the same with one global sign flip | 0.488 | [0.456, 0.521] | [0.413, 0.574] |
| parity_sequence_phased | the same with the phase estimated per case | 0.581 | [0.547, 0.614] | [0.531, 0.641] |
| mapping_free_top1 | highest channel mean, no mapping at all | 0.576 | [0.543, 0.609] | [0.523, 0.636] |
| mapping_free_margin | gap between the top two channel means | 0.486 | [0.453, 0.519] | [0.435, 0.536] |
| argmax_mean | full confidence formula on the argmax channel | 0.579 | [0.545, 0.612] | [0.527, 0.639] |
| paired delta, best minus published | parity_sequence_phased minus region_retired | 0.065 | not applicable | [-0.004, 0.144], P(delta <= 0) = 0.032 |

*Panel B. Label-informed ceilings, every one quoted in sample and held out.*

| ceiling | in sample | held out (40 folds) | what it is |
|---|---:|---:|---|
| best fixed channel | 0.566 (channel 5) | 0.550 (sd 0.044) | exact, exhaustive over all 11 channels |
| best per-level mapping | 0.635 (26 levels) | 0.570 (sd 0.033) | coordinate ascent over 26 free parameters; not a bound |
| the same search, labels shuffled, 1000 reps | 0.594 mean, 0.611 p95, 0.629 max | not applicable | exact permutation p for the observed 0.635 is 0.001 |

*Footnotes.* (a) Per-vertebra level accuracy on matched vertebrae is 79.8 percent (1472 of 1845). (b) 17.7 percent of predicted vertebrae (396 of 2241) fall beyond the 20 mm tolerance and cannot be scored, so verification bias remains. (c) Re-scored on the 1828 vertebrae where every arm is defined, the ranking is unchanged. (d) Held-out splits are by case, not by vertebra, because vertebrae within a case are correlated. (e) These are per-region sigmoid outputs, not a categorical distribution; the channels are independent and do not sum to one.

**Table 5.** What an implementing site should check, and what each check would have caught in this service. None of these requires access to the model, its weights or its training data.

| check to perform | evidence in this study | the failure it would have caught |
|---|---|---|
| Validate every emitted object with two independent validators, because they disagree in both directions | Tables 1 and 2 | Seven required-attribute absences per object that a single validator under-reports, and an encoding one validator rejects that the standard permits |
| Load every emitted object in a reference renderer before release | Figure 1 | An object refused outright, writing zero bytes, while the target viewer renders it |
| Treat acceptance by archive and transport as no evidence of conformance | Table 1 | 38 of 38 non-conformant objects delivered, indexed and retrieved undetected |
| Monitor the firing rate of any per-object quality flag as a first-order safety metric | Table 3, section 3.3 | A flag firing on 97.4 percent of studies and 11.1 percent of objects |
| Evaluate a quality flag against outcome labels with case-clustered intervals and a case-level held-out split | Table 4 | A shipped readout indistinguishable from chance, and an apparent ceiling that does not generalise |
| Verify that a residual-based consistency check is computed out of sample | Figure 2 | An estimator that absorbs the error it exists to detect |
| Instrument and alert on the no-output path | Section 3.5 | A quality layer that is silent exactly where it is most needed |

---

## Appendix A. Attribute-level conformance detail

**A.0 Provenance of the objects, and who the defects belong to.** The 38 objects are analysed exactly as the deployed emitter wrote them on 21 November 2025, unmodified. Every conformance defect reported in this article was already present in the delivered files; none was introduced by our tooling. Objects we constructed appear only as explicitly labelled variants, built on public data, and are never pooled with the 38. Separately, the 38 delivered objects do not identify their true producer. They declare a third-party viewer vendor in `Manufacturer` (0008,0070) and `ManufacturerModelName` (0008,1090), and a vendor string in `ImplementationVersionName` (0002,0013), all written by the deployed pipeline. Readers, archives and any downstream audit therefore attribute these objects to a company that did not produce them. This is recorded because it matters for fairness before it matters for provenance: **every conformance defect reported in this article was introduced by the emitting pipeline, and none of it is attributable to the vendor named in the objects' own metadata.** The released harness emits a truthful-identity variant alongside the as-deployed one for exactly this reason, and no product of that vendor was tested in this work. A service that writes another company's name into the objects it produces should be regarded as a defect in its own right, independent of the seven below.

**A.1 The seven attributes scored as absent, all 38 of 38 delivered objects.**

| type | attribute | module | affected |
|---|---|---|---|
| 1 | FileMetaInformationGroupLength | File Meta Information | 38/38 |
| 1 | FileMetaInformationVersion | File Meta Information | 38/38 |
| 1 | InstanceNumber | Content Identification Macro | 38/38 |
| 1C | PresentationPixelSpacing | Displayed Area | 38/38 |
| 2 | SeriesNumber | General Series | 38/38 |
| 2 | StudyID | General Study | 38/38 |
| 2C | Laterality | General Series | 38/38 |

Two of the seven are conditional and must not be described flatly as required attributes absent. **Laterality** is Type 2C in General Series, required only when the body part examined is one of a pair. The spine is unpaired, so the attribute is correctly absent; dciodvfy cannot evaluate the condition and reports it, and supplying a zero-length value draws a worse diagnostic than omitting it. **PresentationPixelSpacing** (0070,0101) is Type 1C in the Displayed Area module, conditional on PresentationSizeMode being TRUE SIZE. The delivered objects set TRUE SIZE and omit the spacing, so the condition is met and the attribute is genuinely required in these objects. That single conditional is what makes DCMTK refuse them.

**A.2 The six attributes the validator places outside the IOD, all 38 of 38.**

| tag | attribute |
|---|---|
| (0070,0231) | Text Style Sequence |
| (0070,0229) | CSS Font Name |
| (0070,0241) | Text Color CIELab Value |
| (0070,0242) | Horizontal Alignment |
| (0070,0243) | Vertical Alignment |
| (0070,0244) | Shadow Style |

Not flagged, in the same objects: Line Style Sequence (0070,0232), Line Dashing Style, Line Pattern, Line Thickness and Pattern On Color CIELab Value (0070,0251). The attributes are correctly nested, so this is not a misplacement the validator was right to reject; and PS3.3 C.10.5 lists Text Style Sequence, Line Style Sequence and Fill Style Sequence each as Type 3 in the Graphic Annotation Module, which is in the Grayscale Softcopy Presentation State IOD. The asymmetry is therefore a property of the validator's IOD tables and not of the standard.

**A.3 Verbatim diagnostics.**

dciodvfy, closing line on every delivered object:

```
Dicom dataset contains attributes not present in standard DICOM IOD,
this is a Standard Extended SOP Class
```

dcmpschk and dcmp2pgm, the single named cause on all 38 delivered objects:

```
presentation state contains a display area selection SQ item with mode
'TRUE SIZE' but presentationPixelSpacing VM != 2
```

followed in dcmp2pgm by `F: Can't open input file(s).` and exit code 10.

dcmpschk on the as-is reconstruction built on public data:

```
instanceNumber absent or empty in presentation state
```

Also reported by dciodvfy on all 38, and cosmetic rather than structural: DICOMDIR warnings arising from the absent SeriesNumber and StudyID; and `Value dubious for this VR - (0x0010,0x0010) PN Patient's Name = <ANON_PAT_XXXX> - Retired Person Name form`, an artefact of the anonymiser writing a single-component name where DICOM expects caret-delimited components.

**A.4 Nine-variant cross-validation.** Nine encodings of one annotation set, with all 17 text objects and 17 graphic objects held byte identical in UnformattedTextValue and GraphicData, so only conformance attributes, colour route and producer identity vary. dciodvfy and dcmpschk agree on seven variants and disagree on exactly the two that carry text colour: dcmpschk passes `colour_text_outofiod` and `colour_all`, which dciodvfy flags on six attributes each. Both validators independently fail the two as-is variants, which score 5 errors and 6 out-of-IOD attributes; the seven conformant variants score 1 error and 0 out-of-IOD attributes.

**A.5 The Line Style Sequence macro** carries ten Type 1 attributes and dciodvfy enforces all ten; an emitter that supplies six of them fails.

**A.6 Warning to anyone reading the released artefacts.** `results/gsps_conformance_baseline.md` still contains the retired framing that "GSPS lets you colour a line but not text", together with its numbered points 2 to 4 and a statement that IHE AI Results excludes softcopy presentation states. Both are withdrawn; see Appendix G, entry G12, and the IHE quotation in the Introduction. The current statements are those in A.2 above.

## Appendix B. Model output channel semantics

Both step models are region-based nnU-Net (`regions_class_order` present, no background channel), so the network applies a per-region sigmoid and the output channels are independent per-region probabilities that do not sum to one. Two channels alone summed to 1.87 on one measured vertebra. Channel index and label value differ by one. The label definition below is quoted from the checkpoint's own `dataset.json`.

| channel | true meaning | name printed by the deployed json_generator.py |
|---:|---|---|
| 0 | disc union | background |
| 1 | disc_C2_C3 | disc_type_1 |
| 2 | disc_C7_T1 | disc_type_2 |
| 3 | disc_T12_L1 | disc_type_3 |
| 4 | disc_L5_S | disc_type_4 |
| 5 | vertebrae union | disc_type_5 |
| 6 | vertebrae_O, odd | vertebrae_type_1 |
| 7 | vertebrae_E, even | vertebrae_type_2 |
| 8 | sacrum | vertebrae_type_3 |
| 9 | canal | vertebrae_type_4 |
| 10 | cord | spinal_canal |

Every printed name is wrong. The published mapping, which selects a channel from the first letter of the level name, therefore reads the **sacrum** channel for every lumbar vertebra and the **canal** channel for the sacrum.

Parity evidence. The model's alternation follows detection order, not anatomical name: on one measured instance T7, an odd-numbered name, read 0.963 on the **even** channel against 0.0006 on the odd channel. The deployed `get_vertebra_channel` restarts parity at C1, T1 and L1, so C7 and T1 collide and the rule is wrong from T1 downwards rather than only in the lumbar spine. That rule is arm `parity_region_deployed` in Table 4, AUC 0.427.

Two distinct implementations existed in the deployed system and neither is correct: the calibration path, which computed three-dimensional whole-structure values in the range 0.03 to 0.56, and the live service's `confidence_calculator.py`, which computes on a single two-dimensional slice in the range 0.63 to 0.99.

## Appendix C. Statistical protocol and full ablation output

**Bootstrap.** Naive intervals resample the 1845 vertebrae. Clustered intervals resample the 155 **cases** with replacement and rebuild the vertebra set from the drawn cases, 2000 repetitions, percentile method. Cases are the resampling unit because roughly twelve vertebrae come from each case and are correlated within it. The clustered interval is the primary interval throughout.

**Held-out protocol.** Cases are split at random into halves; the readout is fitted on one half and scored on the other, then the direction is reversed, and the whole procedure is repeated 20 times, giving 40 folds. Splitting is by case, never by vertebra.

**Permutation null.** The identical per-level search is run on labels shuffled within the full vertebra set, 1000 repetitions. Its distribution is the optimism floor for any fitted readout.

**Exact p.** If no permutation draw reaches the observed value, the exact permutation p is (0+1)/(N+1) whatever the rest of the distribution looks like. Here no draw of 1000 reached 0.635, the maximum being 0.629, so p = 1/1001 = 0.001, the smallest attainable at this repetition count. The structure the search finds is therefore genuine; held out on unseen cases the same mapping is worth 0.570, so it does not generalise. Both statements are required, and quoting 0.635 without 0.570 misrepresents the result.

**Full per-channel AUC vector**, exhaustive over the 11 channels on all 1845 vertebrae: channel 0, 0.509; 1, 0.401; 2, 0.364; 3, 0.373; 4, 0.401; **5, 0.566**; 6, 0.488; 7, 0.475; 8, 0.440; 9, 0.473; 10, 0.364. Channel 5 is the vertebrae union channel.

**Fitted per-level mapping** reaching 0.635 in sample, by coordinate ascent from 11 starts over an 11^26 space: C1 to 6, C2 to 7, C3 to 6, C4 to 7, C5 to 6, C6 to 3, C7 to 10, T1 to 5, T2 to 5, T3 to 7, T4 to 6, T5 to 5, T6 to 6, T7 to 5, T8 to 6, T9 to 5, T10 to 6, T11 to 0, T12 to 9, L1 to 8, L2 to 4, L3 to 8, L4 to 3, L5 to 6, L6 to 7, SACRUM to 10. It is not a bound.

**Withdrawn oracle.** An earlier `best_per_level` oracle reported 0.536 and was presented as a bound. It was not one: it maximised the within-level AUC and reported the global AUC of that choice, and it dropped levels that were all-correct or all-wrong, which showed as it landing below an unfitted arm. Both defects were fixed and the oracle was replaced by the two ceilings in Table 4 Panel B.

**No claim of a significant repair is made.** The paired delta between the best arm and the published rule is [-0.004, 0.144] with P(delta <= 0) = 0.032 under the case-level bootstrap. It crosses zero.

## Appendix D. Synthetic study construction and the full estimator sweep

**Construction.** 432 synthetic vertebral chains with known ground truth, generated across coverages, slice spacings and 12 random seeds, spanning region sizes of 3, 4, 5, 7, 9 and 12 levels, 6156 vertebrae in total under the deployed rule. Centroid noise is applied at 0 mm and 0.5 mm as a robustness condition.

**Paired design.** Every rate is measured on the same studies before and after injecting a known error, so the control is the same population rather than a different one. Four injections are used: single-level shift, adjacent swap, whole-column off by one, and a lateral 10 mm displacement as a positive control that a distance-to-curve residual must be able to see.

**Reimplementation check.** The deployed detector is reverse engineered from source and `--selftest` confirms that the instrumented reimplementation reproduces the deployed trace on 24 regional residuals, so the residual and the flag can be scored separately from the confidence they are multiplied into.

**z sweep.** Across thresholds from z = 1.00 to z = 4.00 no threshold separates detection at the injected site from its paired control under the deployed rule. At z = 1.00 the deployed rule flags 18.7 percent of vertebrae and every study, and single-level detection is 33.6 percent against a control of the same order. The defect is not a threshold choice.

**Endpoint against interior.** Under the deployed in-sample rule, false positives concentrate in the **interior**, 9.7 percent, against 2.5 percent at region endpoints. Under true leave one out the pattern reverses and becomes extreme, 50.0 percent at endpoints against 0.0 percent in the interior, which is the leverage artefact of removing a point that anchors the fit. Known remedies exist, including excluding endpoints, standardising per depth, or fitting across region boundaries.

**Where the reported z values come from.** For ddof=0 pooling the algebraic bound on a z score is sqrt(n-1), about 4.12 at n = 18. The deployed logs contain a maximum z of 651.46, which is not an outlier detection but the consequence of a 0.1 px standard-deviation floor applied to residuals that are themselves sub-pixel.

**Two hypotheses of the author's that the measurement refuted**, recorded because they cost nothing here and are part of the audit trail. First, endpoint over-flagging was predicted for the deployed configuration from leave-one-out leverage; the opposite holds, because the deployed code does not use leave one out on its normal path. The reasoning was sound and was applied to the wrong code path, having believed the specification instead of reading the implementation. Second, the problem was initially framed as a detector firing on sub-millimetre noise; that is true but shallow, and the stronger and correct claim is that it cannot fire on real displacement at all.

## Appendix E. Reproduction, environment and provenance

**Tool versions.** dciodvfy from dicom3tools, snapshot 20260701065818; DCMTK 3.7.0 (dcmpschk, dcmp2pgm, storescu, dcmdjpeg), the binaries reporting `$dcmtk: dcmp2pgm v3.7.0 2025-12-15 $` and `$dcmtk: dcmpschk v3.7.0 2025-12-15 $` on x64-Windows, built shared with ZLIB 1.3.1; Orthanc 1.12.11, pinned in the compose file by image digest; highdicom 0.28.1; pydicom 3.0.2; nnunetv2 2.4.2; torch 2.8.0+cu128 (CUDA runtime 12.8); Python 3.10.20. Pins are frozen in `env/requirements.lock`.

**Hardware.** One NVIDIA GeForce RTX 5090 Laptop GPU, 24463 MiB, compute capability 12.0, driver 610.74; 63.5 GB RAM; 24 logical CPUs. All measured rows in the claims ledger were produced on this machine unless the row states otherwise.

**Commands.** Every claim in this article maps to one command in the released harness, listed with the claims ledger. The principal entry points are `python -m spinelab.gsps.validate`, `python -m spinelab.gsps.writer`, `python -m spinelab.confidence.channels`, `python scripts/e1_ablation.py`, `python -m spinelab.outliers.spline`, and the viewer bench under `scripts/viewer_bench/`.

**NIfTI to DICOM geometry round trip, reported as a methods validity check and not as a finding.** Public volumes are converted to DICOM by our own converter and read back independently. Over the released three-case run, 288,265,728 voxels compared, zero mismatched and zero Hounsfield-unit error, the worst world-coordinate error is 4.029e-11 mm read back with pydicom and 1.472e-07 mm read back with SimpleITK and GDCM. The two readers therefore disagree by four orders of magnitude, and they do so on the one genuinely oblique sagittal volume in the set. The disagreement is recorded because it bears on how much precision any geometric claim from a DICOM reader can carry; it does not affect any result in this article, which uses no world coordinates from these volumes.

**Level-assignment provenance.** The vertebral level assignment is upstream TotalSpineSeg code: 289 of 307 substantive lines, 94 percent, appear verbatim in `totalspineseg/utils/iterative_label.py`. It is attributed here, not claimed. Two structural consequences of that code are worth recording: `region_max_sizes` permits six lumbar levels, so L6 is representable, while the thoracic maximum equals the default of 12, so **T13 cannot be produced**; and the output range is C1 to L6 plus sacrum, not C1 to L5.

**Retracted claims inside the released artefacts.** The measurement write-ups released with the harness are the working record and were written before several claims were withdrawn. Rather than edit them silently, every superseded passage carries an inline retraction naming its ledger entry: `render_matrix.md` (G17, annotation drawing), `public_gsps_geometry.md` (G18, what the flag caught), `gsps_conformance_baseline.md` and `gsps_variants.md` (B16, the IHE AI Results wording, and B9, an unreproducible literature count). The governing measurement for G17 is `render_annotation_probe.md`: deleting all 19 annotation items, and separately displacing all 57 objects by 120 px, each leave the rendered bitmap byte identical, and applying the presentation state collapses the image from 256 distinct grey levels to 16, which is the greyscale pipeline and not annotation drawing.

## Appendix F. Reporting-guideline statement

IJMI requires AI and machine learning studies to complete its Machine Learning checklist and to observe the relevant reporting guideline. This study develops no model, so most of the named guidelines do not apply. The applicable checklist items are answered as follows.

| item | where it is answered |
|---|---|
| Data provenance and licensing | Methods 2.1; Data availability. VerSe 2019 and 2020, OSF nqjyw and t98fz, CC BY-SA 4.0. Clinical material is a deployed service's own output, used with written permission. |
| Distribution shift stated | Methods 2.1. The weights declare MR as their only training modality; the public cases are CT, so every public-data result is out of distribution by construction. |
| Held-out protocol and its split unit | Methods 2.3; Appendix C. Split by case, never by vertebra, 40 folds. |
| Class balance | Table 4 header. 373 wrong of 1845 matched vertebrae. |
| Evaluation metric and tolerance | Methods 2.3. AUC for separating wrong from correct levels; matching at the benchmark's 20 mm identification tolerance, scored by the organisers' rule. |
| Uncertainty quantification | Table 4. Naive and case-clustered 95 percent intervals, a paired delta, a permutation null and an exact permutation p. |
| Verification bias | Table 4 footnote (b). 17.7 percent of predicted vertebrae fall beyond the tolerance and cannot be scored. |
| Code availability | Data availability. Full harness released with a persistent identifier. |
| Model availability | Data availability. Openly released upstream weights, not redistributed here. |

TRIPOD+AI does not apply because no prediction model is developed, derived, updated or validated as a model; the ablation varies only a fixed post-hoc readout of an unchanged, openly released network. DECIDE-AI does not apply because no early-stage live clinical evaluation was conducted and no clinician used the system under study for this work. SPIRIT-AI and CONSORT-AI do not apply because there is no trial protocol and no trial. PROBAST-AI does not apply because no prediction model is being appraised for risk of bias. The retrospective conformance and delivery audit is descriptive and reports counts over a complete enumerated object set rather than a sampled cohort.

## Appendix G. Claims provenance and withdrawn claims

Every quantitative claim in this article carries a row in the released claims ledger recording its status (measured here, verified against the primary standard, or taken from the literature), the command that produced it, and its source file. The ledger also records what was withdrawn. The withdrawn claims are listed here because a study whose central results are negative should be judged on what its author discarded as well as on what survived, and because two of them were carried in an earlier conference abstract on the same system and are retracted by this article.

| # | Withdrawn claim | Why |
|---|---|---|
| G1 | "Confidence separated broken cases from acceptable ones." | The score was computed from the sacrum channel for lumbar levels. In-sample AUC 0.478 image level, 0.528 per vertebra. Void regardless of splitting. **Retracted from the earlier conference abstract.** |
| G2 | "Processing averaged 100 seconds per study on a single 24 GB GPU." | Untraceable: a transcription of a third-party README table. No timing instrumentation exists anywhere in the project. **Retracted from the earlier conference abstract.** |
| G3 | "Leave-one-out residuals." | The deployed normal path is in sample. |
| G4 | "First end-to-end DICOM-in, DICOM-out spine labelling with vendor-neutral PACS rendering." | Four independent prior systems, two with regulatory clearance. |
| G5 | A named prior mislabel-detection comparator. | It does not exist as described. The paper it was confused with is a scoliosis Cobb-angle platform. |
| G6 | Benchmark published means of 94.3 and 96.6 percent. | Those are the best single algorithms, not across-algorithm means. |
| G7 | "This torch build cannot run on the deployment GPU." | sm_61 is in the compiled architecture list. |
| G8 | "Leave-one-out leverage over-flags region endpoints in the deployed detector." | True only under true leave one out. The deployed in-sample path flags interior points more. |
| G9 | A 558-image rating pass described as radiologist validation. | One observer, one 59-minute session, median 2.37 s per image, unrandomised, filenames visible. It is a developer screening pass. |
| G10 | "The trained checkpoints are this project's own training run." | They are the upstream released weights, trained elsewhere. |
| G11 | "The spline outlier detector does not work." | Too coarse and misattributed. The design works above 40 mm; the shipped implementation computes an in-sample residual, which is what cannot work. |
| G12 | "Text colour is not in the GSPS IOD, while line and layer colour are." | Wrong. PS3.3 C.10.5 lists all three style sequences as Type 3. A validator diagnostic was treated as evidence about the standard. |
| G13 | "Line Color CIELab Value (0070,0251)." | No such attribute. (0070,0251) is Pattern On Color CIELab Value. |
| G14 | Describing PresentationPixelSpacing flatly among "required attributes absent". | It is Type 1C, conditional on TRUE SIZE. |
| G15 | "Varying only channel selection moves flag validity from below chance to usable." | Rested on 18 of 202 cases. On all 155 scorable cases the same two arms read 0.581 and 0.516. The gap was noise. |
| G16 | The in-sample ceiling 0.635 as evidence of headroom. | The same search on shuffled labels reaches 0.594 mean over 1000 repetitions. Held out the mapping is worth 0.570. The excess above the null is real (exact p 0.001) and does not transfer. |
| G17 | "The annotations themselves render, so the labels and leader lines are drawn." | Wrong. Deleting every annotation and separately displacing every annotation both leave the bitmap byte identical. dcmp2pgm draws no annotations. |
| G18 | Figure panel titles "all levels correct" and "two anatomically impossible placements". | Both wrong. The corrected counts are in the Figure 4 caption. The colouring was a confidence threshold relabelled as anatomy. |
| G19 | "PS3.2 does not say Standard Extended objects may be freely exchanged." | Wrong. PS3.2 3.11.3 says exactly that. |
| G20 | "The live server uses the correct parity mapping." | It does not. `get_vertebra_channel` restarts parity at C1, T1 and L1, so C7 and T1 collide. Measured as arm parity_region_deployed, AUC 0.427, the worst of the nine. |
| G21 | Four of the eleven references as first drafted: two titles truncated so they no longer said what the cited paper was about, and two titles paraphrased or expanded from the acronym rather than quoted. One second author was wrong. | Each of the eleven was checked against PubMed, the publisher DOI or the arXiv abstract page before submission. Six were correct as written. Recorded because it is the same failure as G5, where a comparator was cited that does not exist. |

---
