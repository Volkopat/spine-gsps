"""Unattended two step batch inference that keeps statistics, not softmax.

Runs the deployed cascade over many cases and writes one compact JSON per case.
The probability array is held in memory for exactly as long as it takes to reduce
it to per vertebra statistics, then dropped. Nothing of that size touches disk:
one case of step 1 softmax is 757 MB as an .npz (measured, see
results/smoke_inference.md), so a 40 case two step run would be well over 60 GB.

What "the deployed cascade" means here, and why we can reproduce it
------------------------------------------------------------------
The step 2 model takes a TWO CHANNEL input. Channel 0 is the intensity image
cropped to the step 1 bounding box, channel 1 is a BINARY mask of every other
disc found by step 1. Getting channel 1 wrong makes step 2 meaningless, so the
construction was read out of the recovered server source rather than guessed,
and then cross checked against the installed upstream package:

  <path>\\app\\inference_core\\inference_logic.py, lines 275-350
  totalspineseg/inference.py, lines 655-700   (version 20260623, pip installed)

Both perform the identical five steps, and the second is not proprietary, which
is what lets this module call upstream helpers instead of copying vendor code:

  1. largest_component(step1_raw, binarize=True, dilate=5)
  2. iterative_label(...)     step 1 parameter set, discs become 63 to 100
  3. fill_canal(canal_label=2, cord_label=1, largest_canal, largest_cord)
  4. transform_seg2image(input_image, step1_output)      back to input grid
  5. crop_image2seg(image, step1_output, margin=10)      -> channel 0
     transform_seg2image(cropped_image, step1_output)    step 1 seg on that grid
     extract_alternate(seg, labels=list(range(63, 101))) -> channel 1, binary

`extract_alternate` keeps `labels[::2]` of the disc labels actually present, in
ascending label order, and writes 1 into those voxels and 0 everywhere else. So
channel 1 is the odd indexed subset of the DETECTED disc sequence, not of the
anatomical sequence. That is the whole content of the vendor's log line
"Mapping the IVDs labels from the step1 model output to the odd IVDs".

Two facts that the surrounding project gets wrong, recorded here so this module
is not read as endorsing them
-----------------------------------------------------------------------------
1. These are NOT softmax values. Both step models are region based, and
   nnunetv2 sets `inference_nonlin = torch.sigmoid` whenever `has_regions` is
   true (nnunetv2/utilities/label_handling/label_handling.py:47). Every channel
   is an independent per region sigmoid and the channels do not sum to one. The
   project calls them softmax throughout, including in the deployed
   `raw_softmax_values.json`. We keep the statistics identical to what the
   deployed code would compute and name the JSON field `probabilities`.
2. Channel index and label value differ by one because there is no background
   channel. See spinelab.confidence.channels for the authoritative table.

Both step models expose only fold_0, so folds is always (0,), and the trainer is
nnUNetTrainer_DASegOrd0_NoMirroring, so mirroring is always off.
"""
from __future__ import annotations

import datetime
import gc
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from pathlib import Path

import numpy as np

from spinelab import paths
from spinelab.confidence.channels import (
    channel_parity,
    channel_region_retired,
    mapping_free_scores,
)

# nnU-Net insists on these three being set before it is imported. They are only
# used for experiment planning, which we never do, so they point at scratch.
for _var, _sub in (("nnUNet_raw", "raw"), ("nnUNet_preprocessed", "pre"),
                   ("nnUNet_results", "res")):
    os.environ.setdefault(_var, str(paths.RUNS / "nnunet_env" / _sub))
    Path(os.environ[_var]).mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# The deployed iterative labelling parameter sets, verbatim.
