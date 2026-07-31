# Layer, line, or text: a standard, tooling, and validation gap in encoding per-object AI quality flags as DICOM presentation states

Digvijay Patil
University at Buffalo School of Management, Buffalo, NY, USA
ORCID 0009-0003-6878-1712
*Work performed while at aycan Medical Systems LLC.*

*Draft for the SPIE Medical Imaging 2027 proceedings, manuscripts due 27 January 2027.*
*Every figure is traceable to a row in `docs/CLAIMS.md` and to a single command in the*
*released harness. Revised 2026-07-30 after the channel ablation completed on all 202*
*VerSe cases: the provisional result it replaced is recorded as retired claim G15,*
*and the rendering measurement of 2026-07-31 is folded into sections 4.1, 4.3 and 6.*

---

## Abstract

**Background.** Automatic vertebral labelling is mature and commercially deployed. The
unsolved part is delivery: conveying not only labels but a per-vertebra quality signal
into an arbitrary picture archiving and communication system (PACS) in a form the
receiving viewer will render. A DICOM Grayscale Softcopy Presentation State (GSPS)
renders as an overlay on the original series and needs no segmentation support, which
makes it a natural carrier. The IHE AI Results profile nonetheless converges on
Structured Reporting and Segmentation, and states that it does not address encoding
results that lack machine-readable semantics, naming softcopy presentation states as
an example.

**Purpose.** To determine, separately and without conflating them, (i) what a
conformant GSPS can carry and at what granularity it can carry a per-object colour
flag, and (ii) whether the flag such an object carries is trustworthy. These are
independent properties and a system can fail either while passing the other.

**Methods.** Conformance was scored with `dciodvfy` from dicom3tools and cross-checked
against DCMTK's `dcmpschk`, two independent third-party validators, never by our own
reading of the standard. Rendering was measured with `dcmp2pgm`, the reference GSPS
renderer, by diffing the rendered bitmaps rather than by looking at a screen. We emitted
the three DICOM colour routes for annotation, layer, line, and text, in isolation with
annotation content held byte identical, and validated and rendered each. We tested
empirically what the reference implementation `highdicom` can express. We built a
from-scratch conformant GSPS emitter and a DICOM Segmentation comparator, both on 202
public VerSe computed tomography cases under CC BY-SA 4.0, converting NIfTI to DICOM
with a verified geometry round trip. For flag validity we held a deployed two-step
nnU-Net pipeline and its confidence formula fixed and ablated only the rule selecting
which output channel to read, scoring each variant against ground-truth level
correctness within the challenge's own 20 mm identification tolerance, and bounding it
with a label-informed ceiling, a permutation null and a split-half held-out fit. We
characterised the pipeline's geometric consistency check on 432 synthetic studies per
condition with known ground truth, using a paired design in which each rate is
measured on the same studies before and after injecting a known error.

**Results.** The authorities disagree, and the disagreement is not where we first
thought. PS3.3 C.10.5, the Graphic Annotation Module of the GSPS IOD, lists Text Style
Sequence (0070,0231), Line Style Sequence (0070,0232) and Fill Style Sequence
(0070,0233) each as Type 3, so all three colour routes are permitted. `highdicom` 0.28.1
writes none of them: its only CIELab colour attribute anywhere is Graphic Layer
Recommended Display CIELab Value (0070,0401), which is layer level. `dciodvfy` rejects
text colour while `dcmpschk`, written specifically for presentation states, accepts it.
The reference renderer cannot answer the question at all: it draws no annotations.
Deleting all 19 annotation items from an object, and separately displacing all 57
graphic and text objects, each leave its rendered bitmap byte identical, so equality
across the three colour routes is true by construction. The reference toolkit therefore
offers no scriptable way to check what an annotation will show. Conformance, by
contrast, is decisive.
Thirty-eight GSPS objects from a deployed service that rendered correctly in its target
viewer each carried seven required-attribute errors and six out-of-IOD attributes, with
zero of 38 passing validation, and the reference renderer refuses them outright.
Restoring one Type 1 attribute, Instance Number (0020,0013), and changing nothing else,
makes such an object render byte-identically to the conformant variant. Our conformant
emitter reduces the defects to one unevaluable conditional and zero out-of-IOD
attributes, and Segmentation objects validate at zero and zero. Geometry round trips to
a maximum world error of 4.55e-12 mm with zero of 189,267,968 voxels mismatched. The
deployed confidence read the sacrum channel for every lumbar vertebra, which the
checkpoints' own label definition proves; correcting it does not rescue the flag. Across
155 cases and 1845 scored vertebrae, every channel-selection rule falls between 0.481
and 0.581 AUC, and a per-level mapping given the labels is worth 0.570 held out, below
the best rule already deployed. The geometric consistency check showed no
discrimination: a single-level shift was flagged at its own site in 5.1 percent of
studies against a 22.7 percent paired control, and its reported residual was flat at
approximately 0.2 mm across a 0 to 80 mm true displacement, because the fit absorbs the
outlier it is intended to detect.

**Conclusions.** What constrains an AI quality flag is not the standard alone but the
intersection of standard, reference library, two reference validators and the reference
renderer, and the five do not agree. The standard permits per-object colour, the library
cannot write it, one validator rejects a route the other accepts, and the reference
headless renderer draws no annotations, so the practitioner's question is answered by
none of them. Separately, the flag's
content can be invalid for reasons internal to the model interface and independent of
model accuracy, and repairing that interface is necessary without being sufficient: on
this data no reading of the segmentation output yields a usable per-vertebra flag. A
magnitude threshold cannot rescue a signal computed in sample. Conformance and
trustworthiness must be measured separately, and neither implies the other.

---

