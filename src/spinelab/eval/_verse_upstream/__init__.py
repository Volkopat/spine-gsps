"""Unmodified vendored copy of the VerSe challenge organisers' own utilities.

Source      github.com/anjany/verse, branch main, files utils/eval_utilities.py,
            utils/data_utilities.py and LICENSE
Authors     eval_utilities.py: Anjany Sekuboyina
            data_utilities.py: Maximilian T. Loeffler, Malek El Husseini
Licence     MIT, Copyright (c) 2020 Anjany Kumar Sekuboyina. Full text in LICENSE
            next to this file.
Fetched     2026-07-30 from the raw.githubusercontent.com URLs.

The two .py files are BYTE IDENTICAL to upstream. Verified by sha256:

    eval_utilities.py  f4ba9ba660a2d6b33cffe71bb5a30fdc480c38a2e4e2e2c1733b47cc95b1bda2
    data_utilities.py  c79ce1bf8bd5319d80c64106a5bdbfc479ab88c54b8d4b7eae6e06a6e5cff363
    LICENSE            93610521a5b70090161b753ce9cade81f22629d7cf662836d41b025e879d4863

Do not edit them. The whole point of scoring with the benchmark authors' code is
that the code is theirs. If upstream changes, re-fetch and update the hashes.

Two compatibility notes, both handled here rather than by patching their files.

1. data_utilities.py opens with `from numpy.core.numeric import NaN`. numpy 2.0
   removed that name, so the import raises ImportError on numpy 2.2.6. The name
   is never used anywhere in the module body, so we inject it before importing.
2. eval_utilities.compute_dice calls `np.asarray(x).astype(np.bool)`. numpy 1.24
   removed `np.bool` and numpy 2.0 restored it as an alias of np.bool_, so their
   code runs unmodified on numpy 2.2.6 but would fail on 1.24 through 1.26. We
   check rather than let it fail deep inside their function.
"""
from __future__ import annotations

import numpy as _np
import numpy.core.numeric as _npnum

if not hasattr(_npnum, "NaN"):
    # See note 1 above. Injected so the vendored file can stay byte identical.
    _npnum.NaN = float("nan")

if not hasattr(_np, "bool"):
    raise ImportError(
        "numpy %s has no np.bool, which the vendored VerSe compute_dice needs. "
        "numpy 1.24 through 1.26 removed it, 2.0 restored it. This project pins "
        "numpy 2.2.6." % _np.__version__)

UPSTREAM = "github.com/anjany/verse"
SHA256 = {
    "eval_utilities.py":
        "f4ba9ba660a2d6b33cffe71bb5a30fdc480c38a2e4e2e2c1733b47cc95b1bda2",
    "data_utilities.py":
        "c79ce1bf8bd5319d80c64106a5bdbfc479ab88c54b8d4b7eae6e06a6e5cff363",
    "LICENSE":
        "93610521a5b70090161b753ce9cade81f22629d7cf662836d41b025e879d4863",
}
