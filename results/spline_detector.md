# The spline outlier detector: what it is, and what it detects

Measured 2026-07-30. Code: `src/spinelab/outliers/spline.py`.
Reproduce with, from the repo root:

```
$env:PYTHONPATH="<path>\spine-gsps\src"
& C:\Users\dekay\miniconda3\envs\spinelab\python.exe -m spinelab.outliers.spline --selftest
& C:\Users\dekay\miniconda3\envs\spinelab\python.exe -m spinelab.outliers.spline --validate --seeds 12 --json <path>\runs\spline_detector\synthetic.json
```

Runtime 94 to 97 s over three runs, CPU only, no GPU, no clinical data, no
network. Output verified byte identical across two separate processes, so the
seeding is reproducible. numpy 2.2.6, scipy 1.15.3, Python 3.10.20.

**Every number below Section 2 is SYNTHETIC.** Read Section 6 before quoting any
of it. Numbers in Sections 1 and 2 are read from the deployed source and from the
logs it wrote.

## 1. What the deployed algorithm actually is

Read from `$BASELINE\test_api\generate_gsps_4.py` lines 304-413 and 838-846, the
file that wrote the 38 shipped GSPS objects. Full quotations are in the module
docstring of `spline.py`; the summary:

| aspect | what it is |
|---|---|
| fitted object | two independent `UnivariateSpline`, x(t) and y(t), not one curve |
| independent variable | normalised cumulative chord length through the centroids, taken in anatomical NAME order |
| points | midpoint of the bbox corner pair, in IMAGE PIXELS of the middle sagittal slice |
| degree | `k = min(3, n-1)`, so always 3, and the function returns None for n < 4 |
| smoothing | `s = n * 0.5`, in px squared |
| regions | Cervical C1-C7, Thoracic T1-T12, Lumbar L1-L6. Sacrum and T13 are in no region and are silently dropped |
| residual, region with n >= 4 | IN SAMPLE minimum distance to that region's own spline, over 1000 samples of t. Not leave one out, despite the docstring |
| residual, region with n = 1..3 | leave one out distance to a GLOBAL spline that crosses region boundaries |
| standardisation | one pooled mean and `np.std` (ddof=0) over every residual in the study, std floored at 0.1 px |
| flag | one tailed `z > 1.5` |
| penalty | `max(0.3, 1 - (z - 1.5) * 0.4)`, multiplied into the confidence, and red is set exactly when this fired |

Two structural consequences follow from the table without any experiment.

**The detector measures displacement NORMAL to the column, but a mislabel is a
displacement ALONG it.** A mislabelled name lands on a neighbouring vertebral
centroid, which lies on the same smooth curve. The residual is by construction
insensitive to it.

Two smaller behaviours, both verified by `selftest()`:

- **Sacrum and T13 can never be flagged.** They are in none of the three region
  lists, so they are dropped before any fit and receive no entry in the returned
  multiplier dictionary. A study with fewer than 4 vertebrae returns an empty
  dictionary and no QA at all.
- **A duplicated centroid is fitted, not skipped.** Measured on scipy 1.15.3,
  `UnivariateSpline` needs only non decreasing x when s > 0, so two coincident
  consecutive centroids, which is what a merged segmentation component produces,
  still fit. Only an entirely coincident set returns None. This is worth
  recording because the opposite is easy to assume from the bare `except` in
  `fit_parametric_spline`.

**The trigger scale is set by a constant, not by anatomy.** `s` bounds the sum of
squared residuals, so `s = 0.5n` caps the per axis RMS residual at
sqrt(0.5) = 0.707 px for every n. Measured on the synthetic population: mean RMS
per axis 0.227 px in x and 0.248 px in y noiseless, 0.497 px and 0.310 px with
0.5 mm centroid noise, maximum 0.707 px in both, exactly the bound. Because the
bound is in pixels, the detector's physical sensitivity depends on
`PixelSpacing`, which in the shipped studies ranges 0.293 to 0.352 mm.

## 2. Corrections to CLAUDE.md finding 5

Two parts of the recorded finding are wrong, and correcting them matters because
they point at different files.