## 1. Introduction

The literature on vertebral labelling reports subject-level accuracies above 98 percent
on sagittal magnetic resonance imaging, and at least two products with regulatory
clearance already segment and label vertebrae and return results to a PACS. On the
modelling axis there is little left to contest. What remains contested, and largely
unmeasured, is the interface: given a label and a per-vertebra estimate of how much to
trust it, how does that reach the radiologist in a form the viewer in front of them
will actually draw?

DICOM offers several answers. Structured Reporting encodes findings machine readably.
Segmentation encodes voxel extents. A Grayscale Softcopy Presentation State encodes
what to draw over an existing series, which has the practical advantage that a viewer
needs no segmentation support to show it and the storage cost is a small fraction of a
mask. The IHE AI Results profile converges on Structured Reporting and Segmentation. Its
wording about presentation states is precise and worth quoting rather than paraphrasing,
because an earlier version of this paper paraphrased it as an exclusion and that was too
strong. AIR Revision 1.3, 8 August 2025, states:

> "This profile also does not address encoding results that lack machine-readable
> semantics (e.g., using Secondary Captures, or Softcopy Presentation States).
> Implementations that support such encodings as a fallback in addition to the methods
> required in this profile may refer to the IHE Consistent Presentation of Images
> Profile for some guidance."

So presentation states are not forbidden and are not on the profile's explicit
out-of-scope list, which covers data flow, scheduling, non-imaging data and interactive
use. They are contemplated as a fallback and referred elsewhere for guidance. What the
profile declines to do is treat them as a machine-readable result encoding.

That judgement is reasonable, but it has not been tested against what presentation
states can and cannot do. This paper tests it, and in doing
so separates two questions that our own prior work conflated.

The first question is about the **container**. A per-vertebra quality flag is
inherently per object: nineteen vertebrae may have nineteen different confidences, and
the two that are wrong are the ones that matter. Encoding that requires per-object
visual differentiation. Whether a conformant GSPS can express per-object colour, and at
what granularity, turns out to have a specific and constraining answer.

The second question is about the **contents**. A perfectly conformant object can carry
a meaningless number. We found exactly this in a deployed system: a per-vertebra
confidence that read the wrong output channel for an entire anatomical region, and a
geometric consistency check whose reported residual was mathematically incapable of
responding to the error it was designed to find. Neither failure is visible from the
object, from the rendering, or from the model's segmentation accuracy.

Our contributions are:

1. A measured account of the three DICOM colour routes for annotation across five
   authorities: the standard, the reference library, two independent validators, and
   the reference renderer, which do not agree with one another.
2. The empirical finding that the reference implementation cannot express per-object
   colour at all, which forces one graphic layer per annotated object.
3. A measured separation of rendering from conformance: objects that render correctly
   in their target viewer while failing validation on seven counts.
4. A controlled ablation isolating a model-interface error from model accuracy.
5. A paired synthetic evaluation showing that a geometric consistency check computed
   in sample cannot detect the displacement it is built to detect, and that the obvious
   magnitude guard silences it rather than fixing it.

We claim novelty for none of the following, and cite them accordingly: emitting GSPS
from a deep learning pipeline, vertebral labelling, or the level assignment algorithm,
which is upstream code used under its licence.

## 2. Related work

**Presentation states for AI output.** Dikici et al. pushed GSPS objects from a brain
metastasis detection pipeline into a production PACS, with results entering the
electronic record, and named the commercial viewer that rendered them. Their objects
carried point markers. Encoding per-object text identity with an accompanying
per-object quality value, which is what a per-vertebra flag requires, is a different
demand on the IOD and is what we characterise.

**Standardised encoding libraries.** `highdicom` provides standards-conformant writers
for a range of IODs. We report empirically what it can and cannot express for
presentation states, which bears directly on what a practitioner following current best
practice can build.

**AI results profiles.** The IHE AI Results profile converges on Structured Reporting
and Segmentation. Our results are relevant to whether the exclusion of presentation
states is a limitation of the objects or of the tooling.

**Spine labelling and its quality control.** Vertebral labelling accuracy is high and
still improving. Quality control of that labelling has been addressed with learned
approaches: a random forest over dual-model disagreement features emitting a
per-vertebra probability of correct labelling, subsequently externally validated with
per-vertebra adjudication against expert ratings. Our contribution is not a better
detector but a demonstration of how a segmentation-native per-vertebra signal fails, and
why, which is complementary and cautionary rather than competing. Geometric consistency
checks on centroid sequences have also been used to detect labelling failures, and
curve fitting to bone centroids has been used to correct labels; our paired synthetic
evaluation quantifies when such a check can and cannot work.

**Benchmarks.** VerSe provides named-level vertebral ground truth on multi-detector
computed tomography with the organisers' own scorer and a published leaderboard, and is
not part of our model's training data. Datasets that are in that training data are
excluded from all held-out use here.

## 3. Methods

### 3.1 Validation and scoring

All conformance is measured with `dciodvfy` from David Clunie's dicom3tools. We do not
adjudicate conformance ourselves. This choice is load bearing: a prior in-house check
of the same 38 objects with pydicom detected three of the seven errors the independent
validator reports and none of the out-of-IOD attributes.

Vertebral level identification is scored with the VerSe organisers' own
`eval_utilities.py`, vendored with its licence rather than reimplemented, so the
reported identification rate is computed by the benchmark authors' code. The metric is
the challenge definition: a vertebra is correctly identified when the correct label is
the closest predicted landmark and within 20 mm. We validated the wrapper by scoring
ground truth against itself, which must yield an identification rate and Dice of 1.0,
and against a one-level-shifted copy, which must collapse.

### 3.2 The system under study

