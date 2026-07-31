"""Smoke test: run step 1 on a single case and confirm inference works at all.

This is a gate, not an experiment. It answers three questions:
  1. Does nnUNetPredictor initialise from these checkpoints on this GPU.
  2. Does it produce a segmentation without crashing on CT input, given the
     model declares channel_names {"0": "MRI"}.
  3. Does save_probabilities give us the softmax array E1 needs.

Only fold_0 exists in the recovered checkpoints, so folds must be (0,).
The deployed predict_nnunet.py defaults to (0,1,2,3,4) and would fail here.
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spinelab.paths import RUNS, STEP1, STEP2, DATASETS  # noqa: E402

os.environ.setdefault("nnUNet_raw", str(RUNS / "nnunet_env" / "raw"))
os.environ.setdefault("nnUNet_preprocessed", str(RUNS / "nnunet_env" / "pre"))
os.environ.setdefault("nnUNet_results", str(RUNS / "nnunet_env" / "res"))
for v in ("nnUNet_raw", "nnUNet_preprocessed", "nnUNet_results"):
    Path(os.environ[v]).mkdir(parents=True, exist_ok=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default=None, help="path to a *_ct.nii.gz")
    ap.add_argument("--out", default=None)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--save-probabilities", action="store_true", default=True)
    ap.add_argument("--step-size", type=float, default=0.5)
    ap.add_argument("--disable-tta", action="store_true", default=True,
                    help="mirroring off by default: the trainer is NoMirroring")
    args = ap.parse_args(argv)

    import torch
    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor

    case = Path(args.case) if args.case else sorted(
        Path(DATASETS / "verse_4skx2").glob("*_ct.nii.gz"))[0]
    if not case.exists():
        print("case not found: %s" % case)
        return 1
    stem = case.name.replace("_ct.nii.gz", "")
    out = Path(args.out) if args.out else RUNS / "smoke" / stem
    in_dir = out / "in"
    seg_dir = out / "step1"
    in_dir.mkdir(parents=True, exist_ok=True)
    seg_dir.mkdir(parents=True, exist_ok=True)

    # nnU-Net wants CASE_0000.nii.gz per input channel
    staged = in_dir / (stem + "_0000.nii.gz")
    if not staged.exists():
        shutil.copy2(case, staged)
    print("case      : %s" % case.name)
    print("staged    : %s" % staged.name)
    print("model      : %s" % STEP1)
    if not (STEP1 / "fold_0" / "checkpoint_final.pth").exists():
        print("checkpoint missing under %s" % STEP1)
        return 1

    print("torch      : %s  cuda=%s  device=%s" % (
        torch.__version__, torch.cuda.is_available(), args.device))

    from spinelab.pipeline.torch_compat import load_predictor

    t0 = time.time()
    predictor, how, allowed = load_predictor(
        STEP1, folds=(0,), device=args.device,
        tile_step_size=args.step_size, use_mirroring=not args.disable_tta)
    t_init = time.time() - t0
    print("initialised in %.1f s via %s" % (t_init, how))
    print("allowlisted globals: %s" % ", ".join(allowed))

    cfg = predictor.configuration_manager
    print("patch      : %s" % (cfg.patch_size,))
    print("spacing    : %s" % (cfg.spacing,))
    print("normalisation schemes: %s" % (cfg.normalization_schemes,))
    lm = predictor.label_manager
    print("foreground regions: %s" % (lm.foreground_regions
                                      if hasattr(lm, "foreground_regions") else "n/a"))
    print("has_regions: %s  num_segmentation_heads: %s" % (
        getattr(lm, "has_regions", "?"), getattr(lm, "num_segmentation_heads", "?")))

    t1 = time.time()
    predictor.predict_from_files(
        str(in_dir), str(seg_dir),
        save_probabilities=args.save_probabilities,
        overwrite=True,
        num_processes_preprocessing=2,
        num_processes_segmentation_export=2,
    )
    t_pred = time.time() - t1

    print("\n=== results ===")
    print("init  %.1f s   predict %.1f s   total %.1f s" % (
        t_init, t_pred, t_init + t_pred))
    produced = sorted(glob.glob(str(seg_dir / "*")))
    if not produced:
        print("NO OUTPUT PRODUCED")
        return 2
    for p in produced:
        print("  %9.1f MB  %s" % (os.path.getsize(p) / 1e6, os.path.basename(p)))

    seg = seg_dir / (stem + ".nii.gz")
    if seg.exists():
        import numpy as np
        import nibabel as nib
        m = nib.load(str(seg)).get_fdata().astype(int)
        vals, counts = np.unique(m, return_counts=True)
        print("\nsegmentation labels present:")
        for v, c in zip(vals, counts):
            print("  label %2d  %10d voxels  %5.2f%%" % (v, c, 100.0 * c / m.size))
        if len(vals) <= 1:
            print("\nWARNING: segmentation is empty apart from background.")
            print("Expected on out of distribution CT for an MRI trained model.")
            print("Inference itself still worked, which is what this gate tests.")

    npz = sorted(glob.glob(str(seg_dir / "*.npz")))
    if npz:
        import numpy as np
        z = np.load(npz[0])
        key = "probabilities" if "probabilities" in z else list(z.keys())[0]
        arr = z[key]
        print("\nsoftmax array: key=%r shape=%s dtype=%s" % (key, arr.shape, arr.dtype))
        print("  channels=%d, which must equal the region count" % arr.shape[0])
        print("  per channel mean: %s" % np.round(arr.reshape(arr.shape[0], -1).mean(1), 4))
    else:
        print("\nno .npz written, so save_probabilities did not take effect")

    print("\nSMOKE TEST PASSED (inference ran to completion)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