**`generate_gsps_4.py` DOES guard `std_dist`.** Line 400 is
`if std_dist < 0.1: std_dist = 0.1`. Its own log,
`$BASELINE\test_api\gsps_generation.log`, has 130 penalty lines and the largest z
in it is **3.90**, consistent with the algebraic maximum of a ddof=0 z score,
which is sqrt(n-1), or 4.12 for n = 18. Derivation and a numerical check are in
`spline.py`, `selftest()`.

**The z score of 651.46 is from a different file.** It is in
`refined_labels_generation.log`, written by
`debug/refinement/generate_refined_labels_10.py`. Its small region path,
lines 383-394, standardises the test vertebra's residual against the residuals of
the OTHER vertebrae only, so the point is excluded from its own mean and standard
deviation and the sqrt(n-1) bound no longer applies. Its guard is
`if std_dist > 1e-6`, effectively none. The matching log line, verbatim:

```
Global spline check T12: dist=81.9px, mean=0.2px, std=0.1px, z-score=651.46
```

So the unbounded z is not a missing floor, it is a leave one out standardisation
set. Both defects are real. They are in different files, and the one that shipped
the GSPS objects is the bounded one.

Other tallies read from the shipped logs while establishing the above, all
labelled as log tallies rather than per study rates because
`gsps_generation.log` holds more than one run (109 "Extracted confidence" lines,
71 "Using middle slice" lines):

- 130 penalty events over 1230 vertebrae summed from the log, 10.6 percent.
  CLAUDE.md's 11.1 percent over the 38 shipped studies remains the figure to
  quote.
- Per level penalty counts: C5 18, T11 22, T2 17, L3 17, C6 12, L1 9, T10 8,
  T3 7, L2 6, T9 5, T12 4, T1 2, T6 1, T7 1, T8 1, and **zero** for C1, C2, C3,
  C4, C7, T4, T5, L4, L5, L6.
- `refined_labels_generation.log`, regional path trigger distances, n = 260:
  min 0.0, p25 1.4, median 1.5, p75 1.6, max 2.0 px. At the measured
  `PixelSpacing` of 0.293 to 0.352 mm that median is 0.44 to 0.53 mm.
- `PixelSpacing` read from 400 shipped DICOM in `test_api/refined_gsps_1`:
  0.2928 to 0.3515 mm, most common 0.2928.

## 3. The synthetic experiment

`_true_chain` builds a vertebral centroid chain from per level centroid spacings
(17 mm cervical, 19 to 27 mm thoracic, 31 to 35 mm lumbar) with the sagittal
profile `x = A cos(2 pi s)`, s being fractional position down the column. The
function is analytic and infinitely differentiable, so **any residual the
detector reports on it is a property of the detector, not of the anatomy**.

Population: 4 coverages (full C1-L5, cervical C1-T4, thoracolumbar T4-L5,
lumbar T11-L5) x 3 curvature amplitudes (12, 22, 32 mm) x 3 pixel spacings
(0.293, 0.330, 0.352 mm, the measured values) x 12 seeds = **432 studies,
6156 vertebrae**. Run twice, noiseless and with isotropic Gaussian centroid
noise of 0.5 mm, which is a plausible segmentation centroid jitter.

Four decision rules compared:

| rule | score | std floor | mm guard |
|---|---|---|---|
| deployed | in sample pooled z | 0.1 px | none |
| guarded | in sample pooled z | 1.0 px | 3.0 mm |
| loo raw | leave one out pooled z | 1.0 px | none |
| loo | leave one out pooled z | 1.0 px | 3.0 mm |

Injections, all with known ground truth:

- **single level shift**, one missed level at the middle of the visible column,
  propagating caudally, which is how an iterative labeller fails.
- **adjacent swap**, two neighbouring labels exchanged.
- **whole column off by one**, the classic landmark anchor failure.
- **lateral offset 10 mm**, a POSITIVE CONTROL. This is not a mislabel, it is a
  centroid pushed off the curve, the only error class a distance to curve
  detector can see in principle. It is included so a zero detection rate on the
  three mislabels cannot be blamed on a broken harness.