A containerised two-step nnU-Net cascade derived from TotalSpineSeg, deployed as a
Flask service and integrated with a commercial DICOM viewer. Step 1 emits 9 output
channels, step 2 emits 11. Both are region-based configurations, meaning
`regions_class_order` is present and there is no background channel, so output
channel index and class label value differ by one.

This has a consequence the rest of the paper depends on. Because both models are region
based, nnU-Net sets the inference nonlinearity to a sigmoid rather than a softmax and
optimises each region independently, so the channels are **independent per-region
probabilities that do not sum to one**. Measured on one vertebra, the vertebrae-union
channel reads 0.9256 and the odd-vertebrae channel 0.9435, summing to 1.87. The project's
own artefacts, including the deployed `raw_softmax_values.json`, call these softmax
values and they are not. That is why the channel-selection question is well posed at all:
there is no categorical distribution to normalise, only eleven separate probabilities,
and the rule decides which one is read. The level assignment is upstream
code, 94 percent of substantive lines verbatim, and is attributed rather than claimed.
Per-vertebra confidence is a weighted combination of the mean, the 95th percentile, and
the fraction of voxels above 0.7, read from a single output channel. A geometric
consistency check fits regional cubic splines to vertebral centroids and multiplies a
penalty into the confidence.

### 3.3 Colour encodings

DICOM offers three places to attach a colour to a presentation state annotation: the
graphic layer, the graphic object's line style, and the text object's text style. We
emitted each in isolation and in combination, holding annotation content byte identical
across variants, verified by comparing text strings and graphic coordinates. We crossed
this with a producer-identity axis, because the deployed objects declared a third
party's equipment identity, which is a potential confound in any rendering comparison:
if an object must impersonate the viewer to render, vendor neutrality is not
established.

Rendering is measured, not inspected. `dcmp2pgm` (DCMTK 3.7.0) applies a presentation
state to its referenced image and writes the rendered bitmap, so two objects are
compared by hashing their output. The referenced instance is a public VerSe sagittal
reformat, and all nine variants reference the same instance, so any difference in the
bitmap is attributable to the presentation state alone.

### 3.4 Public substrate and geometry

202 VerSe cases were obtained by anonymous OSF download under CC BY-SA 4.0. NIfTI
volumes were converted to conformant single-frame DICOM CT series by our own converter.
The conversion is verified by round trip: reading the emitted series back, reconstructing
the volume, and comparing world coordinates and voxel values, independently with pydicom
and with SimpleITK via GDCM.

World-to-pixel projection for annotation placement inverts the DICOM image plane
equation per instance, after converting the pipeline's RAS centroids to the LPS patient
space DICOM uses. Every run reports how many vertebrae project inside the image bounds,
so a sign error or a transposed axis surfaces immediately rather than being invisible on
a single rendered slice.

### 3.5 The channel-selection ablation

We hold the pipeline, the segmentation, and the confidence formula fixed at the
deployed weights, and vary only the rule that selects which output channel to read:

- **region_retired**, selection by the first letter of the level name, which is what
  produced the system's published numbers.
- **parity_name**, odd/even parity from the canonical anatomical ordinal, which is what
  the deployed service uses.
- **parity_sequence**, parity from position in the detected sequence.
- **parity_sequence_phased**, the same with the alternation phase estimated once per
  case, since the model's alternation follows detection order rather than anatomy.
- **parity_sequence_inverted**, the same with a single global sign flip rather than a
  per-case estimate, which distinguishes a genuine per-case inference from a sign
  error dressed up as one.
- **mapping_free**, no name-to-channel mapping, using the top channel mean and the
  top-to-second margin.
- **argmax_mean**, the full confidence formula applied to the argmax channel.

An arm named `oracle_channel` appeared in an earlier draft, described as an upper
bound. It was neither ground-truth informed nor a bound, which is why other arms beat
it, and it is withdrawn. Two ceilings replace it, both chosen **with** the labels: the
best single channel used for every vertebra, which is exact because eleven channels
are enumerable, and the best channel per anatomical level, found by coordinate ascent
on the global AUC and therefore a lower bound on the true ceiling rather than an
upper one. Because both are fitted, both are also reported held out, fitted on half
the cases and scored on the other half over 40 folds, split by case because vertebrae
within a case are correlated. The per-level search is additionally run on shuffled
labels, which measures how high it climbs when no signal exists.

The label is ground-truth correctness, not a human rating: a vertebra is wrong when its
assigned level disagrees with the VerSe ground truth at the same location, matched by
nearest centroid within 20 mm.

### 3.6 The geometric consistency check

We reverse engineered the deployed detector from source, reproduced it exactly,
verified the reproduction against a trace of the original, and then instrumented it to
emit the residual and the standardised score separately from the confidence they are
multiplied into. Evaluation is on 432 synthetic studies per condition with known ground
truth, in a paired design: each rate is measured on the same studies before and after
injecting a known error, so the control is the same population rather than a different
one. Injections are a single-level shift, an adjacent swap, a whole-column off-by-one,
and a lateral displacement control.

## 4. Results

### 4.1 Five authorities, and none of them answers the practitioner's question

See Table 1. PS3.3 C.10.5 is the Graphic Annotation Module of the GSPS IOD, and it lists
`TextStyleSequence` (0070,0231), `LineStyleSequence` (0070,0232) and `FillStyleSequence`
(0070,0233) each as Type 3. The standard permits all three colour routes. They are not
equally available in practice.

