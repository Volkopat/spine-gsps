# Regression test suite

Written 2026-07-30. Runner is `pytest`, tests live in `tests/`. 208 tests across
seven modules plus `tests/conftest.py`.

Reproduce:

```
$env:PYTHONPATH="<path>\spine-gsps\src"
& "C:\Users\dekay\miniconda3\envs\spinelab\python.exe" -m pytest -q
```

`tests/conftest.py` puts `src` on `sys.path` itself, so a bare `pytest` from the
repository root works without `PYTHONPATH`. `pytest 9.1.1`, `pydicom 3.0.2`,
`numpy 2.2.6`, Python 3.10.20.

## Summary, measured

Full suite on this machine, all external stores present and `dciodvfy` on disk:

```
2 failed, 206 passed, 3 warnings in 2.35s
```

Per module, each run on its own:

| module | tests | result |
|---|---:|---|
| `tests/test_channels.py` | 56 | 1 failed, 55 passed |
| `tests/test_gsps_writer.py` | 69 | 1 failed, 68 passed |
| `tests/test_validate.py` | 26 | 26 passed |
| `tests/test_paths.py` | 36 | 36 passed |
| `tests/test_torch_compat.py` | 9 | 9 passed |
| `tests/test_verse_labels.py` | 9 | 9 passed |
| `tests/test_style.py` | 3 | 3 passed |

**Both failures are defects in the code, not in the tests.** They are described
below and are left failing on purpose. Weakening either assertion would hide a
real problem.

The 3 warnings are `DeprecationWarning: builtin type SwigPyPacked has no
__module__ attribute` and two siblings, raised by SimpleITK's SWIG bindings at
import. Nothing to do with this repository.

## The suite skips rather than fails without the data

Re-run with every external store and the validator pointed at paths that do not
exist:

```
SPINELAB_DCIODVFY, SPINELAB_MODELS, SPINELAB_DATASETS,
SPINELAB_RUNS, SPINELAB_VENDOR, SPINELAB_BASELINE  ->  D:\nope\...

2 failed, 178 passed, 28 skipped, 3 warnings in 1.90s
```

Every skip names what is missing. Verbatim, with the long lines wrapped:

```
SKIPPED [8] tests\test_paths.py:32: MODELS does not resolve on this machine:
  D:\nope\models. Set SPINELAB_MODELS to override.
SKIPPED [1] tests\test_gsps_writer.py:434: dciodvfy not found at
  D:\nope\dciodvfy.exe, set SPINELAB_DCIODVFY to run the conformance tests
SKIPPED [3] tests\test_gsps_writer.py:440: dciodvfy not found at ...
SKIPPED [2] tests\test_gsps_writer.py:448: dciodvfy not found at ...
SKIPPED [1] tests\test_gsps_writer.py:456: dciodvfy not found at ...
```

That is 7 conformance tests skipped, not failed, when dicom3tools is absent.

The same two code defects fail in both configurations, so neither depends on the
machine having the data.

## No test needs private data

The GSPS source object is synthetic, built in `tests/conftest.py` from GSPS IOD
attributes only, plus the five out-of-IOD text style attributes the deployed
`generate_gsps_4.py` actually wrote. `dciodvfy` recognises it as
`GrayscaleSoftcopyPresentationState` and reproduces the measured result from
`results/gsps_variants.md` independently: the in-IOD colour routes score 0
out-of-IOD attributes and 1 error, the text route scores exactly the same 6
out-of-IOD attributes as the 38 shipped objects, and the 1 remaining error is
`Laterality`. Nothing in the suite reads `<path>`.

## What each correction in results/*.md is now guarded by

