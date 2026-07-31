"""Build a GSPS from scratch, given a series and per vertebra annotation geometry.

`writer.py` re-emits variants of an EXISTING object, which is right for holding
content fixed across an ablation but means every artifact inherits a clinical
source. This constructs one from nothing, so the whole E5 artifact can be built on
public data.

Design decision that is forced rather than chosen: **one graphic layer per
vertebra**. Layer level colour, (0070,0401) Graphic Layer Recommended Display CIELab
Value, is the only per object colour route that is both in the GSPS IOD and
writable by the reference implementation. `highdicom` 0.28.1 can write GSPS but
contains zero occurrences of `LineStyleSequence` or `TextStyleSequence`, so per
object line colour is unreachable with it. Therefore per vertebra colour coding
requires per vertebra layers. The deployed emitter's eighteen `MEASUREMENT_*`
layers, which looked like bloat, are the only conformant way to do this.

Every required attribute the deployed emitter omitted is populated here. See
results/gsps_conformance_baseline.md for the list of seven and results/
gsps_variants.md for the ten Type 1 attributes of the Line Style macro.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

import pydicom
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset, validate_file_meta
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from .writer import (DEPLOYED_IDENTITY, GSPS_SOP_CLASS, RED, TAG_LAYER_COLOR,
                     TAG_PATTERN_ON_COLOR, TAG_LINE_STYLE, TAG_TEXT_COLOR,
                     TAG_TEXT_STYLE, TRUE_IDENTITY, YELLOW, Variant)

# Attributes copied from the referenced image so the presentation state lands in
# the right study and patient. Everything else is created fresh.
_COPY_FROM_IMAGE = (
    "SpecificCharacterSet", "PatientName", "PatientID", "PatientBirthDate",
    "PatientSex", "StudyInstanceUID", "StudyDate", "StudyTime", "StudyID",
    "AccessionNumber", "ReferringPhysicianName", "StudyDescription",
    "InstitutionName",
)


@dataclass
class Annotation:
    """One vertebra label. row and col are pixel indices on the referenced image."""
    name: str
    confidence: float
    row: float
    col: float
    flagged: bool = False


def _line_style(colour: list[int]) -> Dataset:
    """All ten Type 1 attributes of the Line Style macro. Omitting any is an error."""
    s = Dataset()
    s.ShadowStyle = "OFF"
    s.ShadowOffsetX = 0.0
    s.ShadowOffsetY = 0.0
    s.ShadowColorCIELabValue = colour
    s.ShadowOpacity = 0.0
    s.LineThickness = 2.0
    s.LineDashingStyle = "DASHED"
    s.LinePattern = 255
    s.PatternOnOpacity = 1.0
    s[TAG_PATTERN_ON_COLOR] = pydicom.DataElement(TAG_PATTERN_ON_COLOR, "US", colour)
    return s


def _text_style(colour: list[int]) -> Dataset:
    """Out of IOD for GSPS. Only emitted for the deliberately non conformant arm."""
    s = Dataset()
    s.CSSFontName = "Arial"
    s.HorizontalAlignment = "LEFT"
    s.VerticalAlignment = "TOP"
    s.ShadowStyle = "OFF"
    s[TAG_TEXT_COLOR] = pydicom.DataElement(TAG_TEXT_COLOR, "US", colour)
    return s


def build_gsps(image: Dataset, annotations: list[Annotation], v: Variant,
               label_col: float | None = None, label_height: float = 22.0,
               label_width: float = 96.0) -> FileDataset:
    """Construct a GSPS referencing one image, annotating each vertebra.

    Labels are stacked in a column to one side of the spine, each joined to its
    vertebra by a dashed leader line, which is the deployed presentation.
    """
    ident = TRUE_IDENTITY if v.identity == "true" else DEPLOYED_IDENTITY
    rows, cols = int(image.Rows), int(image.Columns)
    if label_col is None:
        # place labels clear of the spine, on whichever side has more room
        mean_col = sum(a.col for a in annotations) / max(1, len(annotations))
        label_col = min(cols - label_width - 2.0, mean_col + 90.0) \
            if mean_col < cols / 2 else max(2.0, mean_col - 90.0 - label_width)

    fm = FileMetaDataset()
    fm.MediaStorageSOPClassUID = GSPS_SOP_CLASS
    fm.MediaStorageSOPInstanceUID = generate_uid()
    fm.TransferSyntaxUID = ExplicitVRLittleEndian
    fm.ImplementationClassUID = ident["ImplementationClassUID"]
    fm.ImplementationVersionName = ident["ImplementationVersionName"]

    ds = FileDataset("", {}, file_meta=fm, preamble=b"\0" * 128)
    for kw in _COPY_FROM_IMAGE:
        if kw in image:
            setattr(ds, kw, image[kw].value)
    ds.SpecificCharacterSet = getattr(ds, "SpecificCharacterSet", "ISO_IR 100")

    now = datetime.datetime.now()
    ds.SOPClassUID = GSPS_SOP_CLASS
    ds.SOPInstanceUID = fm.MediaStorageSOPInstanceUID
    ds.SeriesInstanceUID = generate_uid()
    ds.Modality = "PR"
    ds.Manufacturer = ident["Manufacturer"]
    ds.ManufacturerModelName = ident["ManufacturerModelName"]
    if ident["SoftwareVersions"]:
        ds.SoftwareVersions = ident["SoftwareVersions"]
    ds.SeriesDescription = "Vertebral level annotations"
    ds.PresentationCreationDate = now.strftime("%Y%m%d")
    ds.PresentationCreationTime = now.strftime("%H%M%S")
    ds.ContentLabel = "SPINE_QS"
    # VR LO caps at 64 characters and pydicom only warns on overrun, so truncate.
    ds.ContentDescription = ("Spine levels, %s" % v.label)[:64]
    # VR PN expects caret delimited components. A bare single token makes dciodvfy
    # report "Value dubious for this VR ... Retired Person Name form", which is the
    # same complaint it raises about the deployed anonymiser's ANON_PAT_XXXX.
    ds.ContentCreatorName = "spinelab^"
    ds.PresentationLUTShape = "IDENTITY"
    ds.ImageHorizontalFlip = "N"
    ds.ImageRotation = 0

    if v.required_attrs:
        ds.InstanceNumber = 1
        ds.SeriesNumber = 9001
        if "StudyID" not in ds:
            ds.StudyID = ""
        # Laterality is Type 2C on a paired body part. The spine is unpaired, so
        # absent is correct and zero length is worse. dciodvfy flags it either way
        # because it cannot evaluate the condition.

    ref_img = Dataset()
    ref_img.ReferencedSOPClassUID = image.SOPClassUID
    ref_img.ReferencedSOPInstanceUID = image.SOPInstanceUID
    ref_series = Dataset()
    ref_series.SeriesInstanceUID = image.SeriesInstanceUID
    ref_series.ReferencedImageSequence = [ref_img]
    ds.ReferencedSeriesSequence = [ref_series]

    da = Dataset()
    da.ReferencedImageSequence = [ref_img]
    da.DisplayedAreaTopLeftHandCorner = [1, 1]
    da.DisplayedAreaBottomRightHandCorner = [cols, rows]
    da.PresentationSizeMode = "TRUE SIZE"
    if "PixelSpacing" in image:
        # Type 1C, required when PresentationSizeMode is TRUE SIZE. It and
        # PresentationPixelAspectRatio are alternatives, so do not set both.
        da.PresentationPixelSpacing = [float(image.PixelSpacing[0]),
                                       float(image.PixelSpacing[1])]
    else:
        da.PresentationPixelAspectRatio = [1, 1]
    ds.DisplayedAreaSelectionSequence = [da]

    want_text = v.colour_route in ("text", "all")
    want_line = v.colour_route in ("line", "all")
    want_layer = v.colour_route in ("layer", "all")

    layers, annos = [], []
    for i, a in enumerate(sorted(annotations, key=lambda x: x.row)):
        colour = RED if a.flagged else YELLOW
        layer_name = "SPINE_%02d" % (i + 1)

        gl = Dataset()
        gl.GraphicLayer = layer_name
        gl.GraphicLayerOrder = i
        gl.GraphicLayerDescription = "Vertebral level %s" % a.name
        if want_layer:
            gl[TAG_LAYER_COLOR] = pydicom.DataElement(TAG_LAYER_COLOR, "US", colour)
        layers.append(gl)

        top = max(0.0, min(rows - label_height, a.row - label_height / 2.0))
        text = Dataset()
        text.BoundingBoxAnnotationUnits = "PIXEL"
        text.UnformattedTextValue = "%s (%d%%)" % (a.name,
                                                   int(round(100 * a.confidence)))
        text.BoundingBoxTopLeftHandCorner = [float(label_col), float(top)]
        text.BoundingBoxBottomRightHandCorner = [float(label_col + label_width),
                                                 float(top + label_height)]
        text.BoundingBoxTextHorizontalJustification = "LEFT"
        if want_text:
            text[TAG_TEXT_STYLE] = pydicom.DataElement(
                TAG_TEXT_STYLE, "SQ", [_text_style(colour)])

        # leader line from the label edge to the vertebra centroid
        anchor_col = label_col if label_col > a.col else label_col + label_width
        gfx = Dataset()
        gfx.GraphicAnnotationUnits = "PIXEL"
        gfx.GraphicDimensions = 2
        gfx.NumberOfGraphicPoints = 2
        gfx.GraphicData = [float(anchor_col), float(top + label_height / 2.0),
                           float(a.col), float(a.row)]
        gfx.GraphicType = "POLYLINE"
        gfx.GraphicFilled = "N"
        if want_line:
            gfx[TAG_LINE_STYLE] = pydicom.DataElement(
                TAG_LINE_STYLE, "SQ", [_line_style(colour)])

        ga = Dataset()
        ga.GraphicLayer = layer_name
        ga.ReferencedImageSequence = [ref_img]
        ga.TextObjectSequence = [text]
        ga.GraphicObjectSequence = [gfx]
        annos.append(ga)

    ds.GraphicLayerSequence = layers
    ds.GraphicAnnotationSequence = annos

    validate_file_meta(ds.file_meta, enforce_standard=True)
    return ds


def build_from_payload(payload: dict, series_dir: Path, out_dir: Path,
                       variants: list[Variant], flag_below: float = 0.35
                       ) -> list[tuple[str, Path]]:
    """Build variants from an emit_public_gsps.py annotations JSON."""
    import glob

    target = payload["instance"]
    image = None
    for f in sorted(glob.glob(str(series_dir / "*.dcm"))):
        h = pydicom.dcmread(f, stop_before_pixels=True)
        if str(h.SOPInstanceUID) == str(target):
            image = h
            break
    if image is None:
        raise SystemExit("referenced instance %s not found in %s" % (target, series_dir))

    anns = [Annotation(name=a["name"], confidence=float(a["conf"]),
                       row=float(a["row"]), col=float(a["col"]),
                       flagged=float(a["conf"]) < flag_below)
            for a in payload["annotations"] if a.get("inside")]
    if not anns:
        raise SystemExit("no annotations inside the image")

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for v in variants:
        ds = build_gsps(image, anns, v)
        p = out_dir / ("%s__%s.dcm" % (payload["case"], v.label))
        pydicom.dcmwrite(str(p), ds, enforce_file_format=True)
        written.append((v.label, p))
    return written


if __name__ == "__main__":
    import argparse
    import json

    from .writer import DESIGN_2X2, DESIGN_COLOUR_ROUTES

    ap = argparse.ArgumentParser(description="Build GSPS from an annotations JSON")
    ap.add_argument("payload", help="*_annotations.json from emit_public_gsps.py")
    ap.add_argument("--series-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--flag-below", type=float, default=0.35)
    a = ap.parse_args()

    pl = json.loads(Path(a.payload).read_text())
    seen, uniq = set(), []
    for v in DESIGN_2X2 + DESIGN_COLOUR_ROUTES:
        if v.label not in seen:
            seen.add(v.label)
            uniq.append(v)
    for label, p in build_from_payload(pl, Path(a.series_dir), Path(a.out), uniq,
                                       a.flag_below):
        print("%-28s %s" % (label, p.name))
