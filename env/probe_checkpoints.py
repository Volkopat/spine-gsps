"""Can this nnunetv2 resolve the trainer the checkpoints need, and load them?

The trainer lookup is necessary but not sufficient. Actually deserialising the
checkpoint and reading its plans is the real test.
"""
import os
import sys
import traceback
from pathlib import Path

MODELS = Path(os.environ.get("SPINELAB_MODELS", r"<path>\models"))

print("=" * 70)
print("1. versions")
print("=" * 70)
import torch

print("torch     ", torch.__version__)
try:
    import nnunetv2

    ver = getattr(nnunetv2, "__version__", None)
    if ver is None:
        from importlib.metadata import version

        ver = version("nnunetv2")
    print("nnunetv2  ", ver)
except Exception as e:
    print("nnunetv2 import FAILED:", e)
    sys.exit(1)
try:
    from importlib.metadata import version

    print("totalspineseg", version("totalspineseg"))
except Exception as e:
    print("totalspineseg not installed:", e)

print("\n" + "=" * 70)
print("2. trainer resolution")
print("=" * 70)
ok_trainers = True
try:
    from nnunetv2.utilities.find_class_by_name import recursive_find_python_class
    import nnunetv2.training.nnUNetTrainer as T

    root = os.path.dirname(T.__file__)
    for name in ("nnUNetTrainer", "nnUNetTrainer_DASegOrd0_NoMirroring"):
        cls = recursive_find_python_class(root, name, "nnunetv2.training.nnUNetTrainer")
        status = ("FOUND  " + cls.__module__) if cls else "NOT FOUND"
        print("  %-40s %s" % (name, status))
        if cls is None:
            ok_trainers = False
except Exception:
    traceback.print_exc()
    ok_trainers = False

print("\n" + "=" * 70)
print("3. checkpoint deserialisation and plans")
print("=" * 70)
targets = [
    ("step1", "Dataset101_TotalSpineSeg_step1",
     "nnUNetTrainer_DASegOrd0_NoMirroring__nnUNetPlans_small__3d_fullres"),
    ("step2", "Dataset102_TotalSpineSeg_step2",
     "nnUNetTrainer_DASegOrd0_NoMirroring__nnUNetPlans_small__3d_fullres"),
    ("full", "Dataset103_TotalSpineSeg_full", "nnUNetTrainer__nnUNetPlans__3d_fullres"),
]

all_ok = True
for tag, ds, trainer in targets:
    d = MODELS / ds / trainer
    ckpt = d / "fold_0" / "checkpoint_final.pth"
    print("\n[%s] %s" % (tag, ds))
    if not ckpt.exists():
        print("   MISSING", ckpt)
        all_ok = False
        continue
    try:
        blob = torch.load(str(ckpt), map_location="cpu", weights_only=False)
        keys = sorted(blob.keys())
        print("   checkpoint keys:", keys)
        print("   trainer_name   :", blob.get("trainer_name"))
        print("   init_args      :", str(blob.get("init_args"))[:110])
        sd = blob.get("network_weights") or blob.get("state_dict") or {}
        nparam = sum(v.numel() for v in sd.values() if hasattr(v, "numel"))
        print("   tensors=%d  params=%.1fM" % (len(sd), nparam / 1e6))
        import json

        plans = json.loads((d / "plans.json").read_text())
        cfg = plans["configurations"]["3d_fullres"]
        print("   plans_name     :", plans.get("plans_name"))
        print("   patch_size     :", cfg.get("patch_size"))
        print("   spacing        :", cfg.get("spacing"))
        print("   batch_size     :", cfg.get("batch_size"))
        dj = json.loads((d / "dataset.json").read_text())
        labels = dj.get("labels", {})
        print("   channel_names  :", dj.get("channel_names"))
        print("   n_label_entries:", len(labels))
        print("   labels         :", json.dumps(labels)[:400])
        if "regions_class_order" in dj:
            print("   regions_class_order:", dj["regions_class_order"])
            print("   -> REGION BASED, so softmax channel i corresponds to")
            print("      regions_class_order[i], NOT to label value i.")
    except Exception:
        traceback.print_exc()
        all_ok = False

print("\n" + "=" * 70)
print("VERDICT: trainers=%s checkpoints=%s" % (
    "ok" if ok_trainers else "FAIL", "ok" if all_ok else "FAIL"))
print("=" * 70)
sys.exit(0 if (ok_trainers and all_ok) else 3)