| recorded correction | test |
|---|---|
| confidence read the wrong softmax channel, lumbar scored against sacrum | `test_channels.py::test_table_names_match_dataset_json_in_order`, `::test_named_channel_constants_match_dataset_json`, `::test_retired_mapping_reads_sacrum_for_every_lumbar_level` |
| step 1 has 9 channels, step 2 has 11 | `::test_step2_channel_count_is_eleven`, `::test_step1_channel_count_is_nine` |
| region based, no background channel | `::test_step2_is_region_based_with_no_background_channel` |
| Line Style Sequence macro was missing 4 of 10 Type 1 attributes | `test_gsps_writer.py::test_line_style_macro_carries_all_ten_type1_attributes`, `::test_line_style_macro_the_four_attributes_the_earlier_version_omitted` |
| `Laterality` set to zero length instead of absent | `::test_laterality_is_absent_not_zero_length`, over all 9 variants |
| `PresentationPixelSpacing` and `PresentationPixelAspectRatio` both set | `::test_presentation_pixel_spacing_comes_from_the_source_image`, `::test_spacing_and_aspect_ratio_are_never_both_present` |
| `validate.py` counted occurrences, producing "68/9" | `test_validate.py::test_a_repeated_missing_attribute_counts_as_one_file`, `::test_the_count_never_exceeds_the_file_total` |
| text colour route is out of IOD, line and layer are not | `test_gsps_writer.py::test_in_iod_colour_routes_produce_zero_out_of_iod_attributes`, `::test_the_text_colour_route_produces_exactly_the_six_known_attributes` |
| annotation content must be held fixed across variants | `::test_annotation_content_is_identical_to_the_source`, `::test_every_variant_carries_the_same_content_as_every_other` |
| only fold_0 exists, predictor must pass `folds=(0,)` | `test_paths.py::test_only_fold_zero_exists`, `test_torch_compat.py::test_load_predictor_defaults_to_fold_zero_only` |
| mirroring must be off | `test_torch_compat.py::test_load_predictor_defaults_to_mirroring_off` |
| torch 2.6 `weights_only` fallback must not leak | `::test_trusted_load_forces_weights_only_false_then_restores`, `::test_trusted_load_restores_even_when_the_body_raises` |
| sm_61 IS in the arch list, the Pascal claim was wrong | `::test_torch_build_carries_the_gpu_architecture_this_machine_needs` |
| SPIDER and spine-generic are contaminated | `test_paths.py::test_contaminated_contains_spider_and_spine_generic`, `::test_the_contamination_claim_is_backed_by_the_checkpoints_dataset_txt` |
| VerSe labels ARE the anatomical level, T13 is 28 | `test_verse_labels.py::test_sacrum_coccyx_and_t13`, `::test_region_of_puts_t13_in_the_thoracic_region` |
| T13 cannot be produced, so those cases must be found first | `test_verse_labels.py::test_sacrum_coccyx_and_t13` plus the landmark tests |
| no em-dashes, aycan always lowercase | `test_style.py::test_no_em_dash_anywhere`, `::test_aycan_is_always_lowercase` |

The `dciodvfy` output parser is tested against captured text, not against the
binary, so `tests/test_validate.py` is 26 passed with or without dicom3tools
installed. The captured fixture is verbatim output from
`dciodvfy 00001589_GSPS.dcm`, dicom3tools snapshot 20260701065818.

## FINDING 1: the parity fallback is out of phase for lumbar levels

`tests/test_channels.py::test_parity_alternates_between_adjacent_levels_of_a_modal_spine`

```
AssertionError: adjacent levels share a channel: [('T12', 'L1')]
```

`spinelab.confidence.channels.LEVEL_ORDINAL` is built from
`C1-C7 + T1-T13 + L1-L6 + SACRUM`, so the canonical ordinal of L1 is 20. In a
spine with no T13, which is the overwhelming majority, L1 is the 20th vertebra
and its ordinal is 19. `channel_parity("L1")` with no explicit ordinal therefore
returns `CH_VERT_ODD` where the model's alternation gives `CH_VERT_EVEN`, and it
is wrong the same way for L2 through L6.

Why that is definitely wrong rather than a matter of taste: TotalSpineSeg step 2
labels vertebrae 7 (odd) and 8 (even) so that adjacent vertebrae differ, and
upstream depends on it. `_merge_vertebrae_with_same_label` in
`totalspineseg/utils/iterative_label.py` merges two consecutive components that
carry the same odd/even value, with the comment "This is useful when parts of the
vertebrae are not touching in the segmentation but have the same odd/even value".
Two neighbours on the same channel is not a representable state, so T12 and L1
coming back on the same channel cannot be right.

Scope. `channel_parity(level, ordinal)` with a real ordinal from the
segmentation is correct, and the module docstring already says to prefer that.
Only the no-ordinal fallback is affected. No number in `results/` was produced
through this path yet, so nothing measured is invalidated. Fix belongs in
`src/spinelab/confidence/channels.py`: either drop T13 from the canonical ordinal
and treat it as an insertion, or refuse to answer without an explicit ordinal.

### Correction to CLAUDE.md finding 2, verified

CLAUDE.md records that the live server's `utils/confidence_calculator.py` "uses
the CORRECT parity mapping". It does not. Read verbatim, `get_vertebra_channel`
takes the integer out of the vertebra's own name and tests `vertebra_num % 2`:

```python
vertebra_num = int(vertebra_name[1:])
if vertebra_num % 2 == 1:
    return 6  # Odd vertebrae
else:
    return 7  # Even vertebrae
```

