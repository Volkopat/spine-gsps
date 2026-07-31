"""Tests for spinelab.pipeline.torch_compat.

Three facts here are the ones that break inference when they drift:

  1. `folds` must default to (0,). Only fold_0 exists in the recovered model
     directories, and the deployed predict_nnunet.py defaults to (0,1,2,3,4) and
     fails outright.
  2. `use_mirroring` must default to False, because the trainer is
     nnUNetTrainer_DASegOrd0_NoMirroring.
  3. `trusted_load` must restore torch.load, including on an exception. A leaked
     monkeypatch would silently disable weights_only for the rest of the process.

None of these need a GPU or a checkpoint. Building a real predictor does, so
that is left to scripts/smoke_inference.py.
"""
from __future__ import annotations

import inspect

import pytest

torch = pytest.importorskip("torch", reason="torch not installed in this environment")

from spinelab.pipeline import torch_compat as TC  # noqa: E402


def test_load_predictor_defaults_to_fold_zero_only():
    sig = inspect.signature(TC.load_predictor)
    assert sig.parameters["folds"].default == (0,), (
        "folds default is %r, only fold_0 exists on disk"
        % (sig.parameters["folds"].default,))


def test_load_predictor_defaults_to_mirroring_off():
    sig = inspect.signature(TC.load_predictor)
    assert sig.parameters["use_mirroring"].default is False, (
        "the trainer is nnUNetTrainer_DASegOrd0_NoMirroring, mirroring must be off")


def test_load_predictor_other_defaults_are_the_documented_ones():
    sig = inspect.signature(TC.load_predictor)
    assert sig.parameters["checkpoint_name"].default == "checkpoint_final.pth"
    assert sig.parameters["device"].default == "cuda"
    assert sig.parameters["tile_step_size"].default == 0.5


def test_allow_numpy_globals_registers_the_numpy_reconstructors(monkeypatch):
    monkeypatch.setattr(TC, "_applied", False)
    added = TC.allow_numpy_globals()
    assert added, "nothing was added to the torch safe globals allowlist"
    # at least one multiarray scalar reconstructor, under either numpy path
    assert any(n.endswith("multiarray.scalar") for n in added), added
    assert "numpy.dtype" in added
    assert "numpy.float32" in added


def test_allow_numpy_globals_is_idempotent(monkeypatch):
    monkeypatch.setattr(TC, "_applied", False)
    first = TC.allow_numpy_globals()
    assert first
    assert TC.allow_numpy_globals() == []


def test_trusted_load_forces_weights_only_false_then_restores():
    seen = {}
    original = torch.load

    def fake_load(*a, **kw):
        seen.update(kw)
        return "loaded"

    torch.load = fake_load
    try:
        with TC.trusted_load():
            assert torch.load("x") == "loaded"
            assert seen["weights_only"] is False
        assert torch.load is fake_load, "trusted_load did not restore torch.load"
    finally:
        torch.load = original
    assert torch.load is original


def test_trusted_load_restores_even_when_the_body_raises():
    original = torch.load
    with pytest.raises(RuntimeError):
        with TC.trusted_load():
            raise RuntimeError("boom")
    assert torch.load is original


def test_trusted_load_does_not_override_an_explicit_argument_silently():
    """It DOES override, deliberately. Pinned so the behaviour is not a surprise."""
    seen = {}
    original = torch.load
    torch.load = lambda *a, **kw: seen.update(kw)
    try:
        with TC.trusted_load():
            torch.load("x", weights_only=True)
        assert seen["weights_only"] is False
    finally:
        torch.load = original


def test_torch_build_carries_the_gpu_architecture_this_machine_needs():
    """sm_120 for the RTX 5090 Laptop GPU. Skips on a build without CUDA."""
    if not hasattr(torch, "cuda") or not torch.cuda.is_available():
        pytest.skip("no CUDA device visible")
    archs = torch.cuda.get_arch_list()
    assert "sm_120" in archs, archs
    # sm_61 IS present, which is the correction recorded in CLAUDE.md: this build
    # did NOT drop Pascal, so a Tesla P40 is not excluded on architecture grounds.
    assert "sm_61" in archs, archs
