"""Regression tests for spinelab.gsps.validate, the dciodvfy output parser.

The parser is fed CAPTURED dciodvfy text, so these tests run on a machine
without the binary. The fixture below is real output, taken verbatim on
2026-07-30 from dicom3tools snapshot 20260701065818 run against
`00001589_GSPS.dcm`, one of the 38 shipped objects. Only the repetition of the
text style warnings is shortened, and one repetition is kept because the
per-file counting bug depended on exactly that repetition.

Two things are pinned:
  1. every line shape dciodvfy actually emits is recognised,
  2. missing attributes are counted per FILE, not per occurrence. Counting
     occurrences produced the impossible tally "68/9".
"""
from __future__ import annotations

from pathlib import Path

import pytest

from spinelab.gsps import validate as V

# --------------------------------------------------------------------------
# Captured output. Verbatim line shapes.
# --------------------------------------------------------------------------

REAL_OUTPUT = """\
Warning - Missing attribute or value that would be needed to build DICOMDIR - Study ID
Warning - Missing attribute or value that would be needed to build DICOMDIR - Series Number
Warning - Value dubious for this VR - (0x0010,0x0010) PN Patient's Name  PN [1] = \
<ANON_PAT_XXXX> - Retired Person Name form
GrayscaleSoftcopyPresentationState
Error - Missing attribute Type 1 Required Element=<FileMetaInformationGroupLength> \
Module=<FileMetaInformation>
Error - Missing attribute Type 1 Required Element=<FileMetaInformationVersion> \
Module=<FileMetaInformation>
Error - Missing attribute Type 2 Required Element=<StudyID> Module=<GeneralStudy>
Error - Missing attribute Type 2 Required Element=<SeriesNumber> Module=<GeneralSeries>
Error - Missing attribute Type 2C Conditional Element=<Laterality> Module=<GeneralSeries>
Error - Missing attribute Type 1 Required Element=<InstanceNumber> \
Module=<ContentIdentificationMacro>
Error - Missing attribute Type 1C Conditional Element=<PresentationPixelSpacing> \
Module=<DisplayedArea>
Warning - Attribute is not present in standard DICOM IOD - (0x0070,0x0229) LO CSS Font Name
Warning - Attribute is not present in standard DICOM IOD - (0x0070,0x0241) US Text Color CIELab Value
Warning - Attribute is not present in standard DICOM IOD - (0x0070,0x0242) CS Horizontal Alignment
Warning - Attribute is not present in standard DICOM IOD - (0x0070,0x0243) CS Vertical Alignment
Warning - Attribute is not present in standard DICOM IOD - (0x0070,0x0244) CS Shadow Style
Warning - Attribute is not present in standard DICOM IOD - (0x0070,0x0231) SQ Text Style Sequence
Warning - Attribute is not present in standard DICOM IOD - (0x0070,0x0229) LO CSS Font Name
Warning - Attribute is not present in standard DICOM IOD - (0x0070,0x0241) US Text Color CIELab Value
Warning - Attribute is not present in standard DICOM IOD - (0x0070,0x0242) CS Horizontal Alignment
Warning - Attribute is not present in standard DICOM IOD - (0x0070,0x0243) CS Vertical Alignment
Warning - Attribute is not present in standard DICOM IOD - (0x0070,0x0244) CS Shadow Style
Warning - Attribute is not present in standard DICOM IOD - (0x0070,0x0231) SQ Text Style Sequence
Warning - Dicom dataset contains attributes not present in standard DICOM IOD - \
this is a Standard Extended SOP Class
"""

CLEAN_OUTPUT = """\
GrayscaleSoftcopyPresentationState
Error - Missing attribute Type 2C Conditional Element=<Laterality> Module=<GeneralSeries>
"""


class _FakeProc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def _fake_run(text, returncode=1):
    def run(cmd, **kw):
        return _FakeProc(stdout=text, returncode=returncode)
    return run


@pytest.fixture
def parsed(monkeypatch):
    monkeypatch.setattr(V.subprocess, "run", _fake_run(REAL_OUTPUT))
    return V.run_one(Path("00001589_GSPS.dcm"))


# --------------------------------------------------------------------------
# 1. Line shapes
# --------------------------------------------------------------------------

def test_iod_is_recognised(parsed):
    assert parsed["iod"] == "GrayscaleSoftcopyPresentationState"


def test_all_seven_missing_attributes_are_parsed(parsed):
    got = {(m["type"], m["element"], m["module"]) for m in parsed["missing"]}
    assert got == {
        ("1", "FileMetaInformationGroupLength", "FileMetaInformation"),
        ("1", "FileMetaInformationVersion", "FileMetaInformation"),
        ("2", "StudyID", "GeneralStudy"),
        ("2", "SeriesNumber", "GeneralSeries"),
        ("2C", "Laterality", "GeneralSeries"),
        ("1", "InstanceNumber", "ContentIdentificationMacro"),
        ("1C", "PresentationPixelSpacing", "DisplayedArea"),
    }


