"""Regression test for the SlicerPresets scripted module (option C packaging).

Run it *without* the rc hook, so the module is the only thing that can install
the preset hook:

    Slicer.exe --no-splash --ignore-slicerrc \
        --additional-module-path <repo>/SlicerPresets \
        --python-script tests/slicer/module_regression.py

Also works with --no-main-window (the widget checks are then skipped).
Exit code 0 on success.
"""

import traceback

import qt
import slicer

failures = []


def check(cond, msg):
    print(("[module] PASS " if cond else "[module] FAIL ") + msg)
    if not cond:
        failures.append(msg)


def finish():
    print("[module] " + ("OK" if not failures else "FAILED: " + "; ".join(failures)))
    slicer.app.exit(0 if not failures else 1)


def run():
    try:
        # 1) the module itself was discovered on the additional module path
        module = getattr(slicer.modules, "slicerpresets", None)
        check(module is not None, "Slicer discovered the SlicerPresets module")

        # 2) it installed the preset hook at startup, with no rc file involved
        installation = getattr(slicer.modules, "slicerPresets", None)
        check(installation is not None, "module installed the preset hook at startup")
        if installation is None:
            return finish()
        check(len(installation.preset.segments) == 5, "preset loaded (%d segments)" % len(installation.preset.segments))
        check(installation.guard is not None and installation.guard.installed, "import guard installed")
        check(installation.watcher is not None, "new-segmentation watcher installed")

        import SlicerPresets

        check(SlicerPresets.current_installation() is installation, "current_installation() finds the Installation")
        check(SlicerPresets.package_home().joinpath("slicer_presets").is_dir(), "package_home() points at the repo root")

        # 3) the hook actually works: an empty segmentation gets the preset
        node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "FromModule")
        slicer.app.processEvents()
        n = node.GetSegmentation().GetNumberOfSegments()
        check(n == 5, "empty segmentation populated by the module's hook (%d segments)" % n)

        # 4) logic helpers used by the Setup section (read-only: never call register())
        logic = SlicerPresets.SlicerPresetsLogic()
        check(logic.specPath().is_file(), "logic.specPath() resolves to an existing spec file")
        check(len(logic.loadSpecFile().names) >= 1, "logic.loadSpecFile() parses the spec")
        check(isinstance(logic.registeredPaths(), list), "logic.registeredPaths() returns a list")
        check(isinstance(logic.isRegistered(), bool), "logic.isRegistered() returns a bool")

        if slicer.app.commandOptions().noMainWindow:
            print("[module] no main window: skipping the widget checks")
            return finish()
        qt.QTimer.singleShot(0, widget_checks)
    except Exception:
        traceback.print_exc()
        failures.append("exception in run()")
        finish()


def widget_checks():
    try:
        import SlicerPresets

        # 5) opening the module builds the panel without errors and shows the preset
        slicer.util.selectModule("SlicerPresets")
        widget = slicer.modules.slicerpresets.widgetRepresentation().self()
        check(isinstance(widget, SlicerPresets.SlicerPresetsWidget), "module widget created")
        installation = SlicerPresets.current_installation()
        check(widget.presetSelector.count == len(installation.spec_file.names), "preset selector lists every preset")
        check(widget.presetSelector.currentText == installation.preset.name, "preset selector shows the active preset")
        check(widget.segmentTable.rowCount == len(installation.preset.segments), "segment table lists the preset segments")
        check(widget.segmentTable.item(0, 0).text() == installation.preset.segments[0].name, "first table row is the first segment")
        check(widget.applyButton.enabled, "apply button enabled while the hook is active")
        check("active:" in widget.statusLabel.text, "status label reports the hook as active")

        # 6) the buttons work
        widget.onCreate()
        slicer.app.processEvents()
        created = [n for n in slicer.util.getNodesByClass("vtkMRMLSegmentationNode") if n.GetName().startswith(installation.preset.node_name)]
        check(bool(created), "create button made a segmentation named after the preset")
        check(bool(created) and created[0].GetSegmentation().GetNumberOfSegments() == 5, "created segmentation carries the preset segments")

        widget.onReload()
        slicer.app.processEvents()
        check(SlicerPresets.current_installation() is not None, "reload button re-installed the hook")
        check(widget.segmentTable.rowCount == 5, "segment table still populated after reload")
    except Exception:
        traceback.print_exc()
        failures.append("exception in widget_checks()")
    finish()


qt.QTimer.singleShot(1000, run)
qt.QTimer.singleShot(90000, lambda: (failures.append("timeout"), finish()))
