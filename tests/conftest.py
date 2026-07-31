"""Shared fixtures for the spinelab regression suite.

Two design rules for this suite:

1. No test may require the private baseline repository or any clinical DICOM.
   The GSPS source object used by the writer tests is therefore SYNTHETIC and
   built here from GSPS IOD attributes only, plus the five out-of-IOD text style
   attributes the deployed emitter actually wrote, so that the "strip the text
   route" behaviour has something to strip.

2. Anything that needs an external store or an external binary skips with a
   message naming what is missing, rather than failing. A red suite on a machine
   without the data teaches nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The package is not pip installed in the working environment, so make `src`
# importable for a bare `pytest` run from the repository root.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pydicom  # noqa: E402
from pydicom.dataset import Dataset  # noqa: E402
from pydicom.uid import ExplicitVRLittleEndian  # noqa: E402

from spinelab.gsps import writer as W  # noqa: E402

# Fixed UIDs so the fixture is byte stable across runs.
STUDY_UID = "1.2.826.0.1.3680043.10.1000.1"
SERIES_UID = "1.2.826.0.1.3680043.10.1000.2"
GSPS_UID = "1.2.826.0.1.3680043.10.1000.3"
IMAGE_UID = "1.2.826.0.1.3680043.10.1000.4"
IMAGE_SERIES_UID = "1.2.826.0.1.3680043.10.1000.5"
CT_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.2"

# The annotation content the variants must hold fixed.
SOURCE_TEXTS = ("C3 0.91", "C4 0.88", "T1 0.72", "L1 0.31")
SOURCE_LINES = (
    [10.0, 20.0, 60.0, 20.0],
    [10.0, 40.0, 60.0, 40.0],
    [12.0, 60.0, 62.0, 60.0],
    [14.0, 80.0, 64.0, 80.0],
)
LAYER_OK = "SPINE_OK"
LAYER_FLAG = "SPINE_FLAG"

# The ten Type 1 attributes of the Line Style Sequence macro, PS3.3 C.10.5.1.2.
# Named by tag rather than by count, because the regression this guards against
# was four specific omissions.
LINE_STYLE_TYPE1_TAGS = (
    (0x0070, 0x0244),  # Shadow Style
    (0x0070, 0x0245),  # Shadow Offset X
    (0x0070, 0x0246),  # Shadow Offset Y
    (0x0070, 0x0247),  # Shadow Color CIELab Value
    (0x0070, 0x0258),  # Shadow Opacity
    (0x0070, 0x0251),  # Pattern On Color CIELab Value, the line colour
    (0x0070, 0x0284),  # Pattern On Opacity
    (0x0070, 0x0253),  # Line Thickness
    (0x0070, 0x0254),  # Line Dashing Style
    (0x0070, 0x0255),  # Line Pattern
)

# The six out-of-IOD attributes the text colour route drags in, measured on the
# 38 shipped objects, see results/gsps_conformance_baseline.md. Format is the one
# spinelab.gsps.validate stores, lowercased and without the surrounding brackets.
TEXT_ROUTE_OUT_OF_IOD_TAGS = frozenset({
    "0x0070,0x0229",  # CSS Font Name
    "0x0070,0x0231",  # Text Style Sequence
    "0x0070,0x0241",  # Text Color CIELab Value
    "0x0070,0x0242",  # Horizontal Alignment
    "0x0070,0x0243",  # Vertical Alignment
    "0x0070,0x0244",  # Shadow Style
})


def _text_style(colour) -> Dataset:
    """The text style the deployed generate_gsps_4.py wrote, out of IOD and all."""
    st = Dataset()
    st.CSSFontName = "Arial"
    st.HorizontalAlignment = "LEFT"
    st.VerticalAlignment = "TOP"
    st.ShadowStyle = "OFF"
    st[W.TAG_TEXT_COLOR] = pydicom.DataElement(W.TAG_TEXT_COLOR, "US", colour)
    return st


def _line_style(colour) -> Dataset:
    st = Dataset()
    st.ShadowStyle = "OFF"
    st.ShadowOffsetX = 0.0
    st.ShadowOffsetY = 0.0
    st.ShadowColorCIELabValue = colour
    st.ShadowOpacity = 0.0
    st.LineThickness = 2.0
    st.LineDashingStyle = "DASHED"
    st.LinePattern = 255
    st.PatternOnOpacity = 1.0
    st[W.TAG_PATTERN_ON_COLOR] = pydicom.DataElement(W.TAG_PATTERN_ON_COLOR, "US", colour)
    return st


def _text_object(value: str, x: float, y: float, colour) -> Dataset:
    t = Dataset()
    t.AnchorPointAnnotationUnits = "PIXEL"
    t.UnformattedTextValue = value
    t.AnchorPoint = [x, y]
    t.AnchorPointVisibility = "N"
    t[W.TAG_TEXT_STYLE] = pydicom.DataElement(W.TAG_TEXT_STYLE, "SQ", [_text_style(colour)])
    return t


def _graphic_object(points: list[float], colour) -> Dataset:
    g = Dataset()
    g.GraphicAnnotationUnits = "PIXEL"
    g.GraphicDimensions = 2
    g.NumberOfGraphicPoints = len(points) // 2
    g.GraphicData = list(points)
    g.GraphicType = "POLYLINE"
    g.GraphicFilled = "N"
    g[W.TAG_LINE_STYLE] = pydicom.DataElement(W.TAG_LINE_STYLE, "SQ", [_line_style(colour)])
    return g


def build_source_gsps() -> Dataset:
    """A minimal, GSPS-IOD-only presentation state with one flagged layer.

    Deliberately mirrors the shipped objects in the two respects the tests care
    about: the quality flag rides on out-of-IOD text colour, and the required
    attributes InstanceNumber / SeriesNumber / StudyID / Laterality are present
    so that the required_attrs=False arm has something to delete. The shipped
    objects lack all four, so that code path was never exercised in production.
    """
    ds = Dataset()
    ds.SpecificCharacterSet = "ISO_IR 100"

    # Patient
    ds.PatientName = "TEST^SYNTHETIC"
    ds.PatientID = "SYN0001"
    ds.PatientBirthDate = ""
    ds.PatientSex = ""

    # General Study
    ds.StudyInstanceUID = STUDY_UID
    ds.StudyDate = "20260730"
    ds.StudyTime = "120000"
    ds.ReferringPhysicianName = ""
    ds.StudyID = "STU1"
    ds.AccessionNumber = ""

    # General Series and Presentation Series
    ds.Modality = "PR"
    ds.SeriesInstanceUID = SERIES_UID
    ds.SeriesNumber = 9001
    ds.Laterality = ""          # zero length on purpose, the writer must remove it

    # General Equipment
    ds.Manufacturer = "Softneta"
    ds.ManufacturerModelName = "MedDream"

    # Presentation State Identification, Content Identification Macro
    ds.InstanceNumber = 1
    ds.ContentLabel = "SPINE_QS"
    ds.ContentDescription = "synthetic fixture"
    ds.ContentCreatorName = ""
    ds.PresentationCreationDate = "20260730"
    ds.PresentationCreationTime = "120100"

    # Presentation State Relationship
    ref_img = Dataset()
    ref_img.ReferencedSOPClassUID = CT_SOP_CLASS
    ref_img.ReferencedSOPInstanceUID = IMAGE_UID
    ref_ser = Dataset()
    ref_ser.SeriesInstanceUID = IMAGE_SERIES_UID
    ref_ser.ReferencedImageSequence = [ref_img]
    ds.ReferencedSeriesSequence = [ref_ser]

    # Displayed Area
    da = Dataset()
    da.DisplayedAreaTopLeftHandCorner = [1, 1]
    da.DisplayedAreaBottomRightHandCorner = [256, 256]
    da.PresentationSizeMode = "SCALE TO FIT"
    da.PresentationPixelAspectRatio = [1, 1]
    ds.DisplayedAreaSelectionSequence = [da]

    # Graphic Layer
    l_ok = Dataset()
    l_ok.GraphicLayer = LAYER_OK
    l_ok.GraphicLayerOrder = 1
    l_flag = Dataset()
    l_flag.GraphicLayer = LAYER_FLAG
    l_flag.GraphicLayerOrder = 2
    ds.GraphicLayerSequence = [l_ok, l_flag]

    # Graphic Annotation. Three normal annotations on one layer, one flagged
    # annotation on the other, flagged by RED text colour exactly as deployed.
    ann_ok = Dataset()
    ann_ok.GraphicLayer = LAYER_OK
    ann_ok.TextObjectSequence = [
        _text_object(SOURCE_TEXTS[i], SOURCE_LINES[i][0], SOURCE_LINES[i][1], W.YELLOW)
        for i in range(3)
    ]
    ann_ok.GraphicObjectSequence = [
        _graphic_object(list(SOURCE_LINES[i]), W.YELLOW) for i in range(3)
    ]

    ann_flag = Dataset()
    ann_flag.GraphicLayer = LAYER_FLAG
    ann_flag.TextObjectSequence = [
        _text_object(SOURCE_TEXTS[3], SOURCE_LINES[3][0], SOURCE_LINES[3][1], W.RED)
    ]
    ann_flag.GraphicObjectSequence = [_graphic_object(list(SOURCE_LINES[3]), W.YELLOW)]
    ds.GraphicAnnotationSequence = [ann_ok, ann_flag]

    # Spatial Transformation and Softcopy Presentation LUT
    ds.ImageRotation = 0
    ds.ImageHorizontalFlip = "N"
    ds.PresentationLUTShape = "IDENTITY"

    # SOP Common
    ds.SOPClassUID = W.GSPS_SOP_CLASS
    ds.SOPInstanceUID = GSPS_UID
    return ds


def build_source_image() -> Dataset:
    """A stand in for a referenced source image, for PresentationPixelSpacing."""
    img = Dataset()
    img.SOPClassUID = CT_SOP_CLASS
    img.SOPInstanceUID = IMAGE_UID
    img.PixelSpacing = [0.4297, 0.4297]
    return img


@pytest.fixture
def source_gsps() -> Dataset:
    return build_source_gsps()


@pytest.fixture
def source_image() -> Dataset:
    return build_source_image()


@pytest.fixture
def transfer_syntax():
    return ExplicitVRLittleEndian
