# Does `dcmp2pgm` draw GSPS annotations? No.

Measured 2026-07-30, after round two review raised it as concern N1.

Reproduce:

```
python scripts/render_annotation_probe.py \
  --image  runs/public_dicom_sag/sub-verse502_dir-iso/sub-verse502_dir-iso_0217.dcm \
  --pstate runs/public_gsps_objects_v2/sub-verse502_dir-iso__conformant_trueid.dcm
```

## What was claimed, and why it was wrong

Both deliverables stated:

> The annotations themselves render, 237,376 bytes differing from the
> no-presentation-state baseline, so the labels and leader lines are drawn. Only the
> colour is discarded.

The reviewer pointed out that `dcmp2pgm`'s own documentation says textual and graphical
annotations will not be visible in its output, because those are drawn by DICOMscope,
the Java GUI layered on the same DCMTK classes. If so, the 237,376 differing pixels are
the greyscale pipeline, and the sentence is false.

It is false. This was a specific mechanism inferred from an aggregate signal without
isolating it, which is the exact failure mode the claims ledger exists to catch, and it
is the fourth time in this project. Retired as **G17**.

## The isolation

The presentation state carries **19 annotation items, 19 graphic objects and 19 text
objects**. Three renders, one image, everything else held identical.

| render | SHA-256 prefix |
|---|---|
| baseline, no presentation state | `95a87bd57963ead1` |
| with the presentation state | `5ea1ecb666bc6382` |
| with **all 19 annotation items removed** | `5ea1ecb666bc6382` |
| with **all 57 objects displaced by 120 px** | `5ea1ecb666bc6382` |

**Deleting every annotation changes nothing. Moving every annotation changes nothing.**
Both are byte identical to the object that still carries them. The renderer never draws
them.

## Where the 237,376 pixels actually are

| quantity | value |
|---|---:|
| image | 512 x 1119, 572,928 pixels |
| pixels differing, baseline against with-presentation-state | 237,376 (41.4%) |
| **rows containing at least one difference** | **1119 of 1119 (100.0%)** |
| mean differing pixels per occupied row | 212.1 of 512 (41.4%) |
| distinct grey levels, baseline | 256 |
| **distinct grey levels, with presentation state** | **16** |

Annotations are sparse, thin and local. This difference is dense, global, and present in
every single row. The decisive number is the last one: applying the presentation state
collapses the image from 256 grey levels to 16. That is the VOI LUT, together with the
shutter, displayed area and spatial transforms. It is the greyscale pipeline doing
exactly what a **Grayscale** Softcopy Presentation State is for.

## What this does to the paper

**Section 3.1 / 4.1 changes, and the corrected finding is sharper.**

The old claim was that the renderer honours annotations but discards their colour, which
made the byte-identical result across the three colour routes a finding. It is not a
finding, it is true by construction: a renderer that draws no annotations cannot draw
them in different colours. That claim is withdrawn.

The corrected statement is stronger as an interoperability result:

> The DCMTK toolchain has **no scriptable renderer that draws GSPS annotations at all.**
> `dcmp2pgm` applies the greyscale pipeline and ignores the Graphic Annotation Module
> entirely. The annotations are drawn only by DICOMscope, a Java GUI. A practitioner
> therefore has **no headless, reproducible way** to verify what their annotations will
> look like before shipping them, using the reference toolkit.

That is a concrete gap a practitioner hits, it is measured rather than asserted, and it
does not depend on the colour question at all.

**Section 3.2 / 4.3 is unaffected.** The `InstanceNumber` result concerns whether
`dcmp2pgm` accepts and renders the object at all, which is upstream of annotation
drawing. The deployed objects are still refused outright, restoring one Type 1 attribute
still makes them render, and the repaired render is still byte identical to the
conformant variant. All of that stands, and it is now the load-bearing rendering result.

## Limits of this measurement

One renderer, `dcmp2pgm` from DCMTK 3.7.0. It establishes what the reference **headless**
greyscale path does. DICOMscope is on disk and is the DCMTK component that does draw
annotations; it is a GUI and so cannot be scripted into this harness, which is itself
part of the finding. No colour-capable clinical viewer has been tested, and the
statement that the deployed objects' colour is visible in their target viewer remains
reported from deployment rather than measured here.