## 4. Results

### 4.1 False positives on chains with no error at all, 432 studies, 6156 vertebrae

Every flag in this table is a false positive by construction.

| rule | noise | per vertebra | at region endpoints | in region interior | studies with >= 1 flag |
|---|---|---|---|---|---|
| deployed | none | 7.4% (456/6156) | 2.5% (48/1944) | 9.7% (408/4212) | 91.7% (396/432) |
| deployed | 0.5 mm | **10.9% (671/6156)** | 2.2% (43/1944) | 14.9% (628/4212) | **97.0% (419/432)** |
| guarded | 0.5 mm | 0.0% (0/6156) | 0.0% | 0.0% | 0.0% (0/432) |
| loo raw | 0.5 mm | 14.4% (827/5724) | **47.9% (827/1728)** | **0.0% (0/3996)** | 99.1% (428/432) |
| loo | 0.5 mm | 14.4% (827/5724) | 47.9% (827/1728) | 0.0% (0/3996) | 99.1% (428/432) |

**The deployed clinical flag rate is fully explained by an error free spine.** A
synthetic column with every label correct, plus 0.5 mm of centroid noise,
produces 10.9 percent of vertebrae flagged and 97.0 percent of studies carrying
at least one flag. The deployed system measured 11.1 percent of vertebrae and
37 of 38 studies, which is 97.4 percent. The agreement is to within the
resolution of either measurement. Nothing about the clinical flag rate requires
any labelling error to be present.

The `loo` denominator is 5724 rather than 6156 because a leave one out refit is
impossible in a region with exactly 4 levels present, so 432 vertebrae receive
no score at all under that rule.

### 4.2 The endpoint leverage effect, which runs the OPPOSITE way to the prediction

CLAUDE.md predicts "leave one out residuals on a per region spline have highest
leverage at region endpoints, which predicts the strongly patterned flag rate".
The leverage mechanism is real, but it applies to the wrong residual and
therefore predicts the wrong sign.

False positive rate by depth from the nearer end of the vertebra's own region,
0.5 mm noise:

| depth from region end | deployed (in sample) | loo raw (leave one out) |
|---|---|---|
| 0, the endpoint | 2.2% (43/1944) | **47.9% (827/1728)** |
| 1 | 8.0% (147/1836) | 0.0% (0/1620) |
| 2 | 15.8% (188/1188) | 0.0% (0/1188) |
| 3 | 24.7% (160/648) | 0.0% (0/648) |
| 4 | **26.9% (87/324)** | 0.0% (0/324) |
| 5 | 21.3% (46/216) | 0.0% (0/216) |

A high leverage point pulls the fit toward itself, so its IN SAMPLE residual is
systematically SMALL. The deployed regional path uses in sample residuals, so it
UNDER flags endpoints by a factor of 12 and OVER flags the region centre. Only
when the point is left out does leverage inflate its residual, and then it does
so violently: the leave one out residual p95 is 104 px, which is 34 mm at
0.33 mm/px, because the spline is extrapolating past the end of its parameter
interval.

The leverage prediction in CLAUDE.md is therefore correct as physics but is
attached to the wrong file. It describes the small region path of
`generate_refined_labels_10.py`, which genuinely is leave one out, and not the
regional path of `generate_gsps_4.py` that produced the shipped flags.

The clinically observed per level pattern is better explained by region size.
False positive rate by number of levels present in the region, deployed rule,
0.5 mm noise:

| levels present in region | false positive rate |
|---|---|
| 3 (global leave one out path) | 17.0% (55/324) |
| 4 | 0.0% (0/432) |
| 5 | 4.1% (66/1620) |
| 7 | 14.1% (213/1512) |
| 9 | 15.3% (149/972) |
| 12 | 14.5% (188/1296) |

