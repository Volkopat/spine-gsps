# Batch runner for overnight VerSe inference

Built and measured 2026-07-30. Code:
`src/spinelab/pipeline/batch.py` plus the driver `scripts/run_batch.py`.

Reproduce the two case rehearsal below verbatim:

```
$env:PYTHONPATH="<path>\spine-gsps\src"
& "C:\Users\dekay\miniconda3\envs\spinelab\python.exe" `
    <path>\spine-gsps\scripts\run_batch.py `
    --limit 2 --run-dir <path>\runs\batch_smoke
```

Hardware for every number on this page: one RTX 5090 Laptop GPU, sm_120, 23.9 GiB.
`torch 2.8.0+cu128`, `nnunetv2 2.4.2`, `totalspineseg 20260623`, `numpy 2.2.6`,
`nibabel 5.4.2`, `SimpleITK 2.5.5`, Python 3.10.20, fold_0 only, mirroring off.

## Verdict: step 2 WORKS. It is not blocked.

The two channel step 2 input was determined exactly, not guessed. Two
independent sources agree line for line:

| source | lines |
|---|---|
| `$VENDOR\inference_core\inference_logic.py` | 275-350 |
| `totalspineseg/inference.py`, pip installed 20260623 | 655-700 |

Channel 0 is the intensity image cropped to the step 1 bounding box with a 10
voxel margin. Channel 1 is a BINARY mask of every other disc found by step 1:

1. `largest_component(step1_raw, binarize=True, dilate=5)`
2. `iterative_label(...)` with the step 1 parameter set, discs become 63 to 100
3. `fill_canal(canal_label=2, cord_label=1, largest_canal, largest_cord)`
4. `transform_seg2image(input_image, step1_output)`, back to the input grid
5. `crop_image2seg(image, step1_output, margin=10)` gives channel 0,
   `transform_seg2image(cropped_image, step1_output)` puts the step 1 seg on
   that grid, `extract_alternate(seg, labels=list(range(63, 101)))` gives
   channel 1.

`extract_alternate` keeps `labels[::2]` of the disc labels actually present, in
ascending label order, and writes 1 there and 0 elsewhere. So channel 1 is the
odd indexed subset of the DETECTED disc sequence, not of the anatomical one.
Because the deployed call passes `prioratize_labels=[]`, the `labels[1::2]`
branch inside `extract_alternate` never fires.

Because the two sources agree and the upstream one is a normal pip package, this
module calls the upstream helpers rather than copying vendor code into a repo
intended for public release.

### Independent evidence that the reproduction is correct

The probability array comes back in SimpleITK index order `(c, k, j, i)` and has
to be transposed to `(c, i, j, k)` to line up with the nibabel arrays the rest
of the chain uses. If that transpose or the two channel construction were wrong,
the per vertebra channel statistics would be noise. They are not. For
`sub-gl003_dir-ax`, restricted to the voxels of one vertebra:

| vertebra | model's own raw class | ch6 vertebrae_O mean | ch7 vertebrae_E mean | ch5 vert union mean |
|---|---|---|---|---|
| T6, 58,615 voxels | 7, odd | **0.9435** | 0.0003 | 0.9256 |
| T7, 36,318 voxels | 8, even | 0.0057 | **0.9251** | 0.9375 |

The channel that carries the class the model itself assigned is the one that is
near 1, and its partner is near 0, on both parities. Disc, sacrum, canal and
cord channels are all at 0.0000 to 0.0007 inside a vertebra. That is a per
vertebra, per channel confirmation of the channel table in
`spinelab.confidence.channels`, obtained through step 2 rather than step 1.

## Measured per case cost, two cases

Definitive run, `manifests/manifest_20260730T055638+0000.json`.

| | sub-gl003_dir-ax | sub-gl016_dir-ax |
|---|---|---|
| input | 512x512x214, 0.291x0.291x1.25 mm, LPS | 512x512x180, 0.352x0.352x1.25 mm, LPS |
| step 1 predict | 44.2 s | 38.1 s |
| step 1 post processing | 30.9 s | 24.3 s |
| step 2 input construction | 3.2 s | 1.9 s |
| step 2 predict | 7.4 s | 1.0 s |
| step 2 post processing | 6.3 s | 0.4 s |
| statistics, all channels | 0.42 s | 0.06 s |
| final transform to input grid | 1.20 s | 1.02 s |
| **wall clock per case** | **95.8 s** | **68.2 s** |
| peak GPU allocated | 1.406 GiB | 1.010 GiB |
| step 2 grid | 155x256x174 | 84x111x59 |
| probability array held in RAM | 303.8 MB | 24.2 MB |
| vertebrae found | 7 | 3 |
| per case JSON | 21,660 B | 10,078 B |

Both predictors load in 4.0 to 5.5 s once per invocation, measured over five
invocations. Whole two case invocation, including load: 173.3 s.

