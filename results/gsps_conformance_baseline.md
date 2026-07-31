# GSPS conformance baseline

Measured 2026-07-30. Validator: `dciodvfy` from dicom3tools, snapshot
20260701065818, Windows binary from dclunie.com. Independent third party scorer,
not our own reading of PS3.3.

Objects: the 38 GSPS files emitted by `generate_gsps_4.py` on 2025-11-21, held in
the private baseline repository at `test_api/refined_gsps_1/**/*_GSPS.dcm`.

Reproduce with:

```
python -m spinelab.gsps.validate <dir> --pattern _GSPS --json results/gsps_conformance_baseline.json
```

## Headline

All 38 objects are correctly recognised as `GrayscaleSoftcopyPresentationState`.
**Zero of 38 pass validation.** Seven required-attribute errors, each present in
all 38 objects.

| type | attribute | module | affected |
|---|---|---|---|
| 1 | `FileMetaInformationGroupLength` | FileMetaInformation | 38/38 |
| 1 | `FileMetaInformationVersion` | FileMetaInformation | 38/38 |
| 1 | `InstanceNumber` | ContentIdentificationMacro | 38/38 |
| 1C | `PresentationPixelSpacing` | DisplayedArea | 38/38 |
| 2 | `SeriesNumber` | GeneralSeries | 38/38 |
| 2 | `StudyID` | GeneralStudy | 38/38 |
| 2C | `Laterality` | GeneralSeries | 38/38 |

All seven are trivially fixable in the emitter.

## The substantive finding: GSPS lets you colour a line but not text

Six attributes are present that the GSPS IOD does not define, in all 38 objects:

| tag | attribute | affected |
|---|---|---|
| (0070,0231) | Text Style Sequence | 38/38 |
| (0070,0229) | CSS Font Name | 38/38 |
| (0070,0241) | **Text Color CIELab Value** | 38/38 |
| (0070,0242) | Horizontal Alignment | 38/38 |
| (0070,0243) | Vertical Alignment | 38/38 |
| (0070,0244) | Shadow Style | 38/38 |

Note what is **not** flagged. `Line Style Sequence` (0070,0232), `Line Dashing
Style`, `Line Pattern`, `Line Thickness` and `Pattern On Color CIELab Value`
(0070,0251) all pass. They are part of the Grayscale Softcopy Presentation State
IOD.

So the standard permits a coloured, dashed leader line and does not permit
coloured text. The pipeline conveys its per-vertebra quality flag through
**text** colour, which is the non-conformant half of the pair, while the leader
line colour beside it is conformant.

This is the tension the paper should make its subject rather than assert past:

1. A grayscale softcopy presentation state is, by name and by IOD, grayscale.
2. Conveying an AI quality flag by colour therefore sits outside the IOD for
   text, though inside it for line geometry.
3. IHE AI Results Rev 1.3 **does not address** encoding results that lack
   machine-readable semantics, naming Softcopy Presentation States as an
   example, and contemplates them as a fallback. It does **not** place them
   out of scope: its explicit out-of-scope list does not name them.
   (**Corrected, ledger B16.** The earlier wording here, "excludes softcopy
   presentation states from its AI result encoding entirely", overstated it.)
4. Whether viewers honour out-of-IOD text colour, ignore it, or reject the
   object is unmeasured, and no published study compares GSPS against DICOM SEG
   rendering support across viewers, on the search recorded in the recon
   workflow. (**Softened, ledger B9.** An exact PubMed count stood here and an
   external reviewer could not reproduce it, so this is now a claim about our
   search rather than about the literature.)

That makes the viewer experiment falsifiable and gives it a standards-grounded
motivation instead of a preference.

## Consequence for the emitter

Two variants are needed for the viewer matrix, not one:

- **conformant**: seven required attributes added, flag carried by
  `Pattern On Color CIELab Value` inside the legal `Line Style Sequence`.
- **as-is**: current output, flag carried by out-of-IOD `Text Color CIELab Value`.

Crossed with the producer-identity variable (truthful versus the current
`Manufacturer = Softneta`, `ManufacturerModelName = MedDream`,
`ImplementationVersionName = AYCANSTORE3`), that is a 2x2 per viewer.

## Other diagnostics

- DICOMDIR warnings for the absent `SeriesNumber` and `StudyID`, 38/38. Same root
  cause as the errors above.
- `Value dubious for this VR - (0x0010,0x0010) PN Patient's Name = <ANON_PAT_XXXX>
  - Retired Person Name form`, 38/38. The anonymiser writes a single-component
  name where DICOM expects caret-delimited components. Cosmetic, but it is the
  kind of thing a validator flags and a reviewer notices.

## Provenance note

An earlier pydicom-based check of the same 38 objects found only 3 of these 7
errors and did not detect the out-of-IOD attributes at all. The independent
validator found more than our own instrumentation. Use `dciodvfy` for every
conformance claim in the paper.
