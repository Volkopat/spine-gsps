"""Regression tests for spinelab.gsps.writer.

The premise of the whole viewer experiment is that the variants differ ONLY in
conformance attributes, colour route and producer identity. If a variant also
moved a coordinate or changed a label string, any viewer difference would be
uninterpretable. So the first and most important test here holds annotation
content fixed.

The rest pin the four corrections recorded in results/gsps_variants.md:
  1. the Line Style Sequence macro's ten Type 1 attributes, four of which an
     earlier version of this writer omitted,
  2. Laterality absent rather than zero length,
  3. PresentationPixelSpacing and PresentationPixelAspectRatio as alternatives,
  4. which colour routes are inside the GSPS IOD.
"""
from __future__ import annotations

import pytest

import conftest as F
from spinelab.gsps import validate as V
from spinelab.gsps import writer as W

ALL_VARIANTS = W.DESIGN_2X2 + W.DESIGN_COLOUR_ROUTES

HAS_DCIODVFY = V.DCIODVFY.exists()
needs_dciodvfy = pytest.mark.skipif(
    not HAS_DCIODVFY,
    reason="dciodvfy not found at %s, set SPINELAB_DCIODVFY to run the "
           "conformance tests" % V.DCIODVFY)


def _texts(ds):
    out = []
    for ga in ds.get("GraphicAnnotationSequence", []):
        for t in ga.get("TextObjectSequence", []):
            out.append(str(t.UnformattedTextValue))
    return out


def _coords(ds):
    out = []
    for ga in ds.get("GraphicAnnotationSequence", []):
        for g in ga.get("GraphicObjectSequence", []):
            out.append((str(g.GraphicType), int(g.NumberOfGraphicPoints),
                        tuple(float(x) for x in g.GraphicData)))
    return out


def _anchors(ds):
    out = []
    for ga in ds.get("GraphicAnnotationSequence", []):
        for t in ga.get("TextObjectSequence", []):
            out.append(tuple(float(x) for x in t.AnchorPoint))
    return out


def _layers(ds):
    return [str(gl.GraphicLayer) for gl in ds.get("GraphicLayerSequence", [])]


# --------------------------------------------------------------------------
# 1. Content held fixed. The premise of the experiment.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ALL_VARIANTS, ids=[v.label for v in ALL_VARIANTS])
def test_annotation_content_is_identical_to_the_source(source_gsps, variant):
    out = W.build_variant(source_gsps, variant)

    assert _texts(out) == _texts(source_gsps) == list(F.SOURCE_TEXTS)
    assert _coords(out) == _coords(source_gsps)
    assert _anchors(out) == _anchors(source_gsps)
    assert _layers(out) == _layers(source_gsps)
    assert len(out.GraphicAnnotationSequence) == len(source_gsps.GraphicAnnotationSequence)
    for a, b in zip(out.GraphicAnnotationSequence, source_gsps.GraphicAnnotationSequence):
        assert str(a.GraphicLayer) == str(b.GraphicLayer)
        assert len(a.TextObjectSequence) == len(b.TextObjectSequence)
        assert len(a.GraphicObjectSequence) == len(b.GraphicObjectSequence)


@pytest.mark.parametrize("variant", ALL_VARIANTS, ids=[v.label for v in ALL_VARIANTS])
def test_variant_does_not_mutate_the_source(source_gsps, variant):
    before_texts, before_coords = _texts(source_gsps), _coords(source_gsps)
    W.build_variant(source_gsps, variant)
    assert _texts(source_gsps) == before_texts
    assert _coords(source_gsps) == before_coords
    # the source keeps its own out-of-IOD text style, it was deep copied
    assert W.TAG_TEXT_STYLE in source_gsps.GraphicAnnotationSequence[0].TextObjectSequence[0]


def test_every_variant_carries_the_same_content_as_every_other(source_gsps):
    built = [W.build_variant(source_gsps, v) for v in ALL_VARIANTS]
    ref_t, ref_c = _texts(built[0]), _coords(built[0])
    for ds, v in zip(built[1:], ALL_VARIANTS[1:]):
        assert _texts(ds) == ref_t, v.label
        assert _coords(ds) == ref_c, v.label


