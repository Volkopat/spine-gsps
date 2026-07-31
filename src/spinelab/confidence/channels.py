"""Authoritative softmax channel semantics for the two step cascade.

Read from the checkpoints' own dataset.json, not inferred. Both step models are
REGION BASED nnU-Net configurations, which is the whole source of the confusion:

    regions_class_order = [1, 2, ..., 11]

For a region based configuration nnU-Net emits one output channel per FOREGROUND
region and there is NO background channel. Softmax channel i corresponds to class
value regions_class_order[i], so channel index and label value differ by one.

Dataset102 (step 2) labels, verbatim from its dataset.json:

    {"background": 0, "disc": [1,2,3,4,5], "disc_C2_C3": 2, "disc_C7_T1": 3,
     "disc_T12_L1": 4, "disc_L5_S": 5, "vertebrae": [6,7,8,9], "vertebrae_O": 7,
     "vertebrae_E": 8, "sacrum": 9, "canal": [10,11], "cord": 11}

which yields the table below. The third column is the name the deployed
`json_generator.py` prints for that channel, and it is wrong for every channel.
"""
from __future__ import annotations

import re

# channel index -> (true meaning, name printed by the deployed json_generator.py)
STEP2_CHANNELS: dict[int, tuple[str, str]] = {
    0: ("disc (union of 1-5)", "background"),
    1: ("disc_C2_C3", "disc_type_1"),
    2: ("disc_C7_T1", "disc_type_2"),
    3: ("disc_T12_L1", "disc_type_3"),
    4: ("disc_L5_S", "disc_type_4"),
    5: ("vertebrae (union of 6-9)", "disc_type_5"),
    6: ("vertebrae_O (odd vertebrae)", "vertebrae_type_1"),
    7: ("vertebrae_E (even vertebrae)", "vertebrae_type_2"),
    8: ("sacrum", "vertebrae_type_3"),
    9: ("canal", "vertebrae_type_4"),
    10: ("cord", "spinal_canal"),
}

CH_DISC_UNION = 0
CH_VERT_UNION = 5
CH_VERT_ODD = 6
CH_VERT_EVEN = 7
CH_SACRUM = 8
CH_CANAL = 9
CH_CORD = 10

# Ordinal position of each named level along the column, used to derive parity.
# TotalSpineSeg's step 2 alternates classes so that ADJACENT vertebrae carry
# different labels. The alternation follows position in the detected sequence,
# so parity must come from the segmentation, not from the anatomical name.
#
# This table covers the MODAL spine only: C1-C7, T1-T12, L1-L5, sacrum. T13 and L6
# are deliberately excluded. Including them inserts a phantom slot that breaks
# parity for every level below it. Concretely, with T13 in the table T12 lands on
# ordinal 18 and L1 on ordinal 20, both even, so two ADJACENT vertebrae resolve to
# the same channel, which is precisely what the alternation exists to prevent.
# A test caught this (test_parity_alternates_between_adjacent_levels_of_a_modal_spine).
#
# For a spine that actually has T13 or L6, the name derived ordinal is wrong by
# construction and channel_parity raises. Pass the real ordinal from the detected
# sequence instead. That is the same limitation recorded in CLAUDE.md, and it is why
# the E1 ablation needs a fourth arm using sequence derived parity rather than
# name derived parity.
_LEVELS = (["C%d" % i for i in range(1, 8)]     # C1-C7,  ordinals 0-6
           + ["T%d" % i for i in range(1, 13)]  # T1-T12, ordinals 7-18
           + ["L%d" % i for i in range(1, 6)]   # L1-L5,  ordinals 19-23
           + ["SACRUM"])                        # ordinal 24
LEVEL_ORDINAL = {name: i for i, name in enumerate(_LEVELS)}

# Levels that exist anatomically but cannot be positioned from the name alone.
VARIANT_LEVELS = ("T13", "L6")


def normalise(level: str) -> str:
    s = re.sub(r"^vertebrae[_\-]?", "", str(level).strip(), flags=re.I).upper()
    return "SACRUM" if s.startswith("S") and not re.match(r"^S\d", s) else s


# --------------------------------------------------------------------------
# The three variants compared in experiment E1.
# --------------------------------------------------------------------------

def channel_region_retired(level: str) -> int:
    """Variant (a): the retired region mapping that produced every published number.

    Selects by the first letter of the vertebra name, on the false assumption
    that channels 6 to 9 index cervical, thoracic, lumbar and sacral regions.

    Consequences, now provable from the table above:
      C*      -> channel 6, vertebrae_O.  Correct only for C1, C3, C5, C7.
      T*      -> channel 7, vertebrae_E.  Correct only for even thoracic levels.
      L*      -> channel 8, SACRUM.       Never correct.
      sacrum  -> channel 9, CANAL.        Never correct.

    Kept only so the ablation can reproduce the published numbers exactly.
    """
    s = normalise(level)
    if s.startswith("C"):
        return 6
    if s.startswith("T"):
        return 7
    if s.startswith("L"):
        return 8
    return 9