The validator's asymmetry is internal to the validator, not a property of the standard.
`ShadowStyle` (0070,0244) is flagged inside `TextStyleSequence` and passes inside
`LineStyleSequence` **in the same object**, though PS3.3 defines it in both. We verified
that the nesting is correct, so this is not a misplacement rightly rejected. The
validator's closing diagnostic reads "this is a Standard Extended SOP Class". PS3.2
defines that as a conformant category, not a failure. Section 7.3 gives the rules: such a
SOP class "shall be a proper super set of one Standard SOP Class", "may include Standard
and/or Private Type 3 Attributes beyond those defined in the IOD on which it is based",
and shall "use the same UID as the Standard SOP Class on which it is based". Section
3.11.3 goes further and states the consequence for interchange directly: "IODs from a
Standard Extended SOP Class may be freely exchanged between DICOM implementations since
implementations unfamiliar with the additional Type 3 Attributes would simply ignore
them." The diagnostic therefore names a category the standard explicitly describes as
freely exchangeable, not a non-conformance, and a second, independent presentation-state
validator accepts the object the first rejects.

An earlier version of this work read that diagnostic as evidence about the standard and
stated that text colour lies outside the GSPS IOD. That is wrong and is retired as claim
G12. The correction changes the finding from a conformance limit to an interoperability
gap, which we regard as the more useful result: a practitioner cannot act on the standard
alone when the reference library will not write the attribute, one reference validator
rejects it, and the reference renderer discards the distinction entirely.

The single remaining error in every conformant variant is `Laterality`, a Type 2C
conditional the validator cannot evaluate for an unpaired body part; absence is correct
and zero length draws a worse diagnostic.

The Line Style Sequence macro carries ten Type 1 attributes and the validator enforces
all ten. We report this because an earlier version of our own writer populated six and
the omission was caught only by the independent validator, not by pydicom.

**A fifth authority cannot answer the colour question, and that is the finding.**
`dcmp2pgm`, the reference GSPS renderer, produces byte-identical output for all three
colour routes: seven renderable variants of one presentation state, referencing one
image, all hash to `5ea1ecb666bc6382`. An earlier version of this work read that as the
renderer honouring the annotations while discarding their colour, inferring the mechanism
from the 237,376 pixels differing against a no-presentation-state baseline. That
inference was unsupported and is wrong, retired as claim G17.

Isolating it takes two renders. Deleting all 19 annotation items from the object leaves
the bitmap byte identical; separately displacing all 57 graphic and text objects by
120 px also leaves it byte identical. **The renderer draws no annotations at all.** The
237,376 differing pixels span 100.0 percent of rows, 1119 of 1119, and applying the
presentation state collapses the image from 256 distinct grey levels to 16. That is the
VOI LUT, the shutter and the displayed area: the greyscale pipeline, which is what a
**Grayscale** Softcopy Presentation State is for. Equality across the colour routes is
therefore true by construction, since a renderer that draws no annotations cannot draw
them in different colours.

What replaces the withdrawn claim is a sharper statement about the toolchain. **There is
no scriptable renderer in the reference toolkit that draws GSPS annotations.** `dcmp2pgm`
ignores the Graphic Annotation Module; DICOMscope, the DCMTK component that does draw it,
is a Java GUI and cannot be scripted into a regression harness. A practitioner shipping
per-vertebra annotations has no headless, reproducible way to check what a conformant
implementation will show. Whatever a clinical viewer draws, it draws without a reference
implementation to be checked against, and our own claim that the deployed objects' colour
is visible in their target viewer is reported from deployment rather than measured.

### 4.2 The reference implementation forces one graphic layer per object

`highdicom` 0.28.1 can write a GSPS. It cannot write per-object colour into one. The
strings `TextStyleSequence`, `LineStyleSequence`, `FillStyleSequence`,
`TextColorCIELabValue` and `PatternOnColorCIELabValue` occur zero times across the
installed package. Exactly one CIELab colour attribute appears anywhere in its
presentation state module, `GraphicLayerRecommendedDisplayCIELabValue` (0070,0401),
which is layer level; the other two occurrences in the package belong to the annotation
and segmentation IODs.

Combined with 4.1, this yields a structural constraint that follows from neither
authority by itself: per-vertebra colour that is writable with standard tooling **and**
accepted by the standard validator requires one graphic layer per vertebra. A
nineteen-level study needs nineteen layers. The deployed system created one layer per
annotation, which we initially judged to be bloat and which is in fact what the
intersection leaves.

### 4.3 Rendering is not conformance

Thirty-eight objects from the deployed service, which render correctly in the viewer
they were built against, each carry seven required-attribute errors and six out-of-IOD
attributes. Zero of 38 pass. Our conformant emitter, built from scratch on public data,
reduces this to the single unevaluable conditional with zero out-of-IOD attributes.
Segmentation objects validate at zero and zero. See Table 2.

Segmentation is therefore strictly more conformant than a presentation state at its
best. We state this plainly because it cuts against the case for presentation states on
conformance grounds. The remaining argument is that a presentation state renders as an
overlay in viewers with no segmentation support and at materially lower storage cost, a
conformant GSPS carrying nineteen labels being 12 KB against a mean 15,501 KB for the
Segmentations.

**The defects are not academic, and the cause is a single attribute.** `dcmp2pgm`
refuses the deployed objects outright and writes no output, emitting `instanceNumber`
`absent or empty in presentation state`. Restoring **only** `InstanceNumber`
(0020,0013), a Type 1 attribute, and changing nothing else, makes the object render,
and the rendered bitmap is byte-identical to that of the conformant variant. One
attribute is the difference between an object that renders and one that does not.

That isolation is what turns this section from a validator complaint into a result.
The same 38 objects render correctly in the commercial viewer they were built against
and are refused by the reference renderer. A team validating by looking at the screen
sees a working system, and the object is nonetheless unusable in a conformant
greyscale rendering path, for a reason a validator states in one line. Rendering in
one viewer is weak evidence, and here we can say exactly how weak and exactly why.