def test_each_variant_gets_fresh_instance_and_series_uids(source_gsps):
    built = [W.build_variant(source_gsps, v) for v in ALL_VARIANTS]
    sops = [d.SOPInstanceUID for d in built]
    assert len(set(sops)) == len(sops)
    assert len(set(d.SeriesInstanceUID for d in built)) == len(built)
    for d in built:
        assert d.SOPInstanceUID != source_gsps.SOPInstanceUID
        assert d.SOPInstanceUID == d.file_meta.MediaStorageSOPInstanceUID
        assert d.SOPClassUID == W.GSPS_SOP_CLASS
        assert d.Modality == "PR"
        # the study is not re-identified, the presentation state belongs to it
        assert d.StudyInstanceUID == source_gsps.StudyInstanceUID


# --------------------------------------------------------------------------
# 2. The Line Style Sequence macro. Ten Type 1 attributes, by tag.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("route", ("line", "all"))
def test_line_style_macro_carries_all_ten_type1_attributes(source_gsps, route):
    out = W.build_variant(source_gsps, W.Variant(True, route, "true"))
    n_seen = 0
    for ga in out.GraphicAnnotationSequence:
        for g in ga.GraphicObjectSequence:
            assert W.TAG_LINE_STYLE in g
            item = g[W.TAG_LINE_STYLE].value[0]
            present = {(e.tag.group, e.tag.element) for e in item}
            missing = set(F.LINE_STYLE_TYPE1_TAGS) - present
            assert not missing, "Line Style Sequence missing Type 1 %s" % (
                sorted("(0x%04x,0x%04x)" % t for t in missing),)
            n_seen += 1
    assert n_seen == 4


def test_line_style_macro_the_four_attributes_the_earlier_version_omitted(source_gsps):
    """ShadowOffsetX, ShadowOffsetY, ShadowColorCIELabValue, PatternOnOpacity.

    dciodvfy caught all four. Named individually so the failure message says
    which one regressed.
    """
    out = W.build_variant(source_gsps, W.Variant(True, "line", "true"))
    item = out.GraphicAnnotationSequence[0].GraphicObjectSequence[0][W.TAG_LINE_STYLE].value[0]
    for kw in ("ShadowOffsetX", "ShadowOffsetY", "ShadowColorCIELabValue",
               "PatternOnOpacity"):
        assert kw in item, "%s absent from the Line Style Sequence macro" % kw
    assert item.ShadowOffsetX == 0.0
    assert item.ShadowOffsetY == 0.0
    assert item.PatternOnOpacity == 1.0


def test_line_style_is_removed_when_the_route_is_not_line(source_gsps):
    for route in ("none", "text", "layer"):
        out = W.build_variant(source_gsps, W.Variant(True, route, "true"))
        for ga in out.GraphicAnnotationSequence:
            for g in ga.GraphicObjectSequence:
                assert W.TAG_LINE_STYLE not in g, route


def test_text_style_is_removed_when_the_route_is_not_text(source_gsps):
    for route in ("none", "line", "layer"):
        out = W.build_variant(source_gsps, W.Variant(True, route, "true"))
        for ga in out.GraphicAnnotationSequence:
            for t in ga.TextObjectSequence:
                assert W.TAG_TEXT_STYLE not in t, route


def test_layer_colour_is_present_only_for_the_layer_route(source_gsps):
    for route in W.COLOUR_ROUTES:
        out = W.build_variant(source_gsps, W.Variant(True, route, "true"))
        want = route in ("layer", "all")
        for gl in out.GraphicLayerSequence:
            assert (W.TAG_LAYER_COLOR in gl) is want, route


# --------------------------------------------------------------------------
# 3. The flagged layer keeps its colour through every route
# --------------------------------------------------------------------------

def test_flagged_layer_detected_from_the_source(source_gsps):
    assert W._flagged_layers(source_gsps) == {F.LAYER_FLAG}


@pytest.mark.parametrize("route,tag,container",
                         [("line", W.TAG_PATTERN_ON_COLOR, "GraphicObjectSequence"),
                          ("text", W.TAG_TEXT_COLOR, "TextObjectSequence")])