So parity restarts at C1, T1 and L1 rather than running continuously down the
column. C7 and T1 both come back as channel 6, which the alternation forbids.
Measured against continuous alternation over a modal spine, the deployed rule
agrees on all 7 cervical levels and disagrees on all 17 levels from T1 down. It
is not "the corrected parity version", it is a third wrong mapping that happens
to be right in the neck. Pinned by
`test_channels.py::test_the_deployed_confidence_calculator_restarts_parity_at_each_region`,
which passes.

This matters for experiment E1: variant (b) as described in CLAUDE.md, "the
corrected parity mapping used by the deployed server", is two different things.
`channels.channel_parity` with a real ordinal is the correct one. The server's
own function is not, and if the ablation is meant to reproduce what the server
did, it needs the per-region rule, not `channel_parity`.

## FINDING 2: ContentDescription overruns its value representation

`tests/test_gsps_writer.py::test_auto_labelled_variants_also_fit_the_lo_limit`

```
AssertionError: ContentDescription overruns LO (64) for:
['req-yes_colour-none_id-meddream = 68 chars',
 'req-yes_colour-text_id-meddream = 68 chars',
 'req-yes_colour-line_id-meddream = 68 chars',
 'req-yes_colour-layer_id-true = 65 chars',
 'req-yes_colour-layer_id-meddream = 69 chars',
 'req-yes_colour-all_id-meddream = 67 chars']
```

`build_variant` writes `ContentDescription = "Vertebral level annotations,
variant %s" % v.label`, a 37 character prefix. `Variant.__post_init__` generates
labels up to 32 characters when no label is given, so the value reaches 69 where
LO permits 64. `dciodvfy` on the emitted object, verbatim:

```
Error - Value invalid for this VR - (0x0070,0x0081) LO Content Description
  LO [1] = <Vertebral level annotations, variant req-yes_colour-line_id-meddream>
  - Length invalid for this VR = 68, expected <= 64
Error - Dicom dataset contains invalid data values for Value Representations
```

That takes an object from 1 error to 3.

Scope. The nine designed variants in `DESIGN_2X2` and `DESIGN_COLOUR_ROUTES` all
carry short explicit labels, longest 58 characters (`conformant_meddreamid`, 37
character prefix plus a 21 character label, corrected by the verification pass
from 54, which is `conformant_trueid`), so every number in
`results/gsps_variants.md` is unaffected and
`test_content_description_fits_the_lo_value_representation` passes for all nine.
The defect only bites a caller who constructs `Variant(...)` without naming it,
which is the documented default. Fix belongs in `src/spinelab/gsps/writer.py`:
truncate the description to 64, or shorten the auto label.

## Deliberate design choices in the suite

- **Failures are hard, not `xfail`.** Both findings above could be marked
  `xfail(strict=True)` to give a green suite. They are not, because a green suite
  with two known conformance defects in it is exactly the failure mode this
  project has already been burned by.
- **Fixtures over binaries.** `test_validate.py` never invokes `dciodvfy`. It
  monkeypatches `subprocess.run` and feeds the parser captured text, so the
  parser is tested on the real line shapes on any machine.
- **The per-file counting test drives `main()`, not a reimplementation.** The
  dedup that fixed "68/9" lives inline in `validate.main`, so the test runs
  `main` over fake objects with a monkeypatched validator and asserts on the
  printed tallies. That measures the production path rather than a copy of it.
- **The VerSe cohort test asserts on complete triples only.** The store is being
  written by `scripts/fetch_verse.py`, so comparing bare file counts is a race,
  not a test. It was observed going from 81 to 89 masks during this session.
- **`tests/test_style.py` scans the whole repository**, including files this
  suite does not otherwise touch and files other people are writing. A failure
  there names the offending file and line, and is a style violation rather than
  a defect in the tests. It currently passes over every `.py` and `.md` in the
  repository.
- **`tests/test_verse_labels.py` indexes `LANDMARK_DISCS` rows rather than
  unpacking them.** The rows gained a fourth field while this suite was being
  written, and the label convention being tested is independent of the arity.

## Note, not a finding

`<path>\datasets\verse_4skx2` holds 89 masks and 88 images as of the last
run, not the 40 complete cases the task brief and CLAUDE.md describe. It is being
written concurrently, so the count is in flux and the suite does not assert on
it. Whoever owns the cohort should re-state the size once the download settles,
because "40 complete VerSe cases" is currently wrong in both directions:
`fetch_verse.py` has fetched more than 40, and at least one case
(`sub-verse581_dir-ax`) had a mask with no matching image at the time of writing.
