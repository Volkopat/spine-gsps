# highdicom 0.28.1: install provenance

Measured 2026-07-30, on the interpreter that produced every `highdicom` claim in the
paper: `C:\Users\dekay\miniconda3\envs\spinelab\python.exe`, Python 3.10.20.

Round two review, Comment 8, left this disputed. The reviewer's position was that public
PyPI release history shows 0.27.0 (24 October 2025) as the latest release with no 0.28.x
entry, and that the project's documentation build being labelled 0.28.1 is consistent
with 0.28.1 being an in-development version string rather than a published package. The
right response is not to argue but to record the evidence, because the claim that the
library cannot express per-object colour is version-scoped: a reviewer who cannot
reproduce the install cannot reproduce the grep.

## `pip index versions highdicom`

```
highdicom (0.28.1)
Available versions: 0.28.1, 0.28.0, 0.27.0, 0.26.1, 0.26.0, 0.25.1, 0.25.0, 0.24.0,
0.23.1, 0.23.0, 0.22.0, 0.21.1, 0.21.0, 0.20.0, 0.19.0, 0.18.4, 0.18.3, 0.18.2, 0.18.1,
0.18.0, 0.17.0, 0.16.0, 0.15.3, 0.15.2, 0.15.1, 0.15.0, 0.14.2, 0.14.1, 0.14.0, 0.13.1,
0.13.0, 0.12.1, 0.12.0, 0.11.0, 0.10.0, 0.9.2, 0.9.1, 0.9.0, 0.8.0, 0.7.0, 0.6.0, 0.5.1,
0.5.0, 0.4.1, 0.4.0, 0.3.0, 0.2.0, 0.1.0
  INSTALLED: 0.28.1
  LATEST:    0.28.1
```

Both **0.28.0 and 0.28.1** are listed as available from the index, not only 0.27.0.

## `pip show highdicom`

```
Name: highdicom
Version: 0.28.1
Location: c:\users\dekay\miniconda3\envs\spinelab\lib\site-packages
```

`Location` is site-packages. There is no `Editable project location` field, so this is
not an editable or source install.

## The decisive artefact: `direct_url.json` is absent

`C:\Users\dekay\miniconda3\envs\spinelab\Lib\site-packages\highdicom-0.28.1.dist-info\`
contains:

```
INSTALLER  METADATA  RECORD  REQUESTED  WHEEL  licenses  top_level.txt
```

**There is no `direct_url.json`.** Per PEP 610, pip writes that file if and only if the
distribution was installed from a direct URL: a VCS checkout, a local directory, or a
remote archive. Its absence means this was resolved and installed from a **package
index**. Supporting metadata:

```
INSTALLER: pip
WHEEL:
  Wheel-Version: 1.0
  Generator: setuptools (83.0.0)
  Root-Is-Purelib: true
  Tag: py3-none-any
METADATA:
  Metadata-Version: 2.4
  Name: highdicom
  Version: 0.28.1
  Author: Markus D. Herrmann, Christopher P. Bridge
  License-Expression: MIT
  Project-URL: homepage, https://github.com/imagingdatacommons/highdicom
```

A built wheel, installed by pip, from an index, with no direct-URL record.

## Conclusion

0.28.1 is a released artefact obtained from a package index, and is what every
`highdicom` claim in this paper was measured against. The reviewer's concern was
reasonable and the correct resolution was to record the provenance rather than to
adjudicate release history in prose. Ledger row B11 stands, and B11a records this.

## What a reviewer should do to reproduce

```
python -m pip index versions highdicom
python -m pip show highdicom
ls  <site-packages>/highdicom-0.28.1.dist-info/     # expect no direct_url.json
python -c "import highdicom; print(highdicom.__version__, highdicom.__file__)"
```

If a future release adds a text or line style attribute, claim B7 becomes false for that
version and the paper's version scoping is what makes that checkable rather than
embarrassing.