n = 2, so treat 82.0 s as the only mean available and not as an estimate with a
spread. The split is informative though: step 1 predict plus step 1 post
processing is 75 of 96 s and 62 of 68 s, so **step 2 is nearly free and step 1
post processing costs about as much as a second inference pass**. That post
processing is `iterative_label` plus two torchio resamples on a 512x512 grid, all
on CPU, and it is the obvious target if the 40 case run needs to be faster.

Naive extrapolation to 40 cases at 82.0 s: about 55 minutes. Do not quote that
as a result, VerSe volumes vary and the two cases here are the two smallest by
sort order.

## Output size, and what is never written

On disk after two cases: **625,334 bytes total, 7 files, 0.60 MB.**

```
manifest.json                                  3,257
manifests\manifest_20260730T055638+0000.json   3,257
run_log.jsonl                                  1,446
cases\sub-gl003_dir-ax.json                   21,660
cases\sub-gl016_dir-ax.json                   10,078
seg\sub-gl003_dir-ax_step2_output.nii.gz     333,317
seg\sub-gl016_dir-ax_step2_output.nii.gz     252,319
```

Extrapolating the per case part to 40 cases gives roughly 12 MB. For contrast,
`save_probabilities` wrote **757 MB per case** for step 1 alone in
`results/smoke_inference.md`. The runner never calls it. It uses
`nnUNetPredictor.predict_single_npy_array`, which returns the probabilities as an
in memory array, reduces them, and drops them. The per case JSON records
`prob_array_bytes_not_written` so the saving is auditable rather than asserted.

Five small intermediate NIfTIs per case are written under `work/` and deleted
unless `--keep-work` is given. With `--keep-work` they came to 11.6 MB for two
cases, the bulk of which is the cropped step 2 channel 0 image.

## What is in each per case JSON

Per vertebra, for EVERY vertebra in the step 2 labelled output, and across ALL
11 channels so that all three E1 variants can be evaluated from one run:

- `n_voxels`, `centroid_voxel`, `centroid_world_ras_mm`
- `channels[c]` for c in 0 to 10: `mean`, `median`, `p75`, `p95`, `max`, `min`,
  `std`, `n_gt_0p7`
- `mapping_free`: `margin`, `entropy_inv`, `top1`, `agree`, `modal_channel`,
  from `spinelab.confidence.channels.mapping_free_scores`
- `ordinal_superior_to_inferior`, the real ordinal from the segmentation, which
  is what `channel_parity` needs
- `channel_retired`, `channel_parity_from_ordinal`, `channel_parity_from_name`,
  precomputed so the ablation does not have to re-derive them
- `raw_class_hist` and `raw_class_modal`: the histogram of step 2 RAW model
  classes inside that vertebra's mask. This is the model's own answer to the
  parity question and it is not derivable from any name based mapping.

Plus per case: input geometry, label histograms at all four stages, the disc
sets before and after cropping, which discs `extract_alternate` selected, the
probability array shape and the bytes not written, a timing breakdown, wall
clock and peak GPU.

## Provenance

One manifest per invocation, written to `manifests/manifest_<utc>.json` and
never overwritten, with a copy at `manifest.json` for convenience. Contents:
UTC timestamp, full `argv`, resolved arguments, both case lists (requested and
to run), interpreter path, Python version, platform, repo git HEAD, versions of
torch, torch cuda, nnunetv2, totalspineseg, numpy, nibabel and SimpleITK, GPU
name and compute capability and total memory and compiled arch list, and for each
step model the folder plus **sha256 and size of `fold_0/checkpoint_final.pth`,
`plans.json` and `dataset.json`**.

Measured hashes, for the record:

| file | sha256 | bytes |
|---|---|---|
| step1 `fold_0/checkpoint_final.pth` | `595f71302ee74b80523c4a95103057c0563058983ad74cef627ec0a75f965ef6` | 247,335,038 |
| step2 `fold_0/checkpoint_final.pth` | `ced0cc06cda89da27f453fc05b387f35da22e7e804d865b47d8d3fb0c6cf44b1` | 247,487,358 |

The earlier resume behaviour of overwriting `manifest.json` was wrong and is
fixed: a resumed run is a second invocation with different arguments, and losing
the first record would make the output unattributable.

## Resumability and crash tolerance, both tested rather than assumed

**Resume.** Second invocation over the same run directory:
`2 case(s) requested, 0 to run, 2 already done`, exit 0, no predictor load, no
inference. Resume keys on the per case JSON, so a case that died mid way leaves
no JSON and is retried.

**Mode aware resume.** A `--step1-only` result must not satisfy a full request.
It did, at first: a step 1 only rehearsal wrote `status: ok_step1_only` and a
subsequent full run skipped the case, so no step 2 statistics would ever have
been produced for it. Now verified all three ways in one directory:

```
step1-only result, full request         -> 1 to run, 0 already done   (runs)
full result,       full request         -> 0 to run, 1 already done   (skips)
full result,       step1-only request   -> 0 to run, 1 already done   (skips)
```