### 4.4 Geometry, and what it implies about single-slice presentation states

Conversion round trips to a maximum world error of 4.55e-12 mm with zero of 189,267,968
voxels mismatched and zero Hounsfield error, pydicom and SimpleITK/GDCM agreeing.

On an axial series the vertebrae of one study span 215 mm along the slice normal, so no
single axial slice can contain them; a sagittal reformat brings the mean absolute offset
to 4.6 mm and all nineteen levels project inside one image. A single-slice presentation
state presupposes a sagittal or reformatted acquisition, which constrains 60 of 202
VerSe cases out of the design without a reformat.

### 4.5 A conformant object can carry an invalid flag

The checkpoints' own label definition establishes that channel 8 is the sacrum and
channel 9 the canal, which the deployed code names `vertebrae_type_3` and
`vertebrae_type_4` on the assumption that channels 6 to 9 index anatomical regions.
Every lumbar vertebra was scored against the sacrum channel. Independently confirmed
three ways: the checkpoint `dataset.json`, the predictor's reported
`foreground_regions`, and per-vertebra channel statistics measured through step 2.

Correcting it does not rescue the flag. Table 3 gives all eight arms on 155 cases and
1845 scored vertebrae, of which 373 carry a wrong level. Every rule falls between 0.481
and 0.581 AUC. The published rule scores 0.516 [0.483, 0.549], the rule the live server
uses 0.572 [0.539, 0.606], and the best arm 0.581 [0.547, 0.614]. The improvement from
repairing the mapping is 0.065 with intervals that barely fail to overlap.

Two ceilings computed with the labels bound what a channel-selection rule could achieve.
Both must be read held out rather than in sample, and the difference is large enough to
change the conclusion. The best single channel applied to every vertebra reaches 0.566
in sample and 0.550 when fitted on half the cases and scored on the other half. A best
channel chosen per anatomical level reaches 0.635 in sample, which looks like real
headroom above the best rule at 0.581, and 0.570 held out, which is below it.

The in-sample figure is not headroom. The identical search run on shuffled labels, where
no signal exists by construction, reaches 0.594 on average over one thousand repetitions
and 0.629 at its maximum, because it fits 26 free parameters to 1845 points. The excess
above that null is real rather than noise: no permutation of a thousand reached the
observed 0.635, so the exact permutation p is (0+1)/(1000+1) = 0.001, the smallest value
attainable at this rep count. The search does find genuine level-specific structure. What
it does not do is generalise, and that is the point: fitted with the labels and scored on
unseen cases the same mapping is worth 0.570, below the best rule already deployed.
Significant and useless are not in tension. An earlier draft called this figure pure
optimism, which overstated it in the opposite direction and is corrected here.
Only the fixed-channel ceiling is exact, being exhaustive over eleven channels; the
per-level search covers an 11^26 space and is therefore a lower bound on the true
ceiling rather than an upper one. We report it anyway, with its null, because the
question a reader has is how much room a label-informed search finds, and the answer is
that it finds none that survives being held out.

What the two jointly indicate is unambiguous: **the limit is not the mapping.** A
per-vertebra confidence read from this model's per-region sigmoids carries little signal about
whether the level attached to that vertebra is the right one, however the channel is
chosen.

The phase estimation is nevertheless doing real work rather than disguising a sign
error, which is what the provisional numbers suggested. Uncalibrated sequence parity
scores 0.481, a global inversion of it scores 0.488, and per-case phase estimation
scores 0.581. A global sign flip recovers 0.007; estimating the phase per case recovers
0.100. The mechanism is that parity follows the vertebra's position in the model's
detected sequence, not its anatomical name, so a name-derived ordinal is out of phase
whenever the topmost visible vertebra is not C1: we observe anatomical T7, which is odd,
on the even channel at 0.963 against 0.0006 on the odd channel.

The negative result is the more useful half. It is consistent with what is known about
calibration of deep segmentation outputs, with the caveat that the calibration
literature we cite concerns categorical softmax outputs and does not transfer unchanged
to independent per-region sigmoids, and it sits alongside the strongest published
per-vertebra mislabel detector, which learns a random forest over geometric and intensity
features derived from the disagreement between two independently trained models and
reports an area under the curve of 0.82. Three qualifications, because this comparison is
load bearing. That paper does not describe itself as avoiding a softmax; the contrast
with our arms is our inference from its feature set and is stated as such. We quote 0.82
as its journal abstract states it and do not describe it as ROC AUC, because an earlier
conference version phrased the figure as precision-recall and no interval is given. The
per-vertebra external validation against expert adjudication is a separate, later paper
and is cited separately rather than merged into one reference. An interface bug of this
kind is worth finding and reporting because it is invisible to every check that compares
the score against human ratings rather than ground truth, but finding it does not by
itself yield a working quality flag.

### 4.6 The estimator, not the idea: an in-sample residual absorbs the outlier

The check is specified as leave one out residuals against regional splines fitted to
vertebral centroids. **That specification is sound**, and we verify it: implemented as
specified it detects 75.0 percent of single-level shifts and, on the masking analysis,
75.0 percent at 40 mm and 100.0 percent at 80 mm displacement.

The deployed code does not implement it. For regions of four or more levels, which is
the normal case, it computes an **in-sample** residual against the region's own spline;
true leave one out is reached only for regions of one to three levels, and then against
a global rather than a regional fit. Table 4 gives the consequence: the reported
residual is flat at approximately 0.2 mm across a 0 to 80 mm true displacement, and if
anything decreases, because the spline is fitted through the displaced point and
accommodates it. The leave-one-out residual tracks displacement almost exactly, 0.553
to 78.553 mm.

