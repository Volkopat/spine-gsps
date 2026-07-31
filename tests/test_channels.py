"""The channel table must agree with the checkpoints' own dataset.json.

This is the test that would have caught the confidence bug. The published
confidence numbers scored every lumbar vertebra against the SACRUM channel
because the region-based channel semantics were never read off the checkpoint.
The table in spinelab.confidence.channels is now the single source of truth, so
it has to be pinned to the artifact it claims to describe.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from spinelab.confidence import channels as C
from spinelab import paths


# --------------------------------------------------------------------------
# 1. The table versus the checkpoint
# --------------------------------------------------------------------------

def _load_dataset_json(folder):
    p = folder / "dataset.json"
    if not p.exists():
        pytest.skip("no dataset.json at %s, checkpoint store not present" % p)
    return json.loads(p.read_text())


def _foreground_regions(dsj):
    """The label entries nnU-Net turns into output channels, in channel order.

    For a region based configuration nnU-Net emits one channel per non
    background entry of `labels`, in insertion order, and `regions_class_order`
    gives the class value each channel decodes to. Confirmed independently:
    nnUNetPredictor reported `foreground_regions` for step 1 as
    [(1,2,3,4,5), 2, 3, 4, 5, (6,7), 7, (8,9), 9], which is exactly this list.
    See results/smoke_inference.md.
    """
    return [(k, v) for k, v in dsj["labels"].items() if k != "background"]


@pytest.fixture(scope="module")
def step2_json():
    return _load_dataset_json(paths.STEP2)


@pytest.fixture(scope="module")
def step1_json():
    return _load_dataset_json(paths.STEP1)


def test_step2_is_region_based_with_no_background_channel(step2_json):
    """regions_class_order present and starting at 1 is the whole premise."""
    rco = step2_json["regions_class_order"]
    assert rco, "regions_class_order absent, the model would not be region based"
    assert rco[0] == 1, "channel 0 must decode to class 1, not background"
    assert 0 not in rco, "a background channel would shift every index"
    # channel index and label value differ by exactly one
    assert list(rco) == list(range(1, len(rco) + 1))


def test_step2_channel_count_is_eleven(step2_json):
    assert len(step2_json["regions_class_order"]) == 11
    assert len(_foreground_regions(step2_json)) == 11
    assert sorted(C.STEP2_CHANNELS) == list(range(11))


def test_step1_channel_count_is_nine(step1_json):
    """Step 1 has 9 channels, step 2 has 11. Confusing the two shifts everything."""
    assert len(step1_json["regions_class_order"]) == 9
    assert len(_foreground_regions(step1_json)) == 9


def test_table_names_match_dataset_json_in_order(step2_json):
    """Each row's 'true meaning' must be the dataset.json key for that channel."""
    fg = _foreground_regions(step2_json)
    for ch, (key, _value) in enumerate(fg):
        truth = C.STEP2_CHANNELS[ch][0]
        # rows read either "sacrum" or "vertebrae_O (odd vertebrae)"
        assert truth.split(" (")[0] == key, (
            "channel %d: table says %r, dataset.json says %r" % (ch, truth, key))


def test_table_class_values_match_regions_class_order(step2_json):
    """A union region decodes to the lowest value it covers, a leaf to its own."""
    fg = _foreground_regions(step2_json)
    rco = step2_json["regions_class_order"]
    for ch, (key, value) in enumerate(fg):
        expected = min(value) if isinstance(value, (list, tuple)) else value
        assert rco[ch] == expected, "channel %d (%s)" % (ch, key)


def test_named_channel_constants_match_dataset_json(step2_json):
    """CH_SACRUM etc must be the index dataset.json puts that label at."""
    index = {k: i for i, (k, _v) in enumerate(_foreground_regions(step2_json))}
    assert C.CH_DISC_UNION == index["disc"]
    assert C.CH_VERT_UNION == index["vertebrae"]
    assert C.CH_VERT_ODD == index["vertebrae_O"]
    assert C.CH_VERT_EVEN == index["vertebrae_E"]
    assert C.CH_SACRUM == index["sacrum"]
    assert C.CH_CANAL == index["canal"]
    assert C.CH_CORD == index["cord"]
    # and the specific numbers, so a reordered dataset.json is also caught
    assert (C.CH_VERT_ODD, C.CH_VERT_EVEN, C.CH_SACRUM, C.CH_CANAL, C.CH_CORD) == (
        6, 7, 8, 9, 10)


