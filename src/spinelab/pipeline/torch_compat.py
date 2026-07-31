"""Bridge nnunetv2 2.4.2 to torch 2.6+ checkpoint loading.

torch 2.6 flipped the default of `torch.load(weights_only=...)` from False to
True. nnunetv2 2.4.2 predates that and calls torch.load without the argument, so
loading a checkpoint that pickles numpy scalars fails with:

    UnpicklingError: Unsupported global: GLOBAL numpy.core.multiarray.scalar

Two ways out. We prefer the narrow one: allowlist the specific numpy
reconstructors these checkpoints use, leaving the weights_only protection in
place for everything else. The broad fallback (weights_only=False) is scoped to a
context manager and used only if the allowlist is insufficient.

This is safe here specifically because the checkpoints are our own artifacts,
recovered from our own container image. Do not reuse this to load a checkpoint
from an untrusted source.
"""
from __future__ import annotations

import contextlib
import importlib

import torch

_ALLOWED_NAMES = [
    # numpy 1.x pickle paths, which is what the 2025-09-29 checkpoints carry
    ("numpy.core.multiarray", "scalar"),
    ("numpy.core.multiarray", "_reconstruct"),
    ("numpy", "dtype"),
    ("numpy", "ndarray"),
    # numpy 2.x private paths, in case a checkpoint was written under numpy 2
    ("numpy._core.multiarray", "scalar"),
    ("numpy._core.multiarray", "_reconstruct"),
]

_applied = False


def allow_numpy_globals() -> list[str]:
    """Add numpy reconstructors to torch's safe-globals allowlist. Idempotent."""
    global _applied
    added: list[str] = []
    if _applied:
        return added
    objs = []
    for mod_name, attr in _ALLOWED_NAMES:
        try:
            mod = importlib.import_module(mod_name)
            obj = getattr(mod, attr)
        except Exception:
            continue
        objs.append(obj)
        added.append("%s.%s" % (mod_name, attr))
    # numpy scalar dtypes get pickled individually by np.dtype instances
    try:
        import numpy as np

        for name in ("float64", "float32", "int64", "int32", "bool_", "uint8"):
            t = getattr(np, name, None)
            if t is not None:
                objs.append(t)
                added.append("numpy.%s" % name)
    except Exception:
        pass
    if objs and hasattr(torch.serialization, "add_safe_globals"):
        torch.serialization.add_safe_globals(objs)
        _applied = True
    return added


@contextlib.contextmanager
def trusted_load():
    """Force weights_only=False for the duration of the block.

    Broad fallback. Only for loading checkpoints we produced ourselves.
    """
    orig = torch.load

    def patched(*a, **kw):
        kw["weights_only"] = False
        return orig(*a, **kw)

    torch.load = patched
    try:
        yield
    finally:
        torch.load = orig


def load_predictor(model_folder, folds=(0,), checkpoint_name="checkpoint_final.pth",
                   device="cuda", tile_step_size=0.5, use_mirroring=False,
                   verbose=False, allow_tqdm=True):
    """Build an nnUNetPredictor, handling the torch 2.6 loading change.

    Mirroring defaults to OFF because the checkpoints' trainer is
    nnUNetTrainer_DASegOrd0_NoMirroring. Folds defaults to (0,) because only
    fold_0 exists in the recovered model directories, whereas the deployed
    predict_nnunet.py defaults to all five and would fail.
    """
    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor

    added = allow_numpy_globals()
    predictor = nnUNetPredictor(
        tile_step_size=tile_step_size,
        use_gaussian=True,
        use_mirroring=use_mirroring,
        perform_everything_on_device=True,
        device=torch.device(device),
        verbose=verbose,
        verbose_preprocessing=verbose,
        allow_tqdm=allow_tqdm,
    )
    try:
        predictor.initialize_from_trained_model_folder(
            str(model_folder), tuple(folds), checkpoint_name=checkpoint_name)
        return predictor, "safe_globals", added
    except Exception as e:
        first = "%s: %s" % (type(e).__name__, str(e)[:120])
        with trusted_load():
            predictor.initialize_from_trained_model_folder(
                str(model_folder), tuple(folds), checkpoint_name=checkpoint_name)
        return predictor, "trusted_load_fallback (%s)" % first, added