def channel_parity(level: str, ordinal: int | None = None) -> int:
    """Variant (b): the corrected parity mapping used by the deployed server.

    `ordinal` is the vertebra's index in the detected caudal-to-cranial sequence.
    When omitted we fall back to the canonical anatomical ordinal, which is what
    utils/confidence_calculator.py effectively does. That fallback is wrong
    whenever the model's alternation is out of phase with anatomy, for example
    when the topmost visible vertebra is not C1, so prefer passing the real
    ordinal from the segmentation.
    """
    s = normalise(level)
    if s == "SACRUM":
        return CH_SACRUM
    if ordinal is None:
        if s in VARIANT_LEVELS:
            raise ValueError(
                "%s is a transitional level, so its position cannot be derived from "
                "its name. Pass ordinal= from the detected sequence." % s)
        ordinal = LEVEL_ORDINAL.get(s)
        if ordinal is None:
            raise ValueError("unknown level %r" % level)
    return CH_VERT_ODD if ordinal % 2 == 0 else CH_VERT_EVEN


def mapping_free_scores(probs) -> dict[str, float]:
    """Variant (c): no name to channel mapping at all.

    `probs` is an array of shape (n_channels, n_voxels) holding the softmax
    values for the voxels of one segmented vertebra. Returns uncertainty
    measures that need no knowledge of which channel the vertebra belongs to,
    which removes the entire class of bug above.

    - margin:  mean over voxels of (top1 - top2). High means confident.
    - entropy: mean normalised Shannon entropy. Low means confident, so we
               return 1 - entropy so that higher is better throughout.
    - top1:    mean of the maximum probability, the naive baseline.
    - agree:   fraction of voxels whose argmax is the modal argmax, a purely
               structural consistency measure.
    """
    import numpy as np

    p = np.asarray(probs, dtype=np.float64)
    if p.ndim != 2:
        raise ValueError("expected (n_channels, n_voxels), got %r" % (p.shape,))
    p = np.clip(p, 1e-12, 1.0)
    p = p / p.sum(axis=0, keepdims=True)

    srt = np.sort(p, axis=0)
    top1 = srt[-1]
    top2 = srt[-2] if p.shape[0] > 1 else np.zeros_like(top1)
    ent = -(p * np.log(p)).sum(axis=0) / np.log(p.shape[0])

    arg = p.argmax(axis=0)
    modal = np.bincount(arg, minlength=p.shape[0]).argmax()

    return {
        "margin": float(np.mean(top1 - top2)),
        "entropy_inv": float(1.0 - np.mean(ent)),
        "top1": float(np.mean(top1)),
        "agree": float(np.mean(arg == modal)),
        "modal_channel": int(modal),
    }


def describe() -> str:
    rows = ["ch  true meaning                     name printed by json_generator.py"]
    rows.append("-" * 74)
    for i, (truth, printed) in STEP2_CHANNELS.items():
        flag = "  <-- misleading" if truth.split()[0].lower() not in printed.lower() else ""
        rows.append("%2d  %-32s %-22s%s" % (i, truth, printed, flag))
    return "\n".join(rows)


if __name__ == "__main__":
    print(describe())
    print("\nretired region mapping, what each level actually reads:")
    for lv in ("C1", "C2", "T1", "T2", "L1", "L3", "L5", "SACRUM"):
        ch = channel_region_retired(lv)
        print("  %-7s -> ch%-2d = %s" % (lv, ch, STEP2_CHANNELS[ch][0]))


def channel_region_restart(name: str) -> int:
    """The channel the DEPLOYED service selects. Not the same as channel_parity.

    `utils/confidence_calculator.py::get_vertebra_channel` reads the integer inside
    the vertebra's own name and tests its parity, so counting restarts at C1, T1 and
    L1 instead of running continuously down the column. C7 and T1 therefore land on
    the same channel, which two adjacent vertebrae never should.

    Transcribed from the deployed source, which lives outside this repository in the
    recovered container tree and is not redistributable. `tests/test_channels.py`
    pins the behaviour independently: it agrees with `channel_parity` on C1 to C7
    only, and asserts the C7/T1 collision.
    """
    s = normalise(name)
    if s.startswith("S"):
        return 8
    return 6 if int(s[1:]) % 2 == 1 else 7