# Source: inference_logic.py:148-165 (step 1) and :375-394 (step 2).
# Identical in totalspineseg/inference.py:495-509 and :778-797.
#
# NEVER pass these dicts to iterative_label directly. Use iterative_kwargs()
# below. See the comment there: iterative_label mutates the list it is given.
# --------------------------------------------------------------------------
STEP1_ITERATIVE = dict(
    selected_disc_landmarks=[2, 5, 3, 4],
    disc_labels=[1, 2, 3, 4, 5],
    disc_landmark_labels=[2, 3, 4, 5],
    disc_landmark_output_labels=[63, 71, 91, 100],
    canal_labels=[8],
    canal_output_label=2,
    cord_labels=[9],
    cord_output_label=1,
    sacrum_labels=[6],
    sacrum_output_label=50,
    map_input_dict={7: 11},
)

STEP2_ITERATIVE = dict(
    selected_disc_landmarks=[2, 5, 3, 4],
    disc_labels=[1, 2, 3, 4, 5],
    disc_landmark_labels=[2, 3, 4, 5],
    disc_landmark_output_labels=[63, 71, 91, 100],
    vertebrae_labels=[7, 8, 9],
    vertebrae_landmark_output_labels=[13, 21, 41, 50],
    vertebrae_extra_labels=[6],
    canal_labels=[10],
    canal_output_label=2,
    cord_labels=[11],
    cord_output_label=1,
    sacrum_labels=[9],
    sacrum_output_label=50,
)


def iterative_kwargs(base: dict) -> dict:
    """Deep copy of a parameter set, because iterative_label mutates its input.

    This is not defensive style, it is a required fix. `iterative_label` calls
    `selected_disc_landmarks.remove(2)` and `.remove(5)` on the caller's own
    list object when the top disc is not C2-C3 or the bottom disc is not L5-S
    (totalspineseg/utils/iterative_label.py:592-606). The list is never copied.

    The deployed pipeline never noticed because `iterative_label_mp` fans out
    over `process_map`, so each case gets a fresh copy of the partial in its own
    process. A single process batch driver that reuses one dict silently
    degrades: the first case strips 2 and 5, and every case after it runs with
    `selected_disc_landmarks=[3, 4]` only. Measured here on 2026-07-30: case 1
    succeeded, case 2 then failed with "At least one of the landmarks must be in
    the segmentation or localizer (landmarks: [3, 4])" even though its
    disc_C2_C3 label was present with 2481 voxels after largest_component.
    """
    import copy

    return copy.deepcopy(base)


# Disc output labels that extract_alternate selects from, inference_logic.py:311.
DISC_OUTPUT_LABELS = list(range(63, 101))

# Vertebra label values in the step 2 labelled output. Derived from
# vertebrae_landmark_output_labels=[13, 21, 41, 50], meaning C3, T1, L1, sacrum,
# and confirmed by the vendor's own preview legend, inference_logic.py:439-444.
VERTEBRA_NAMES: dict[int, str] = {}
for _i, _lab in enumerate(range(11, 18)):
    VERTEBRA_NAMES[_lab] = "C%d" % (_i + 1)
for _i, _lab in enumerate(range(21, 33)):
    VERTEBRA_NAMES[_lab] = "T%d" % (_i + 1)
for _i, _lab in enumerate(range(41, 47)):
    VERTEBRA_NAMES[_lab] = "L%d" % (_i + 1)
VERTEBRA_NAMES[50] = "SACRUM"

PROB_THRESHOLD = 0.7
ROUND = 6


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------

def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _pkg_version(name: str) -> str:
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:
        return "unknown"


