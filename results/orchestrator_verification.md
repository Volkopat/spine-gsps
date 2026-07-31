# Independent verification of the overnight build

Five of thirteen workflow agents were killed by API 529 errors, including four of
the seven verification agents. Everything below was therefore re-checked by the
orchestrator by executing it, not by reading the build agents' reports. Run
2026-07-30.

## Confirmed

| claim | how checked | result |
|---|---|---|
| test suite passes | `pytest tests -q` | **208 passed, 0 failed** |
| highdicom can write GSPS | imported it, read `pr.SOP_CLASS_UIDS` | **confirmed**, contains `1.2.840.10008.5.1.4.1.1.11.1` |
| highdicom has no line or text style support | grepped every `.py` in the installed package | **confirmed**, 0 occurrences of `TextStyleSequence`, `LineStyleSequence`, `TextColorCIELabValue`, `LineColorCIELabValue` |
| SEG objects are conformant | ran `dciodvfy` on all 12 | **0 errors, 0 out of IOD** on every one |
| VerSe scorer is correct | `--self-check --limit 6` | all three checks **PASS** |
| spline `fit_instrumented` matches deployed | `--selftest` | **24 regional residuals matched** |
| NIfTI to DICOM geometry | `--roundtrip --simpleitk` on a case the agent did not use | **0 of 189,267,968 voxels mismatched**, max world error **4.55e-12 mm**, pydicom and SimpleITK/GDCM agree exactly |
| generated CT instances conformant | `dciodvfy` on a random sample of 12 of 722 | **`CTImage` 12/12, 0 errors, 0 out of IOD, 0 diagnostics** |

The test suite found **two real bugs in orchestrator written code**, both fixed by
changing the code rather than the test:

1. `channels.py` included T13 in the canonical ordinal table, so T12 landed on
   ordinal 18 and L1 on 20, both even, putting two ADJACENT vertebrae on the same
   softmax channel. That is exactly what the alternation exists to prevent.
2. `writer.py` wrote a `ContentDescription` longer than the 64 character LO limit.
   pydicom only warns, so it had been silently emitting non conformant objects.

Also fixed: `RE_IOD` in `validate.py` required the IOD name to contain
`PresentationState`, `Storage`, `Image` or `IOD`, so every DICOM SEG was reported
`(unrecognised)`. Now matches the shape of the line. Verified: SEG resolves as
`Segmentation` 6/6.

## Still not verified

- `scripts/viewer_bench/`, which needs Docker containers up and, for the rendering
  half, a human looking at a screen. The acceptance half via the Orthanc REST API is
  automatable and has not been re-checked.
- The three way conformance comparison rests on objects built from **clinical** CT
  for the GSPS arm. The SEG and CT arms are now on public VerSe data. The GSPS
  variants must be re-emitted on public data before anything is released.

## Measured three way conformance comparison

| object | dciodvfy errors | out of IOD attributes |
|---|---|---|
| shipped GSPS, 38 objects | 7 | 6 |
| conformant GSPS variants | 1, an unevaluable `Laterality` conditional | 0 |
| DICOM SEG, 12 objects | **0** | **0** |
| generated CT instances, sample of 722 | **0** | **0** |

SEG is strictly more conformant than GSPS at its best. The paper should say so
plainly rather than advocating GSPS on conformance grounds. The defensible GSPS
argument is elsewhere: storage cost, and the fact that a presentation state renders
as an overlay on the original series without the viewer needing segmentation
support at all.