**Crash tolerance.** Deliberate test with a 10 byte file named
`sub-corrupt_ct.nii.gz` alongside one good case:

```
[1/2] sub-corrupt
    EXCEPTION after 0.1 s: ImageFileError: File ...sub-corrupt_ct.nii.gz is not a gzip file
[2/2] sub-good
    ok  66.5 s  peak 1.44 GiB  json 9.8 KB
done: 1 ok, 1 failed
```

Exit code 3, full traceback in `run_log.jsonl`, no per case JSON for the failed
case so it retries on resume. `run_log.jsonl` gets one line per case with wall
clock, `torch.cuda.max_memory_allocated`, status, timing breakdown, JSON size,
and on failure the exception and traceback, flushed immediately so a run killed
overnight still leaves a usable log.

Note that peak GPU is torch's caching allocator figure, not total process VRAM.
It is the number the task asked for, and 1.4 GiB against 23.9 GiB means VRAM is
not the constraint here.

## Three findings from building this

### 1. `iterative_label` mutates the caller's list, which breaks any single process batch loop

`totalspineseg/utils/iterative_label.py:592-606` calls
`selected_disc_landmarks.remove(2)` and `.remove(5)` on the list object the
caller passed in, and never copies it.

The deployed pipeline never noticed, because `iterative_label_mp` fans out over
`process_map` and each case gets its own copy of the `partial` in its own
process. A single process driver that reuses one parameter dict silently
degrades after the first case.

Measured, on the first version of this runner: case 1 succeeded, case 2 then
failed with `At least one of the landmarks must be in the segmentation or
localizer (landmarks: [3, 4])` although `[2, 5, 3, 4]` was passed. Case 2's
`disc_C2_C3` label was genuinely present, with 2,481 voxels surviving
`largest_component`. Case 1 had stripped 2 and 5 from the shared list. With a
per call deep copy, case 2 completes and reports 3 vertebrae. This is why
`batch.py` routes every call through `iterative_kwargs()`.

This matters beyond this runner: any code here that loops over cases in one
process and reuses a parameter dict has the same bug.

### 2. These are not softmax values, they are per region sigmoids

Both step models are region based, and nnunetv2 sets
`inference_nonlin = torch.sigmoid` whenever `has_regions` is true
(`nnunetv2/utilities/label_handling/label_handling.py:47`). Every channel is an
independent per region probability and the channels do not sum to one. Measured
directly on T6 above: vertebrae union 0.9256 plus vertebrae_O 0.9435 is 1.87.

The whole project calls these softmax values, including the deployed
`raw_softmax_values.json`. The statistics this runner computes are identical to
what the deployed code would compute, so nothing downstream changes, but any
sentence in the paper that says "softmax" is describing a sigmoid. `entropy_inv`
inside `mapping_free_scores` renormalises to sum one before taking an entropy,
so it is well defined either way, but it is not a categorical entropy.

### 3. Ordinal derived parity goes out of phase, and the model's own class does not

`sub-gl016_dir-ax`, three vertebrae, top one labelled C1:

| name | ordinal | model's raw class | parity from ordinal | agrees |
|---|---|---|---|---|
| C1 | 0 | 8, even | ch6, odd | no |
| C2 | 1 | 7, odd | ch7, even | no |
| C3 | 2 | 8, even | ch6, odd | no |

The whole sequence is inverted. So the model's odd/even alternation is not
anchored to C1: an ordinal derived parity can be globally out of phase even when
the topmost detected vertebra IS C1.

`sub-gl003_dir-ax` shows the other failure. A 314 voxel stray fragment labelled
T5 sits between T7 and T10 by centroid, and everything below it is out of phase:
T6 and T7 agree, then T5, T10, T12, L1 and L2 all disagree.

Both are only visible because the runner stores `raw_class_modal` next to the
ordinal. The conclusion for E1 is that variant (b) should be evaluated against
the model's own assigned class, and that the CLAUDE.md instruction to pass the
real ordinal from the segmentation, while strictly better than a name derived
one, is still not sufficient. n = 2 here, so this is a mechanism demonstrated on
two cases, not a rate.

## Caveats on these two cases

Both are out of distribution by construction: the models declare
`channel_names {"0": "MRI"}` and VerSe is CT. Neither result is anatomically
right. `sub-gl003_dir-ax` has ground truth C1-C7 plus T1-T5 and the pipeline
labelled T6 to L2. `sub-gl016_dir-ax` produced a 78,517 voxel structure labelled
C1. That is expected, is a stated limitation, and is what the identification rate
evaluation exists to quantify. It says nothing about whether the runner is
correct, which is what the channel alignment table above establishes.

`--limit 2` takes the first two by sort order, so these two are not a random
sample. Nothing here has been run over more than two cases, and no case with a
sacrum, an L6, or a VerSe T13 has been through this code yet. The T13 question
raised in `results/level_assignment.md` remains open.