The distinction matters for what a reader should take away. This is not evidence that
geometric consistency checking is a poor idea for vertebral labelling. It is evidence
that the choice between an in-sample and a held-out residual decides whether such a
check functions at all, that the difference is invisible from the object, the rendering
and the model's segmentation accuracy, and that a deployed implementation can silently
diverge from a correct specification on exactly this point.

The paired injection design shows no discrimination. A single-level shift is flagged at
its own site in 5.1 percent of studies against a 22.7 percent control, which is worse
than chance. A whole-column error scores 97.0 percent against a 97.0 percent control.
False positives on error-free chains are 7.4 percent per vertebra and 91.7 percent per
study, closely reproducing the 11.1 percent and 97.4 percent measured on real deployed
output.

A 3.0 mm minimum-residual guard removes every false positive and every detection,
because in-sample residuals never exceed about 0.3 mm. A magnitude guard silences an
in-sample detector rather than repairing it. True leave one out detects 75.0 percent at
40 mm and 100.0 percent at 80 mm, at a cost of 50.0 percent false positives at region
endpoints, a leverage artifact with known remedies.

## 5. Discussion

Three findings generalise beyond spine imaging.

**Granularity is a property of the container.** Any per-object AI quality signal
delivered as a presentation state inherits the constraint in 4.1 and 4.2. If per-object
colour requires per-object layers, then the object count scales with the finding count,
which has implications for file size, for viewer layer handling, and for how a
practitioner following the reference implementation will discover the limitation only
after building.

**Rendering is weak evidence, and we can now say how weak.** A system validated by
looking at its output in one viewer can be non-conformant on many counts and can be
refused outright by the reference renderer for the same defects, with the cause
isolated to one Type 1 attribute. Conformance is what predicts behaviour in the next
viewer, and it is cheap to measure: two independent validators and a reference
renderer, all offline, all scriptable. We would argue this belongs in any AI-results
deployment as a routine gate, and that a rendered bitmap hash is a better regression
test than a screenshot review.

**Model accuracy and interface correctness are independent failure modes.** The
confidence failure here is not a modelling error. The segmentation was unchanged, the
formula was unchanged, and the published weights were as described. The error was in
which array index was read, and it was invisible to every check the project ran because
those checks compared the score against human ratings rather than against ground truth.
An ablation that holds the pipeline fixed and varies one interface decision isolates
this class of error, and we suggest it as a general instrument.

The negative result in 4.6 has a constructive form worth stating. The distinction
between an in-sample and a leave-one-out residual determines whether a geometric
consistency check works at all. That is a choice of estimator, not of threshold, and no
sweep over thresholds recovers it.

## 6. Limitations

The labelling model is trained on magnetic resonance imaging and the public benchmark
with named-level ground truth is computed tomography, so the flag-validity experiment
is out of distribution by construction. Segmentation quality is correspondingly poor
and a substantial share of cases produce no labelled output at all. We regard the
out-of-distribution setting as the one where a quality flag matters most, but it is not
an in-distribution result and should not be read as one. No clean, in-distribution,
named-level public magnetic resonance dataset exists for this model: the candidates are
either in its training data or group the spine into a single class.

One renderer is measured and no clinical viewer is. `dcmp2pgm` is the reference
greyscale rendering path and ships with the toolkit that also supplies `dcmpschk`, so
those two are not fully independent of each other. It establishes what a conformant
greyscale renderer does with these objects, which is the question sections 4.1 and 4.3
answer. It is not evidence about what a colour-capable clinical viewer draws, and our
statement that the deployed objects' colour is visible in their target viewer is
reported from deployment rather than measured here. A screen-based check across Weasis
and DICOMscope remains the obvious next step and is not a substitute for what is
measured, nor it for that.

Verification bias affects every AUC. 396 of 2241 predicted vertebrae, 17.7 percent, fall
beyond the 20 mm tolerance from any ground-truth centroid and cannot be scored, and 47
of 202 cases produce no landmark at all. Every arm is therefore computed on the matched
subset. The direction is unknown but not plausibly benign: if unmatched predictions are
disproportionately gross failures, the flag is being evaluated where the pipeline
already worked. The negative result is the robust direction, since removing hard cases
would if anything flatter the flag.

The geometric consistency results are synthetic. Synthetic data with known ground truth
establishes what an estimator can and cannot do in principle; it does not establish a
clinical rate.

A supporting clinical cohort exists, with research use permitted by its owner. It is
reported descriptively and is not the basis of any quantitative claim. Its internal
quality review was a single-observer screening pass, unrandomised and unblinded, and is
described as such.

## 7. Conclusion

Delivering a per-vertebra AI quality flag to an arbitrary viewer is constrained by the
container in a specific way: a conformant presentation state can carry per-object
colour only through per-object layers, the reference implementation cannot write it at
all, and the reference headless renderer draws no annotations, so it cannot be checked
there either. What the container does decide, and decisively, is whether the object
renders at all: one absent Type 1 attribute is the difference between an object a
conformant renderer accepts and one it refuses outright. Independently, the flag itself can be invalid for reasons internal to the model
interface, and a geometric consistency check computed in sample cannot detect the
displacement it is designed to find. Conformance and trustworthiness are separate
properties of an AI result object. Both are cheap to measure, neither implies the other,
and a deployed system can pass one while failing the other without any external
symptom.

## Tables

**Table 1.** The three colour routes against five authorities. Every cell is a
measurement, not a reading of the standard by us, except the PS3.3 column which cites
C.10.5 directly.

