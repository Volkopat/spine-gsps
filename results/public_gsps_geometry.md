# Public data GSPS: coordinate chain verified, and two demonstration cases

Run 2026-07-30. Removes the clinical data dependency from the GSPS arm, which
previously re-emitted variants of an existing clinical object and therefore could
not be released.

Reproduce:

```
python scripts/emit_public_gsps.py --case sub-verse502_dir-iso --series-root <root>
```

## The coordinate chain

```
batch JSON  centroid_world_ras_mm       RAS, millimetres
  -> negate x and y                     RAS to LPS, DICOM patient space is LPS
  -> inverse of P(r,c) = IPP + c*dCol*X + r*dRow*Y
     where IOP = [X(3), Y(3)] and PixelSpacing = [dRow, dCol]
  -> choose the instance minimising total |offset along X cross Y|
  -> pixel row, column
```

Self check on every run: how many vertebrae project inside the image bounds. A sign
error or a transposed row/column axis puts points outside immediately, which is the
failure a visual check of one slice would not catch.

## Verified

| case | acquisition | instances | size | vertebrae inside | mean abs normal offset |
|---|---|---|---|---|---|
| `sub-gl247_dir-ax` | axial | 228 | 512x512 | **12/12** | 62.2 mm |
| `sub-verse502_dir-iso` | isotropic, reformatted sagittal | 512 | 1119x512 | **19/19** | **4.6 mm** |

## A single slice GSPS assumes a sagittal acquisition

On the axial case the vertebrae span +135.9 mm to -79.6 mm along the slice normal, so
**no single axial slice can contain them**. The deployed design annotates one selected
slice, which only makes sense when the whole column lies in that plane. Reformatting
an isotropic volume to sagittal brings the spread to 4.6 mm mean and 14.2 mm worst,
and all 19 levels land in one image.

That is the MPR step the abstract refers to, now validated rather than asserted, and
it constrains which VerSe cases are usable for the GSPS arm.

Cohort composition, counted from filenames over all 202 cases:

| acquisition | n |
|---|---|
| axial (`dir-ax`) | 60 |
| isotropic (`dir-iso`) | 56 |
| sagittal (`dir-sag`) | 15 |
| no suffix | 71 |

So roughly 71 cases, the isotropic and sagittal ones, are directly suited to a single
slice GSPS. The axial ones need a reformat or a multi instance presentation state.

## Two demonstration cases, on public data, with the corrected confidence

Displayed confidence is the `parity_sequence_phased` arm, the only channel selection
rule measured to carry signal. So these objects show the CORRECTED confidence, not the
one the deployed system displays.

**Success, `sub-verse502_dir-iso`.** Nineteen contiguous levels, C7 through sacrum, in
correct anatomical order. Rows increase monotonically 4.5 to 773.4 down the column, and
columns trace thoracic kyphosis (260 to 288) then lumbar lordosis (288 to 253) then the
sacrum (287). Confidence is uniformly high and tightly clustered, **96.4 to 98.4
percent** across all nineteen.

**Failure, `sub-gl247_dir-ax`.** Twelve levels with two gross errors. `T1` is placed at
normal offset -63.3 mm, **inferior to L4**, and `L5` at -79.6 mm, **below the sacrum**.
Both are anatomically impossible, and the confidence rule scores them **0.2 percent
and 0.1 percent** while the ten plausible labels score 61.7 to 95.9 percent.

> **PARTLY RETRACTED, ledger G18.** Reading the two lines above as "the flag
> catches the impossible placements" is wrong, and the figure built on that
> reading was withdrawn. On this case **8 of the 12 assigned names are levels
> absent from the volume entirely**, 7 of them carrying confidence 0.82 to 0.96,
> and the flag fires on 2, one of which is a level that IS present. The two
> low scores are real; the generalisation from them was not. "Corrected
> confidence" also names the wrong arm: it is `parity_name`, which no deployed
> version ever used. See G20. The
detected set also skips T7, T9, T10 and L3, so the sequence is non contiguous, which is
an error signature in itself.

These two cases are the figure pair for the paper: the same pipeline, the same
confidence rule, one case where it is right and reports high confidence, one where it is
grossly wrong and reports near zero. Both on CC BY-SA public data.

## Not yet done

`spinelab.gsps.writer` re-emits variants of an existing object. A from scratch build
path, taking a series plus this annotation geometry and producing the GSPS directly, is
the remaining step. This script writes the geometry and the confidences to JSON and
deliberately stops there rather than half wiring it.
