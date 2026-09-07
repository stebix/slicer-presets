# slicer-presets

Segment Editor presets for 3D Slicer, defined in JSON and applied automatically:
every segmentation you create starts with your list of segments (names, order,
label values, colours). Ships as a Slicer module (or a `~/.slicerrc.py` startup hook), with a launcher
and a guard/sanitiser for a Slicer 5.10.0 crash that the previous startup
script triggered on every scene load (fixed upstream in 5.12.3; the guard is
kept for 5.10.0 and is harmless on 5.12.3).

```
slicer_presets/           Python package (works inside Slicer and standalone)
  spec.py                 JSON spec parsing/validation      (pure Python)
  scene_files.py          .mrml/.mrb sanitiser              (pure Python)
  rcfile.py, cli.py       rc bootstrap + command line       (pure Python)
  segmentation.py         create/populate segmentation nodes  (Slicer)
  guard.py                scene-import crash guard            (Slicer)
  startup.py              install(): wiring at startup        (Slicer)
SlicerPresets/            Slicer scripted module (recommended install route)
  SlicerPresets.py        module metadata, panel, calls install() at startup
presets/default.json      preset spec (InnerEar)
launch-slicer.cmd         double-click / drag-and-drop launcher
tests/                    pytest unit tests + Slicer smoke/regression scripts
```

## Requirements

* **3D Slicer 5.10.0 or newer**; **5.12.3 is recommended** because it fixes the
  scene-import crash entirely (see *Why the old setup crashed*).
  Download: <https://download.slicer.org>
* **Nothing else.** Slicer ships its own Python 3.12 (`PythonSlicer`), which runs
  both the startup hook and the `slicer_presets` command line, so no separate
  Python, pip, venv or uv installation is needed to *use* this repository. uv is
  only needed to run the unit tests, or to get `slicer-presets` as a standalone
  command instead of `PythonSlicer -m slicer_presets`.
* **Windows, macOS and Linux** are all supported. The presets, the panel and the
  import guard behave identically; only the file paths differ, plus the
  `launch-slicer.cmd` launcher, which is Windows-only (see *Launcher*).

## Where Slicer is installed

The commands below need one of two executables: the Slicer application, and the
Python interpreter bundled with it. Default locations of the official builds:

| | Slicer application | bundled Python |
|---|---|---|
| **Windows** | `%LOCALAPPDATA%\slicer.org\3D Slicer 5.12.3\Slicer.exe` | `%LOCALAPPDATA%\slicer.org\3D Slicer 5.12.3\bin\PythonSlicer.exe` |
| **macOS** | `/Applications/Slicer.app/Contents/MacOS/Slicer` | `/Applications/Slicer.app/Contents/bin/PythonSlicer` |
| **Linux** | `<extracted folder>/Slicer` | `<extracted folder>/bin/PythonSlicer` |

If yours is elsewhere, ask Slicer itself: **View > Python Console**, then

```python
import sys; print(sys.executable)        # -> the bundled Python (PythonSlicer)
print(slicer.app.applicationDirPath())   # -> the folder holding the application
```

`sys.executable` is the `PythonSlicer` path for your machine on every platform.

From here on **`Slicer`** and **`PythonSlicer`** stand for these two paths.
Substitute your own, and keep the quotes on Windows - the default path contains
spaces.

## Installation

There are two ways to hook the presets into Slicer. **Pick one.**

| | **Segment Presets module** (recommended) | `~/.slicerrc.py` hook |
|---|---|---|
| loaded via | Slicer's module search path | Slicer's user startup script |
| clashes with an rc file you already have | no | yes - it owns that single file |
| scope | per Slicer installation | shared by every Slicer installation |
| GUI | full panel + Edit-menu action | Edit-menu action only |

Having both active is harmless (the rc file installs first, the module then
stands down) but confusing; the module's *Setup* section tells you when it
happens.

The installation is the same on all three platforms - only the paths change.

### Step 1 - get the files

```
git clone <repository-url> slicer-presets
```

Put the clone somewhere permanent, because Slicer stores its absolute path:

* **Windows** `C:\Users\<you>\code\slicer-presets`
* **macOS / Linux** `~/code/slicer-presets`

There is nothing to build or compile. No git? Download the ZIP and extract it -
the folder layout is all that matters.