The 0.0 percent at n = 4 is a hard structural fact, not noise: with n = 4 and
k = 3 the cubic spline has exactly enough degrees of freedom to interpolate, so
the residual collapses. Measured on the 0.5 mm noise population, in sample
residual in regions with exactly 4 levels present: **mean 0.027 px, max
0.131 px**, against mean 0.552 px, max 1.928 px everywhere else, n = 432 and
5724. The pooled z for such a vertebra can then never reach 1.5. So a study whose
thoracic coverage happens to be exactly 4 levels receives no QA on those levels
whatsoever, while the same anatomy in a 12 level region is flagged 14.5 percent of
the time. The leave one out rules cannot score those vertebrae either, for the
different reason that removing one leaves 3 points and the fit refuses n < 4.

### 4.3 Detection of known mislabels, paired against the same studies before injection

432 studies per row, 0.5 mm centroid noise. The bracketed number is the paired
control: the same rate computed on the identical study with no error injected.
**Equal values mean zero discrimination.**

| rule | injection | site flagged (control) | any bad level flagged (control) |
|---|---|---|---|
| deployed | single level shift | 5.1% (22.7%) | 21.8% (39.4%) |
| deployed | adjacent swap | 11.3% (22.7%) | 34.0% (29.6%) |
| deployed | whole column off by one | 0.0% (0.0%) | **97.0% (97.0%)** |
| deployed | lateral 10 mm, control | 23.1% (22.7%) | 23.1% (22.7%) |
| guarded | all four | 0.0% (0.0%) | 0.0% (0.0%) |
| loo raw | single level shift | 0.0% (0.0%) | 75.0% (69.0%) |
| loo raw | adjacent swap | **13.7% (0.0%)** | 13.7% (19.0%) |
| loo raw | whole column off by one | 46.8% (23.4%) | 75.0% (75.0%) |
| loo raw | lateral 10 mm, control | 0.0% (0.0%) | 0.0% (0.0%) |

Reading:

- **Whole column off by one: 97.0 percent against a 97.0 percent control.** The
  detector fires on nearly every study whether or not the whole column is
  mislabelled. This is exactly zero information. It is also the expected result:
  an off by one shift leaves the SET of centroid positions unchanged apart from
  dropping one end, so the geometry the detector sees is the geometry of a
  correct study.
- **Single level shift and adjacent swap: the site is flagged LESS often than a
  random correct vertebra.** 5.1 percent and 11.3 percent against a 22.7 percent
  control. Negative discrimination.
- **The positive control also fails under the deployed rule**, 23.1 percent
  against a 22.7 percent control. A 10 mm off curve displacement, which is 30 px,
  is not detected. Section 4.4 explains why.
- The two cells with a positive margin at this threshold are both `loo raw`: the
  adjacent swap, 13.7 percent against a 0.0 percent control, and the single level
  shift, 75.0 percent against a 69.0 percent control. Both come with a
  14.4 percent per vertebra false positive rate on error free chains. Note the
  paired control for a row uses only the perturbed level names, which is why
  69.0 percent here and 99.1 percent for the whole study in Section 4.1 are both
  correct.

### 4.4 Masking: the reported residual does not grow with the true error

One centroid is pushed a known distance off the curve. Median over 144 studies
spanning all coverages and spacings. All distances in mm.

| true off curve displacement | in sample residual | leave one out residual | neighbour residual | detected, deployed | detected, guarded | detected, loo |
|---|---|---|---|---|---|---|
| 0.0 | 0.212 | 0.553 | 0.132 | 21.5% | 0.0% | 0.0% |
| 0.5 | 0.247 | 0.818 | 0.135 | 24.3% | 0.0% | 0.0% |
| 1.0 | 0.265 | 1.171 | 0.158 | 27.8% | 0.0% | 0.0% |
| 2.0 | 0.286 | 1.970 | 0.221 | 26.4% | 0.0% | 0.0% |
| 5.0 | 0.290 | 4.923 | 0.388 | 23.6% | 0.0% | 0.0% |
| 10.0 | 0.239 | 9.903 | 0.396 | 22.9% | 0.0% | 0.0% |
| 20.0 | 0.235 | 19.843 | 0.359 | **3.5%** | 0.0% | 0.0% |
| 40.0 | 0.153 | 39.532 | 0.310 | **2.1%** | 0.0% | 75.0% |
| 80.0 | 0.118 | 78.553 | 0.192 | 7.6% | 0.0% | 100.0% |

