# DICOM SEG writer, measured

Measured 2026-07-30. Validator: `dciodvfy` from dicom3tools, the same binary the
GSPS baseline used (`<path>\tools\dicom3tools\dciodvfy.exe`, 10,298,894
bytes, dated 2026-07-01, recorded elsewhere in these results as snapshot
20260701065818). Independent third party scorer, not our own reading of PS3.3.

Environment: `C:\Users\dekay\miniconda3\envs\spinelab\python.exe`, Python 3.10.20,
**highdicom 0.28.1**, pydicom 3.0.2, numpy 2.2.6, nibabel. No GPU used, no model
run: the SEG objects below carry the VerSe ground truth mask, not a prediction.

New module: `src/spinelab/gsps/seg_writer.py`.

## 1. What highdicom can actually write

Determined by enumerating every `highdicom.SOPClass` subclass in the installed
package, not by reading documentation.

| module | class | writes |
|---|---|---|
| `highdicom.seg` | `Segmentation` | Segmentation Storage |
| `highdicom.pr` | `GrayscaleSoftcopyPresentationState` | **GSPS, 1.2.840.10008.5.1.4.1.1.11.1** |
| `highdicom.pr` | `ColorSoftcopyPresentationState` | Color Softcopy PS |
| `highdicom.pr` | `PseudoColorSoftcopyPresentationState` | Pseudo-Color Softcopy PS |
| `highdicom.pr` | `AdvancedBlendingPresentationState` | Advanced Blending PS |
| `highdicom.sr` | `EnhancedSR`, `ComprehensiveSR`, `Comprehensive3DSR` | Structured Reporting |
| `highdicom.pm` | `ParametricMap` | Parametric Map |
| `highdicom.ko` | `KeyObjectSelectionDocument` | Key Object Selection |
| `highdicom.sc` | `SCImage` | Secondary Capture |
| `highdicom.ann` | `MicroscopyBulkSimpleAnnotations` | Microscopy Bulk Annotations |
| `highdicom.legacy` | `LegacyConvertedEnhanced{CT,MR,PET}Image` | legacy converted enhanced |

`highdicom.pr.SOP_CLASS_UIDS` is verbatim
`{'1.2.840.10008.5.1.4.1.1.11.1', '.11.2', '.11.3', '.11.8'}`.

**So highdicom CAN write a Grayscale Softcopy Presentation State. The paper must
not claim otherwise.** Proven by construction, not inference: a scratch probe under
`$RUNS` builds one with `hd.pr.GrayscaleSoftcopyPresentationState`, referencing the
demo CT series, with two `hd.pr.GraphicLayer` items each carrying a
`display_color`, two `hd.pr.TextObject` items and two `hd.pr.GraphicObject`
polylines. Verbatim `dciodvfy` on the result:

```
GrayscaleSoftcopyPresentationState
Error - Missing attribute Type 2C Conditional Element=<Laterality> Module=<GeneralSeries>
```

One error, and it is the same unevaluable `Laterality` conditional that our own
conformant GSPS variants carry (see `gsps_variants.md`). **highdicom's GSPS is at
conformance parity with our hand rolled conformant variant.**

### The gap that does exist, stated narrowly

highdicom cannot put a colour on an individual annotation inside a GSPS. Measured
by grepping the installed package:

| attribute | occurrences in highdicom 0.28.1 |
|---|---|
| `RecommendedDisplayCIELabValue` | 5, in `ann/content.py`, `pr/content.py`, `seg/content.py`, `seg/sop.py` |
| `GraphicLayerRecommendedDisplayCIELabValue` | 1, in `pr/content.py` |
| `TextStyleSequence` | **0** |
| `LineStyleSequence` | **0** |
| `TextColorCIELabValue` | **0** |
| `LineColorCIELabValue` | **0** |

Confirmed on the object it wrote: `TextObjectSequence[0]` has no (0070,0231) and
`GraphicObjectSequence[0]` has no (0070,0232). Its only GSPS colour route is
`GraphicLayer(display_color=...)` writing (0070,0401).

Consequence for the GSPS colour experiment in `gsps_variants.md`: of the three
routes, highdicom can express **layer** only. It cannot express **line**, the
conformant per-annotation route, and it cannot express **text**, the out-of-IOD
route the deployed pipeline actually uses. Both remaining arms require the hand
rolled `writer.py`. That is the citable gap, and it is a per-annotation colour
gap, not a GSPS gap.

### CIELab encoding cross check

Independent agreement between highdicom and our hand rolled encoder, so the two
arms of the viewer experiment carry the identical colour:

| colour | L\*a\*b\* | `hd.color.CIELabColor().value` | `writer.cielab()` |
|---|---|---|---|
| normal | 74.9, 23.9, 78.9 | 49086, 39038, 53173 | 49086, 39038, 53173 |
| flagged | 81.2, 118.1, 72.1 | 53214, 63248, 51426 | 53214, 63248, 51426 |

Both match exactly. Asserted by `python -m spinelab.gsps.seg_writer --codes`.

## 2. Coded concepts, looked up rather than typed

Every SNOMED CT code is read at import time from pydicom's copy of the DICOM
PS3.16 concept tables (`pydicom.sr.codedict.codes.SCT`). No code value is written
by hand anywhere in the module, so none can be fabricated.

**26 of 28 VerSe levels have a PS3.16 SNOMED CT code. 2 do not.**

| levels | scheme | evidence |
|---|---|---|
| C1-C7, T1-T12, L1-L5 | SCT | all present, and all are members of CID 7151 Segmentation Property Type and CID 7603 Vertebra |
| Sacrum | SCT 54735007 | member of CID 7151 |
| Coccyx | SCT 64688005 | member of CID 7151 |
| **L6** (VerSe label 25) | **99SPINELAB** | no SCT entry matches "L6" or "sixth lumbar" in 11,349 SCT keywords |
| **T13** (VerSe label 28) | **99SPINELAB** | no SCT entry matches "T13" or "thirteenth thoracic" |

Segmented Property Category is `(91723000, SCT, "Anatomical Structure")`, verified
to be a member of CID 7150 Segmentation Property Category.

L6 and T13 use the private coding scheme designator `99SPINELAB`, which PS3.3
C.12.1.1.1 requires to begin with "99", and the object declares it in a
`CodingSchemeIdentificationSequence` item. `dciodvfy` reports it, verbatim:

```
Warning - Unrecognized defined term <99SPINELAB> for value 1 of attribute <Coding Scheme Designator>
```

Twice, once for the segment's type code and once for the declaration. That
warning is the correct outcome: the standard permits a locally defined scheme and
the validator has no way to recognise ours. The alternative would have been to
invent a SNOMED code, which was not done.

Print the whole table with:

```
python -m spinelab.gsps.seg_writer --codes
```

## 3. Segmentation type: BINARY, and why

The labels are a hard argmax. VerSe mask values are mutually exclusive integer
levels with no per-voxel occupancy or probability behind them, so FRACTIONAL
would assert a number that does not exist. The confidence signal this project
actually has is one value per vertebra, not per voxel, so it belongs in a segment
level attribute, not in the pixels. BINARY is also the variant viewers have
supported longest, which matters when the measurement is rendering support.
LABELMAP exists in highdicom 0.28.1 (`SegmentationTypeValues` is
`['BINARY', 'FRACTIONAL', 'LABELMAP']`) but is a recent addition to the standard
and would confound a viewer comparison, so it is not used.

## 4. Colour in SEG: (0062,000D) is in the IOD

SEG has exactly one place for a colour, Recommended Display CIELab Value, Type 3
inside each item of Segment Sequence. `dciodvfy` reports **zero** out-of-IOD
attributes for every object below, including the ones that set it, which is the
measured evidence that it is in the Segmentation IOD. Contrast with GSPS, where
the text colour route draws six out-of-IOD flags.

The colour axis, analogous to `writer.COLOUR_ROUTES`:

| variant | segments | segments with (0062,000D) | normal | flagged | flagged levels | bytes |
|---|---|---|---|---|---|---|
| `seg_colour_none` | 12 | 0 | 0 | 0 | none | 11,512,906 |
| `seg_colour_uniform` | 12 | 12 | 12 | 0 | none | 11,513,076 |
| `seg_colour_flag` | 12 | 12 | 10 | 2 | C3, T1 | 11,513,074 |

Carrying a per-vertebra colour flag in SEG costs **168 bytes** for 12 segments,
`flag` minus `none`, which is exactly 12 items of (0062,000D) US with 3 values
under explicit VR little endian: 4 byte tag, 2 byte VR, 2 byte length, 6 byte
value. The 2 byte difference between `flag` and `uniform` is a randomly generated
UID length, not content.
Pixel data, frame count and segment codes are byte-identical across the three, so
any difference a viewer shows is attributable to the colour attribute alone. That
makes the GSPS versus SEG comparison fair on the colour axis: both formats carry
the same two CIELab colours per vertebra.

## 5. dciodvfy results, verbatim

