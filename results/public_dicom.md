# VerSe NIfTI to DICOM CT: geometry round trip and conformance

Measured 2026-07-30 on this machine. Converter:
`src/spinelab/io/nifti_to_dicom.py`. Validator: `dciodvfy` from dicom3tools,
Windows binary dated 2026-07-01, the same snapshot used for the GSPS baseline.
Readers used for verification: `pydicom` 3.0.2 and `SimpleITK` 2.5.5 with GDCM.
`nibabel` 5.4.2, `numpy` 2.2.6, Python 3.10.20.

## Why

All nine GSPS variants measured in `gsps_variants.md` derive from aycan clinical
CT, so the artifact cannot be released. VerSe is CC BY-SA 4.0 and public but ships
as NIfTI, while both the pipeline and the GSPS objects need DICOM. This converter
removes the clinical dependency: every artifact can now be rebuilt from public
data.

Reproduce:

```
python -m spinelab.io.nifti_to_dicom --demo --out <path>\runs\public_dicom \
    --roundtrip --simpleitk --json <path>\runs\public_dicom\_roundtrip.json
python -m spinelab.gsps.validate <path>\runs\public_dicom \
    --json results/public_dicom_validation.json
```

## Headline

**933 CT Image Storage instances across three cases. dciodvfy reports zero errors
and zero out of IOD attributes on all 933. Worst world coordinate round trip error
over the three cases is 4.03e-11 mm read back with pydicom and 1.47e-07 mm read
back with SimpleITK and GDCM. Of 288,265,728 voxels compared, zero mismatched and
the maximum Hounsfield difference is 0.**

The remaining diagnostic is one warning on the 119 sagittal instances, discussed
below, and it is a defined term extension, not a missing or illegal attribute.

## The three cases

The staged VerSe subset carries three distinct orientation codes, so all three are
converted rather than the two the task asked for. The third is also the only case
in the subset that is not axial and the only one whose affine is not exactly axis
aligned.

| case | NIfTI axcodes | plane chosen | instances | Rows x Columns | PixelSpacing (row, col) mm | SpacingBetweenSlices mm | HU range | RescaleIntercept |
|---|---|---|---:|---|---|---|---|---:|
| `sub-gl003_dir-ax` | LPS | AXIAL | 214 | 512 x 512 | 0.29101601243019, 0.29101601243019 | 1.25 | -3024 to 3071 | -3024 |
| `sub-verse505` | LAS | AXIAL | 600 | 512 x 512 | 0.9765625, 0.9765625 | 0.90000152587891 | -1024 to 1921 | -1024 |
| `sub-verse525_dir-sag` | PSR | SAGITTAL | 119 | 1229 x 512 | 0.38079739243097, 0.38085936995772 | 3.00038329389425 | -1024 to 2106 | -1024 |

Note that the third case is anisotropic in plane as well (0.380797 against
0.380859 mm), so a converter that wrote a single PixelSpacing value would already
be wrong here.

Resulting Image Orientation Patient values, as written:

```
sub-gl003_dir-ax      1, 0, 0, 0, 1, 0
sub-verse505          1, 0, 0, -0, 1, -0
sub-verse525_dir-sag  -0.0212347057904, 0.99977426140829, -0.0007165860002,
                       0.03372678176645, -0.0, -0.9994310902667
```

`sub-verse505` is LAS, so its second axis points anterior and has to be reversed
to give the conventional posterior column direction. The reversal shows in the
Image Position Patient origin, not in the cosines, which is exactly the kind of
change that is invisible unless the round trip is checked.

`sub-verse525_dir-sag` is a genuinely oblique sagittal volume: the plane normal is
0.9994 along patient right, tilted by about 1.2 degrees, and the two in plane axes
are orthogonal to 3.9e-11 in cosine. Its Image Position Patient for instance 60 is
`14.9270500168204, -283.54821123183, -1438.5714568719`.

Output size on disk: 107.4 MB, 301.0 MB and 143.0 MB, 551.4 MB in total. Written
under `<path>\runs\public_dicom`, which is gitignored.

## Round trip geometry error, the number asked for

The series is read back, the affine is reconstructed from Image Position Patient,
Image Orientation Patient, Pixel Spacing and Rows and Columns alone, and the index
permutation between that and the source NIfTI is recovered from the two affines.
Nothing is taken from the writer's own bookkeeping. Both maps are affine, so the
maximum coordinate disagreement over the volume is attained at a corner of the
index cube and all eight corners are evaluated.

Read back with this module's `read_series`, that is pydicom:

| case | max world error mm | mean world error mm | index residual voxels | voxels compared | mismatched | max HU error |
|---|---|---|---|---:|---:|---:|
| `sub-gl003_dir-ax` | **7.637e-13** | 4.609e-13 | 3.553e-15 | 56,098,816 | 0 | 0 |
| `sub-verse505` | **1.137e-13** | 5.684e-14 | 2.220e-16 | 157,286,400 | 0 | 0 |
| `sub-verse525_dir-sag` | **4.029e-11** | 2.577e-11 | 2.910e-11 | 74,880,512 | 0 | 0 |