def _git_head() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(paths.REPO),
                             capture_output=True, text=True, timeout=20)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def build_manifest(args: dict, model_folders: dict, argv: list[str]) -> dict:
    """Everything needed to say what produced a run. Hashes are of the files."""
    import torch

    gpu = {}
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        gpu = {
            "name": props.name,
            "capability": "sm_%d%d" % (props.major, props.minor),
            "total_memory_bytes": int(props.total_memory),
            "count": torch.cuda.device_count(),
            "arch_list": torch.cuda.get_arch_list(),
        }

    checkpoints = {}
    for step, folder in model_folders.items():
        folder = Path(folder)
        entry: dict = {"model_folder": str(folder), "files": {}}
        for rel in ("fold_0/checkpoint_final.pth", "plans.json", "dataset.json"):
            fp = folder / rel
            if fp.exists():
                entry["files"][rel] = {
                    "sha256": file_sha256(fp),
                    "size_bytes": fp.stat().st_size,
                }
            else:
                entry["files"][rel] = {"sha256": None, "size_bytes": None,
                                       "note": "missing"}
        checkpoints[step] = entry

    return {
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"),
        "argv": list(argv),
        "args": args,
        "interpreter": sys.executable,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "repo_git_head": _git_head(),
        "versions": {
            "torch": torch.__version__,
            "torch_cuda": torch.version.cuda,
            "nnunetv2": _pkg_version("nnunetv2"),
            "totalspineseg": _pkg_version("totalspineseg"),
            "numpy": _pkg_version("numpy"),
            "nibabel": _pkg_version("nibabel"),
            "SimpleITK": _pkg_version("SimpleITK"),
        },
        "gpu": gpu,
        "checkpoints": checkpoints,
        "settings": {
            "folds": [0],
            "use_mirroring": False,
            "reason_folds": "only fold_0 exists in the recovered checkpoints",
            "reason_mirroring": "trainer is nnUNetTrainer_DASegOrd0_NoMirroring",
            "probability_nonlinearity": "sigmoid per region, not softmax",
            "prob_threshold": PROB_THRESHOLD,
        },
    }


# --------------------------------------------------------------------------
# Statistics. This is the only thing that ever sees the probability array.
# --------------------------------------------------------------------------

def _r(x: float) -> float:
    return round(float(x), ROUND)


def channel_statistics(vals: np.ndarray, threshold: float = PROB_THRESHOLD) -> dict:
    """Reduce one channel's values over one vertebra to eight numbers."""
    p75, p95 = np.percentile(vals, [75.0, 95.0])
    return {
        "mean": _r(vals.mean()),
        "median": _r(np.median(vals)),
        "p75": _r(p75),
        "p95": _r(p95),
        "max": _r(vals.max()),
        "min": _r(vals.min()),
        "std": _r(vals.std()),
        "n_gt_0p7": int((vals > threshold).sum()),
    }


def vertebra_statistics(probs_xyz: np.ndarray, labelled: np.ndarray,
                        raw: np.ndarray | None, affine: np.ndarray,
                        threshold: float = PROB_THRESHOLD) -> list[dict]:
    """Per vertebra statistics over ALL channels.

    probs_xyz  (n_channels, X, Y, Z), same voxel grid as `labelled`.
    labelled   (X, Y, Z) step 2 labelled output, vertebra values per
               VERTEBRA_NAMES.
    raw        (X, Y, Z) step 2 raw model output, values 1 to 11, or None. Used
               to record which region class the model itself assigned, which is
               the ground truth for the parity question that E1 variant (b) is
               about.
    affine     nibabel affine of that grid, RAS+, used for world centroids.

    All three E1 variants must be evaluable from this output alone, so we store
    every channel rather than the one channel a mapping would select.
    """
    n_ch = probs_xyz.shape[0]
    present = [int(v) for v in np.unique(labelled) if int(v) in VERTEBRA_NAMES]

    rows = []
    for lab in present:
        mask = labelled == lab
        n_vox = int(mask.sum())
        if n_vox == 0:
            continue
        idx = np.array(np.nonzero(mask), dtype=np.float64)          # (3, n)
        centroid_vox = idx.mean(axis=1)
        world = affine[:3, :3] @ centroid_vox + affine[:3, 3]

        sub = probs_xyz[:, mask]                                    # (C, n)
        row = {
            "label": lab,
            "name": VERTEBRA_NAMES[lab],
            "n_voxels": n_vox,
            "centroid_voxel": [_r(v) for v in centroid_vox],
            "centroid_world_ras_mm": [_r(v) for v in world],
            "channels": {str(c): channel_statistics(sub[c], threshold)
                         for c in range(n_ch)},
            "mapping_free": {k: (_r(v) if isinstance(v, float) else v)
                             for k, v in mapping_free_scores(sub).items()},
        }
        if raw is not None:
            vals, counts = np.unique(raw[mask], return_counts=True)
            hist = {str(int(v)): int(c) for v, c in zip(vals, counts)}
            row["raw_class_hist"] = hist
            fg = [(c, v) for v, c in zip(vals, counts) if int(v) != 0]
            row["raw_class_modal"] = int(max(fg)[1]) if fg else None
        rows.append(row)

    # Ordinal along the column, 0 = most superior. RAS+ means +z is superior.
    # channels.channel_parity needs this real ordinal, not a name derived one:
    # the model's alternation follows detected position, so a name derived
    # ordinal is out of phase whenever the topmost visible vertebra is not C1.
    rows.sort(key=lambda r: -r["centroid_world_ras_mm"][2])
    for i, row in enumerate(rows):
        row["ordinal_superior_to_inferior"] = i
        row["channel_retired"] = channel_region_retired(row["name"])
        row["channel_parity_from_ordinal"] = channel_parity(row["name"], i)
        try:
            row["channel_parity_from_name"] = channel_parity(row["name"])
        except ValueError:
            row["channel_parity_from_name"] = None
    return rows


