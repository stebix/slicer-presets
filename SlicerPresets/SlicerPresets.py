"""Slicer scripted module that wires up the segment presets at startup.

This is the packaging alternative to ``~/.slicerrc.py``: point Slicer at this
folder (Settings > Modules > Additional module paths) and the preset hook is
active in every session, without touching the single global rc file. All the
behaviour lives in the :mod:`slicer_presets` package one directory up; this
module only

* puts the repo root on ``sys.path`` and calls :func:`slicer_presets.install`
  when Slicer has finished starting,
* offers a small panel (preset picker, segment list, apply/create buttons),
* can register its own folder in Slicer's persistent module search path.

Note on names: Slicer registers this module as ``slicer.modules.slicerpresets``
(all lowercase), while ``install()`` publishes its Installation object as
``slicer.modules.slicerPresets`` (capital P). Different attributes, both valid.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import ctk
import qt
import slicer
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleLogic,
    ScriptedLoadableModuleTest,
    ScriptedLoadableModuleWidget,
)

log = logging.getLogger("slicer_presets")

MODULE_DIR = Path(__file__).resolve().parent
#: Slicer's persistent list of extra module search paths.
ADDITIONAL_PATHS_KEY = "Modules/AdditionalPaths"


def package_home() -> Path:
    """Repo root holding the ``slicer_presets`` package (``$SLICER_PRESETS_HOME`` wins)."""
    env = os.environ.get("SLICER_PRESETS_HOME")
    return Path(env) if env else MODULE_DIR.parent


def ensure_importable() -> Path:
    """Make ``import slicer_presets`` work from this module's location."""
    home = package_home()
    if str(home) not in sys.path:
        sys.path.insert(0, str(home))
    return home


def current_installation():
    """The active ``Installation`` object, or ``None`` if the hook is not running."""
    return getattr(slicer.modules, "slicerPresets", None)


def install_presets(preset_name: str | None = None, spec_path: str | Path | None = None):
    """Run :func:`slicer_presets.install`; never raises (Slicer must still start)."""
    try:
        home = ensure_importable()
        import slicer_presets

        return slicer_presets.install(spec_path=spec_path, preset_name=preset_name, home=str(home))
    except Exception:
        log.exception("slicer-presets: the SlicerPresets module could not install the preset hook")
        return None