Read back independently with SimpleITK 2.5.5 and GDCM, which is what any
downstream consumer will actually use:

| case | max world error mm | mean world error mm | direction determinant | voxels compared | mismatched | max HU error |
|---|---|---|---:|---:|---:|---:|
| `sub-gl003_dir-ax` | **7.637e-13** | 4.609e-13 | 1 | 56,098,816 | 0 | 0 |
| `sub-verse505` | **1.137e-13** | 5.684e-14 | 1 | 157,286,400 | 0 | 0 |
| `sub-verse525_dir-sag` | **1.472e-07** | 7.362e-08 | 1 | 74,880,512 | 0 | 0 |

The residual is decimal string precision, nothing else. Direction cosines and
positions are written as DS values formatted to the most precision that fits in
the 16 byte VR limit, which is about 15 significant figures. SimpleITK is four
orders of magnitude looser than pydicom on the oblique case only, consistent with
GDCM parsing the same strings at lower internal precision on a geometry where the
error is amplified by the tilt. Both are eleven orders of magnitude below one
voxel and eight orders below the 20 mm tolerance the VerSe scorer uses.

The determinant of the reconstructed direction matrix is +1 in all three cases.
Slices advance along `cross(IOP[0:3], IOP[3:6])`, so SpacingBetweenSlices is
positive and the frame is right handed rather than accidentally mirrored.

Intra series consistency, measured on read back: Image Orientation Patient spread
across instances is exactly 0 in all three cases, worst slice spacing spread is
8.98e-12 mm, worst residual of the fitted linear position stack is below 1e-11 mm.

## Anatomical check with the dataset's own annotation

The VerSe centroid JSON is an independent annotation that carries its own
`direction` record, matching the NIfTI axcodes in all three cases. Mapping each
labelled vertebral centroid to LPS through the NIfTI affine and then into the
DICOM index space gives:

| case | ctd direction | centroids | max affine disagreement mm | max HU difference |
|---|---|---:|---|---:|
| `sub-gl003_dir-ax` | LPS | 12 | 1.421e-14 | 0 |
| `sub-verse505` | LAS | 10 | 1.271e-13 | 0 |
| `sub-verse525_dir-sag` | PSR | 6 | 2.309e-13 | 0 |

All 28 centroids land on the same voxel and the same Hounsfield value through both
paths. Distance from an exact centroid to the centre of the nearest DICOM voxel is
0.31 to 0.57 mm, which is half voxel quantisation and nothing more. A transposed
or flipped axis mapping would put the centroid of a vertebral body in air, so this
is a domain level check and not another restatement of the affine algebra.

Method note: rounding to the nearest voxel independently on each side is tie
sensitive, because a centroid whose coordinate is exactly 224.5 tie breaks
differently from 224.5 plus 1e-13, and differently again when the axis is flipped.
A first version of this check reported spurious 176 HU and 47 HU differences from
exactly that. It now rounds once, in the source index space, and carries the
integer index through, which removes the artifact. The affine numbers above were
unaffected either way.

## Generality: 48 signed permutations and the full staged subset

The three real cases exercise three of the 48 possible axis permutation and flip
combinations. A synthetic 7 x 9 x 11 volume at 0.7, 1.3, 2.9 mm was written and
round tripped under all 48:

```
passed 48/48, worst max world error 4.314e-13 mm
```

Separately, `plan_geometry` was run header only over every VerSe CT volume staged
on this machine. At the time of the run there were 105 `*_ct.nii.gz` files and all
105 planned without error: 96 axial and 9 sagittal, with axcodes LPS 30, LAS 66,
PSR 9.

**Surprise worth recording.** `CLAUDE.md` says `verse_4skx2` has 40 complete VerSe
cases. It held 47 CT volumes when this task started, 49 a minute later, 105 when
the sweep ran and 106 a minute after that. The directory is being populated
concurrently, so the 105 figure is a timestamp, not a dataset size. Do not quote
it as the cohort.

## dciodvfy verdict, exact output

933 files, one subprocess per file:

```
IOD recognised as
  CTImage                                              933/933

ERRORS: required attributes absent  (count = files affected of 933)
  none

OUT OF IOD: attributes present that this IOD does not define
  none

OTHER DIAGNOSTICS
  warning Unrecognized defined term <REFORMATTED> for value 3 of attribute <Image  119/933

files with zero errors: 933/933
```

Records in `results/public_dicom_validation.json`.

Verbatim single file output. The two axial cases are completely silent:

```
### sub-gl003_dir-ax\sub-gl003_dir-ax_0001.dcm
exit code 0
CTImage

### sub-verse505\sub-verse505_0300.dcm
exit code 0
CTImage

### sub-verse525_dir-sag\sub-verse525_dir-sag_0060.dcm
exit code 0
CTImage
Warning - Unrecognized defined term <REFORMATTED> for value 3 of attribute <Image Type>
```

The 814 axial instances produce no diagnostic of any kind, not even the DICOMDIR
warnings that all 38 shipped GSPS objects carry.

### The one remaining warning, and why it was chosen deliberately

