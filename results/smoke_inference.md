# Smoke test: step 1 inference on VerSe CT

Measured 2026-07-30. Case `sub-gl003_dir-ax` from VerSe 2020, 512x512x214 at
0.291 x 0.291 x 1.25 mm, LPS. Hardware: RTX 5090 Laptop GPU, sm_120, 23.9 GiB.
`torch 2.8.0+cu128`, `nnunetv2 2.4.2`, fold_0 only, mirroring off (the trainer is
NoMirroring).

Reproduce: `python scripts/smoke_inference.py`

## Verdict: inference runs

```
init      1.1 s
predict  97.8 s
total    98.9 s
```

One case, step 1 only. A full two step cascade plus level assignment will be
materially more. This is the first timing number in this project that was actually
measured, so it supersedes nothing yet but it is the baseline for the real
benchmark. Note the coincidence with the old untraceable "100 seconds per study"
claim is exactly that, a coincidence: different hardware, one step, one series.

## Step 1 region structure, confirmed independently

`nnUNetPredictor` reports `has_regions: True`, `num_segmentation_heads: 9`, and

```
foreground_regions: [(1,2,3,4,5), 2, 3, 4, 5, (6,7), 7, (8,9), 9]
```

which gives step 1's channel semantics directly:

| ch | region | meaning |
|---:|---|---|
| 0 | (1,2,3,4,5) | disc union |
| 1 | 2 | disc_C2_C3 |
| 2 | 3 | disc_C7_T1 |
| 3 | 4 | disc_T12_L1 |
| 4 | 5 | disc_L5_S |
| 5 | (6,7) | vertebrae union |
| 6 | 7 | vertebrae_C1 |
| 7 | (8,9) | canal union |
| 8 | 9 | cord |

Nine channels for step 1, eleven for step 2. This is a second, independent
confirmation of the region-based reading in `spinelab.confidence.channels`: the
predictor itself reports the regions, so the channel-to-meaning mapping is not an
inference from `dataset.json` alone.

Normalisation scheme is `ZScoreNormalization` and `channel_names` is
`{"0": "MRI"}`, so CT Hounsfield values are z-scored by a scheme designed for MR
intensities. That is the out-of-distribution mechanism, stated concretely.

## Output on out of distribution CT: degraded but not degenerate

```
label  0   55,350,934 voxels  98.67%   background
label  1       40,103          0.07%
label  3        2,548          0.00%
label  6      629,462          1.12%   vertebrae
label  7        3,499          0.01%   vertebrae_C1
label  8       54,306          0.10%   canal
label  9       17,964          0.03%   cord
```

Ground truth for this case has 12 named vertebrae, C1 through C7 and T1 through
T5. The model finds a vertebral structure occupying 1.12 percent of the volume,
plus canal and cord. So it produces poor but non-trivial output on CT rather than
failing outright, which means the out-of-distribution arm will yield
non-degenerate numbers rather than an uninformative floor. That was the risk worth
testing before queueing 40 cases.

## Two practical findings

**Disk.** `save_probabilities` wrote a **757 MB** `.npz` for one case, shape
`(9, 214, 512, 512)` float32. Forty cases of step 1 alone would be roughly 30 GB,
and step 2 has eleven channels. For the E1 ablation we need per-vertebra softmax
statistics, not the raw arrays, so the batch runner must compute statistics in
process and discard the array rather than persisting it. Persisting softmax does
not scale to an overnight run.

**Checkpoint loading.** `torch.serialization.add_safe_globals` was **not**
sufficient and the loader fell back to `weights_only=False`. Cause: the
checkpoints were pickled under numpy 1.x, so the pickle references
`numpy.core.multiarray.scalar`, while under the installed numpy 2.2.6 that object
reports `__module__` of `numpy._core.multiarray`. The allowlist therefore registers
under a different path than the pickle names. The fallback is scoped to a context
manager in `spinelab.pipeline.torch_compat` and is logged on every use rather than
being silent. It is acceptable only because these are our own checkpoints from our
own container image. Pinning `numpy<2` would let the narrow allowlist work and is
the cleaner long term fix.