def test_step2_model_is_declared_mri(step2_json):
    """VerSe is CT. Out of distribution by construction, stated not fixed."""
    assert step2_json["channel_names"]["0"] == "MRI"


def test_printed_names_are_all_wrong(step2_json):
    """Every name the deployed json_generator.py prints disagrees with the truth.

    Pinning this stops anyone "correcting" the table towards the printed names.
    """
    fg = dict(_foreground_regions(step2_json))
    for ch, (truth, printed) in C.STEP2_CHANNELS.items():
        key = truth.split(" (")[0]
        assert key in fg
        assert printed != key, "channel %d: printed name %r is in fact correct" % (ch, printed)


# --------------------------------------------------------------------------
# 2. The retired mapping, documented as a property
# --------------------------------------------------------------------------

def test_retired_mapping_reads_sacrum_for_every_lumbar_level():
    """Variant (a) scored L1-L6 against the sacrum channel. That is the bug."""
    for lv in ("L1", "L2", "L3", "L4", "L5", "L6"):
        assert C.channel_region_retired(lv) == C.CH_SACRUM
    assert C.STEP2_CHANNELS[C.channel_region_retired("L3")][0] == "sacrum"


def test_retired_mapping_reads_canal_for_sacrum():
    ch = C.channel_region_retired("SACRUM")
    assert ch == C.CH_CANAL
    assert C.STEP2_CHANNELS[ch][0] == "canal"


def test_retired_mapping_cervical_and_thoracic_are_parity_accidents():
    """C* always reads odd and T* always reads even, so they agree with the
    correct answer only when the level's parity happens to match."""
    for lv in ("C1", "C2", "C7"):
        assert C.channel_region_retired(lv) == C.CH_VERT_ODD
    for lv in ("T1", "T2", "T12"):
        assert C.channel_region_retired(lv) == C.CH_VERT_EVEN
    # C1 is odd positioned so the retired mapping is right there
    assert C.channel_region_retired("C1") == C.channel_parity("C1")
    # C2 is even positioned so it is wrong
    assert C.channel_region_retired("C2") != C.channel_parity("C2")


def test_retired_mapping_accepts_the_vertebrae_prefix():
    assert C.channel_region_retired("vertebrae_L3") == C.CH_SACRUM
    assert C.channel_region_retired("L3") == C.CH_SACRUM


# --------------------------------------------------------------------------
# 3. channel_parity
# --------------------------------------------------------------------------

def _expected_parity_channel(ordinal: int) -> int:
    return C.CH_VERT_ODD if ordinal % 2 == 0 else C.CH_VERT_EVEN


@pytest.mark.parametrize("ordinal", list(range(0, 26)))
def test_parity_round_trips_for_explicit_ordinals(ordinal):
    assert C.channel_parity("C1", ordinal) == _expected_parity_channel(ordinal)
    assert C.channel_parity("T7", ordinal) == _expected_parity_channel(ordinal)


# A spine WITHOUT T13, which is the modal anatomy: 7 cervical, 12 thoracic,
# 5 lumbar, 24 presacral vertebrae.
MODAL_SPINE = (["C%d" % i for i in range(1, 8)]
               + ["T%d" % i for i in range(1, 13)]
               + ["L%d" % i for i in range(1, 6)])

# The full list channels.py declares, T13 and L6 included.
DECLARED_SEQUENCE = [lv for lv, _o in sorted(C.LEVEL_ORDINAL.items(),
                                             key=lambda kv: kv[1])
                     if lv != "SACRUM"]


def test_parity_alternates_across_the_declared_level_list():
    """Self consistency of the table: consecutive ordinals must alternate.

    TotalSpineSeg's step 2 labels vertebrae 7 (odd) and 8 (even) so that ADJACENT
    vertebrae differ. Upstream depends on it: _merge_vertebrae_with_same_label in
    totalspineseg/utils/iterative_label.py merges two consecutive components that
    carry the SAME odd/even value, so two neighbours sharing a channel is not a
    representable state.
    """
    seen = [C.channel_parity(lv) for lv in DECLARED_SEQUENCE]
    assert set(seen) == {C.CH_VERT_ODD, C.CH_VERT_EVEN}
    for lv, a, b in zip(DECLARED_SEQUENCE, seen, seen[1:]):
        assert a != b, "%s and the level below it share a channel" % lv