| route | attribute | PS3.3 | `highdicom` writes | `dciodvfy` | `dcmpschk` | `dcmp2pgm` draws it |
|---|---|---|---|---|---|---|
| graphic layer | Graphic Layer Recommended Display CIELab Value (0070,0401) | Type 3 | **yes** | yes | yes | no annotations drawn |
| line style | Pattern On Color CIELab Value (0070,0251), in Line Style Sequence (0070,0232) | Type 3 | no | yes | yes | no annotations drawn |
| text style | Text Color CIELab Value (0070,0241), in Text Style Sequence (0070,0231) | Type 3 | no | **no** | yes | no annotations drawn |

The rejection in the last cell is internal to the validator. `ShadowStyle` (0070,0244)
is flagged inside Text Style Sequence and accepted inside Line Style Sequence in the
same object, and a second independent presentation-state validator accepts the object
`dciodvfy` rejects.

**Table 2.** Conformance by object class, scored by `dciodvfy`. Errors are distinct
required-attribute absences per object; out-of-IOD counts distinct tags the validator
reports as not belonging to the IOD.

| object class | n | errors per object | out-of-IOD | passing |
|---|---:|---:|---:|---:|
| deployed GSPS, clinical | 38 | 7 | 6 | 0 of 38 |
| conformant GSPS, public VerSe | 9 | 1 | 0 | 0 of 9 |
| DICOM Segmentation, public VerSe | 6 | **0** | **0** | **6 of 6** |
| generated CT instances | 933 | **0** | **0** | **933 of 933** |

The single error on our conformant emitter is `Laterality`, a Type 2C conditional the
validator cannot evaluate for an unpaired body part. Absence is correct and a zero
length value draws a worse diagnostic.

**Table 3.** The channel-selection ablation. 155 of 202 public VerSe cases produced a
labelled result; 2241 vertebrae were predicted, 1845 matched a ground-truth centroid
within the challenge's 20 mm tolerance, and 373 of those carry a wrong level. The
pipeline, the segmentation and the confidence formula are identical across every row.
Only the rule choosing which output channel to read changes.

| arm | what it is | AUC | 95% CI |
|---|---|---:|---|
| `region_retired` | the published rule: channel from the first letter of the level name | 0.516 | [0.483, 0.549] |
| `parity_name` | the live server's rule: parity of the anatomical name | 0.572 | [0.539, 0.606] |
| `parity_sequence` | parity of position in the model's detected sequence | 0.481 | [0.449, 0.514] |
| `parity_sequence_inverted` | the same with one global sign flip | 0.488 | [0.456, 0.521] |
| `parity_sequence_phased` | the same with the phase estimated per case | **0.581** | [0.547, 0.614] |
| `mapping_free_top1` | highest channel mean, no mapping at all | 0.576 | [0.543, 0.609] |
| `mapping_free_margin` | gap between the top two channel means | 0.486 | [0.453, 0.519] |
| `argmax_mean` | full confidence formula on the argmax channel | 0.579 | [0.545, 0.612] |

Re-scored on the 1828 vertebrae where all eight arms are defined the ranking is
unchanged, so it is not an artefact of `parity_name` dropping its 17 undefined cases.

Ceilings, all chosen **with** the labels. Held out means fitted on half the cases and
scored on the other half, both directions, 40 folds; split by case rather than by
vertebra because vertebrae within a case are correlated.

| ceiling | in sample | held out | what it is |
|---|---:|---:|---|
| best single channel for all vertebrae | 0.566 | **0.550** | exact, exhaustive over 11 channels |
| best channel per anatomical level | 0.635 | **0.570** | coordinate ascent over 26 free parameters, **not** a bound |
| the same per-level search, **labels shuffled**, 1000 reps | 0.594 mean, 0.629 max | n/a | the optimism of the search with no signal present |

The in-sample 0.635 is not headroom. A search on shuffled labels, where no signal exists
by construction, reaches 0.594 on average over 1000 repetitions, so most of that figure
is the optimism of fitting 26 parameters to 1845 points. The excess is real rather than
noise, since no permutation reached 0.635 and the exact permutation p is
(0+1)/(1000+1) = 0.001. What the excess is not is transferable: evaluated on unseen
cases the same fitted mapping is worth 0.570, below the best rule already deployed. The
structure the search finds is genuine and worthless.

**Table 4.** The geometric consistency check, 432 synthetic studies per condition with
known ground truth, paired so each rate is measured on the same studies before and
after injecting the error.

| true displacement | reported residual, deployed (in sample) | residual under true leave one out | deployed detects |
|---:|---:|---:|---:|
| 0 mm | 0.212 mm | 0.553 mm | 21.5% |
| 20 mm | 0.235 mm | 19.843 mm | 3.5% |
| 40 mm | not tabulated separately | tracks displacement | 75.0% under the specification |
| 80 mm | 0.118 mm | 78.553 mm | 7.6% |

## Figures

**Figure 1.** The three colour routes against five authorities: PS3.3, `highdicom`,
`dciodvfy`, `dcmpschk` and `dcmp2pgm`. A status matrix, one row per route, with the
attribute tag on the row and the count of flagged attributes in the cell that rejects.
The renderer column is a third state, neither pass nor fail: it draws no annotations, so
it cannot answer the colour question.

**Figure 2.** Conformance across object classes, deployed GSPS, conformant GSPS, and
Segmentation, as a stacked count of errors and out-of-IOD attributes.

