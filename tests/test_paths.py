"""Tests for spinelab.paths, the single source of truth for locations.

Two jobs here.

First, every external store either resolves or the test SKIPS with a message
naming what is missing. These stores are deliberately outside the repository and
are not committed anywhere, so a checkout on another machine has none of them.
A suite that goes red for that reason would be discarded, which is worse than
one that reports honestly what it could not check.

Second, the contamination table. SPIDER and spine-generic are in this project's
own training data, so using either as a held out evaluation set would invalidate
every number derived from it. That table is load bearing and is asserted here
rather than only described in prose.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from spinelab import paths


EXTERNAL_STORES = ("MODELS", "DATASETS", "RUNS", "VENDOR", "BASELINE")


def _store(name):
    p = getattr(paths, name)
    if not p.exists():
        pytest.skip("%s does not resolve on this machine: %s. Set SPINELAB_%s to "
                    "override." % (name, p, name))
    return p


# --------------------------------------------------------------------------
# 1. Resolution
# --------------------------------------------------------------------------

def test_repo_root_is_the_checkout_and_holds_src():
    assert paths.REPO.exists()
    assert (paths.REPO / "src" / "spinelab" / "paths.py").exists()
    assert (paths.REPO / "tests").exists()


def test_results_and_figures_are_inside_the_repo():
    assert paths.RESULTS == paths.REPO / "results"
    assert paths.FIGURES == paths.RESULTS / "figures"
    assert paths.RESULTS.exists()


@pytest.mark.parametrize("name", EXTERNAL_STORES)
def test_external_store_resolves_or_skips(name):
    p = _store(name)
    assert p.is_dir(), "%s is not a directory: %s" % (name, p)


@pytest.mark.parametrize("name", EXTERNAL_STORES)
def test_external_store_is_outside_the_repository(name):
    """Nothing large or clinical may sit inside a repo intended to be public."""
    p = getattr(paths, name).resolve()
    assert paths.REPO.resolve() not in p.parents
    assert p != paths.REPO.resolve()


def test_environment_variable_overrides_the_default(monkeypatch):
    """Every store goes through _p, so overriding one overrides all of them."""
    monkeypatch.setenv("SPINELAB_TESTSTORE", os.path.join("Z:", "override"))
    assert paths._p("SPINELAB_TESTSTORE", r"D:\default") == Path("Z:", "override")
    monkeypatch.delenv("SPINELAB_TESTSTORE")
    assert paths._p("SPINELAB_TESTSTORE", r"D:\default") == Path(r"D:\default")


@pytest.mark.parametrize("name", EXTERNAL_STORES)
def test_every_external_store_is_overridable(name):
    """The override is by an environment variable of the same name, prefixed."""
    src = Path(paths.__file__).read_text()
    assert '_p("SPINELAB_%s"' % name in src


def test_describe_lists_every_store_with_a_verdict():
    text = paths.describe()
    for name in ("REPO",) + EXTERNAL_STORES:
        assert name in text
    for line in text.splitlines():
        assert line.rstrip().endswith("ok") or line.rstrip().endswith("MISSING")


def test_require_raises_with_a_useful_message(tmp_path):
    with pytest.raises(FileNotFoundError) as e:
        paths.require(tmp_path / "absent", "the thing")
    assert "the thing" in str(e.value)
    assert paths.require(tmp_path, "tmp") == tmp_path


# --------------------------------------------------------------------------
# 2. Contamination. The genuinely load bearing table.
# --------------------------------------------------------------------------

def test_contaminated_contains_spider_and_spine_generic():
    assert "SPIDER" in paths.CONTAMINATED
    assert "spine-generic" in paths.CONTAMINATED


def test_contaminated_also_lists_the_upstream_training_sets():
    assert "whole-spine" in paths.CONTAMINATED
    assert "MRSpineSeg" in paths.CONTAMINATED
    assert len(paths.CONTAMINATED) == 4


def test_every_contaminated_entry_states_a_reason():
    for name, why in paths.CONTAMINATED.items():
        assert isinstance(why, str) and len(why) > 10, name


def test_no_clean_evaluation_set_is_a_contaminated_one():
    """The four exported evaluation paths must not name a contaminated dataset."""
    clean = {"TS_MRI": paths.TS_MRI, "TS_CT": paths.TS_CT,
             "VERSE19": paths.VERSE19, "VERSE20": paths.VERSE20}
    for var, p in clean.items():
        low = str(p).lower()
        for bad in paths.CONTAMINATED:
            assert bad.lower() not in low, "%s points at contaminated %s" % (var, bad)


def test_the_contamination_claim_is_backed_by_the_checkpoints_dataset_txt():
    """models/*/dataset.txt is the evidence. Skips if the model store is absent."""
    models = _store("MODELS")
    hits = {}
    for txt in sorted(models.glob("*/dataset.txt")):
        body = txt.read_text(errors="replace").lower()
        hits[txt.parent.name] = {
            "spider": body.count("spider"),
            "spine-generic": body.count("sub-multi"),
        }
    if not hits:
        pytest.skip("no models/*/dataset.txt present under %s" % models)
    assert any(v["spider"] > 0 for v in hits.values()), hits
    assert any(v["spine-generic"] > 0 for v in hits.values()), hits