def test_parity_alternates_between_adjacent_levels_of_a_modal_spine():
    """FINDING: the name-derived fallback is out of phase for lumbar levels.

    LEVEL_ORDINAL inserts T13 between T12 and L1, so the canonical ordinal of L1
    is 20. In a spine with no T13, which is the overwhelming majority, L1 is the
    20th vertebra and its ordinal is 19. The fallback therefore returns the wrong
    parity channel for every lumbar level of a normal spine, and T12 and L1 come
    back on the same channel, which the model's alternation cannot produce.

    Left failing on purpose. The fix is in spinelab/confidence/channels.py, not
    here: either drop T13 from the canonical ordinal and treat it as an insertion,
    or refuse to answer without an explicit ordinal.
    """
    seen = [C.channel_parity(lv) for lv in MODAL_SPINE]
    collisions = [(MODAL_SPINE[i], MODAL_SPINE[i + 1])
                  for i in range(len(seen) - 1) if seen[i] == seen[i + 1]]
    assert not collisions, (
        "adjacent levels share a channel: %s" % collisions)


def _deployed_rule(name: str) -> int:
    """utils/confidence_calculator.py:get_vertebra_channel, verbatim in effect.

    Parity is taken from the NUMBER INSIDE THE REGION, so it restarts at C1, T1
    and L1 instead of running continuously down the column.
    """
    if name.upper().startswith("S"):
        return 8
    return 6 if int(name[1:]) % 2 == 1 else 7


def test_the_deployed_confidence_calculator_restarts_parity_at_each_region():
    """FINDING, and a correction to CLAUDE.md finding 2.

    The notes record that the live server's confidence_calculator.py "uses the
    CORRECT parity mapping". It does not. It derives odd/even from the number in
    the vertebra's own name, so C7 and T1 both come back as odd and land on the
    same channel. Two adjacent vertebrae cannot share a channel, so the deployed
    mapping is wrong from T1 downwards, not just for the lumbar spine.

    It is correct for the cervical levels only, where the region index and the
    column index coincide.
    """
    for lv in ("C1", "C2", "C3", "C4", "C5", "C6", "C7"):
        assert _deployed_rule(lv) == C.channel_parity(lv), lv

    assert _deployed_rule("C7") == _deployed_rule("T1"), (
        "if these differ the deployed rule is not the per region one we read")

    seen = [_deployed_rule(lv) for lv in MODAL_SPINE]
    collisions = [(MODAL_SPINE[i], MODAL_SPINE[i + 1])
                  for i in range(len(seen) - 1) if seen[i] == seen[i + 1]]
    assert collisions == [("C7", "T1")], collisions

    # and from T1 down it is inverted relative to continuous alternation
    continuous = {lv: (C.CH_VERT_ODD if i % 2 == 0 else C.CH_VERT_EVEN)
                  for i, lv in enumerate(MODAL_SPINE)}
    wrong = [lv for lv in MODAL_SPINE if _deployed_rule(lv) != continuous[lv]]
    assert wrong == MODAL_SPINE[7:], (
        "expected every level from T1 down to disagree, got %s" % wrong)


def test_parity_uses_canonical_ordinal_when_none_given():
    for lv, ordinal in C.LEVEL_ORDINAL.items():
        if lv == "SACRUM":
            continue
        assert C.channel_parity(lv) == _expected_parity_channel(ordinal)


def test_parity_handles_sacrum_and_ignores_its_ordinal():
    assert C.channel_parity("SACRUM") == C.CH_SACRUM
    assert C.channel_parity("sacrum") == C.CH_SACRUM
    assert C.channel_parity("vertebrae_sacrum") == C.CH_SACRUM
    for ordinal in (0, 1, 25, 99):
        assert C.channel_parity("SACRUM", ordinal) == C.CH_SACRUM


def test_parity_out_of_phase_when_ordinal_is_name_derived():
    """The documented hazard: if the topmost visible vertebra is not C1 the
    anatomical ordinal is out of phase with the model's alternation."""
    name_derived = C.channel_parity("T1")
    from_segmentation = C.channel_parity("T1", ordinal=0)
    assert name_derived != from_segmentation


def test_parity_rejects_an_unknown_level():
    with pytest.raises(ValueError):
        C.channel_parity("Q9")