### Step 2 - register the module with Slicer

Identical on every platform:

1. **Edit > Application Settings > Modules**
2. Drag the `SlicerPresets` folder from a file manager onto the
   **Additional module paths** list - or click the `>>` button, then **Add**, and
   select it.
   Point it at the **`SlicerPresets` sub-folder**, not at the repository root.
3. Restart Slicer when it offers to.

Prefer the keyboard? Open the Python console (**View > Python Console**, or
Ctrl+3 / Cmd+3) and run, with your own path:

```python
# Windows: use a raw string so backslashes survive
import sys; sys.path.insert(0, r"C:\Users\<you>\code\slicer-presets\SlicerPresets")
# macOS / Linux:
# import sys; sys.path.insert(0, "/home/<you>/code/slicer-presets/SlicerPresets")
import SlicerPresets; SlicerPresets.SlicerPresetsLogic().register()
```

Then restart Slicer.

To **try it without changing any setting**, start Slicer once with the module
path on the command line:

```bat
:: Windows
"%LOCALAPPDATA%\slicer.org\3D Slicer 5.12.3\Slicer.exe" --additional-module-path "C:\Users\<you>\code\slicer-presets\SlicerPresets"
```

```sh
# macOS
/Applications/Slicer.app/Contents/MacOS/Slicer --additional-module-path ~/code/slicer-presets/SlicerPresets

# Linux
~/Slicer-5.12.3-linux-amd64/Slicer --additional-module-path ~/code/slicer-presets/SlicerPresets
```

The module's **Setup** section then offers a *Load this module automatically at
startup* button that performs the registration above, so you never have to type
the path twice.

### Step 3 - check that it works

1. The module list (**Modules:** drop-down) contains **Segmentation > Segment
   Presets**. Open it: it shows the spec file it read, the active preset, its
   segments with their colours, and a status line such as
   `active: 5 segments, auto-apply on, import guard on`.
2. Switch to **Segment Editor** and press **Create new segmentation**. It comes
   up with the preset segments already in it instead of an empty list.

That is the whole installation. Segmentations that come *from* a scene or a
loaded `.seg.nrrd` are never modified - that is deliberate, so opening a case
never rewrites its segments.

### Step 4 - make it your own preset

Edit `presets/default.json` (format under *Preset JSON*), then press **Reload
spec file** in the panel - no restart needed. To check a file before loading it,
run the command line from the clone directory:

```bat
:: Windows
cd C:\Users\<you>\code\slicer-presets
"%LOCALAPPDATA%\slicer.org\3D Slicer 5.12.3\bin\PythonSlicer.exe" -m slicer_presets validate
```

```sh
# macOS
cd ~/code/slicer-presets
/Applications/Slicer.app/Contents/bin/PythonSlicer -m slicer_presets validate

# Linux
cd ~/code/slicer-presets
~/Slicer-5.12.3-linux-amd64/bin/PythonSlicer -m slicer_presets validate
```

Running from the clone is what puts the package on the import path; no
`PYTHONPATH` and no install step are involved.

Several presets can live in one file; the panel's drop-down switches between
them. To keep a personal file without touching the shared one, point
`SLICER_PRESETS_SPEC` at it:

```bat
:: Windows, for this session / permanently
set SLICER_PRESETS_SPEC=C:\Users\<you>\my-presets.json
setx SLICER_PRESETS_SPEC "C:\Users\<you>\my-presets.json"
```

```sh
# macOS / Linux, for this session / permanently
export SLICER_PRESETS_SPEC=~/my-presets.json
echo 'export SLICER_PRESETS_SPEC=~/my-presets.json' >> ~/.zshrc   # or ~/.bashrc
```

Slicer must be started from a shell that has the variable set, so on macOS a
variable exported in `~/.zshrc` will not reach Slicer when it is launched from
the Dock or Finder. Editing `presets/default.json`, or using the panel's preset
drop-down, avoids the problem entirely.

### Alternative: the `~/.slicerrc.py` hook

The original mechanism, still supported, and what `launch-slicer.cmd` sets up.
It writes a 10-line bootstrap into Slicer's user startup script, which lives at
`~/.slicerrc.py` on every platform (`C:\Users\<you>\.slicerrc.py` on Windows).
Run from the clone directory:

```bat
:: Windows
cd C:\Users\<you>\code\slicer-presets
"%LOCALAPPDATA%\slicer.org\3D Slicer 5.12.3\bin\PythonSlicer.exe" -m slicer_presets install-rc
"%LOCALAPPDATA%\slicer.org\3D Slicer 5.12.3\bin\PythonSlicer.exe" -m slicer_presets show
```

```sh
# macOS / Linux
cd ~/code/slicer-presets
/Applications/Slicer.app/Contents/bin/PythonSlicer -m slicer_presets install-rc
/Applications/Slicer.app/Contents/bin/PythonSlicer -m slicer_presets show
```

With uv installed, `uv run slicer-presets install-rc` works the same on all
platforms.

`install-rc` refuses to overwrite an rc file it did not write; `--force`
replaces it and keeps a timestamped backup next to it. Because there is only one
such file per user account, this route is the one that can collide with other
Slicer customisations you may already have.

## Usage routes

Once installed, there are five ways to reach the presets. The first two need no
action at all.

| route | what it gives you | available with |
|---|---|---|
| **Automatic** | every segmentation *created empty* is filled with the preset segments - Segment Editor "create new", the Segmentations module, or a script | both install routes |
| **Edit menu** | *Apply segment preset '\<name\>'* applies the preset to the segmentation currently in the Segment Editor, creating one if there is none | both install routes |
| **Segment Presets panel** | switch preset, apply, create a new segmentation, reload the spec file after editing it, register the module path | module route only |
| **Python console** | the full API on `slicer.modules.slicerPresets` - see *Using it from the Slicer Python console* | both install routes |
| **Command line** | `validate`, `show`, `sanitize`, `install-rc`, `launch` outside Slicer - see *Command line* | both install routes |

Deliberate non-behaviours, in every route: segmentations loaded from a scene or
a `.seg.nrrd` are never rewritten, no module is switched at startup, and no
segmentation is created at startup unless `createOnStartup` is turned on.

## Command line

`PythonSlicer -m slicer_presets <command>`, run from the clone directory (or
`slicer-presets <command>` with uv). Every command works on all platforms:

| command | what it does |
|---|---|
| `validate [SPEC]` | parse a spec file and print its presets, colours and options |
| `show` | print the resolved paths: package, spec, rc file, Slicer executable |
| `sanitize FILE...` | rewrite `.mrb`/`.mrml` so they load safely on 5.10.0 - see *Sanitising scene files* |
| `install-rc` | write the `~/.slicerrc.py` bootstrap |
| `launch [FILES...]` | start Slicer with the preset environment set - see *Launcher* |

## Updating

```
cd <clone>
git pull
```

Restart Slicer. Nothing is ever copied into the Slicer installation - both the
module and the rc hook run the code straight from the clone, so a pull is the
whole update, on every platform. This also means the clone must stay where it
is; if you move it, re-register the new path (and re-run `install-rc` if you use
the rc hook).

Upgrading Slicer itself does not disturb either route, because nothing was
written into the Slicer install directory. Module paths are remembered per
Slicer revision, though, so after a major upgrade you may need to add the
`SlicerPresets` path once more.

## Uninstalling or disabling

* **Module:** Edit > Application Settings > Modules, remove the path from
  *Additional module paths*, restart.
* **rc hook:** delete `~/.slicerrc.py`, or restore one of the `.bak-*` files
  next to it.
* **Just for one session:** `--ignore-slicerrc` disables the rc hook (it does
  not disable the module); `slicer-presets launch --no-presets` does the same.
* **Keep the presets but drop the crash guard:** `"sceneGuard": false` in the
  preset options.

## Launcher

**Windows only.** `launch-slicer.cmd [files...]`, or `slicer-presets launch
[files...]`, picks the newest install under `%LOCALAPPDATA%\slicer.org`
(override with `--slicer` or `SLICER_EXE`), sets the preset environment and
opens the files. Options: `--preset NAME`, `--spec FILE`, `--sanitize` (strip
saved editor state from scene files first), `--no-presets` (plain Slicer via
`--ignore-slicerrc`), `--no-splash`, `--wait`, and `-- <extra Slicer args>`.

Create a shortcut to `launch-slicer.cmd` for a one-click start; scene files can
be dropped onto it.