def test_conditional_types_keep_their_letter(parsed):
    types = {m["element"]: m["type"] for m in parsed["missing"]}
    assert types["Laterality"] == "2C"
    assert types["PresentationPixelSpacing"] == "1C"
    assert types["InstanceNumber"] == "1"


def test_out_of_iod_attributes_are_parsed_with_tag_vr_and_name(parsed):
    got = {(n["tag"], n["vr"], n["name"]) for n in parsed["not_in_iod"]}
    assert got == {
        ("0x0070,0x0229", "LO", "CSS Font Name"),
        ("0x0070,0x0241", "US", "Text Color CIELab Value"),
        ("0x0070,0x0242", "CS", "Horizontal Alignment"),
        ("0x0070,0x0243", "CS", "Vertical Alignment"),
        ("0x0070,0x0244", "CS", "Shadow Style"),
        ("0x0070,0x0231", "SQ", "Text Style Sequence"),
    }


def test_tags_are_lowercased_and_bracketless_for_stable_grouping(parsed):
    """The stored form is what results/*_validation.json carries, so pin it."""
    for n in parsed["not_in_iod"]:
        assert n["tag"] == n["tag"].lower()
        assert n["tag"].startswith("0x") and "," in n["tag"]
        assert "(" not in n["tag"] and ")" not in n["tag"]


def test_trailing_whitespace_is_stripped_from_names(parsed):
    for n in parsed["not_in_iod"]:
        assert n["name"] == n["name"].strip()


def test_out_of_iod_warnings_do_not_leak_into_other_warnings(parsed):
    for msg in parsed["other_warnings"]:
        assert "not present in standard DICOM IOD - (0x" not in msg


def test_missing_errors_do_not_leak_into_other_errors(parsed):
    for msg in parsed["other_errors"]:
        assert not msg.startswith("Missing attribute Type ")


def test_dicomdir_and_dubious_vr_warnings_are_kept(parsed):
    joined = " | ".join(parsed["other_warnings"])
    assert "needed to build DICOMDIR - Study ID" in joined
    assert "Retired Person Name form" in joined
    assert "Standard Extended SOP Class" in joined


def test_a_clean_object_parses_to_a_single_flag(monkeypatch):
    monkeypatch.setattr(V.subprocess, "run", _fake_run(CLEAN_OUTPUT))
    rec = V.run_one(Path("variant.dcm"))
    assert rec["iod"] == "GrayscaleSoftcopyPresentationState"
    assert [m["element"] for m in rec["missing"]] == ["Laterality"]
    assert rec["not_in_iod"] == []
    assert rec["other_errors"] == []


def test_empty_output_does_not_crash_the_parser(monkeypatch):
    monkeypatch.setattr(V.subprocess, "run", _fake_run("", returncode=0))
    rec = V.run_one(Path("nothing.dcm"))
    assert rec["iod"] is None
    assert rec["missing"] == [] and rec["not_in_iod"] == []


def test_stderr_is_parsed_as_well_as_stdout(monkeypatch):
    def run(cmd, **kw):
        return _FakeProc(stdout="GrayscaleSoftcopyPresentationState\n",
                         stderr="Error - Missing attribute Type 1 Required "
                                "Element=<InstanceNumber> Module=<ContentIdentificationMacro>\n",
                         returncode=1)
    monkeypatch.setattr(V.subprocess, "run", run)
    rec = V.run_one(Path("x.dcm"))
    assert [m["element"] for m in rec["missing"]] == ["InstanceNumber"]


def test_record_carries_the_file_path_and_exit_code(monkeypatch):
    monkeypatch.setattr(V.subprocess, "run", _fake_run(CLEAN_OUTPUT, returncode=7))
    rec = V.run_one(Path("some") / "where.dcm")
    assert rec["file"].endswith("where.dcm")
    assert rec["exit_code"] == 7


# --------------------------------------------------------------------------
# 2. Counting per FILE, not per occurrence. The "68/9" bug.
# --------------------------------------------------------------------------

REPEATED = (
    "GrayscaleSoftcopyPresentationState\n"
    + ("Error - Missing attribute Type 1C Conditional "
       "Element=<PresentationPixelSpacing> Module=<DisplayedArea>\n") * 17
    + ("Warning - Attribute is not present in standard DICOM IOD - "
       "(0x0070,0x0241) US Text Color CIELab Value \n") * 17
)


def _run_main(monkeypatch, capsys, tmp_path, text, n_files=1):
    """Drive validate.main over n_files fake objects, all producing `text`."""
    for i in range(n_files):
        (tmp_path / ("f%02d.dcm" % i)).write_bytes(b"not really dicom")
    # main refuses to run if the validator is absent, so point it at a real file
    monkeypatch.setattr(V, "DCIODVFY", Path(__file__).resolve())
    monkeypatch.setattr(V.subprocess, "run", _fake_run(text))
    rc = V.main([str(tmp_path)])
    return rc, capsys.readouterr().out


def test_a_repeated_missing_attribute_counts_as_one_file(monkeypatch, capsys, tmp_path):
    """17 occurrences in 1 file must read 1/1, never 17/1."""
    rc, out = _run_main(monkeypatch, capsys, tmp_path, REPEATED, n_files=1)
    assert rc == 0
    lines = [ln for ln in out.splitlines() if "PresentationPixelSpacing" in ln]
    assert lines, out
    assert lines[0].strip().endswith("1/1"), lines[0]
    assert "17/1" not in out