def test_normalise():
    assert C.normalise("vertebrae_L3") == "L3"
    assert C.normalise(" l3 ") == "L3"
    assert C.normalise("vertebrae-C2") == "C2"
    assert C.normalise("sacrum") == "SACRUM"
    assert C.normalise("S") == "SACRUM"
    # S1 keeps its digit rather than collapsing to SACRUM
    assert C.normalise("S1") == "S1"


# --------------------------------------------------------------------------
# 4. mapping_free_scores, variant (c)
# --------------------------------------------------------------------------

N_CH = 11
N_VOX = 64


def _confident(channel: int = 6, peak: float = 0.98) -> np.ndarray:
    p = np.full((N_CH, N_VOX), (1.0 - peak) / (N_CH - 1), dtype=np.float64)
    p[channel, :] = peak
    return p


def _uniform() -> np.ndarray:
    return np.full((N_CH, N_VOX), 1.0 / N_CH, dtype=np.float64)


def test_scores_are_in_range_for_both_extremes():
    for p in (_confident(), _uniform()):
        s = C.mapping_free_scores(p)
        assert 0.0 <= s["margin"] <= 1.0
        assert 0.0 <= s["entropy_inv"] <= 1.0
        assert 0.0 <= s["top1"] <= 1.0
        assert 0.0 <= s["agree"] <= 1.0


def test_confident_beats_uniform_on_margin_and_entropy():
    conf = C.mapping_free_scores(_confident())
    unif = C.mapping_free_scores(_uniform())
    assert conf["margin"] > unif["margin"]
    assert conf["entropy_inv"] > unif["entropy_inv"]
    assert conf["top1"] > unif["top1"]


def test_uniform_distribution_scores_at_the_floor():
    s = C.mapping_free_scores(_uniform())
    assert s["margin"] == pytest.approx(0.0, abs=1e-12)
    assert s["entropy_inv"] == pytest.approx(0.0, abs=1e-9)
    assert s["top1"] == pytest.approx(1.0 / N_CH, abs=1e-12)


def test_confident_margin_is_near_the_peak_gap():
    peak = 0.98
    s = C.mapping_free_scores(_confident(peak=peak))
    assert s["margin"] == pytest.approx(peak - (1.0 - peak) / (N_CH - 1), abs=1e-9)
    assert s["modal_channel"] == 6
    assert s["agree"] == pytest.approx(1.0)


def test_scores_renormalise_unnormalised_input():
    """Softmax slices sampled from a mask need not sum to one after clipping."""
    a = C.mapping_free_scores(_uniform())
    b = C.mapping_free_scores(_uniform() * 7.0)
    for k in ("margin", "entropy_inv", "top1", "agree"):
        assert a[k] == pytest.approx(b[k], abs=1e-9)


def test_scores_need_no_channel_mapping_at_all():
    """The point of variant (c): the same array scores identically whichever
    vertebra it came from, so a name to channel mistake cannot happen."""
    p = _confident(channel=8)
    assert C.mapping_free_scores(p) == C.mapping_free_scores(p.copy())


def test_agree_falls_when_voxels_disagree():
    p = _confident(channel=6)
    p[:, : N_VOX // 2] = _confident(channel=7)[:, : N_VOX // 2]
    s = C.mapping_free_scores(p)
    assert s["agree"] == pytest.approx(0.5)


def test_scores_reject_wrong_shape():
    with pytest.raises(ValueError):
        C.mapping_free_scores(np.zeros((N_CH,)))
    with pytest.raises(ValueError):
        C.mapping_free_scores(np.zeros((2, N_CH, N_VOX)))


def test_scores_survive_exact_zeros():
    """A one hot slice must not produce nan through log(0)."""
    p = np.zeros((N_CH, 4), dtype=np.float64)
    p[3, :] = 1.0
    s = C.mapping_free_scores(p)
    assert all(np.isfinite(v) for k, v in s.items() if k != "modal_channel")
    assert s["margin"] == pytest.approx(1.0, abs=1e-9)
    assert s["modal_channel"] == 3


def test_describe_prints_one_row_per_channel():
    lines = C.describe().splitlines()
    assert len(lines) == len(C.STEP2_CHANNELS) + 2   # header plus rule
    body = lines[2:]
    for ch, (truth, printed) in C.STEP2_CHANNELS.items():
        assert body[ch].startswith("%2d " % ch)
        assert truth in body[ch]
        assert printed in body[ch]
