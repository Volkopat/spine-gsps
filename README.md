# spine-gsps

Evaluation harness for *"Separating conformance from trustworthiness: an audit of the delivery path, and eight checks, for an AI result sent to a clinical archive."*

Every number in the article has a row in [`docs/CLAIMS.md`](docs/CLAIMS.md)
giving its status, the command that produces it, and its source file. That
ledger also records **thirty claims that were retired**, several of them
asserted confidently before measurement contradicted them; seven corrected when
peer review of the article found four of them wrong and three overstated; one,
every count from clinical material, withdrawn so that every result rests on
public data; and one, a description of the service as more deployed than it was,
corrected in a second round of review. It is the honest guide to how this
analysis fails.

## What this is

Three measurements on one DICOM service, built for clinical use and deployed
internally during its development, but never used in patient care:

1. **Conformance and delivery.** The service's own presentation-state emitter,
   run unmodified on 155 public VerSe cases, writes objects that all fail two
   independent validators on the same seven absent attributes. Two archives,
   Orthanc and dcm4chee, accept every one over C-STORE and return it over DICOMweb
   unaltered; one renderer (DCMTK) refuses them and a second (dcm4che) loads them.
   Nothing in the delivery path detected the defects.
2. **A nine-arm ablation of the quality signal.** Only the rule choosing which
   per-region sigmoid channel to read varies. All nine land between 0.427 and
   0.581 AUC on matched vertebrae; the rule that shipped carries no information,
   its case-clustered interval containing 0.5. The revision adds the predictions
   the benchmark cannot score, model-agnostic reference checks, permutation nulls
   within case and level, and the flag's predictive values, scored from the
   service's own emitter and from a reimplementation, with the two reconciled.
3. **The geometric consistency check.** Specified as leave-one-out, implemented
   in sample on its normal path, so the spline absorbs the displacement it
   exists to detect; and the specified leave-one-out residual does not repair it.

## Running it

```
python -m spinelab.paths                        # check every store resolves
python -m pytest tests -q                       # the factual constraints
python -m spinelab.confidence.channels          # channel table vs the checkpoints
python -m spinelab.gsps.validate <dir>          # dciodvfy over a DICOM directory
python -m spinelab.eval.verse --self-check      # the scorer against known answers
python -m spinelab.outliers.spline --validate   # the synthetic evaluation
python scripts/e1_ablation.py --run-dir <run>   # ablation, ceilings, null
python scripts/rev1_build.py --run-dir <run> # all 2241 predictions, positive control
python scripts/rev1_stats.py                 # unmatched, references, the flag, selection
python scripts/rev1_nulls.py                 # nulls within case and level, held out
python scripts/rev1_synthetic.py             # ROC and PR for both estimators
python scripts/rev1_archives.py ...          # two archives, see scripts/second_archive
python scripts/rev1_second_renderer.py ...   # dcm4che dcm2jpg
python scripts/rev3_emitter_flag.py --work <run>  # the emitter's own flag vs ground truth
python scripts/make_figures.py                  # every figure, from results/*.json
```

Pins are frozen in `env/requirements.lock`. `nnunetv2==2.4.2` must be installed
explicitly: current `totalspineseg` no longer depends on it, and without it the
checkpoints will not deserialise.

**No metric in the article is computed by code written for the purpose of
computing that metric.** Conformance is scored by `dciodvfy` (dicom3tools).
Vertebral identification is scored by the VerSe organisers' own
`eval_utilities.py`, vendored rather than reimplemented.

## What is not here, and why

- **The clinical material.** Earlier versions of the article reported counts
  from presentation states the service produced on clinical examinations during
  its development. The
  revised article withdraws every one of those counts and rests every result on
  public data: the container findings are reproduced by running the service's own
  emitter, unmodified, on 155 public VerSe cases (`scripts/rev2_deployed_on_public.py`,
  `scripts/rev2_measure_deployed_public.py`, `results/rev2_deployed_public.json`).
  The clinical objects, the cohort they came from and the per-attribute validator
  records over them are not here. Write-ups from earlier versions that report on
  them remain in `results/` as the historical audit record and are not cited by the
  revised article.
- **The service's emitter.** The service's own presentation-state emitter belongs
  to the company that developed the service and is not redistributed;
  `src/spinelab/outliers/spline.py` reimplements its flag rule. Its SHA-256 is
  recorded in the run's provenance, and the 155
  presentation states it wrote on public data are attached to this release as an
  archive, under the licence of the data they derive from.
- **The model checkpoints.** They are the openly released upstream TotalSpineSeg
  weights, obtainable from release r20241005 at
  github.com/neuropoly/totalspineseg. They were not trained here.
- **The public datasets.** VerSe 2019 and 2020, 202 cases, by anonymous download
  from OSF (osf.io/nqjyw, osf.io/t98fz) under CC BY-SA 4.0.

## Licence

MIT, see `LICENSE`. The vendored VerSe evaluation code carries its own.