**Figure 3.** The public pair, both from VerSe under CC BY-SA. Left, a contiguous
nineteen-level labelling as the object encodes it; seventeen of the nineteen names
appear in the ground-truth mask, which labels T1 to L5 for this case, so C7 and SACRUM
are unscoreable rather than known wrong. Right, the same pipeline on a case whose ground
truth contains C1 to T6 only: eight assigned names are levels absent from the volume,
seven of them carrying confidence 0.82 to 0.96, while the flag fires on just two, one of
which is a level that is present. Marker fill encodes whether the level exists in the
volume and outline colour encodes whether the flag fired, so the two facts are separable
and hue is never the only encoding. Neither panel checks position within the 20 mm
tolerance, because these records carry no world coordinate.

An earlier version of this figure titled the left panel "all levels correct" and the
right panel "two anatomically impossible placements", and coloured the right panel by a
confidence threshold while describing it as anatomy. Both were overclaims: see retired
claim G18.

**Figure 4.** Channel selection ablation. Area under the curve per arm with 95 percent
intervals, the published and deployed rules marked, and below a divider the two
label-informed ceilings shown both in sample and held out, together with the same
search run on shuffled labels. The divider is there because the two groups have
different nulls: the eight rules fit nothing and their null is 0.50, while the ceilings
are fitted and their null is the shuffled-label distribution.

**Figure 5.** Reported residual against true displacement, in sample versus leave one
out, with the deployed flag rate overlaid. This is the single figure that carries
Section 4.6.

**Figure 6.** One Type 1 attribute decides whether a conformant renderer draws the
object. (a) the deployed encoding, which `dcmp2pgm` refuses, writing zero bytes and
emitting `instanceNumber absent or empty in presentation state`. (b) the same object
with only `InstanceNumber` (0020,0013) restored, which renders. (c) our from-scratch
conformant object. (b) and (c) are byte identical, SHA-256 prefix `5ea1ecb666bc6382`,
computed at figure-build time from the files on disk rather than quoted. All 38 objects
the deployed pipeline emitted lack this attribute and all 38 render correctly in the
commercial viewer they were built against. This result concerns whether the object is
accepted at all, which is upstream of annotation drawing, so it is unaffected by retired
claim G17.

## Declarations

**Funding.** None.

**Competing interests.** The author's affiliation is University at Buffalo School of
Management. The pipeline under study is an internal service developed by the author
while employed at aycan Medical Systems LLC, integrated with a commercial viewer; it is
not a cleared or released product, and nothing here should be read as a statement about
a regulated device. The clinical cohort is aycan's. Research use, publication of the
findings reported here, and release of the analysis code were granted by aycan in
writing on 31 July 2026. The segmentation checkpoints are the openly released upstream
TotalSpineSeg weights, not proprietary artefacts, and all quantitative claims rest on
public data and public weights. The commercial viewer named in the deployment
description is a third-party product, evaluated nowhere in this work, and no endorsement
is implied or received.

**Authorship.** Sole author. No other individual meets the ICMJE criteria for this work.

**Ethics.** The clinical cohort is retrospective and pseudonymised. No prospective
human subjects research was conducted. Public benchmark data is used under its stated
licence.

**Prior submission.** An earlier and substantially different abstract on this pipeline
was submitted to RSNA 2026 and not accepted. The present work retracts two quantitative
claims made there, as recorded in the claims ledger.

## Data and code availability

The evaluation harness, the validator invocations, the emitters, and the analysis
scripts are released. Public data identifiers: VerSe 2019 and 2020, OSF `nqjyw` and
`t98fz`, CC BY-SA 4.0. Model weights are not redistributable. The clinical cohort is
not released.

Every quantitative claim is traceable to one command in the released harness and to a
row in the claims ledger recording whether it was measured here, taken from the
literature, or retired.

## References

To be completed. Every entry requires field-by-field verification against the publisher
record before submission; the project has already found one citation in its own prior
prior-art list that does not exist as described. Verified so far:

1. Sekuboyina A, et al. VerSe: a vertebrae labelling and segmentation benchmark for
   multi-detector CT images. Medical Image Analysis. 2021;73:102166.
2. Dikici E, Bigelow M, Prevedello LM, White RD, Erdal BS. Integrating AI into radiology
   workflow: levels of research, production, and feedback maturity. Journal of Medical
   Imaging. 2020;7(1):016502.
3. Bridge CP, et al. Highdicom: a Python library for standardized encoding of image
   annotations and machine learning model outputs in pathology and radiology. Journal of
   Digital Imaging. 2022;35(6):1719-1737.
4. Isensee F, Jaeger PF, Kohl SAA, Petersen J, Maier-Hein KH. nnU-Net: a self-configuring
   method for deep learning-based biomedical image segmentation. Nature Methods. 2021.
5. IHE Radiology Technical Framework Supplement: AI Results (AIR), Revision 1.3, Trial
   Implementation.
6. Ilkhan IH, Gumuskaya H, Turgut F. Vertebra segmentation and Cobb angle calculation
   platform for scoliosis diagnosis using deep learning: SpineCheck. Informatics.
   2025;12(4):140.
7. Son Y, Joo B, Park M, Ahn SJ, Kim S, Lee HS. Real-world use of PACS-integrated
   automated spine numbering in MRI. Clinical Imaging. 2026;132:110744.
8. Sung J, Chang PD, Ayobi A, et al. Multicenter, multinational, and multivendor
   validation of an artificial intelligence application. Diagnostics. 2026;16(2):194.
9. Mehrtash A, et al. Confidence calibration and predictive uncertainty estimation for
   deep medical image segmentation. IEEE Transactions on Medical Imaging. 2020.
10. Netherton TJ, et al. An automated treatment planning framework for spinal radiation
    therapy. International Journal of Radiation Oncology, Biology, Physics. 2022.
11. Moller H, et al. VERIDAH. arXiv:2601.14066. 2026.
12. Warszawer Y, et al. TotalSpineSeg. Preprint; no journal version located as of
    2026-07-30.