def test_a_repeated_out_of_iod_attribute_counts_as_one_file(monkeypatch, capsys, tmp_path):
    rc, out = _run_main(monkeypatch, capsys, tmp_path, REPEATED, n_files=1)
    lines = [ln for ln in out.splitlines() if "Text Color CIELab Value" in ln]
    assert lines, out
    assert lines[0].strip().endswith("1/1"), lines[0]


def test_the_count_never_exceeds_the_file_total(monkeypatch, capsys, tmp_path):
    """The whole class of bug: a numerator larger than the denominator."""
    import re

    rc, out = _run_main(monkeypatch, capsys, tmp_path, REPEATED, n_files=9)
    assert "9/9" in out
    bad = [(a, b) for a, b in re.findall(r"(\d+)/(\d+)\s*$", out, flags=re.M)
           if int(a) > int(b)]
    assert not bad, "numerator exceeds denominator: %r" % bad


def test_the_denominator_is_the_number_of_files(monkeypatch, capsys, tmp_path):
    rc, out = _run_main(monkeypatch, capsys, tmp_path, REPEATED, n_files=4)
    assert "validating 4 file(s)" in out
    lines = [ln for ln in out.splitlines() if "PresentationPixelSpacing" in ln]
    assert lines[0].strip().endswith("4/4"), lines[0]


def test_clean_files_are_counted_as_clean(monkeypatch, capsys, tmp_path):
    """Laterality is the only flag on a conformant object, and it IS an error, so
    the clean count is zero. Pinned so the definition of clean does not drift."""
    rc, out = _run_main(monkeypatch, capsys, tmp_path, CLEAN_OUTPUT, n_files=3)
    assert "files with zero errors: 0/3" in out
    rc, out = _run_main(monkeypatch, capsys, tmp_path,
                        "GrayscaleSoftcopyPresentationState\n", n_files=3)
    assert "files with zero errors: 3/3" in out


def test_json_output_holds_one_record_per_file(monkeypatch, capsys, tmp_path):
    import json

    for i in range(3):
        (tmp_path / ("g%02d.dcm" % i)).write_bytes(b"x")
    monkeypatch.setattr(V, "DCIODVFY", Path(__file__).resolve())
    monkeypatch.setattr(V.subprocess, "run", _fake_run(REAL_OUTPUT))
    out_json = tmp_path / "sub" / "recs.json"
    assert V.main([str(tmp_path), "--json", str(out_json)]) == 0
    data = json.loads(out_json.read_text())
    assert data["n_files"] == 3
    assert len(data["records"]) == 3
    assert len(data["records"][0]["missing"]) == 7


# --------------------------------------------------------------------------
# 3. File collection
# --------------------------------------------------------------------------

def test_collect_recurses_directories_and_sorts(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "2.dcm").write_bytes(b"x")
    (tmp_path / "a" / "1.dcm").write_bytes(b"x")
    (tmp_path / "b.dcm").write_bytes(b"x")
    (tmp_path / "c.txt").write_bytes(b"x")
    got = [p.name for p in V.collect([str(tmp_path)])]
    assert got == ["1.dcm", "2.dcm", "b.dcm"]
    assert "c.txt" not in got


def test_collect_accepts_explicit_files(tmp_path):
    f = tmp_path / "one.txt"
    f.write_bytes(b"x")
    assert V.collect([str(f)]) == [f]


def test_collect_ignores_paths_that_do_not_exist(tmp_path):
    assert V.collect([str(tmp_path / "nope")]) == []


def test_pattern_filter_selects_gsps_only(monkeypatch, capsys, tmp_path):
    (tmp_path / "aaa_GSPS.dcm").write_bytes(b"x")
    (tmp_path / "bbb_image.dcm").write_bytes(b"x")
    monkeypatch.setattr(V, "DCIODVFY", Path(__file__).resolve())
    monkeypatch.setattr(V.subprocess, "run", _fake_run(CLEAN_OUTPUT))
    assert V.main([str(tmp_path), "--pattern", "_GSPS"]) == 0
    assert "validating 1 file(s)" in capsys.readouterr().out


def test_main_reports_a_missing_validator_rather_than_crashing(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(V, "DCIODVFY", tmp_path / "definitely_absent.exe")
    assert V.main([str(tmp_path)]) == 2
    assert "not found" in capsys.readouterr().out


def test_main_reports_no_matching_files(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(V, "DCIODVFY", Path(__file__).resolve())
    assert V.main([str(tmp_path)]) == 1
    assert "no files matched" in capsys.readouterr().out


def test_validate_module_uses_subprocess_not_a_shell():
    """run_one must pass a list, so a path with spaces cannot be re-split.

    The baseline objects live under "<path>", which has a
    space in it.
    """
    src = Path(V.__file__).read_text()
    assert "shell=True" not in src
    assert "[str(DCIODVFY), str(path)]" in src