On **macOS and Linux** there is no `.cmd` equivalent and the automatic search
for installed Slicer versions does not apply (it only knows the Windows
`%LOCALAPPDATA%\slicer.org` layout). `slicer-presets launch` still works if you
tell it where Slicer is:

```sh
export SLICER_EXE=/Applications/Slicer.app/Contents/MacOS/Slicer
PythonSlicer -m slicer_presets launch case.mrb --sanitize
```

or pass `--slicer /path/to/Slicer` per call. The launcher is a convenience only:
with the module installed, starting Slicer normally gives you the presets, and
`sanitize` can be run on its own beforehand.

## Troubleshooting

| symptom | cause and fix |
|---|---|
| **Segment Presets** is missing from the module list | The path was not registered, points at the repository root instead of `<clone>/SlicerPresets`, or Slicer was not restarted. Check Edit > Application Settings > Modules. |
| It disappeared after upgrading Slicer | Additional module paths are stored per Slicer revision; add the path again. |
| Panel says **hook not installed** | The spec file could not be read; the Description line shows the parse error (line and column). Fix `presets/default.json` and press *Reload spec file*. |
| New segmentations still come up empty | `applyToNewSegmentations` is off, or the segmentation was **loaded** from a file rather than created - loaded nodes are never touched by design. |
| Segments appear but with the wrong colours/order | Another spec file is in use. The panel's *Spec file* line shows which one; `SLICER_PRESETS_SPEC` overrides it. |
| `SLICER_PRESETS_SPEC` seems to be ignored (macOS) | Applications started from the Dock or Finder do not inherit shell variables. Start Slicer from a terminal, or edit the spec file instead. |
| Slicer **5.10.0** still crashes when opening a scene | The guard must be active *before* the scene loads. Confirm the panel says `import guard on`, or upgrade to 5.12.3, or run `sanitize` on the file. |
| The panel warns that `~/.slicerrc.py` is also active | Both mechanisms are installed. Harmless, but delete the rc file to keep things clear. |
| `slicer-presets launch` cannot find Slicer (macOS/Linux) | Automatic detection is Windows-only. Set `SLICER_EXE` or pass `--slicer`. |
| Nothing works and you need the log | Windows `%LOCALAPPDATA%\Temp\Slicer\Slicer_<version>_*.log`; macOS/Linux the terminal Slicer was started from, or Help > Report a Bug. The hook logs lines starting with `slicer-presets:`. |

## Preset JSON

```json
{
  "version": 1,
  "default": "InnerEar",
  "options": { "applyToNewSegmentations": true, "createOnStartup": false,
               "openSegmentEditor": false, "sceneGuard": true, "menuAction": true },
  "presets": [
    {
      "name": "InnerEar",
      "description": "optional",
      "options": { "nodeName": "InnerEar" },
      "segments": [
        { "name": "Cochlea",   "labelValue": 1, "color": "#E6194B" },
        { "name": "Vestibule", "labelValue": 2, "color": [60, 180, 75], "id": "vestibule",
          "order": 1, "terminology": "optional raw Slicer terminology string" }
      ]
    }
  ]
}
```

* A file with a single top-level preset (`name` + `segments`, the old format) is
  still accepted.
* `color`: `"#RRGGBB"`, `[r, g, b]` floats 0-1, or ints 0-255.
* `labelValue`: positive integer used in exported label maps; give it for all
  segments or for none. `order` sorts; `id` sets the segment ID (default: name).
* Options (file level = defaults, preset level overrides):

  | key | default | meaning |
  |---|---|---|
  | `applyToNewSegmentations` | true | populate segmentation nodes created empty |
  | `createOnStartup` | false | create a preset segmentation after startup |
  | `skipIfSceneHasSegmentation` | true | ...unless the scene already has one |
  | `openSegmentEditor` | false | switch to the Segment Editor after that (creates the widget early: keep off on 5.10.0; safe on 5.12.3) |
  | `sceneGuard` | true | install the import guard |
  | `menuAction` | true | Edit-menu action |
  | `nodeName` | preset name | name of created segmentation nodes |

Unknown keys are rejected so typos are caught by `slicer-presets validate`.

## Using it from the Slicer Python console

Available with either install route, on every platform:

```python
inst = slicer.modules.slicerPresets          # the active Installation
inst.preset.name, [s.name for s in inst.preset.segments]
inst.apply_to_current()                      # apply to the editor's segmentation and show it
from slicer_presets.segmentation import apply_preset, create_segmentation
apply_preset(node, inst.preset)              # merge into any node (updates existing, adds missing)
slicer_presets.install(preset_name="Other")  # switch preset at runtime
```

## Sanitising scene files

Makes a scene file safe to open on Slicer 5.10.0 even where the guard is not
installed - worth doing to any `.mrb` before sharing it with someone whose
Slicer version you do not know.

```
slicer-presets sanitize case.mrb                # -> case.safe.mrb
slicer-presets sanitize case.mrb --in-place     # keeps case.mrb.bak
slicer-presets sanitize case.mrb --mode node    # drop the whole SegmentEditor node
```

Without uv, from the clone directory on any platform:
`PythonSlicer -m slicer_presets sanitize case.mrb`.

Default mode strips only `activeEffectName`; the remembered active effect is the
only thing lost.

## File association (Windows)

Uninstalling a Slicer version removes the `.mrb` association it owned
(`HKCU\Software\Classes\Slicer\shell\open\command`), and double-clicking a scene
then does nothing. To point Explorer at a given install:

```
reg add "HKCU\Software\Classes\Slicer\shell\open\command" /ve /t REG_SZ /d "\"%LOCALAPPDATA%\slicer.org\3D Slicer 5.12.3\Slicer.exe\" \"%1\"" /f
reg add "HKCU\Software\Classes\.mrb" /ve /t REG_SZ /d "Slicer" /f
```

or point the association at `launch-slicer.cmd` to get the launcher's options.

On macOS and Linux use the desktop environment's own *Open With* / default
application settings; nothing in this repository is involved either way, and
opening a scene by double-click never needed the presets - Slicer loads
command-line files before any startup hook runs.

## Why the old setup crashed

Symptom: Slicer 5.10.0 died while loading a large `.mrb` scene whenever
`~/.slicerrc.py` was active.

Root cause (reproduced and bisected on this machine, see *Verification*):

1. **Slicer 5.10.0 bug.** Importing a scene whose saved `SegmentEditor` node has an
   `activeEffectName` (the MRB was saved with the *Islands* effect active) while a
   Segment Editor widget exists ends in an access violation in
   `qSlicerSegmentationsModuleWidgets.dll` (Windows event log: exception
   `0xc0000005`, offset `0x2f3fc`). The singleton editor node is overwritten
   mid-import and the widget re-activates the effect before node references are
   resolved. Removing only `activeEffectName` from the scene, or not having the
   editor widget, avoids the crash. Slicer 5.8.1 loads the same file fine.
2. **The old rc script made the bug unavoidable.** It created a segmentation at
   startup and switched to the Segment Editor immediately, so the widget always
   existed by the time a scene was opened from the GUI.

Other problems in the old design that are fixed here:

* `slicerinit.py` executed `main()` at import time *and* the rc file called it
  again; each launch ran it twice and logged every line twice (print + logging).
* The startup segmentation had no reference volume and was discarded as soon as a
  scene was loaded, so it never helped in the MRB workflow; the "skip if a
  segmentation exists" gate meant loaded scenes never got the preset either.
* The rc file's `startupCompleted` handling was guesswork: in 5.8+ the rc file
  runs *after* command-line files were loaded and the window is shown, so the
  signal never fires for it.
* Everything lived on the Desktop with hard-coded paths.

Note: files opened by **double-clicking** never crashed, because Slicer loads
command-line files *before* the rc file. Also, the `.mrb` association on this PC
points at `Slicer 5.8.1\Slicer.exe`, not 5.10.0 (see *File association*).

## Design

* Two entry points, both of which only locate the package and call
  `slicer_presets.install()`, wrapped so a preset error can never break Slicer
  startup. Location overrides for both: `SLICER_PRESETS_HOME`,
  `SLICER_PRESETS_SPEC`, `SLICER_PRESET`.
  * `SlicerPresets/SlicerPresets.py` is a scripted module. Its
    `ScriptedLoadableModule.__init__` runs during module discovery and connects
    to `startupCompleted()`, so the hook is installed without the user ever
    opening the module; the panel is built only when they do. It stands down if
    an Installation already exists, so having the rc file too is harmless.
  * `~/.slicerrc.py` is a 10-line bootstrap that adds this repo to `sys.path`.
    Slicer runs it before `startupCompleted()` fires, so with both installed the
    rc file wins the race and the module skips.
