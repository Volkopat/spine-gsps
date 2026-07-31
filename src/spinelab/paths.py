"""Single source of truth for where things live.

Every large or sensitive artifact sits OUTSIDE the repository. Override any of
these with an environment variable of the same name if the layout changes.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Everything lives under the project root, which is the parent of this repository.
# Derived rather than hardcoded so the whole tree can be relocated by moving one
# directory, which is exactly what happened on 2026-07-30 when these stores were
# consolidated from <path> into <path>.
ROOT = Path(os.environ.get("SPINELAB_ROOT", str(REPO.parent)))


def _p(env: str, default: Path) -> Path:
    return Path(os.environ.get(env, str(default)))


# --- large stores, never committed to either repository -------------------
MODELS = _p("SPINELAB_MODELS", ROOT / "models")
DATASETS = _p("SPINELAB_DATASETS", ROOT / "datasets")
RUNS = _p("SPINELAB_RUNS", ROOT / "runs")
TOOLS = _p("SPINELAB_TOOLS", ROOT / "tools")

# Code recovered from paratus-spine-labeling-cuda.tar. Read only, for porting
# and reference. Proprietary, do NOT copy into this repository.
VENDOR = _p("SPINELAB_VENDOR", ROOT / "_spine_extract" / "app")

# The private baseline repository holding the as-received material. This repository
# is nested inside it, and is excluded by the baseline's .gitignore.
BASELINE = _p("SPINELAB_BASELINE", ROOT)

# Third party validators
DCIODVFY = _p("SPINELAB_DCIODVFY", TOOLS / "dicom3tools" / "dciodvfy.exe")

# --- in repo, committed ---------------------------------------------------
RESULTS = REPO / "results"
FIGURES = RESULTS / "figures"

# --- nnU-Net checkpoint layout --------------------------------------------
# The two step cascade. Both step models were trained with the
# nnUNetTrainer_DASegOrd0_NoMirroring trainer and a custom nnUNetPlans_small
# plans identifier, so both must resolve in the installed nnunetv2.
TRAINER_STEP = "nnUNetTrainer_DASegOrd0_NoMirroring__nnUNetPlans_small__3d_fullres"
TRAINER_FULL = "nnUNetTrainer__nnUNetPlans__3d_fullres"

STEP1 = MODELS / "Dataset101_TotalSpineSeg_step1" / TRAINER_STEP
STEP2 = MODELS / "Dataset102_TotalSpineSeg_step2" / TRAINER_STEP
FULL = MODELS / "Dataset103_TotalSpineSeg_full" / TRAINER_FULL

# --- public evaluation sets ------------------------------------------------
# Only these two are CLEAN. The project's own checkpoints were trained on
# SPIDER and spine-generic (see models/*/dataset.txt), so those two datasets
# and whole-spine and MRSpineSeg are all contaminated and must not be used as
# held out evaluation sets. See CLAUDE.md.
TS_MRI = DATASETS / "totalsegmentator_mri"   # Zenodo 14710732, CC BY 4.0, in distribution
TS_CT = DATASETS / "totalsegmentator_ct"     # Zenodo 10047292, CC BY 4.0
VERSE19 = DATASETS / "verse2019"             # OSF nqjyw, CC BY-SA 4.0, CT so out of distribution
VERSE20 = DATASETS / "verse2020"             # OSF t98fz, CC BY-SA 4.0

CONTAMINATED = {
    "SPIDER": "in this project's own training data, dataset.txt",
    "spine-generic": "in this project's own training data, dataset.txt",
    "whole-spine": "upstream TotalSpineSeg training data",
    "MRSpineSeg": "upstream TotalSpineSeg sacrum labels",
}


def require(path: Path, what: str) -> Path:
    if not path.exists():
        raise FileNotFoundError("%s not found at %s" % (what, path))
    return path


def describe() -> str:
    rows = [
        ("ROOT", ROOT), ("REPO", REPO), ("MODELS", MODELS), ("DATASETS", DATASETS),
        ("RUNS", RUNS), ("TOOLS", TOOLS), ("VENDOR", VENDOR),
        ("BASELINE", BASELINE), ("DCIODVFY", DCIODVFY),
    ]
    out = []
    for name, p in rows:
        out.append("  %-10s %-46s %s" % (name, p, "ok" if p.exists() else "MISSING"))
    return "\n".join(out)


if __name__ == "__main__":
    print(describe())