def test_contaminated_names_are_not_reachable_as_dataset_attributes():
    """No module level path in paths.py may point at a contaminated dataset.

    Cheap structural guard: if someone adds `SPIDER = DATASETS / "spider"` to
    make an evaluation split, this fails before the number reaches a paper.
    """
    offenders = []
    for attr in dir(paths):
        if attr.startswith("_") or attr == "CONTAMINATED":
            continue
        val = getattr(paths, attr)
        if not isinstance(val, Path):
            continue
        low = str(val).lower()
        for bad in paths.CONTAMINATED:
            if bad.lower().replace("-", "") in low.replace("-", "").replace("_", ""):
                offenders.append("%s -> %s" % (attr, val))
    assert not offenders, offenders


# --------------------------------------------------------------------------
# 3. Checkpoint layout. Only fold_0 exists.
# --------------------------------------------------------------------------

def test_trainer_directory_names_are_the_ones_on_disk():
    assert paths.TRAINER_STEP == (
        "nnUNetTrainer_DASegOrd0_NoMirroring__nnUNetPlans_small__3d_fullres")
    assert paths.TRAINER_FULL == "nnUNetTrainer__nnUNetPlans__3d_fullres"
    assert paths.STEP1.name == paths.TRAINER_STEP
    assert paths.STEP2.name == paths.TRAINER_STEP
    assert paths.FULL.name == paths.TRAINER_FULL


def test_the_trainer_is_the_no_mirroring_variant():
    """Mirroring must be OFF at inference. The trainer name is the evidence."""
    assert "NoMirroring" in paths.TRAINER_STEP


@pytest.mark.parametrize("name", ("STEP1", "STEP2", "FULL"))
def test_checkpoint_folder_resolves_or_skips(name):
    _store("MODELS")
    p = getattr(paths, name)
    if not p.exists():
        pytest.skip("%s not present at %s" % (name, p))
    assert (p / "dataset.json").exists(), "no dataset.json in %s" % p
    assert (p / "plans.json").exists(), "no plans.json in %s" % p


@pytest.mark.parametrize("name", ("STEP1", "STEP2", "FULL"))
def test_only_fold_zero_exists(name):
    """The deployed predict_nnunet.py defaults to folds (0,1,2,3,4) and fails.

    Any predictor call in this repo must pass folds=(0,). Asserted against the
    directory listing rather than trusted from a comment.
    """
    _store("MODELS")
    p = getattr(paths, name)
    if not p.exists():
        pytest.skip("%s not present at %s" % (name, p))
    folds = sorted(d.name for d in p.iterdir() if d.is_dir() and d.name.startswith("fold_"))
    assert folds == ["fold_0"], "%s has folds %r" % (name, folds)
    assert (p / "fold_0" / "checkpoint_final.pth").exists()


def test_step1_and_step2_are_different_datasets():
    assert paths.STEP1.parent.name == "Dataset101_TotalSpineSeg_step1"
    assert paths.STEP2.parent.name == "Dataset102_TotalSpineSeg_step2"
    assert paths.FULL.parent.name == "Dataset103_TotalSpineSeg_full"


def test_verse_cohort_naming_convention_holds():
    """The cohort at datasets/verse_4skx2 must follow the naming the scripts glob.

    Deliberately asserts on COMPLETE triples only. The store is written by
    scripts/fetch_verse.py and can be mid-download, so a bare count comparison
    would be a race rather than a test.
    """
    d = _store("DATASETS") / "verse_4skx2"
    if not d.exists():
        pytest.skip("VerSe cohort not staged at %s" % d)

    def stems(pattern, suffix):
        return {p.name[: -len(suffix)] for p in d.glob(pattern)}

    masks = stems("*_seg-vert_msk.nii.gz", "_seg-vert_msk.nii.gz")
    imgs = stems("*_ct.nii.gz", "_ct.nii.gz")
    ctds = stems("*_seg-subreg_ctd.json", "_seg-subreg_ctd.json")
    if not masks:
        pytest.skip("no *_seg-vert_msk.nii.gz under %s yet" % d)

    complete = masks & imgs & ctds
    assert complete, ("no complete case in %s: %d masks, %d images, %d centroid "
                      "files, no overlap" % (d, len(masks), len(imgs), len(ctds)))
    # every complete case must carry all three files under one stem, which is what
    # scripts/verse_composition.py assumes when it pairs mask to centroid json
    for stem in sorted(complete):
        assert (d / (stem + "_ct.nii.gz")).exists()
        assert (d / (stem + "_seg-vert_msk.nii.gz")).exists()
        assert (d / (stem + "_seg-subreg_ctd.json")).exists()
