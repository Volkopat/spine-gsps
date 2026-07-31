# GSPS variant conformance, measured

Measured 2026-07-30 with `dciodvfy` (dicom3tools snapshot 20260701065818).
Source object: `00001589_GSPS.dcm` from the 2025-11-21 run. Variants re-emitted by
`spinelab.gsps.writer`, validated by `spinelab.gsps.validate`.

Reproduce:

```
python -m spinelab.gsps.writer <src_GSPS.dcm> --out <dir> --source-image <src.dcm> --design both
python -m spinelab.gsps.validate <dir> --json results/gsps_variants_validation.json
```

## Content is held fixed

All 9 variants carry 17 text objects and 17 graphic objects, with byte-identical
`UnformattedTextValue` strings and identical `GraphicData` coordinates to the
source. Only conformance attributes, colour route and producer identity vary. Any
difference a viewer shows is attributable to those three axes and nothing else.

## Result

| variant | required attrs | colour route | identity | dciodvfy errors | out of IOD attrs |
|---|---|---|---|---|---|
| `asis_trueid` | no | text | spinelab | 5 | 6 |
| `asis_meddreamid` | no | text | Softneta/MedDream | 5 | 6 |
| `conformant_trueid` | yes | line | spinelab | **1** | **0** |
| `conformant_meddreamid` | yes | line | Softneta/MedDream | **1** | **0** |
| `colour_none` | yes | none | spinelab | **1** | **0** |
| `colour_line_iod` | yes | line (0070,0251) | spinelab | **1** | **0** |
| `colour_layer_iod` | yes | layer (0070,0401) | spinelab | **1** | **0** |
| `colour_text_outofiod` | yes | text (0070,0241) | spinelab | **1** | 6 |
| `colour_all` | yes | all three | spinelab | **1** | 6 |

The original 38 shipped objects score **7 errors and 6 out-of-IOD attributes**.
The conformant variants reduce that to **1 error and 0 out-of-IOD attributes**.

## The one remaining flag is an unevaluable conditional

`Laterality`, Type 2C in General Series, is required only when the body part is a
paired structure. The spine is not paired, so absent is correct. `dciodvfy` flags
it because it cannot evaluate the condition from the object alone. Setting it to
zero length produces a worse diagnostic, verbatim: "is only permitted to be empty
when actually unknown; should be absent (not zero length)". So absence is the
right answer and this line is benign. The original objects carry the identical
flag, so the conformant variants are at parity on this item and strictly better on
the other six.

## Three colour routes, one of which is illegal

| route | tag | in the GSPS IOD | evidence |
|---|---|---|---|
| layer | (0070,0401) Graphic Layer Recommended Display CIELab Value | **yes** | `colour_layer_iod` scores 0 out-of-IOD attributes |
| line | (0070,0251) Pattern On Color CIELab Value in Line Style Sequence | **yes** | `colour_line_iod` scores 0 out-of-IOD attributes |
| text | (0070,0241) Text Color CIELab Value in Text Style Sequence | **no** | flagged with its five siblings in every variant that uses it |

The deployed pipeline uses the text route, the only illegal one, to carry its
per-vertebra quality flag. Two legal alternatives exist and both validate clean.

This is the experiment: three encodings of the same visual signal, two conformant
and one not, content otherwise identical. Which do viewers honour? Nobody has
published this, on the search recorded in the recon workflow, while IHE AI
Results Rev 1.3 states that it does not address encodings lacking
machine-readable semantics and names Softcopy Presentation States as an example.

> **Corrected, ledger B9 and B16.** This paragraph previously quoted an exact
> PubMed count that an external reviewer could not reproduce, and said IHE AIR
> "excludes" presentation states "altogether". AIR contemplates them as a
> fallback and its explicit out-of-scope list does not name them.

## Corrections to earlier work in this repo

1. An earlier version of `writer.py` populated only 6 of the 10 Type 1 attributes
   in the Line Style Sequence macro, omitting `ShadowOffsetX`, `ShadowOffsetY`,
   `ShadowColorCIELabValue` and `PatternOnOpacity`. `dciodvfy` caught all four.
   The deployed `generate_gsps_4.py` populates the macro correctly, so this was a
   regression introduced here, not a defect in the original.
2. An earlier version set `Laterality` to zero length, which is worse than absent.
3. An earlier version set both `PresentationPixelSpacing` and
   `PresentationPixelAspectRatio`. They are alternatives, so setting one requires
   removing the other.
4. `validate.py` counted missing-attribute occurrences rather than files affected,
   which produced impossible tallies such as "68/9" when an attribute is absent
   from many items of one sequence. Now deduplicated per file.