# --------------------------------------------------------------------------
# One case
# --------------------------------------------------------------------------

def _label_histogram(arr: np.ndarray) -> dict:
    vals, counts = np.unique(arr, return_counts=True)
    return {str(int(v)): int(c) for v, c in zip(vals, counts)}


def _save_seg(img, path: Path):
    """Write a label image as uint8, the way every vendor `_*_mp` worker does."""
    import nibabel as nib

    data = np.asanyarray(img.dataobj).round().astype(np.uint8)
    out = nib.Nifti1Image(data, img.affine, img.header)
    out.set_data_dtype(np.uint8)
    out.set_qform(out.affine)
    out.set_sform(out.affine)
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(out, str(path))
    return out


def _save_image(img, path: Path):
    """Write an intensity image without casting it.

    Mirrors the vendor's `_crop_image2seg`: take whatever dtype the array
    already has and declare that as the output dtype. Casting here would drop
    any scl_slope scaling that nibabel had already applied on read.
    """
    import nibabel as nib

    data = np.asanyarray(img.dataobj)
    out = nib.Nifti1Image(data, img.affine, img.header)
    out.set_data_dtype(data.dtype)
    out.set_qform(out.affine)
    out.set_sform(out.affine)
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(out, str(path))
    return out


def run_case(case_path: Path, predictor1, predictor2, work_dir: Path,
             seg_dir: Path, step1_only: bool = False,
             threshold: float = PROB_THRESHOLD, keep_work: bool = False) -> dict:
    """Full cascade for one case. Returns the record that gets written as JSON.

    Raises nothing that the caller should not see: expected pipeline dead ends
    (no landmark disc, no odd discs) come back as a status string. Genuine bugs
    propagate so the batch loop can log the traceback.
    """
    import nibabel as nib
    from nnunetv2.imageio.simpleitk_reader_writer import SimpleITKIO
    from totalspineseg.utils.crop_image2seg import crop_image2seg
    from totalspineseg.utils.extract_alternate import extract_alternate
    from totalspineseg.utils.fill_canal import fill_canal
    from totalspineseg.utils.iterative_label import iterative_label
    from totalspineseg.utils.largest_component import largest_component
    from totalspineseg.utils.transform_seg2image import transform_seg2image

    stem = case_path.name.replace("_ct.nii.gz", "").replace(".nii.gz", "")
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    io = SimpleITKIO()
    t0 = time.time()

    rec: dict = {
        "case": stem,
        "input_path": str(case_path),
        "status": "running",
        "n_channels_step2": None,
        "prob_note": "per region sigmoid, not softmax, channels do not sum to 1",
        "prob_threshold": threshold,
        "timings_s": {},
    }

    image_nib = nib.load(str(case_path))
    rec["input"] = {
        "shape": [int(v) for v in image_nib.shape],
        "zooms_xyz_mm": [_r(v) for v in image_nib.header.get_zooms()[:3]],
        "axcodes": "".join(nib.aff2axcodes(image_nib.affine)),
    }

    # ---- step 1 -----------------------------------------------------------
    t = time.time()
    img_npy, props = io.read_images([str(case_path)])
    seg1_npy = predictor1.predict_single_npy_array(
        img_npy, {"spacing": props["spacing"]},
        save_or_return_probabilities=False)
    rec["timings_s"]["step1_predict"] = _r(time.time() - t)
    del img_npy

    step1_raw_path = work_dir / (stem + "_step1_raw.nii.gz")
    io.write_seg(seg1_npy, str(step1_raw_path), props)
    rec["step1_raw_labels"] = _label_histogram(seg1_npy)
    del seg1_npy

    # ---- step 1 post processing, the deployed chain ------------------------
    t = time.time()
    seg1 = nib.load(str(step1_raw_path))
    seg1 = largest_component(seg1, binarize=True, dilate=5)
    try:
        seg1 = iterative_label(seg1, **iterative_kwargs(STEP1_ITERATIVE))
    except ValueError as e:
        rec["status"] = "step1_no_landmark"
        rec["error"] = "iterative_label step 1: %s" % e
        rec["timings_s"]["total"] = _r(time.time() - t0)
        return rec
    seg1 = fill_canal(seg1, canal_label=2, cord_label=1,
                      largest_canal=True, largest_cord=True)
    seg1 = transform_seg2image(image_nib, seg1)
    step1_out_path = work_dir / (stem + "_step1_output.nii.gz")
    seg1 = _save_seg(seg1, step1_out_path)
    rec["timings_s"]["step1_post"] = _r(time.time() - t)
    rec["step1_output_labels"] = _label_histogram(np.asanyarray(seg1.dataobj))

    if step1_only:
        rec["status"] = "ok_step1_only"
        rec["timings_s"]["total"] = _r(time.time() - t0)
        return rec

    # ---- step 2 input, two channels ---------------------------------------
    t = time.time()
    # Upstream crop_image2seg returns only the cropped image and uses
    # nibabel's img.slicer, which fixes the affine for us. The vendor copy
    # returns a (image, seg) tuple and slices the arrays by hand. We take the
    # upstream form and re-derive channel 1 with transform_seg2image, which is
    # what both versions do on the next line anyway.
    cropped_image = crop_image2seg(image_nib, seg1, margin=10)
    seg1_cropped = transform_seg2image(cropped_image, seg1)
    ch1 = extract_alternate(seg1_cropped, labels=DISC_OUTPUT_LABELS)
    ch1_data = np.asanyarray(ch1.dataobj).round().astype(np.uint8)

    # extract_alternate keeps `labels[::2]` of the disc labels present on THIS
    # grid, in ascending label order, so the selected set has to be read off the
    # cropped and resampled seg, not off the full step 1 output. Nearest
    # neighbour resampling can drop a thin disc.
    full = set(int(v) for v in np.unique(np.asanyarray(seg1.dataobj)))
    crop = set(int(v) for v in np.unique(
        np.asanyarray(seg1_cropped.dataobj).round().astype(np.uint8)))
    discs_full = [l for l in DISC_OUTPUT_LABELS if l in full]
    discs_crop = [l for l in DISC_OUTPUT_LABELS if l in crop]
    rec["step2_input"] = {
        "shape": [int(v) for v in cropped_image.shape],
        "discs_in_step1_output": discs_full,
        "discs_on_cropped_grid": discs_crop,
        "n_discs_detected": len(discs_crop),
        "odd_discs_selected": discs_crop[::2],
        "channel1_nonzero_voxels": int(ch1_data.sum()),
    }
    if int(ch1_data.sum()) == 0:
        rec["status"] = "no_odd_discs"
        rec["error"] = ("extract_alternate produced an empty channel 1, so step "
                        "2 input is degenerate. The deployed mp wrapper deletes "
                        "the file here and silently skips the case.")
        rec["timings_s"]["total"] = _r(time.time() - t0)
        return rec

    p0 = work_dir / (stem + "_step2_0000.nii.gz")
    p1 = work_dir / (stem + "_step2_0001.nii.gz")
    _save_image(cropped_image, p0)
    _save_seg(ch1, p1)
    rec["timings_s"]["step2_input"] = _r(time.time() - t)

    # ---- step 2 -----------------------------------------------------------
    t = time.time()
    two_ch, props2 = io.read_images([str(p0), str(p1)])
    seg2_npy, probs = predictor2.predict_single_npy_array(
        two_ch, {"spacing": props2["spacing"]},
        save_or_return_probabilities=True)
    rec["timings_s"]["step2_predict"] = _r(time.time() - t)
    del two_ch

    probs = np.asarray(probs, dtype=np.float32)
    rec["n_channels_step2"] = int(probs.shape[0])
    rec["prob_array_shape_nnunet_order"] = [int(v) for v in probs.shape]
    rec["prob_array_bytes_not_written"] = int(probs.nbytes)

    step2_raw_path = work_dir / (stem + "_step2_raw.nii.gz")
    io.write_seg(seg2_npy, str(step2_raw_path), props2)
    rec["step2_raw_labels"] = _label_histogram(seg2_npy)
    del seg2_npy

    # ---- step 2 post processing -------------------------------------------
    t = time.time()
    raw2 = nib.load(str(step2_raw_path))
    raw2_data = np.asanyarray(raw2.dataobj).round().astype(np.uint8)
    seg2 = largest_component(raw2, binarize=True, dilate=5)
    try:
        seg2 = iterative_label(seg2, **iterative_kwargs(STEP2_ITERATIVE))
    except ValueError as e:
        del probs
        rec["status"] = "step2_no_landmark"
        rec["error"] = "iterative_label step 2: %s" % e
        rec["timings_s"]["total"] = _r(time.time() - t0)
        return rec
    seg2 = fill_canal(seg2, canal_label=2, cord_label=1,
                      largest_canal=True, largest_cord=True)
    labelled = np.asanyarray(seg2.dataobj).round().astype(np.uint8)
    rec["step2_output_labels"] = _label_histogram(labelled)
    rec["timings_s"]["step2_post"] = _r(time.time() - t)

    # ---- statistics, then throw the array away ----------------------------
    # nnU-Net probability arrays are in SimpleITK index order (c, k, j, i).
    # nibabel arrays are (i, j, k). The vendor's extract_soft does the same
    # transpose, utils/nifti_processing/segmentation_extraction.py:108.
    t = time.time()
    probs_xyz = np.transpose(probs, (0, 3, 2, 1))
    if probs_xyz.shape[1:] != labelled.shape:
        del probs, probs_xyz
        raise RuntimeError(
            "probability grid %s does not match step 2 labelled grid %s"
            % (probs_xyz.shape[1:], labelled.shape))
    rec["vertebrae"] = vertebra_statistics(
        probs_xyz, labelled, raw2_data, seg2.affine, threshold=threshold)
    rec["n_vertebrae"] = len(rec["vertebrae"])
    rec["timings_s"]["statistics"] = _r(time.time() - t)
    del probs, probs_xyz

    # ---- final segmentation in the input grid, small and needed by eval ----
    t = time.time()
    final = transform_seg2image(image_nib, seg2)
    _save_seg(final, Path(seg_dir) / (stem + "_step2_output.nii.gz"))
    rec["timings_s"]["final_transform"] = _r(time.time() - t)
    rec["final_seg"] = str(Path(seg_dir) / (stem + "_step2_output.nii.gz"))

    if not keep_work:
        for p in (step1_raw_path, step1_out_path, p0, p1, step2_raw_path):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass

    rec["status"] = "ok"
    rec["timings_s"]["total"] = _r(time.time() - t0)
    return rec