* `install()` does **not** create nodes or switch modules. It
  * watches the scene: any segmentation node that is *created empty* (Segment
    Editor "create new", Segmentations module, scripts) is populated with the
    preset. Slicer's placeholder `Segment_1` is re-purposed as the first preset
    segment, so nothing stray is left. Nodes coming from a scene import or a
    loaded `.seg.nrrd` are never touched;
  * installs the **import guard**: on `StartImportEvent` the Segment Editor widget
    is detached from its parameter node; on `EndImportEvent` the saved
    `activeEffectName` is cleared on the imported editor node before anything
    re-attaches, then the widget is re-attached and the scene's segmentation and
    source volume are re-selected in the editor once the node lists have been
    refilled. This makes the 5.10.0 crash scenario load cleanly (verified with
    the original MRB, with and without clearing the scene). Only the remembered
    active effect is lost;
  * adds *Edit > Apply segment preset '<name>'* (applies to the editor's current
    segmentation, or creates one);
  * optionally (`createOnStartup`) reproduces the old behaviour.
* The preset is a plain JSON file; several presets per file, selectable by name.
* `slicer-presets sanitize` rewrites `.mrb`/`.mrml` files so they are safe to load
  on 5.10.0 even without the guard (e.g. on another machine).

## Upstream

The crash was a Slicer regression in 5.10.0 only: 5.8.1 loaded the scene fine and
**5.12.3 fixes it** (re-checked 2026-09-07 with the same unguarded script - see
*Verification*). On 5.12.3 the same import logs a warning instead of faulting
(`updateEffectsSectionFromMRML: Cannot activate effect, failed to set binary
labelmap as source representation`) and ends with no active effect - the same end
state the guard produces. Minimal reproduction for the record: open the Segment
Editor, then load any scene saved while an effect was active (`activeEffectName`
set on the `SegmentEditor` node).

The guard is therefore no longer *needed* on 5.12.3, but it is still harmless
there (the regression test passes) and still required for 5.10.0, so it stays on
by default. Turn it off per preset with `"sceneGuard": false`.

## Verification

```
uv run pytest                                                                  # unit tests
Slicer.exe --no-main-window --ignore-slicerrc --python-script tests/slicer/smoke_headless.py
Slicer.exe --no-splash --python-script tests/slicer/gui_regression.py         # needs the rc hook installed
Slicer.exe --no-splash --ignore-slicerrc --additional-module-path SlicerPresets \
           --python-script tests/slicer/module_regression.py                  # the scripted module
```

`module_regression.py` checks the packaging: that Slicer finds the module, that
it installs the hook at startup with no rc file present, and that the panel and
its buttons work.

`gui_regression.py` replays the original crash: opens the Segment Editor at
startup, imports a scene twice, and checks that the preset is applied to
segmentations created before and after the import. Point
`SLICER_PRESETS_TEST_MRB` at a scene of your own that was saved while a Segment
Editor effect was selected; without it the test reports SKIP.

Bisection performed on this machine (Slicer 5.10.0 r34045, Windows 11), each case a
separate GUI launch that loads the example MRB from a timer:

| Segment Editor open | scene | result |
|---|---|---|
| no | original MRB | OK |
| yes | original MRB | crash |
| yes | original, `SegmentEditor` node removed | OK |
| yes | original, only `activeEffectName` removed | OK |
| yes | original, only `selectedSegmentID` removed | crash |
| yes | synthetic MRB (no active effect) | OK |
| yes, on Slicer 5.8.1 | original MRB | OK |
| yes, with import guard | original MRB | OK |

Re-checked on **Slicer 5.12.3** (2026-09-07), after 5.8.1 was uninstalled:

| test | result |
|---|---|
| `pytest` (29 unit tests) | pass |
| `smoke_headless.py` on 5.12.3 | pass, incl. MRB import |
| `gui_regression.py` on 5.12.3 (guard active) | pass |
| `module_regression.py` on 5.12.3, headless and GUI | pass |
| unguarded: editor open + original MRB on 5.12.3 | **no crash** (fixed upstream) |
| same unguarded script on 5.10.0 | crash, as before (control) |