def test_red_and_yellow_are_routed_to_the_right_layers(source_gsps, route, tag, container):
    out = W.build_variant(source_gsps, W.Variant(True, route, "true"))
    style_tag = W.TAG_LINE_STYLE if route == "line" else W.TAG_TEXT_STYLE
    for ga in out.GraphicAnnotationSequence:
        expect = W.RED if str(ga.GraphicLayer) == F.LAYER_FLAG else W.YELLOW
        for obj in ga[container].value:
            got = list(obj[style_tag].value[0][tag].value)
            assert got == list(expect), str(ga.GraphicLayer)


def test_layer_route_colours_the_flagged_layer_red(source_gsps):
    out = W.build_variant(source_gsps, W.Variant(True, "layer", "true"))
    got = {str(gl.GraphicLayer): list(gl[W.TAG_LAYER_COLOR].value)
           for gl in out.GraphicLayerSequence}
    assert got[F.LAYER_FLAG] == list(W.RED)
    assert got[F.LAYER_OK] == list(W.YELLOW)


def test_cielab_encoding_round_trips():
    for L, a, b in ((0.0, -128.0, -128.0), (50.0, 0.0, 0.0), (74.9, 23.9, 78.9),
                    (100.0, 127.0, 127.0)):
        dL, da, db = W.decode_cielab(W.cielab(L, a, b))
        assert dL == pytest.approx(L, abs=0.01)
        assert da == pytest.approx(a, abs=0.01)
        assert db == pytest.approx(b, abs=0.01)


def test_cielab_clamps_to_the_unsigned_short_range():
    for v in W.cielab(1000.0, 1000.0, -1000.0):
        assert 0 <= v <= 65535
    assert W.cielab(-50.0, -500.0, -500.0) == [0, 0, 0]


def test_red_is_distinguishable_from_yellow_by_the_flag_detector():
    """_flagged_layers thresholds a* at 60, so the two colours must straddle it."""
    assert W.decode_cielab(W.RED)[1] > 60
    assert W.decode_cielab(W.YELLOW)[1] <= 60


# --------------------------------------------------------------------------
# 4. The required attributes axis
# --------------------------------------------------------------------------

def test_required_attrs_true_yields_instance_series_and_study_id(source_gsps):
    out = W.build_variant(source_gsps, W.Variant(True, "line", "true"))
    for kw in ("InstanceNumber", "SeriesNumber", "StudyID"):
        assert kw in out, "%s absent with required_attrs=True" % kw
    assert out.InstanceNumber == 1
    assert out.SeriesNumber == 9001
    assert str(out.StudyID) == str(source_gsps.StudyID)


def test_required_attrs_false_removes_them_again(source_gsps):
    out = W.build_variant(source_gsps, W.Variant(False, "text", "true"))
    for kw in ("InstanceNumber", "SeriesNumber", "StudyID", "Laterality"):
        assert kw not in out, "%s survived required_attrs=False" % kw


@pytest.mark.parametrize("variant", ALL_VARIANTS, ids=[v.label for v in ALL_VARIANTS])
def test_laterality_is_absent_not_zero_length(source_gsps, variant):
    """The source carries a zero length Laterality. Absent is the correct answer.

    dciodvfy on a zero length value says, verbatim: "is only permitted to be
    empty when actually unknown; should be absent (not zero length)".
    """
    assert "Laterality" in source_gsps and source_gsps.Laterality == ""
    out = W.build_variant(source_gsps, variant)
    assert "Laterality" not in out


def test_presentation_pixel_spacing_comes_from_the_source_image(source_gsps, source_image):
    out = W.build_variant(source_gsps, W.Variant(True, "line", "true"), source_image)
    for da in out.DisplayedAreaSelectionSequence:
        assert "PresentationPixelSpacing" in da
        assert [float(x) for x in da.PresentationPixelSpacing] == [
            pytest.approx(0.4297), pytest.approx(0.4297)]
        # the two are alternatives, so the aspect ratio must be gone
        assert "PresentationPixelAspectRatio" not in da


def test_aspect_ratio_is_the_fallback_when_no_source_image(source_gsps):
    out = W.build_variant(source_gsps, W.Variant(True, "line", "true"), None)
    for da in out.DisplayedAreaSelectionSequence:
        assert "PresentationPixelAspectRatio" in da
        assert "PresentationPixelSpacing" not in da


