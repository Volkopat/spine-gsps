"""The VerSe label convention, pinned.

VerSe mask label VALUES are the anatomical level, verbatim from the OSF readme:

    1-7 C1-C7 | 8-19 T1-T12 | 20-25 L1-L6 | 26 sacrum | 27 coccyx | 28 T13

Getting this off by one silently shifts every identification rate, so the map in
scripts/verse_composition.py is asserted here rather than trusted. T13 = 28 in
particular is load bearing: the level assignment algorithm cannot produce T13 at
all (results/level_assignment.md), so those cases must be identified before the
evaluation runs, not explained afterwards.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from spinelab import paths

SCRIPT = paths.REPO / "scripts" / "verse_composition.py"


@pytest.fixture(scope="module")
def vc():
    if not SCRIPT.exists():
        pytest.skip("scripts/verse_composition.py not present at %s" % SCRIPT)
    spec = importlib.util.spec_from_file_location("_verse_composition", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ImportError as e:
        pytest.skip("cannot import %s: %s" % (SCRIPT.name, e))
    return mod


def test_cervical_labels_are_one_to_seven(vc):
    for i in range(1, 8):
        assert vc.NAME[i] == "C%d" % i


def test_thoracic_labels_are_eight_to_nineteen(vc):
    assert vc.NAME[8] == "T1"
    assert vc.NAME[19] == "T12"
    for v in range(8, 20):
        assert vc.NAME[v] == "T%d" % (v - 7)


def test_lumbar_labels_are_twenty_to_twentyfive(vc):
    assert vc.NAME[20] == "L1"
    assert vc.NAME[25] == "L6"
    for v in range(20, 26):
        assert vc.NAME[v] == "L%d" % (v - 19)


def test_sacrum_coccyx_and_t13(vc):
    assert vc.NAME[26] == "sacrum"
    assert vc.NAME[27] == "coccyx"
    assert vc.NAME[28] == "T13", "T13 must be 28, it is the level that cannot be produced"


def test_the_map_covers_exactly_one_to_twentyeight(vc):
    assert sorted(vc.NAME) == list(range(1, 29))


def test_region_of_puts_t13_in_the_thoracic_region(vc):
    """28 sits after the lumbar range numerically but is a thoracic level."""
    assert vc.region_of(28) == "T"
    assert vc.region_of(8) == "T"
    assert vc.region_of(19) == "T"


def test_region_of_for_every_label(vc):
    expected = ({v: "C" for v in range(1, 8)}
                | {v: "T" for v in range(8, 20)}
                | {v: "L" for v in range(20, 26)}
                | {26: "S", 27: "S", 28: "T"})
    for v, want in expected.items():
        assert vc.region_of(v) == want, v


def test_landmark_discs_are_the_four_the_algorithm_anchors_on(vc):
    """Priority order is selected_disc_landmarks=[2, 5, 3, 4] in the deployed
    inference_logic.py, which maps to C2-C3, L5-S, C7-T1, T12-L1 in that order.

    Indexed rather than unpacked, so an extra field per row does not break this.
    """
    names = [row[0] for row in vc.LANDMARK_DISCS]
    assert names == ["C2-C3", "L5-S", "C7-T1", "T12-L1"]


def test_landmark_neighbour_labels_are_consistent_with_the_name_map(vc):
    for row in vc.LANDMARK_DISCS:
        name, a, b = row[0], row[1], row[2]
        upper, lower = name.split("-")
        assert vc.NAME[a].upper().startswith(upper.upper())
        if lower == "S":
            assert vc.NAME[b] == "sacrum"
        else:
            assert vc.NAME[b].upper() == lower.upper()
