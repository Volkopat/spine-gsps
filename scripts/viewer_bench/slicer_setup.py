"""Run INSIDE 3D Slicer's python to report its build and install bench extensions.

Slicer has no GUI installer requirement on Windows: the published .exe is an NSIS
archive and 7-Zip extracts it, and the extracted tree runs headless. This script
is the non interactive half, so the whole Slicer leg of the bench needs no clicks.

Invoke from the host, not from the spinelab interpreter:

    Slicer.exe --no-main-window --no-splash --python-script slicer_setup.py \
               --exit-after-startup

Add --install to actually fetch extensions, otherwise it only reports. dcmqi is
what reads and writes DICOM SEG; QuantitativeReporting pulls dcmqi in and adds the
segmentation reporting UI. Neither reads a Grayscale Softcopy Presentation State,
which is the point: Slicer sits on the SEG side of the matrix, not the GSPS side.
"""
import sys

import slicer

WANTED = ["QuantitativeReporting", "SlicerDcm2nii"]
# dcmqi ships as a dependency of QuantitativeReporting rather than as a
# separately installable extension in recent Slicer releases.


def report():
    print("SLICER version   %s" % slicer.app.applicationVersion)
    print("SLICER revision  %s" % slicer.app.revision)
    print("SLICER os        %s" % slicer.app.os)
    print("SLICER extensions dir %s" % slicer.app.extensionsInstallPath)
    emm = slicer.app.extensionsManagerModel()
    try:
        installed = list(emm.installedExtensions)
    except Exception as exc:
        installed = []
        print("SLICER cannot list installed extensions: %s" % exc)
    print("SLICER installed %d extension(s): %s"
          % (len(installed), ", ".join(sorted(installed)) or "none"))
    return emm, installed


def install(emm, installed):
    for name in WANTED:
        if name in installed:
            print("SLICER %s already installed" % name)
            continue
        try:
            ok = emm.downloadAndInstallExtensionByName(name, True, True)
            print("SLICER install %-24s -> %s" % (name, ok))
        except TypeError:
            # Older signature takes only the name.
            try:
                ok = emm.downloadAndInstallExtensionByName(name)
                print("SLICER install %-24s -> %s (legacy signature)" % (name, ok))
            except Exception as exc:
                print("SLICER install %-24s -> FAILED %s: %s"
                      % (name, type(exc).__name__, exc))
        except Exception as exc:
            print("SLICER install %-24s -> FAILED %s: %s"
                  % (name, type(exc).__name__, exc))


def probe_seg_support():
    """Can this Slicer read a DICOM SEG, and can it read a GSPS."""
    try:
        import DICOMSegmentationPlugin  # noqa: F401
        print("SLICER DICOM SEG plugin  present")
    except Exception as exc:
        print("SLICER DICOM SEG plugin  ABSENT: %s: %s" % (type(exc).__name__, exc))
    try:
        from DICOMLib import DICOMPlugin  # noqa: F401
        import slicer as _s
        names = sorted(_s.modules.dicomPlugins.keys())
        print("SLICER dicom plugins     %s" % ", ".join(names))
    except Exception as exc:
        print("SLICER dicom plugins     unavailable: %s" % exc)


def main():
    emm, installed = report()
    if "--install" in sys.argv:
        emm.interactive = False
        install(emm, installed)
        print("SLICER note: a restart is required before installed extensions load")
    probe_seg_support()
    sys.stdout.flush()


main()
