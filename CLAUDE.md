# spine-gsps

Working notes for the SPIE Medical Imaging 2027 spine labeling work. Read this
before touching anything. Written 2026-07-30 after a full forensic audit of the
material received from the previous deployment.

## What this repository is

The clean, public-facing testing and evaluation harness. It contains only code
written here. It is intended to be released alongside the paper, the way
`github.com/Volkopat/palimpsest` was released for the Florence-2 work.

It is deliberately separate from the private baseline repository so that
clinical data cannot leak into a public release.

| location | contents | status |
|---|---|---|
| `<path>\spine-gsps` | this repo, code we write | intended PUBLIC |
| `<path>` | as-received material, 1735 clinical DICOM, baseline commit `9bb5648` | PRIVATE forever |
| `<path>\app` | server code recovered from the container | PROPRIETARY, do not redistribute |
| `<path>\models` | three trained nnU-Net checkpoints, 793 MB | not committed anywhere |
| `<path>\datasets` | public evaluation data | not committed anywhere |
| `<path>\runs` | batch outputs | not committed anywhere |

Paths are centralised in `src/spinelab/paths.py`. Run `python -m spinelab.paths`
to check every store resolves.

## Hard rules

- No em-dashes in any file, comment, or document. Commas, colons, or recast.
  En-dashes in numeric ranges are fine.
- "aycan" is always lowercase.
- Every number must be one we actually ran. Numbers carried over from the RSNA
  abstract or a prior run must be labelled as such inline.
- Measure through the production path, not a separate diagnostic harness. This
  project has already been burned twice by diagnostic-only code disagreeing with
  the deployed code.
- Do not tune on a test split. If a split is held out, it stays held out.
- Kill runs based on buggy code even if nearly finished.
- Commit early and often.

## Environment

The container is `volkopat/paratus-spine-labeling:latest`, built 2025-12-08 on
`nvidia/cuda:12.8.0-devel-ubuntu22.04`. We are NOT running the container. We run
locally, because the container's own stack is correct for this machine's GPU and
wrong for the machine it was deployed on.

Target environment, reconstructed from the image build history:

- Python 3.10
- `torch==2.8.0` from the cu128 wheel index
- `totalspineseg` (pip), then `nnunetv2` uninstalled and replaced with a git
  clone of nnUNet HEAD. That substitution is a known risk, see below.
- `batchgeneratorsv2`, `fft-conv-pytorch` from git HEAD
- `numpy nibabel pydicom psutil scipy tqdm torchio PyYAML Pillow gunicorn flask`
  `batchgenerators acvl-utils dynamic-network-architectures opencv-python`
  `pylibjpeg pylibjpeg-libjpeg gdcm matplotlib seaborn`
- `flash-attn` was in the build but SILENTLY FAILED to install (its layer is
  1,536 bytes). Do not list it as part of the stack.

Only `torch==2.8.0` was pinned, and even that pin is suspect: the following
`pip install torchvision --index-url ... --upgrade` produced a 3.11 GB layer,
which is only explicable if it replaced torch or the nvidia wheels. Verify the
resolved version before quoting it anywhere.

### This machine

One GPU: **NVIDIA GeForce RTX 5090 Laptop GPU, 24463 MiB, compute capability 12.0
(sm_120)**, driver 610.74. Alienware 18 Area-51, 63.5 GB RAM, 24 logical CPUs.
Docker Desktop 4.53 present with the nvidia runtime, WSL2 Ubuntu.

There is no RTX 5070 and there are no Tesla P40s on this machine. Any timing or
VRAM figure must name this GPU.

### Both gates PASSED, measured 2026-07-30

Interpreter: `C:\Users\dekay\miniconda3\envs\spinelab\python.exe`, Python 3.10.20.
Pins frozen in `env/requirements.lock` (108 lines). Rebuild with
`env/setup_local.ps1`, which now checks every exit code.

GPU gate, measured rather than assumed:

```
torch 2.8.0+cu128, cuda runtime 12.8
arch_list  ['sm_61','sm_70','sm_75','sm_80','sm_86','sm_90','sm_100','sm_120']
device     NVIDIA GeForce RTX 5090 Laptop GPU, sm_120, 23.9 GiB
fp32 OK   fp16 OK   bf16 OK   conv3d OK
```

**Correction to an earlier claim in these notes.** It was recorded here that this
build dropped Pascal and therefore could not run on the Tesla P40s. That is
wrong. `sm_61` IS in the compiled arch list. The torch 2.8.0 release note about
dropping sm50 to sm60 does not cover sm_61, which is what a P40 is. So the
container could have run on the P40s and the 100 s figure cannot be ruled out on
architecture grounds. What still stands, and is the load-bearing part: there is
no timing instrumentation anywhere in the project and the number traces to a
transcribed third party README table, so it must be re-measured regardless.