The three cases reference the canonical public CT series from
`spinelab.io.nifti_to_dicom` (see `public_dicom.md`), which itself scores zero
dciodvfy errors on all 933 instances, so nothing in the chain carries an error.

Case A, `sub-gl003_dir-ax`, cervical axial CT, 12 levels C1-T5, all SNOMED coded:

```
Segmentation
```

Nothing else. Zero errors, zero warnings.

Case B, `sub-verse505`, thoracolumbar axial CT converted from an LAS volume, 10
levels T9-**L6**:

```
Segmentation
Warning - Unrecognized defined term <99SPINELAB> for value 1 of attribute <Coding Scheme Designator>
Warning - Unrecognized defined term <99SPINELAB> for value 1 of attribute <Coding Scheme Designator>
```

Case C, `sub-verse525_dir-sag`, obliquely oriented sagittal CT, 6 lumbar levels
L1-**L6**: byte for byte identical dciodvfy output to case B.

Aggregate over all 6 SEG objects, the three cases plus the three colour variants:

```
python -m spinelab.gsps.validate <path>\runs\seg_demo\canonical --json results/seg_writer_validation.json
```

| metric | value |
|---|---|
| files with zero errors | **6/6** |
| required attributes absent | **none** |
| out-of-IOD attributes | **none** |
| other diagnostics | 2/6, the `99SPINELAB` defined term on the two cases carrying L6 |

For comparison, the 38 shipped GSPS objects score 7 errors and 6 out-of-IOD
attributes each, and the conformant GSPS variants score 1 error and 0 out-of-IOD.
**The SEG objects score 0 and 0.**

## 6. Fidelity: the SEG round trips exactly

Read back with `highdicom.seg.segread` and
`get_pixels_by_source_instance(combine_segments=True, relabel=False)`, then
compared voxel for voxel against the source NIfTI mask, case `sub-gl003_dir-ax`:

| metric | value |
|---|---|
| exact voxel agreement | **56,098,816 / 56,098,816 = 1.000000** |
| mismatching voxels | **0** |
| Dice per segment, all 12 | **1.000000** |
| read back time | 0.1 s |

Per-segment voxel counts, source and read back identical: C1 138,777, C2 178,444,
C3 128,568, C4 125,267, C5 140,211, C6 150,088, C7 182,036, T1 222,491,
T2 228,435, T3 226,412, T4 259,518, T5 274,639.

Repeated for all three canonical cases. Per-segment voxel counts are order
independent, which makes the comparison valid on `sub-verse505`, where the
converter had to reverse an axis to turn an LAS volume into a conventional
posterior column direction.

| case | segments | read back total | NIfTI total | every segment count equal |
|---|---:|---:|---:|---|
| `sub-gl003_dir-ax` | 12 | 2,254,886 | 2,254,886 | **yes** |
| `sub-verse505`, LAS | 10 | 761,116 | 761,116 | **yes** |
| `sub-verse525_dir-sag`, oblique | 6 | 1,217,604 | 1,217,604 | **yes** |

That is an independent cross check between two separately written geometry
implementations: `nifti_to_dicom` plans the DICOM grid by permuting the affine,
`seg_writer` samples the mask back onto that grid by inverting it. They agree
exactly on an axis aligned case, an axis reversed case and an oblique case.

### Mismatched grid path, measured

`resample_labels_to_series` maps the label volume onto whatever grid the
referenced series actually has, by inverting the NIfTI affine into DICOM LPS. On
an identical grid it is exact: mask voxels on the series grid equal mask voxels in
the NIfTI for both demo cases (2,254,886 and 1,217,604, both exact).

Deliberate mismatch test, public data only: a CT series built from every second
slice of the same volume and shifted half a source slice, so no sample lands on a
source voxel centre.

| metric | value |
|---|---|
| source instances | 107, spacing 0.29101601243, thickness 2.5 |
| mask voxels, source grid | 2,254,886 |
| mask voxels, coarse grid | 1,128,680 |
| ratio | **0.5005**, expected about 0.5 |
| labels preserved | all 12 |
| SEG written | 12 segments, 172 frames, 5.7 MB, 0 dciodvfy errors |

### Verified negative: an unrelated series is refused, not silently mislabelled

Pointing the writer at a geometrically unrelated series is the failure mode that
would produce a plausible looking but wrong SEG. Tested against the clinical
sagittal CT (40 instances, 1027x512, oblique, `ImageOrientationPatient`
`[-0.1099, 0.9939, 0.0, -0.0186, -0.0021, -0.9998]`, a different patient):

```
mask voxels landing on the clinical grid: 0
correctly refused: ValueError: label volume is empty on this series grid
```