# --------------------------------------------------------------------------
# The batch loop
# --------------------------------------------------------------------------

def find_cases(data_dir: Path, pattern: str = "*_ct.nii.gz") -> list[Path]:
    return sorted(Path(data_dir).glob(pattern))


def already_done(case_json: Path, step1_only: bool = False) -> bool:
    """Has this case a usable result for the mode being asked for.

    A step 1 only result must NOT satisfy a full two step request, or a
    --step1-only rehearsal would silently poison the real overnight run: the
    cases it touched would be skipped and no step 2 statistics would ever be
    produced. Measured on 2026-07-30, this is exactly what the naive
    startswith("ok") test did. A full result does satisfy a step 1 only
    request, since it strictly contains that work.
    """
    if not case_json.exists():
        return False
    try:
        rec = json.loads(case_json.read_text())
    except Exception:
        return False
    status = str(rec.get("status", ""))
    if status == "ok":
        return True
    if status == "ok_step1_only":
        return bool(step1_only)
    return False


def run_batch(cases: list[Path], run_dir: Path, device: str = "cuda",
              step1_only: bool = False, step_size: float = 0.5,
              overwrite: bool = False, keep_work: bool = False,
              threshold: float = PROB_THRESHOLD,
              manifest_extra: dict | None = None,
              argv: list[str] | None = None) -> dict:
    """Run the cascade over `cases`, resumable and crash tolerant.

    One bad case is logged with its traceback and the loop continues. Per case
    wall clock and peak GPU allocation go to run_log.jsonl as they happen, so a
    run killed halfway still leaves a usable log.
    """
    import torch

    from spinelab.pipeline.torch_compat import load_predictor

    run_dir = Path(run_dir)
    case_dir = run_dir / "cases"
    work_root = run_dir / "work"
    seg_dir = run_dir / "seg"
    for d in (case_dir, work_root, seg_dir):
        d.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "run_log.jsonl"

    todo = [c for c in cases
            if overwrite or not already_done(
                case_dir / (c.name.replace("_ct.nii.gz", "")
                            .replace(".nii.gz", "") + ".json"),
                step1_only=step1_only)]
    print("%d case(s) requested, %d to run, %d already done"
          % (len(cases), len(todo), len(cases) - len(todo)))
    if not todo:
        return {"manifest": None, "ran": 0, "ok": 0, "failed": 0}

    args = {
        "n_cases_requested": len(cases),
        "n_cases_to_run": len(todo),
        "device": device,
        "step1_only": step1_only,
        "step_size": step_size,
        "overwrite": overwrite,
        "keep_work": keep_work,
        "prob_threshold": threshold,
        "run_dir": str(run_dir),
        "cases_requested": [c.name for c in cases],
        "cases_to_run": [c.name for c in todo],
    }
    if manifest_extra:
        args.update(manifest_extra)

    folders = {"step1": paths.STEP1}
    if not step1_only:
        folders["step2"] = paths.STEP2
    manifest = build_manifest(args, folders, argv or sys.argv)
    # One manifest per invocation, never overwritten. A resumed run is a second
    # invocation with different arguments, and losing the first one's record
    # would make the output unattributable.
    stamp = manifest["utc"].replace(":", "").replace("-", "")
    mdir = run_dir / "manifests"
    mdir.mkdir(parents=True, exist_ok=True)
    body = json.dumps(manifest, indent=2)
    (mdir / ("manifest_%s.json" % stamp)).write_text(body)
    (run_dir / "manifest.json").write_text(body)
    print("manifest -> %s" % (mdir / ("manifest_%s.json" % stamp)))

    t = time.time()
    predictor1, how1, _ = load_predictor(
        paths.STEP1, folds=(0,), device=device, tile_step_size=step_size,
        use_mirroring=False, allow_tqdm=False)
    predictor2 = None
    how2 = "not loaded"
    if not step1_only:
        predictor2, how2, _ = load_predictor(
            paths.STEP2, folds=(0,), device=device, tile_step_size=step_size,
            use_mirroring=False, allow_tqdm=False)
    init_s = time.time() - t
    print("predictors loaded in %.1f s  step1 via %s  step2 via %s"
          % (init_s, how1, how2))

    with open(log_path, "a", encoding="utf-8") as log:
        log.write(json.dumps({
            "event": "run_start",
            "utc": manifest["utc"],
            "init_seconds": round(init_s, 3),
            "step1_load": how1,
            "step2_load": how2,
            "n_todo": len(todo),
        }) + "\n")
        log.flush()

        n_ok = n_fail = 0
        for i, case in enumerate(todo, 1):
            stem = case.name.replace("_ct.nii.gz", "").replace(".nii.gz", "")
            print("[%d/%d] %s" % (i, len(todo), stem), flush=True)
            if device == "cuda" and torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
            t0 = time.time()
            entry = {"event": "case", "case": stem,
                     "utc": datetime.datetime.now(
                         datetime.timezone.utc).isoformat(timespec="seconds")}
            try:
                rec = run_case(case, predictor1, predictor2,
                               work_root / stem, seg_dir,
                               step1_only=step1_only, threshold=threshold,
                               keep_work=keep_work)
                wall = time.time() - t0
                peak = (int(torch.cuda.max_memory_allocated())
                        if device == "cuda" and torch.cuda.is_available() else None)
                rec["wall_seconds"] = round(wall, 3)
                rec["peak_gpu_allocated_bytes"] = peak
                out = case_dir / (stem + ".json")
                out.write_text(json.dumps(rec, indent=1))
                entry.update({
                    "status": rec["status"],
                    "wall_seconds": round(wall, 3),
                    "peak_gpu_allocated_bytes": peak,
                    "peak_gpu_allocated_gib": (round(peak / 2 ** 30, 3)
                                               if peak else None),
                    "n_vertebrae": rec.get("n_vertebrae"),
                    "json_bytes": out.stat().st_size,
                    "timings_s": rec.get("timings_s"),
                })
                if str(rec["status"]).startswith("ok"):
                    n_ok += 1
                else:
                    n_fail += 1
                print("    %s  %.1f s  peak %s  json %.1f KB"
                      % (rec["status"], wall,
                         "%.2f GiB" % (peak / 2 ** 30) if peak else "n/a",
                         out.stat().st_size / 1024.0))
            except BaseException as e:              # noqa: BLE001
                wall = time.time() - t0
                peak = (int(torch.cuda.max_memory_allocated())
                        if device == "cuda" and torch.cuda.is_available() else None)
                entry.update({
                    "status": "exception",
                    "wall_seconds": round(wall, 3),
                    "peak_gpu_allocated_bytes": peak,
                    "exception": "%s: %s" % (type(e).__name__, e),
                    "traceback": traceback.format_exc(),
                })
                n_fail += 1
                print("    EXCEPTION after %.1f s: %s: %s"
                      % (wall, type(e).__name__, e))
                if isinstance(e, KeyboardInterrupt):
                    log.write(json.dumps(entry) + "\n")
                    log.flush()
                    raise
            finally:
                log.write(json.dumps(entry) + "\n")
                log.flush()
                # A failing case leaves the probability array reachable from the
                # traceback frame. Over 40 cases that fragments both heaps, so
                # release explicitly rather than trusting refcount timing.
                gc.collect()
                if device == "cuda" and torch.cuda.is_available():
                    torch.cuda.empty_cache()

        summary = {"event": "run_end", "ok": n_ok, "failed": n_fail,
                   "utc": datetime.datetime.now(
                       datetime.timezone.utc).isoformat(timespec="seconds")}
        log.write(json.dumps(summary) + "\n")

    print("\ndone: %d ok, %d failed. log %s" % (n_ok, n_fail, log_path))
    return {"manifest": manifest, "ran": len(todo), "ok": n_ok, "failed": n_fail}