Checkpoint gate: `nnunetv2==2.4.2` is required and must be installed explicitly,
because current `totalspineseg` (version 20260623) no longer depends on it. With
2.4.2, `nnUNetTrainer_DASegOrd0_NoMirroring` resolves to
`nnunetv2.training.nnUNetTrainer.variants.data_augmentation.nnUNetTrainerDAOrd0`
and all three checkpoints deserialise: 292 tensors, 88.2M parameters each,
`plans_name` `nnUNetPlans_small` for the two step models, patch 128x96x96 at 1 mm
isotropic, `channel_names` `{"0": "MRI"}` for step 1 and
`{"0": "MRI", "1": "noNorm"}` for step 2.

### The channel semantics, now proven from the checkpoints themselves

Both step models are REGION BASED (`regions_class_order` present, no background
channel), so per-region sigmoid channel i carries class value `regions_class_order[i]`, and
channel index and label value differ by one. Dataset102 `labels`, verbatim from
its own `dataset.json`:

```
{"background":0, "disc":[1,2,3,4,5], "disc_C2_C3":2, "disc_C7_T1":3,
 "disc_T12_L1":4, "disc_L5_S":5, "vertebrae":[6,7,8,9], "vertebrae_O":7,
 "vertebrae_E":8, "sacrum":9, "canal":[10,11], "cord":11}
```

| ch | true meaning | name printed by the deployed `json_generator.py` |
|---:|---|---|
| 0 | disc union | `background` |
| 1-4 | disc_C2_C3, disc_C7_T1, disc_T12_L1, disc_L5_S | `disc_type_1..4` |
| 5 | vertebrae union | `disc_type_5` |
| 6 | **vertebrae_O**, odd | `vertebrae_type_1` |
| 7 | **vertebrae_E**, even | `vertebrae_type_2` |
| 8 | **sacrum** | `vertebrae_type_3` |
| 9 | **canal** | `vertebrae_type_4` |
| 10 | **cord** | `spinal_canal` |

Every printed name is wrong. The retired region mapping therefore reads the
**sacrum** channel for every lumbar vertebra and the **canal** channel for the
sacrum, and is right for cervical and thoracic levels only when the name's parity
happens to match the model's alternation. This is no longer an inference: it is
the checkpoint's own label definition.

Encoded in `src/spinelab/confidence/channels.py` together with the three E1
variants. Run `python -m spinelab.confidence.channels` to print the table.

Note for variant (b): parity follows the vertebra's position in the model's
detected sequence, not its anatomical name, so a name-derived ordinal is out of
phase whenever the topmost visible vertebra is not C1. Pass the real ordinal from
the segmentation.

## Entry points

Recovered server code, under `$VENDOR` (`<path>\app`):

| file | role |
|---|---|
| `api.py`, `app.py` | Flask service, gunicorn on port 57143 |
| `cfg/config.yml` | `device: "gpu_all"`, `data_path: "models"`, `step1_only: false`, series `priority_list` |
| `inference_core/predict_nnunet.py` | nnU-Net invocation |
| `inference_core/iterative_labeling_main.py` | **the vertebral level assignment algorithm** |
| `inference_core/iterative_labeling_landmarks.py` | landmark disc anchoring |
| `utils/confidence_calculator.py` | **production per-vertebra confidence. Its `get_vertebra_channel` restarts parity at C1, T1 and L1, so it is NOT the continuous-parity rule these notes once called "corrected". See G20 and `channel_region_restart`.** |
| `utils/json_generator.py` | writes `raw_softmax_values.json` |
| `utils/preview_selector.py` | middle-appearance slice selection |
| `TechnicalReport.md`, `README.md` | upstream documentation, 24 KB and 10 KB |

Client side, under `$BASELINE\test_api`:

| file | role |
|---|---|
| `generate_gsps_4.py` | **production GSPS emitter**, wrote the 38 objects on disk |
| `debug/refinement/generate_refined_labels_10.py` | final label refinement |
| `config.py` | `API_URL = http://10.1.1.28:57143/segment` |

Numbered siblings (`generate_gsps.py` through `_3`, `generate_refined_labels`
through `_9b`) are superseded. Do not read them for current behaviour.

## Data

Only two public datasets are CLEAN for this project.

| dataset | modality | why | access |
|---|---|---|---|
| TotalSegmentator MRI | MR | in distribution, named vertebrae | Zenodo 14710732, CC BY 4.0, anonymous |
| TotalSegmentator CT | CT | named C1-L5 plus S1, 1228 cases | Zenodo 10047292, CC BY 4.0, anonymous |
| VerSe 2019 + 2020 | CT | out of distribution, but has the organiser's own scorer and a published leaderboard | OSF nqjyw and t98fz, CC BY-SA 4.0, anonymous |

**Contaminated, must never be used as a held out evaluation set:** SPIDER,
spine-generic, whole-spine and MRSpineSeg are all in UPSTREAM TotalSpineSeg's
training data. The checkpoints here are the upstream released weights, not a local
training run: `fold_0/debug.json` records hostname ng20104.narval.calcul.quebec, a
Digital Research Alliance of Canada cluster, on an A100-SXM4-40GB with torch 2.3.1.
The `dataset.txt` and `progress.png` files ship inside the released model folder
and are upstream's records, not evidence of local training.

