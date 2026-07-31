# Rendering, measured with the reference renderer

Measured 2026-07-31. `dcmp2pgm` (DCMTK 3.7.0) applies a presentation state to an image
and writes the rendered bitmap. It is the reference implementation of GSPS rendering,
so rendering can be measured by diffing bitmaps rather than by looking at a screen.

Reproduce: `python scripts/render_matrix.py --image <referenced instance> --pstate-dir <dir>`

Source: `sub-verse502_dir-iso_0217.dcm`, public VerSe, sagittal reformat. Nine variants
of one presentation state, annotation content held byte identical across all nine.

## Result 1: the conformance defects are not academic

| variant | renders | bytes |
|---|---|---|
| `asis_trueid`, `asis_meddreamid` | **no** | 0 |
| all seven others | yes | 572,944 |

The renderer emits `W: instanceNumber absent or empty in presentation state` and then
produces nothing.

**Isolated to a single attribute.** Restoring **only** `InstanceNumber` to an `asis`
object, changing nothing else, makes it render, and the output is **byte identical**
(SHA-256 prefix `5EA1ECB666BC6382`) to the conformant variant. One Type 1 attribute is
the difference between an object that renders and one that does not.

This matters because the 38 objects emitted by the deployed pipeline all lack
`InstanceNumber`, and all render correctly in the commercial viewer they were built
against. So the defect is not a technicality that a validator alone notices: **the same
object renders in one viewer and is refused outright by the reference renderer.** That
is a measured interoperability failure with an isolated cause, not a hypothetical one.

## Result 2: the reference renderer is indifferent to all three colour routes

All seven renderable variants produce **byte-identical output**:

| variant | rendered SHA-256 prefix |
|---|---|
| `colour_none` | `5ea1ecb666bc6382` |
| `colour_layer_iod` | `5ea1ecb666bc6382` |
| `colour_line_iod` | `5ea1ecb666bc6382` |
| `colour_text_outofiod` | `5ea1ecb666bc6382` |
| `colour_all` | `5ea1ecb666bc6382` |
| `conformant_trueid`, `conformant_meddreamid` | `5ea1ecb666bc6382` |

> **RETRACTED, ledger G17.** The sentence below is wrong and is kept only so the
> record shows what was claimed. `dcmp2pgm` draws **no** GSPS annotations at all.
> Deleting all 19 annotation items, and separately displacing all 57 objects by
> 120 px, each leave the rendered bitmap byte identical. The 237,376 differing
> bytes are the VOI LUT: applying the presentation state collapses the image from
> 256 distinct grey levels to 16. The governing measurement is
> `results/render_annotation_probe.md`.
>
> ~~The annotations themselves do render: 237,376 bytes differ from the baseline
> rendered without any presentation state, so the labels and leader lines are
> drawn.~~

But the colour route makes **no difference at all**, and colour is indistinguishable
from no colour. This is not a defect in the renderer. A **Grayscale** Softcopy
Presentation State is greyscale by name and by IOD, and `dcmp2pgm` writes PGM. There is
nowhere for a colour to go.

## What this does to the paper

It changes the emphasis of the container half, and strengthens it.

The colour-route question, which the earlier draft led with, is **moot in the reference
renderer**. All three routes, permitted or not, writable or not, accepted by a validator
or not, produce identical greyscale output. A per-object colour flag encoded in a GSPS
is a hint that a conformant greyscale renderer is free to ignore, and the reference one
does. Any viewer that does show the colour is going beyond the object class.

The conformance question is the opposite of moot. It has a measured, isolated,
single-attribute causal effect on whether the object renders at all.

Four authorities, four answers:

| | text colour | line colour | layer colour |
|---|---|---|---|
| permitted by PS3.3 C.10.5 | yes, Type 3 | yes, Type 3 | yes |
| writable with `highdicom` | no | no | yes |
| accepted by `dciodvfy` | **no** | yes | yes |
| accepted by `dcmpschk` | yes | yes | yes |
| **rendered differently by `dcmp2pgm`** | **no** | **no** | **no** |

## Limits of this measurement

One renderer, and the one bundled with the toolkit that also supplies `dcmpschk`, so
these two are not fully independent of each other. It establishes what the reference
greyscale rendering path does, not what a colour-capable clinical viewer does. Weasis
and DICOMscope are on disk and a screen-based check across them remains the obvious next
step; this does not replace it, but it does convert the three questions a viewer study
would answer from wholly unmeasured to partly measured, and it answers the sharpest of
them, whether the defects matter, with an isolated cause.