Zero voxels land and `build_segmentation` refuses by name. No SEG was written and
none was kept. This was the only use made of clinical data in this task, and it
produced no output object.

`resample_labels_to_series` also now verifies that every instance shares frame 0's
Rows, Columns, PixelSpacing and ImageOrientationPatient, and raises naming the
offending instance if not, rather than silently assuming a single plane stack.

## 7. Size, GSPS versus SEG

Same case, same referenced series, same information content (12 named vertebrae,
2 flagged red):

| object | bytes | ratio |
|---|---|---|
| GSPS written by highdicom, 2 layers | 2,432 | 1 |
| GSPS shipped by the deployed pipeline, 17 annotations | 10,242 | 4.2 |
| **SEG, `sub-gl003_dir-ax`, 12 segments, 345 frames, BINARY** | **11,513,080** | **4,734** |
| SEG, `sub-verse525_dir-sag`, 6 segments, 203 frames | 16,096,198 | 6,618 |
| SEG, `sub-verse505`, 10 segments, 598 frames | 20,011,096 | 8,228 |

Byte counts vary by up to a few bytes between runs because generated UIDs vary in
length. The sagittal SEG measured 16,096,198 on one run and 16,096,200 on the next.
Nothing else changes.

Three orders of magnitude. That is a real, measured argument for the presentation
state side of the comparison and it should be in the paper. Note the GSPS row is
2 layers to the SEG's 12 segments, so the ratio is indicative rather than a
matched comparison; the deployed 17 annotation GSPS row is the closer analogue and
is still 1,124 times smaller than the SEG. A presentation state's size is set by
annotation count, a SEG's by voxel count, which is the structural point.

Write time, measured on this machine, CPU only, no GPU, `seg_from_nifti` end to
end including reading and decoding every source instance:

| case | source instances | segments | frames | seconds |
|---|---:|---:|---:|---:|
| `sub-gl003_dir-ax` | 214 | 12 | 345 | **9.1** |
| `sub-verse525_dir-sag` | 119 | 6 | 203 | **9.1** |
| `sub-verse505` | 600 | 10 | 598 | **26.7** |

Single measurement per case, n = 1, so treat as an order of magnitude only. Most
of the time is reading the source series, not building the SEG.

## 8. Reproduce

The demo runs entirely on public VerSe data. Step one is the canonical converter
owned by the `public-dicom` task, step two onward is this module.

```
$env:PYTHONPATH="<path>\spine-gsps\src"
$py="C:\Users\dekay\miniconda3\envs\spinelab\python.exe"
$D="<path>\datasets\verse_4skx2"
$P="<path>\runs\public_dicom"
$R="<path>\runs\seg_demo\canonical"

# 1. the public CT series to reference, 933 instances over three cases
& $py -m spinelab.io.nifti_to_dicom --demo --out $P

# 2. one SEG per case
& $py -m spinelab.gsps.seg_writer --mask "$D\sub-gl003_dir-ax_seg-vert_msk.nii.gz" `
    --series "$P\sub-gl003_dir-ax" --out "$R\sub-gl003_dir-ax_SEG.dcm" `
    --colour flag --flag "C3,T1"
& $py -m spinelab.gsps.seg_writer --mask "$D\sub-verse505_seg-vert_msk.nii.gz" `
    --series "$P\sub-verse505" --out "$R\sub-verse505_SEG.dcm" `
    --colour flag --flag "L4"
& $py -m spinelab.gsps.seg_writer --mask "$D\sub-verse525_dir-sag_seg-vert_msk.nii.gz" `
    --series "$P\sub-verse525_dir-sag" --out "$R\sub-verse525_dir-sag_SEG.dcm" `
    --colour flag --flag "L6"

# 3. the three colour variants, source series held fixed
& $py -m spinelab.gsps.seg_writer --mask "$D\sub-gl003_dir-ax_seg-vert_msk.nii.gz" `
    --series "$P\sub-gl003_dir-ax" --out "$R\variants" --design --flag "C3,T1"

# 4. coded concept table and the CIELab cross check
& $py -m spinelab.gsps.seg_writer --codes