def test_spacing_and_aspect_ratio_are_never_both_present(source_gsps, source_image):
    for img in (None, source_image):
        for v in ALL_VARIANTS:
            out = W.build_variant(source_gsps, v, img)
            for da in out.DisplayedAreaSelectionSequence:
                both = ("PresentationPixelSpacing" in da
                        and "PresentationPixelAspectRatio" in da)
                assert not both, "%s: both alternatives present" % v.label


# --------------------------------------------------------------------------
# 5. The identity axis
# --------------------------------------------------------------------------

def test_identity_axis_changes_manufacturer_model_and_implementation_version(source_gsps):
    true_id = W.build_variant(source_gsps, W.Variant(True, "line", "true"))
    dep_id = W.build_variant(source_gsps, W.Variant(True, "line", "meddream"))

    assert true_id.Manufacturer != dep_id.Manufacturer
    assert true_id.ManufacturerModelName != dep_id.ManufacturerModelName
    assert (true_id.file_meta.ImplementationVersionName
            != dep_id.file_meta.ImplementationVersionName)
    assert (true_id.file_meta.ImplementationClassUID
            != dep_id.file_meta.ImplementationClassUID)

    assert true_id.Manufacturer == "spinelab"
    assert true_id.ManufacturerModelName == "spinelab-gsps"
    assert true_id.file_meta.ImplementationVersionName == "SPINELAB_0_1"
    assert true_id.SoftwareVersions == "0.1.0"

    assert dep_id.Manufacturer == "Softneta"
    assert dep_id.ManufacturerModelName == "MedDream"
    assert dep_id.file_meta.ImplementationVersionName == "AYCANSTORE3"
    assert "SoftwareVersions" not in dep_id


@pytest.mark.parametrize("variant", ALL_VARIANTS, ids=[v.label for v in ALL_VARIANTS])
def test_content_description_fits_the_lo_value_representation(source_gsps, variant):
    """LO is capped at 64 characters. The nine designed labels all fit."""
    out = W.build_variant(source_gsps, variant)
    assert len(str(out.ContentDescription)) <= 64, (
        "%s: ContentDescription is %d characters"
        % (variant.label, len(str(out.ContentDescription))))


AUTO_LABELLED = [W.Variant(True, r, i) for r in W.COLOUR_ROUTES for i in W.IDENTITIES]


def test_auto_labelled_variants_also_fit_the_lo_limit(source_gsps):
    """FINDING: they do not. Left failing on purpose.

    build_variant writes ContentDescription = "Vertebral level annotations,
    variant <label>", 37 characters of prefix. The auto generated label
    "req-yes_colour-line_id-meddream" is 31 characters, so the value is 68 and
    overruns LO. Measured with dciodvfy on the emitted object, verbatim:

      Error - Value invalid for this VR - (0x0070,0x0081) LO Content Description
      LO [1] = <Vertebral level annotations, variant req-yes_colour-line_id-meddream>
      - Length invalid for this VR = 68, expected <= 64

    which also adds "Error - Dicom dataset contains invalid data values for Value
    Representations", taking the object from 1 error to 3. The nine designed
    variants in results/gsps_variants.md carry short labels and are unaffected, so
    no published number changes. Any new caller that builds a Variant without
    naming it does hit this. Fix belongs in writer.py, by truncating the
    description or shortening the auto label.
    """
    over = []
    for v in AUTO_LABELLED:
        n = len(str(W.build_variant(source_gsps, v).ContentDescription))
        if n > 64:
            over.append("%s = %d chars" % (v.label, n))
    assert not over, "ContentDescription overruns LO (64) for: %s" % over


def test_variant_rejects_an_unknown_axis_value():
    with pytest.raises(ValueError):
        W.Variant(True, "rainbow", "true")
    with pytest.raises(ValueError):
        W.Variant(True, "line", "philips")


def test_variant_autolabels_itself():
    assert W.Variant(True, "line", "true").label == "req-yes_colour-line_id-true"
    assert W.Variant(False, "text", "meddream").label == "req-no_colour-text_id-meddream"
    assert W.Variant(True, "line", "true", "custom").label == "custom"