PS3.3 C.8.2.1.1.1 gives AXIAL and LOCALIZER as the Defined Terms for value 3 of
Image Type in a CT image, and dciodvfy treats an absent value 3 as a hard error:

```
Error - A value is required for value 3 in CT Images - attribute <ImageType>
```

Measured tolerance of the validator, one instance per candidate:

| value 3 | dciodvfy |
|---|---|
| `AXIAL` | clean |
| `LOCALIZER` | clean |
| `REFORMATTED` | `Warning - Unrecognized defined term <REFORMATTED>` |
| `SAGITTAL` | same warning |
| `VOLUME` | same warning |
| absent | **Error**, a value is required |

So a non axial CT series must either carry a term outside the list or state
something false. Defined Terms are extensible under PS3.5 Section 6.1, so
`REFORMATTED` is used for non axial planes and `AXIAL` for axial ones. Calling a
sagittal image AXIAL would put a factual misstatement inside the object to buy a
silent validator, which is the wrong trade for a paper about conformance.
`--image-type-value3` overrides it if a viewer under test refuses the extension.

This is a small instance of the same tension `gsps_conformance_baseline.md`
documents for colour in a presentation state: the IOD's enumerated vocabulary is
narrower than the data that exists.

## What the converter asserts, and what it refuses to invent

Deliberately synthetic, and named so:

| attribute | value |
|---|---|
| `PatientName` | `VERSE^SUB-GL003_DIR-AX`, family `VERSE`, given the subject id |
| `PatientID` | the VerSe subject id verbatim, for example `sub-gl003_dir-ax` |
| `InstitutionName`, `InstitutionalDepartmentName` | `PUBLIC_VERSE_DATA` |
| `Manufacturer` | `spinelab` |
| `ManufacturerModelName` | `spinelab-nifti-to-dicom` |
| `PatientIdentityRemoved` | `YES` |
| `DeidentificationMethod` | `PUBLIC VERSE DATA, SYNTHETIC IDENTIFIERS ONLY` |
| `DerivationDescription` | `VerSe CC BY-SA 4.0, converted from NIfTI by spinelab` |
| `ImageComments` | `Source <original NIfTI filename>` |

The caret delimited PatientName matters: the 38 shipped GSPS objects all draw
`Value dubious for this VR - Retired Person Name form` because the anonymiser
wrote a single component name. These do not.

Left zero length rather than invented, all Type 2 or 2C so this is conformant:
`PatientBirthDate`, `PatientSex`, `AccessionNumber`, `ReferringPhysicianName`,
`PositionReferenceIndicator`, `KVP`, `AcquisitionNumber`.

Three documented assumptions, each one a place where the source is silent:

1. `PatientPosition` is set to `HFS`. VerSe does not record it. It is consistent
   with the derived Image Orientation Patient for both axial cases, which come out
   as the textbook head first supine `1\0\0\0\1\0`. It is a guess for the oblique
   sagittal case. Configurable via `--patient-position`.
2. `SliceThickness` is set equal to `SpacingBetweenSlices`. VerSe publishes
   resampled volumes and no collimation width, so the voxel extent is the only
   defensible value. It is not a claim about the original acquisition.
3. `StudyDate`, `StudyTime`, `SeriesDate`, `ContentDate` and `ContentTime` are the
   conversion timestamp. VerSe publishes no acquisition dates. These are not
   acquisition times and must not be reported as such.

Rescale is exact rather than approximately right. VerSe stores integer Hounsfield
units, verified by asserting integrality before writing, so `RescaleSlope` is 1
and `RescaleIntercept` is an integer, `PixelRepresentation` 0 with
`BitsAllocated` 16, `BitsStored` 16 and `HighBit` 15. The intercept is the
conventional -1024 unless the volume goes below it, which it does: `sub-gl003` has
-3024 padding, and elsewhere in the subset `sub-gl059` carries a metal artifact
peak of +10110 HU, which is why the intercept is derived rather than hardcoded.
The converter raises rather than quantise silently if a volume is ever non
integral or does not fit 16 bits. `RescaleType` is `HU`.

An in plane shear is refused, not squared off. Image Orientation Patient carries
two direction cosines that every reader treats as orthogonal, so a sheared in
plane pair is not representable and raises. Obliquity of the slice axis relative to
the plane is allowed, because each instance carries its own Image Position
Patient. Worst in plane skew across the three cases is 3.9e-11 in cosine, so no
VerSe case triggers the refusal.

## Limitations

- These are single frame instances, one per slice, not enhanced multi frame CT.
  That is the simpler and better supported route for a viewer comparison, and it
  is what the existing GSPS objects reference.
- Uncompressed Explicit VR Little Endian only. No transfer syntax variation is
  exercised here.
- The out of distribution problem is untouched by this work. The model declares
  `channel_names {"0": "MRI"}` and VerSe is CT, exactly as before. Converting the
  container format does not change the modality mismatch.
- `ImplementationClassUID` is still pydicom's registered root, as in
  `gsps/writer.py`. An owned root is needed before anything clinical.
- Nothing here has been rendered in a viewer yet. Conformance to the IOD and
  geometric fidelity are necessary, not sufficient, for the viewer matrix.