# 5. conformance
& $py -m spinelab.gsps.validate "$R" --json results\seg_writer_validation.json
```

The source series is referenced correctly, verified rather than assumed. For every
case: each SOP Instance UID in `ReferencedSeriesSequence` is present on disk
(214/214, 600/600, 119/119), zero series UID mismatches, zero SOP class UID
mismatches, and the SEG's `FrameOfReferenceUID` and `StudyInstanceUID` both equal
the source series values.

## 9. Corrections and caveats

1. **The demo used public VerSe data, not clinical data.** Every SEG object
   reported here references a CT series derived from the public VerSe volumes. The
   clinical series under
   `$BASELINE\test_api\refined_gsps_1\pat_XXXX\SAGITTAL_BONE_SN007` was read only
   for the geometry probe and the refusal test in section 6, and produced no
   output object. Nothing in this file needs redoing on public data. It already
   is public data.
2. **The demo was re-pointed at the canonical public series and this file reports
   the re-measured numbers.** An earlier pass used
   `seg_writer.nifti_to_ct_series`, a stopgap written here before
   `spinelab.io.nifti_to_dicom` landed. Both were run. Every SOP Instance UID
   differs between the two, and the SEG for the same case differs by 1,764 bytes
   (11,511,316 against 11,513,080) because the canonical converter writes longer
   UIDs. Every other measurement was identical: same segment count, same frame
   count, same exact voxel round trip, 6/6 zero errors either way.
   `nifti_to_ct_series` is retained but marked superseded and must not be used for
   anything released. Its instances score one dciodvfy error, the unevaluable
   `Laterality` conditional, where the canonical converter's score zero.
3. **`validate.py` reports the IOD as "(unrecognised)" 6/6.** Its `RE_IOD` regex
   requires the IOD name to end in `PresentationState`, `Storage`, `Image` or
   `IOD`, and `dciodvfy` prints the bare word `Segmentation`. The IOD **is**
   recognised by the validator, as the verbatim output in section 5 shows. This is
   a cosmetic limitation of our aggregator, not a finding about the objects.
   `validate.py` was deliberately not modified, because another agent may be
   editing it concurrently. Adding `Segmentation` to that alternation is a
   one-line fix for whoever owns the file.
4. **The stopgap CT series had two real conformance bugs, both found by dciodvfy
   and fixed.** Recorded because the same two traps catch anyone writing DICOM out
   of numpy, not because this code is still on the critical path. First, pydicom
   wrote `repr(float)` into Pixel Spacing, giving
   `0.29101601243019104`, 19 characters, and DS is capped at 16 bytes: verbatim
   `Error - Value invalid for this VR - (0x0028,0x0030) DS Pixel Spacing ...
   Length invalid for this VR = 19, expected <= 16`. Fixed with `_fmt_ds`.
   Second, `Error - A value is required for value 3 in CT Images - attribute
   <ImageType>`. Fixed by deriving the plane from the slice normal. The CT
   instances now score one error, the same unevaluable `Laterality` Type 2C
   conditional as everything else in this project, plus for the sagittal case
   `Warning - Unrecognized defined term <SAGITTAL> for value 3 of attribute
   <Image Type>`, because PS3.3 C.8.2.1.1.1 lists only AXIAL and LOCALIZER and has
   no term for a reformatted plane. Reporting SAGITTAL was preferred to falsely
   claiming AXIAL.
5. **Person Name.** Writing a bare `spinelab` into a PN draws
   `Warning - Value dubious for this VR - ... Retired Person Name form` from
   dciodvfy and a matching warning from highdicom. This is the identical warning
   all 38 shipped GSPS objects carry for `PatientName = ANON_PAT_XXXX`. Fixed here
   by a trailing caret, which is the documented way to declare a deliberate one
   component name. The same one line fix would clear that warning from the GSPS
   side.
6. **The flagged levels are hand chosen, not detector output.** C3 and T1 in case
   A and L6 in case B were passed on the command line purely to exercise the
   colour path. No flag detector was run. Given finding 5 in CLAUDE.md, that the
   spline detector fires on noise, no automatic flag should be wired into this
   writer until the detector is fixed.
7. **`verse_4skx2` case count is unstable and CLAUDE.md is out of date on it.**
   The brief says 40 complete cases. Counted directly four times over about
   twenty minutes on 2026-07-30, in order: **66**, then 126, then 129, then 144
   cases with both a CT and a vertebra mask. Another agent is populating the
   directory concurrently and the manifest declares 202 subjects available. Any
   claim quoting a VerSe case count must re-measure at the time of writing. The
   two demo cases were confirmed complete at the time they were used.
8. **No model was run.** These SEG objects carry the VerSe organiser's ground
   truth mask. The out-of-distribution caveat in CLAUDE.md (an MRI-only model
   applied to CT) does not apply to any number in this file. When the writer is
   fed real predictions, it will.
9. **`ImplementationClassUID`.** highdicom writes its own registered
   implementation class UID. We do not own a UID root. That is fine for a research
   artifact and must be replaced before any clinical use, the same caveat
   `writer.py` carries.