This is the mechanism behind every other table.

**The in sample residual is flat, and then falls.** At a true displacement of
80 mm the reported residual is 0.118 mm, LOWER than the 0.212 mm reported when
nothing is wrong. `UnivariateSpline` inserts knots until the sum of squared
residuals falls below `s = 0.5n`, so it is forced to bend through the outlier.
The larger the error, the better the fit hides it. Detection under the deployed
rule is flat at 21 to 28 percent from 0 to 10 mm, which is just the base false
positive rate, and then collapses to 2 to 4 percent in the 20 to 40 mm range,
which is precisely the range a real single level mislabel occupies.

**The leave one out residual tracks the truth exactly**, 9.903 mm reported for a
10.0 mm displacement. So the geometric information is recoverable. It is the in
sample fit, not the geometry, that destroys it.

**But the leave one out z still does not detect it**, 0.0 percent at 10 mm,
because the pooled standardisation includes the region endpoint leave one out
residuals, which reach 34 mm from extrapolation alone. A genuine 10 mm error is
not an outlier relative to that. Detection only appears at 40 mm, where the real
error finally exceeds the extrapolation noise.

### 4.5 Z threshold sweep, 1.0 to 4.0

Deployed rule, in sample z, std floor 0.1 px, no mm guard. 432 clean studies for
the false positive columns, 432 injected studies per detection column. Detection
is the study level rate of flagging any perturbed level.

| z | FP per vertebra | FP per study | single level shift | adjacent swap | whole column off by one | lateral 10 mm control |
|---|---|---|---|---|---|---|
| 1.00 | 18.7% | 100.0% | 33.6% | 47.5% | 100.0% | 25.2% |
| 1.25 | 14.8% | 100.0% | 27.8% | 42.1% | 99.8% | 24.8% |
| **1.50** | **10.9%** | **97.0%** | **21.8%** | **34.0%** | **97.0%** | **23.1%** |
| 1.75 | 7.5% | 85.2% | 16.9% | 23.1% | 82.9% | 14.4% |
| 2.00 | 4.4% | 56.9% | 11.6% | 13.0% | 60.9% | 5.3% |
| 2.25 | 2.1% | 29.4% | 5.1% | 5.1% | 31.9% | 1.6% |
| 2.50 | 0.8% | 11.1% | 1.9% | 1.6% | 15.3% | 0.5% |
| 2.75 | 0.2% | 3.2% | 0.2% | 1.2% | 5.3% | 0.0% |
| 3.00 | 0.0% | 0.5% | 0.0% | 0.2% | 0.7% | 0.0% |
| 3.25 | 0.0% | 0.2% | 0.0% | 0.0% | 0.5% | 0.0% |
| 3.50 | 0.0% | 0.0% | 0.0% | 0.0% | 0.2% | 0.0% |
| 3.75 | 0.0% | 0.0% | 0.0% | 0.0% | 0.2% | 0.0% |
| 4.00 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |

Leave one out z, std floor 1.0 px:

| z | FP per vertebra | FP per study | single level shift | adjacent swap | whole column off by one | lateral 10 mm control |
|---|---|---|---|---|---|---|
| 1.00 | 22.9% | 100.0% | 75.0% | 50.0% | 100.0% | 0.0% |
| 1.25 | 19.0% | 100.0% | 75.0% | 49.1% | 100.0% | 0.0% |
| 1.50 | 14.4% | 99.1% | 75.0% | 13.7% | 75.0% | 0.0% |
| 1.75 | 9.3% | 50.2% | 60.2% | 0.0% | 54.4% | 0.0% |
| 2.00 | 4.4% | 32.6% | 49.8% | 0.0% | 49.8% | 0.0% |
| 2.25 | 3.7% | 25.0% | 25.7% | 0.0% | 25.0% | 0.0% |
| 2.50 | 1.1% | 14.1% | 25.0% | 0.0% | 25.0% | 0.0% |
| 2.75 | 0.0% | 0.0% | 13.4% | 0.0% | 8.8% | 0.0% |
| 3.00 to 4.00 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |

**Verdict on z = 1.5: refuted, and not rescuable by any other threshold in the
range.** Measured margins over all 13 thresholds, detection minus study level
false positive rate:

| injection, deployed rule | best margin over the 13 thresholds |
|---|---|
| single level shift | **+0.0 pp**, never above the false positive rate |
| adjacent swap | **+0.0 pp**, never above the false positive rate |
| lateral 10 mm control | **+0.0 pp**, never above the false positive rate |
| whole column off by one | +4.2 pp, at z = 2.50, where detection is 15.3% and the false positive rate is 11.1% |

So for three of the four injections the operating curve never rises above the
chance diagonal at any threshold, and for the fourth the best margin is
4.2 percentage points. Raising z does not trade sensitivity for specificity here,
it turns the detector off: by z = 3.00 both columns are at zero.

Leave one out is not a fix, but unlike the deployed rule it is not literally
uninformative. Its best margin on a single level shift is **+17.1 pp at
z = 2.00**, 49.8 percent detection against a 32.6 percent study level false
positive rate. That is real but weak, and it carries a confound: the single level
shift injection also removes one level from the column, which changes region
sizes, and Section 4.2 shows region size alone moves the false positive rate by a
factor of three. On the adjacent swap, which has no such confound, the best margin
over all 13 thresholds is +0.0 pp.

### 4.6 The two guards, quantified

The guards are in the module because they are the right shape of fix, but the
measurement shows they cannot rescue this residual and it is more honest to say
so than to ship them as a repair.

**The 1.0 px std floor alone reduces the deployed false positive rate from
10.9 percent to 0.0 percent.** Not one vertebra in 6156 achieves z > 1.5 once the
standard deviation cannot fall below 1.0 px. The reason is in Section 4.1: the
entire in sample residual distribution has median 0.401 px and p95 1.320 px, so
`residual - mean` never reaches 1.5 px. The deployed 0.1 px floor is ten times
smaller than the residual distribution it is supposed to regularise, and smaller
than the 0.030 to 0.057 px discretisation bias of the residual itself.

**The 3.0 mm absolute guard is never the binding constraint.** Under the guarded
rule the z test already rejects everything, so the mm guard blocks nothing
(z passed 0 times). Under the leave one out rules, 827 vertebrae pass z > 1.5 and
the mm guard blocks 0 of them, because a region endpoint leave one out residual
is already tens of millimetres. The guard is correct in principle, a mislabel
detector must not fire on sub millimetre deviations, and it is retained and
configurable, but on this residual it is redundant.

Two further numerical facts worth recording:

- **Discretisation.** The residual is a minimum over 1000 samples of t. Measured
  against a 200000 sample reference, the 1000 sample estimate carries a positive
  bias of mean 0.046 px, max 0.349 px on noiseless chains, which is
  **25.3 percent of the median residual**. With 0.5 mm noise it is 0.030 px mean,
  7.6 percent of the median. So a quarter of the quantity being standardised on
  clean data is numerical error in the search for the minimum.
- **Convergence.** 0 of 123 sampled regional fits produced a scipy warning about
  the requested smoothing not being reached, so the `s = 0.5n` target is
  attainable and the fits are converging. This was checked because such warnings
  do appear on some configurations and would be invisible under gunicorn.

## 5. What this means for the paper and for E2

1. **The flag and the confidence must be separated before either can be
   evaluated.** `fit_instrumented` does this. It returns, per vertebra, the
   residual in px and mm, the leave one out residual in px and mm, three
   standardised scores, the region, the index within the region, whether the
   vertebra is a region endpoint, and the n used for standardisation, with no
   field referring to confidence at all. `selftest()` asserts that no field name
   contains "conf", "penal" or "mult".
2. **`fit_deployed` reproduces current behaviour** for the ablation baseline.
   `selftest()` cross checks all 24 regional residuals and z scores of a full
   column against `deployed_trace()` to 1e-9 and 1e-6.