def rc_hook_also_active() -> bool:
    """True if ``~/.slicerrc.py`` carries the generated bootstrap as well."""
    try:
        ensure_importable()
        from slicer_presets import rcfile

        path = rcfile.rc_path()
        return path.is_file() and rcfile.is_generated(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return False


class SlicerPresets(ScriptedLoadableModule):
    """Module metadata; its constructor runs during startup, before the GUI exists."""

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        parent.title = "Segment Presets"
        parent.categories = ["Segmentation"]
        parent.dependencies = []
        parent.contributors = ["slicer-presets contributors"]
        parent.helpText = (
            "Starts every new segmentation with a fixed list of segments (names, order, "
            "label values, colours) defined in a JSON preset file, and guards against the "
            "Slicer 5.10.0 scene-import crash. See README.md in the repository for setup."
        )
        parent.acknowledgementText = ""
        # Install as soon as Slicer is up. Doing it here (rather than in the widget's
        # setup()) means the hook is active without the user ever opening this module.
        slicer.app.connect("startupCompleted()", self.onStartupCompleted)

    def onStartupCompleted(self) -> None:
        if current_installation() is None:
            install_presets()


class SlicerPresetsLogic(ScriptedLoadableModuleLogic):
    """Thin bridge to the package so the widget holds no preset logic of its own."""

    def specPath(self) -> Path:
        ensure_importable()
        from slicer_presets import spec as spec_module

        return spec_module.default_spec_path(package_home())

    def loadSpecFile(self):
        """Return the parsed spec file, or raise ``SpecError``."""
        ensure_importable()
        from slicer_presets import spec as spec_module

        return spec_module.load_spec_file(self.specPath())

    def reinstall(self, presetName: str | None = None):
        return install_presets(preset_name=presetName)

    def createSegmentation(self):
        installation = current_installation()
        if installation is None:
            return None
        ensure_importable()
        from slicer_presets.segmentation import create_segmentation, current_source_volume, show_in_segment_editor

        node = create_segmentation(installation.preset, reference_volume=current_source_volume())
        show_in_segment_editor(node)
        return node

    # -- persistent registration -------------------------------------------------------
    def registeredPaths(self) -> list[str]:
        settings = slicer.app.revisionUserSettings()
        value = settings.value(ADDITIONAL_PATHS_KEY)
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value else []
        return [str(v) for v in value]

    def isRegistered(self) -> bool:
        here = os.path.normcase(os.path.normpath(str(MODULE_DIR)))
        return any(os.path.normcase(os.path.normpath(p)) == here for p in self.registeredPaths())

    def register(self) -> bool:
        """Add this folder to Slicer's module search path. Returns True if it changed."""
        if self.isRegistered():
            return False
        paths = self.registeredPaths() + [str(MODULE_DIR)]
        slicer.app.revisionUserSettings().setValue(ADDITIONAL_PATHS_KEY, paths)
        log.info("slicer-presets: registered module path %s (restart Slicer to take effect)", MODULE_DIR)
        return True


class SlicerPresetsWidget(ScriptedLoadableModuleWidget):
    """Panel shown in the Segmentation category."""

    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        self.logic = SlicerPresetsLogic()
        self._updating = False

    def setup(self) -> None:
        ScriptedLoadableModuleWidget.setup(self)

        presetBox = ctk.ctkCollapsibleButton()
        presetBox.text = "Preset"
        self.layout.addWidget(presetBox)
        boxLayout = qt.QVBoxLayout(presetBox)
        form = qt.QFormLayout()
        boxLayout.addLayout(form)

        self.presetSelector = qt.QComboBox()
        self.presetSelector.toolTip = "Presets defined in the spec file; switching re-installs the hook."
        self.presetSelector.connect("currentIndexChanged(int)", self.onPresetChanged)
        form.addRow("Preset:", self.presetSelector)

        self.descriptionLabel = qt.QLabel()
        self.descriptionLabel.wordWrap = True
        form.addRow("Description:", self.descriptionLabel)

        self.specLabel = qt.QLabel()
        self.specLabel.wordWrap = True
        self.specLabel.textInteractionFlags = qt.Qt.TextSelectableByMouse
        form.addRow("Spec file:", self.specLabel)

        self.statusLabel = qt.QLabel()
        self.statusLabel.wordWrap = True
        form.addRow("Status:", self.statusLabel)

        self.segmentTable = qt.QTableWidget()
        self.segmentTable.columnCount = 2
        self.segmentTable.setHorizontalHeaderLabels(["Segment", "Label"])
        self.segmentTable.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        self.segmentTable.horizontalHeader().setSectionResizeMode(1, qt.QHeaderView.ResizeToContents)
        self.segmentTable.verticalHeader().visible = False
        self.segmentTable.selectionMode = qt.QAbstractItemView.NoSelection
        self.segmentTable.setMinimumHeight(140)
        boxLayout.addWidget(self.segmentTable)

        self.applyButton = qt.QPushButton("Apply preset to current segmentation")
        self.applyButton.toolTip = "Add the preset segments to the Segment Editor's segmentation, creating one if needed."
        self.applyButton.connect("clicked()", self.onApply)
        boxLayout.addWidget(self.applyButton)

        self.createButton = qt.QPushButton("Create new segmentation from preset")
        self.createButton.connect("clicked()", self.onCreate)
        boxLayout.addWidget(self.createButton)

        self.reloadButton = qt.QPushButton("Reload spec file")
        self.reloadButton.toolTip = "Re-read the JSON file after editing it, and re-install the hook."
        self.reloadButton.connect("clicked()", self.onReload)
        boxLayout.addWidget(self.reloadButton)

        setupBox = ctk.ctkCollapsibleButton()
        setupBox.text = "Setup"
        setupBox.collapsed = True
        self.layout.addWidget(setupBox)
        setupLayout = qt.QVBoxLayout(setupBox)

        self.registrationLabel = qt.QLabel()
        self.registrationLabel.wordWrap = True
        setupLayout.addWidget(self.registrationLabel)

        self.registerButton = qt.QPushButton("Load this module automatically at startup")
        self.registerButton.toolTip = "Add this folder to Slicer's additional module paths."
        self.registerButton.connect("clicked()", self.onRegister)
        setupLayout.addWidget(self.registerButton)

        self.rcWarningLabel = qt.QLabel()
        self.rcWarningLabel.wordWrap = True
        setupLayout.addWidget(self.rcWarningLabel)

        self.layout.addStretch(1)
        self.refresh()

    def enter(self) -> None:
        ScriptedLoadableModuleWidget.enter(self)
        self.refresh()

    # -- state ---------------------------------------------------------------------------
    def refresh(self) -> None:
        self._updating = True
        try:
            self._refreshPresetList()
        finally:
            self._updating = False
        self._refreshStatus()
        self._refreshSegments()
        self._refreshSetup()

    def _refreshPresetList(self) -> None:
        self.specLabel.text = str(self.logic.specPath())
        self.presetSelector.clear()
        try:
            specFile = self.logic.loadSpecFile()
        except Exception as exc:
            self.presetSelector.enabled = False
            self.descriptionLabel.text = "<b>" + str(exc) + "</b>"
            return
        self.presetSelector.enabled = True
        installation = current_installation()
        active = installation.preset.name if installation else specFile.default
        for name in specFile.names:
            self.presetSelector.addItem(name)
        index = self.presetSelector.findText(active)
        if index >= 0:
            self.presetSelector.currentIndex = index
        preset = specFile.presets.get(active)
        self.descriptionLabel.text = (preset.description if preset else "") or "-"

    def _refreshStatus(self) -> None:
        installation = current_installation()
        if installation is None:
            self.statusLabel.text = "<b>hook not installed</b> - use Reload spec file"
            return
        options = installation.preset.options
        parts = [
            str(len(installation.preset.segments)) + " segments",
            "auto-apply on" if options.apply_to_new_segmentations else "auto-apply off",
            "import guard on" if installation.guard and installation.guard.installed else "import guard off",
        ]
        self.statusLabel.text = "active: " + ", ".join(parts)

    def _refreshSegments(self) -> None:
        installation = current_installation()
        segments = installation.preset.segments if installation else ()
        self.segmentTable.setRowCount(len(segments))
        for row, segment in enumerate(segments):
            pixmap = qt.QPixmap(14, 14)
            pixmap.fill(qt.QColor(*[int(round(c * 255)) for c in segment.color]))
            nameItem = qt.QTableWidgetItem(segment.name)
            nameItem.setIcon(qt.QIcon(pixmap))
            nameItem.setFlags(qt.Qt.ItemIsEnabled)
            labelItem = qt.QTableWidgetItem("auto" if segment.label_value is None else str(segment.label_value))
            labelItem.setFlags(qt.Qt.ItemIsEnabled)
            self.segmentTable.setItem(row, 0, nameItem)
            self.segmentTable.setItem(row, 1, labelItem)
        enabled = installation is not None
        self.applyButton.enabled = enabled
        self.createButton.enabled = enabled

    def _refreshSetup(self) -> None:
        if self.logic.isRegistered():
            self.registrationLabel.text = "This module is registered to load at startup from<br><i>" + str(MODULE_DIR) + "</i>"
            self.registerButton.enabled = False
        else:
            self.registrationLabel.text = (
                "This module is <b>not</b> in Slicer's permanent module path. It was loaded from<br><i>"
                + str(MODULE_DIR)
                + "</i><br>and will be gone after a restart unless you register it."
            )
            self.registerButton.enabled = True
        self.rcWarningLabel.text = (
            "<b>Note:</b> ~/.slicerrc.py also installs the preset hook. "
            "That is harmless (the last one wins) but redundant - you can delete the rc file."
            if rc_hook_also_active()
            else ""
        )

    # -- actions -------------------------------------------------------------------------
    def onPresetChanged(self, index: int) -> None:
        if self._updating or index < 0:
            return
        self.logic.reinstall(self.presetSelector.currentText)
        self._refreshStatus()
        self._refreshSegments()

    def onApply(self) -> None:
        installation = current_installation()
        if installation is not None:
            installation.apply_to_current()

    def onCreate(self) -> None:
        self.logic.createSegmentation()

    def onReload(self) -> None:
        self.logic.reinstall(self.presetSelector.currentText or None)
        self.refresh()

    def onRegister(self) -> None:
        changed = self.logic.register()
        self._refreshSetup()
        slicer.util.infoDisplay(
            "Module path registered. Restart Slicer to load the presets automatically."
            if changed
            else "This module path was already registered.",
            windowTitle="Segment Presets",
        )


class SlicerPresetsTest(ScriptedLoadableModuleTest):
    """Self-test, runnable from the Reload & Test panel in developer mode."""

    def setUp(self) -> None:
        slicer.mrmlScene.Clear(0)
        install_presets()

    def runTest(self) -> None:
        self.setUp()
        self.test_PresetAppliedToNewSegmentation()

    def test_PresetAppliedToNewSegmentation(self) -> None:
        self.delayDisplay("Creating an empty segmentation node")
        installation = current_installation()
        assert installation is not None, "preset hook is not installed"
        expected = len(installation.preset.segments)

        node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "TestSegmentation")
        slicer.app.processEvents()
        actual = node.GetSegmentation().GetNumberOfSegments()
        assert actual == expected, "expected %d preset segments, got %d" % (expected, actual)

        names = [node.GetSegmentation().GetNthSegment(i).GetName() for i in range(actual)]
        assert names == [s.name for s in installation.preset.segments], "unexpected segment names: %s" % names
        self.delayDisplay("Passed: %d segments applied from preset '%s'" % (actual, installation.preset.name))