VerSe scorer: `github.com/anjany/verse`, `utils/eval_utilities.py`, MIT, runs
offline. Metric is identification rate, correct label closest and within 20 mm.
A copy is staged in the session scratchpad.

## Findings that constrain what the paper can claim

1. **The published confidence numbers are void.** `build_confidence_calibration.py`
   selects the output channel from the first letter of the vertebra name
   (C to channel 6, T to 7, L to 8). The model is a region-based nnU-Net with no
   background channel, so the real semantics are channel 6 = odd vertebrae,
   7 = even vertebrae, 8 = **sacrum**, 9 = canal, 10 = cord. Lumbar vertebrae were
   scored against the sacrum channel. Measured consequence: median per-vertebra
   confidence in images rated all good is 0.00015 at L1 and 0.00685 at L5, and
   46.1 percent of all vertebrae score below 0.1.

2. **There are two confidence implementations, and NEITHER is correct.** The
   calibration path above, and the live server's `utils/confidence_calculator.py`,
   dated two days after the calibration was built. These notes used to call the
   server version "the CORRECT parity mapping". It is not. Its
   `get_vertebra_channel` restarts parity at C1, T1 and L1, so C7 and T1 collide
   and it is wrong from T1 downwards, not just for the lumbar spine. Measured as
   arm `parity_region_deployed`: **AUC 0.427**, the worst of the nine, and
   indistinguishable from chance once the intervals respect case clustering.
   Retired as G20. They also differ in
   kind: the server computes on a single 2D slice with range 0.63 to 0.99, the
   calibration computed 3D whole-structure values with range 0.03 to 0.56.

3. **Calibration and evaluation are the same 558 images.** 100 percent overlap.
   Thresholds are percentiles of the ratings they are evaluated against.
   Measured in sample: Spearman with severity +0.0205, AUC 0.478 for detecting
   not-all-good, 0.528 per vertebra. Note this is separate from segmentation,
   which does have a legitimate 5 fold held out split in
   `models/*/splits_final.json` with `validation/summary.json` metrics.

4. **The spline flag and the confidence are one number.** `generate_gsps_4.py`
   does `penalized = confidence * multiplier` and colours red exactly when the
   multiplier fired. Any ablation treating them as independent signals requires
   instrumenting the code to emit them separately first.

5. **The spline detector fires on noise.** One tailed `z > 1.5` on logged
   distances of 1.4 to 1.8 px, roughly 0.5 mm, when a real mislabel displaces a
   centroid by a vertebral height. 11.1 percent of vertebrae flagged, 37 of 38
   studies carry at least one flag. No guard against `std_dist` approaching zero:
   max logged z is 651.46 where theory caps near 4.0 for n around 18.

6. **The 100 s per study figure is untraceable.** It is a transcription of a
   third party README table for a single P40. There is zero timing
   instrumentation in the entire project.

7. **The reviewed cohort is MR, the surviving GSPS objects are CT**, produced by
   an MRI-only model out of distribution. Declared `channel_names` is
   `{"0": "MRI"}` and training is 100 percent T1w/T2w.

8. **The 558 ratings are a single one-hour session**, median 2.37 s per image, in
   a local matplotlib tool presenting in patient order with filenames visible.
   Describe as a developer screening pass, not radiologist validation.

## Novelty position, verified 2026-07-29

Dead: "first end to end DICOM in / DICOM out spine labeling with vendor neutral
PACS rendering". Killed by Siemens AI-Rad Companion MSK (FDA K222361, 2022),
Son et al. Clinical Imaging 2026;132:110744, Avicenna CINA-CSpine (FDA 2024,
validated Diagnostics 2026;16(2):194), and deepc shipping GSPS today.

Dead: `Chen et al. 2025, SpineCheck` does not exist. The real SpineCheck is
Ilkhan et al., Informatics 2025;12(4):140, a scoliosis Cobb angle platform.

Pre-empted: labeling accuracy, by VERIDAH (arXiv:2601.14066, Jan 2026), which
beats TotalSpineSeg 98.30 vs 94.24 percent on MRI. Per-vertebra mislabel
confidence, by Netherton et al. 2020, 2022 IJROBP, and 2025 external validation.

Alive and verified: **no published study empirically compares GSPS versus DICOM
SEG rendering support across viewers.** PubMed returns three records total for
"Grayscale Softcopy Presentation State", none a viewer matrix. IHE AI Results
Rev 1.3 explicitly excludes presentation states, which is the tension to argue.

**SPIE Medical Imaging 2027 is abandoned and nothing was ever submitted to it.**
SPIE will not publish a paper that is not presented, the author will not travel to
Vancouver, and there is no remote or publication-only route. The 5 August 2026
abstract deadline and the 2-to-4-page supplemental format are both dead. Anything in
this repository still written against them is superseded, including
`docs/spie2027/`.