3. **The red colour in the 38 shipped GSPS objects should be described as a
   geometric artefact, not a quality signal.** The synthetic measurement
   reproduces the deployed flag rate on data with zero labelling errors, and in
   the deployed rule no threshold in 1.0 to 4.0 gives detection above the false
   positive rate on the two unconfounded mislabel classes.
4. **A replacement QA statistic should be tangential, not normal.** The mislabel
   classes that matter all displace a label ALONG the column. The natural
   statistics are the inter centroid spacing sequence, its ratio to the expected
   per level spacing, and the count of levels between anchor landmarks. None of
   these is a distance to a fitted curve. This is a design consequence of the
   measurement, not itself a measured result.
5. **If a distance to curve residual is kept at all, it must be leave one out and
   it must not be standardised against endpoint extrapolation error.** Section
   4.4 shows the leave one out residual recovers the true displacement to within
   1 percent at 10 mm. The failure is entirely in the standardisation.

## 6. What is synthetic, and what that does and does not establish

**Synthetic.** Everything in Sections 3, 4 and 5. The vertebral chains are
generated by `_true_chain`, an analytic cosine profile with tabulated per level
spacings. No image, no segmentation, no clinical case, no model inference is
involved anywhere in the validation.

**What it does establish.** These are properties of the algorithm, provable on
any input, and the synthetic data is a sufficient witness:

- The residual scale is pinned near 0.707 px per axis by `s = 0.5n`. Measured
  bound reached exactly.
- The in sample residual does not grow with a true off curve displacement and
  falls below its own no error value by 80 mm. Masking is a property of the
  smoothing constraint, not of the data.
- A mislabel is tangential to the fitted curve, so a normal distance residual
  carries no information about it. Measured: 97.0 percent detection against a
  97.0 percent paired control on a whole column off by one.
- The endpoint versus interior asymmetry has the opposite sign for an in sample
  residual than for a leave one out one, 2.2 percent versus 47.9 percent at the
  endpoints.
- A region with exactly 4 levels present receives no QA at all, because the cubic
  spline interpolates it. Residual mean 0.027 px against 0.552 px elsewhere.
- In the deployed rule, no threshold in 1.0 to 4.0 gives detection above the study
  level false positive rate on the single level shift, the adjacent swap or the
  off curve control. The best margin on any injection is +4.2 pp.

**What it does NOT establish.**

- **The clinical false positive rate.** The agreement between the synthetic
  10.9 percent and the deployed 11.1 percent is strong evidence that the
  deployed flag rate needs no labelling errors to explain it, but the synthetic
  noise level of 0.5 mm was chosen for plausibility, not measured from the
  segmentations. It should be estimated from real centroids before the agreement
  is presented as a quantitative match. It is offered here as consistency, not
  as a calibration.
- **The real distribution of mislabel types.** The three injected classes are the
  ones the iterative labelling code can produce, read from
  `iterative_labeling_main.py`, but their relative frequencies in real studies
  are unmeasured. The detection results are per class, not weighted.
- **The real per level flag pattern.** Section 4.2 offers region size as a better
  explanation than endpoint leverage for the clinically observed pattern, C5 18
  and T11 22 against zero for C1 to C4 and L4 to L5. That is an inference from
  the synthetic region size table plus the fact that real coverage varies. It has
  not been tested by tabulating coverage per shipped study, which is the obvious
  next step and needs only the existing JSON.
- **Anything about the anatomy.** The chain is a cosine. Real sagittal profiles
  have curvature concentrated at the apices of each curve, which would move the
  interior flag pattern around. The conclusions above were chosen to be ones that
  do not depend on where the curvature sits, but the specific per depth
  percentages in Section 4.2 do depend on it and should not be quoted as
  anatomy.

## 7. Files

| file | role |
|---|---|
| `src/spinelab/outliers/spline.py` | the module. Part 1 of the docstring quotes the deployed source, `fit_deployed` reproduces it, `fit_instrumented` decouples the signal, `validate()` runs everything above |
| `<path>\runs\spline_detector\validate.txt` | full console output of the run these tables come from, not committed |
| `<path>\runs\spline_detector\synthetic.json` | machine readable form of every number above, not committed |