def test_design_labels_are_unique_so_no_variant_overwrites_another():
    labels = [v.label for v in ALL_VARIANTS]
    assert len(set(labels)) == len(labels) == 9
    # conformant_trueid and colour_line_iod are the same cell of the design under
    # two names, which is intentional. Record it so a reader is not surprised.
    cells = [(v.required_attrs, v.colour_route, v.identity) for v in ALL_VARIANTS]
    assert len(set(cells)) == 8


# --------------------------------------------------------------------------
# 6. emit_all writes readable files
# --------------------------------------------------------------------------

def _write_source(tmp_path, transfer_syntax):
    import pydicom
    from pydicom.dataset import FileDataset, FileMetaDataset

    src = F.build_source_gsps()
    fm = FileMetaDataset()
    fm.MediaStorageSOPClassUID = src.SOPClassUID
    fm.MediaStorageSOPInstanceUID = src.SOPInstanceUID
    fm.TransferSyntaxUID = transfer_syntax
    fm.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
    fds = FileDataset("", {}, file_meta=fm, preamble=b"\0" * 128)
    for elem in src:
        fds.add(elem)
    p = tmp_path / "synthetic_GSPS.dcm"
    pydicom.dcmwrite(str(p), fds, enforce_file_format=True)
    return p


def test_emit_all_round_trips_through_disk(tmp_path, transfer_syntax):
    import pydicom

    src_path = _write_source(tmp_path, transfer_syntax)
    written = W.emit_all(src_path, tmp_path / "out", ALL_VARIANTS[:4])
    assert len(written) == 4
    for label, p in written:
        assert p.exists() and p.stat().st_size > 0
        back = pydicom.dcmread(str(p))
        assert _texts(back) == list(F.SOURCE_TEXTS)
        assert _coords(back) == _coords(F.build_source_gsps())
        assert back.SOPClassUID == W.GSPS_SOP_CLASS
        assert label in p.name


# --------------------------------------------------------------------------
# 7. dciodvfy, the independent scorer. Skipped cleanly when absent.
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def emitted(tmp_path_factory):
    """Emit every colour route once, to disk, for the conformance tests."""
    import pydicom
    from pydicom.dataset import FileDataset, FileMetaDataset

    d = tmp_path_factory.mktemp("gsps")
    src = F.build_source_gsps()
    fm = FileMetaDataset()
    fm.MediaStorageSOPClassUID = src.SOPClassUID
    fm.MediaStorageSOPInstanceUID = src.SOPInstanceUID
    fm.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    fm.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
    fds = FileDataset("", {}, file_meta=fm, preamble=b"\0" * 128)
    for elem in src:
        fds.add(elem)
    src_path = d / "synthetic_GSPS.dcm"
    pydicom.dcmwrite(str(src_path), fds, enforce_file_format=True)

    out = {"__source__": src_path}
    for label, p in W.emit_all(src_path, d / "variants", W.DESIGN_COLOUR_ROUTES):
        out[label] = p
    return out


@needs_dciodvfy
def test_source_fixture_is_recognised_as_a_gsps(emitted):
    rec = V.run_one(emitted["__source__"])
    assert rec["iod"] == "GrayscaleSoftcopyPresentationState"


@needs_dciodvfy
@pytest.mark.parametrize("label", ("colour_line_iod", "colour_layer_iod", "colour_none"))
def test_in_iod_colour_routes_produce_zero_out_of_iod_attributes(emitted, label):
    rec = V.run_one(emitted[label])
    tags = sorted({n["tag"] for n in rec["not_in_iod"]})
    assert tags == [], "%s: %s" % (label, tags)


@needs_dciodvfy
@pytest.mark.parametrize("label", ("colour_text_outofiod", "colour_all"))
def test_the_text_colour_route_produces_exactly_the_six_known_attributes(emitted, label):
    rec = V.run_one(emitted[label])
    tags = {n["tag"] for n in rec["not_in_iod"]}
    assert tags == set(F.TEXT_ROUTE_OUT_OF_IOD_TAGS), "%s: %s" % (label, sorted(tags))


@needs_dciodvfy
def test_laterality_is_the_only_remaining_conformance_flag(emitted):
    """Type 2C on an unpaired body part. dciodvfy cannot evaluate the condition."""
    rec = V.run_one(emitted["colour_line_iod"])
    elems = sorted(m["element"] for m in rec["missing"])
    assert elems == ["Laterality"], elems
