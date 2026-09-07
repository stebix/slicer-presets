"""``slicer-presets`` command line.

    slicer-presets launch [scene files...] [--preset NAME] [--spec FILE] [--slicer EXE] [--sanitize]
    slicer-presets sanitize FILE [FILE...] [-o OUT] [--mode MODE] [--in-place]
    slicer-presets validate [SPEC]
    slicer-presets install-rc [--force] [--print]
    slicer-presets show
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, rcfile, scene_files, spec

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)(-\d{4}-\d{2}-\d{2})?")


def slicer_installs() -> list[tuple[tuple[int, int, int, int], Path]]:
    """All ``Slicer.exe`` under ``%LOCALAPPDATA%\\slicer.org``, best version first."""
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "slicer.org"
    found: list[tuple[tuple[int, int, int, int], Path]] = []
    if root.is_dir():
        for child in root.iterdir():
            exe = child / "Slicer.exe"
            m = _VERSION_RE.search(child.name)
            if exe.is_file() and m:
                release = 0 if m.group(4) else 1  # dated preview builds rank below releases
                found.append(((int(m.group(1)), int(m.group(2)), int(m.group(3)), release), exe))
    found.sort(reverse=True)
    return found


def find_slicer(explicit: str | None = None) -> Path:
    candidate = explicit or os.environ.get("SLICER_EXE")
    if candidate:
        path = Path(candidate)
        if not path.is_file():
            raise FileNotFoundError(f"Slicer executable not found: {path}")
        return path
    for _, exe in slicer_installs():
        return exe
    which = shutil.which("Slicer")
    if which:
        return Path(which)
    raise FileNotFoundError("no Slicer installation found; pass --slicer or set SLICER_EXE")


def _home(args) -> Path:
    return Path(args.home) if args.home else Path(os.environ.get(spec.ENV_HOME) or spec.package_home())


# -- commands --------------------------------------------------------------------------


def cmd_launch(args) -> int:
    exe = find_slicer(args.slicer)
    home = _home(args)
    spec_path = Path(args.spec) if args.spec else spec.default_spec_path(home)
    spec_file = spec.load_spec_file(spec_path)
    preset = spec.select_preset(spec_file, args.preset)

    env = dict(os.environ)
    env[spec.ENV_HOME] = str(home)
    env[spec.ENV_SPEC] = str(spec_path)
    env[spec.ENV_PRESET] = preset.name

    files: list[str] = []
    for f in args.files:
        path = Path(f)
        if not path.exists():
            raise FileNotFoundError(f"scene file not found: {path}")
        if args.sanitize and path.suffix.lower() in (".mrb", ".mrml") and scene_files.needs_sanitizing(path):
            out, n = scene_files.sanitize_scene_file(path, mode=args.mode)
            print(f"sanitized {path.name} -> {out} ({n} change(s))")
            path = out
        files.append(str(path))

    command = [str(exe)]
    if args.no_splash:
        command.append("--no-splash")
    if args.no_presets:
        command.append("--ignore-slicerrc")
    command += args.slicer_args
    command += files

    print("launching:", " ".join(f'"{c}"' if " " in c else c for c in command))
    print(f"preset: {preset.name} ({len(preset.segments)} segments) from {spec_path}")
    if args.wait:
        return subprocess.call(command, env=env)
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(command, env=env, creationflags=flags, close_fds=True)
    return 0


def cmd_sanitize(args) -> int:
    if args.output and len(args.files) != 1:
        raise SystemExit("-o/--output can only be used with a single input file")
    for f in args.files:
        path = Path(f)
        if not scene_files.needs_sanitizing(path, args.mode):
            print(f"{path}: already clean (no SegmentEditor state to strip)")
            continue
        if args.in_place:
            backup = path.with_name(path.name + ".bak")
            shutil.copy2(path, backup)
            tmp = path.with_name(path.name + ".tmp")
            out, n = scene_files.sanitize_scene_file(path, tmp, args.mode)
            os.replace(out, path)
            print(f"{path}: {n} change(s) written in place (backup: {backup.name})")
        else:
            out, n = scene_files.sanitize_scene_file(path, args.output, args.mode)
            print(f"{path} -> {out} ({n} change(s))")
    return 0


def cmd_validate(args) -> int:
    path = Path(args.spec) if args.spec else spec.default_spec_path(_home(args))
    spec_file = spec.load_spec_file(path)
    print(f"{path}: {len(spec_file.presets)} preset(s), default = {spec_file.default}")
    for preset in spec_file.presets.values():
        print(f"\n[{preset.name}] {preset.description}".rstrip())
        o = preset.options
        print(f"  options: autoApply={o.apply_to_new_segmentations} createOnStartup={o.create_on_startup} "
              f"openSegmentEditor={o.open_segment_editor} sceneGuard={o.scene_guard} menuAction={o.menu_action} nodeName={preset.node_name}")
        for s in preset.segments:
            rgb = "#" + "".join(f"{round(c * 255):02X}" for c in s.color)
            label = f"label {s.label_value:>3}" if s.label_value is not None else "label auto"
            print(f"  {label}  {rgb}  {s.name}" + (f"  (id: {s.segment_id})" if s.segment_id else ""))
    return 0


def cmd_install_rc(args) -> int:
    home = _home(args)
    if args.print:
        sys.stdout.write(rcfile.render(home))
        return 0
    target, backup = rcfile.install_rc(home, args.path, force=args.force)
    print(f"wrote {target} (package home: {home})")
    if backup:
        print(f"previous file backed up to {backup}")
    return 0


def cmd_show(args) -> int:
    home = _home(args)
    print(f"package home : {home}")
    print(f"spec file    : {spec.default_spec_path(home)}")
    print(f"preset       : {os.environ.get(spec.ENV_PRESET) or '(file default)'}")
    print(f"rc file      : {rcfile.rc_path()}")
    try:
        print(f"slicer       : {find_slicer(None)}")
    except FileNotFoundError as exc:
        print(f"slicer       : {exc}")
    installs = slicer_installs()
    if installs:
        print("installs     : " + ", ".join(exe.parent.name for _, exe in installs))
    return 0


# -- parser --------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="slicer-presets", description="Segment Editor presets for 3D Slicer")
    parser.add_argument("--version", action="version", version=f"slicer-presets {__version__}")
    parser.add_argument("--home", help=f"package root (default: ${spec.ENV_HOME} or the installed package location)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("launch", help="start Slicer with the preset hook configured")
    p.add_argument("files", nargs="*", help="scene/data files to open (.mrb, .mrml, .nrrd, ...)")
    p.add_argument("--preset", help=f"preset name (default: ${spec.ENV_PRESET} or the spec's default)")
    p.add_argument("--spec", help=f"spec JSON (default: ${spec.ENV_SPEC} or presets/default.json)")
    p.add_argument("--slicer", help="Slicer.exe to use (default: $SLICER_EXE or newest install)")
    p.add_argument("--sanitize", action="store_true", help="strip saved Segment Editor state from .mrb/.mrml files before opening")
    p.add_argument("--mode", choices=list(scene_files.MODES), default=scene_files.DEFAULT_MODE, help="what --sanitize strips")
    p.add_argument("--no-splash", action="store_true")
    p.add_argument("--no-presets", action="store_true", help="launch with --ignore-slicerrc (plain Slicer)")
    p.add_argument("--wait", action="store_true", help="wait for Slicer to exit and return its exit code")
    p.add_argument("slicer_args", nargs=argparse.REMAINDER, help="extra Slicer arguments after '--'")
    p.set_defaults(func=cmd_launch)

    p = sub.add_parser("sanitize", help="make a scene file safe to load while the Segment Editor is open (Slicer 5.10.0)")
    p.add_argument("files", nargs="+")
    p.add_argument("-o", "--output", help="output path (single input only; default: <name>.safe.<ext>)")
    p.add_argument("--mode", choices=list(scene_files.MODES), default=scene_files.DEFAULT_MODE)
    p.add_argument("--in-place", action="store_true", help="overwrite the input (a .bak copy is kept)")
    p.set_defaults(func=cmd_sanitize)

    p = sub.add_parser("validate", help="parse a spec file and list its presets")
    p.add_argument("spec", nargs="?")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("install-rc", help="write the ~/.slicerrc.py bootstrap")
    p.add_argument("--path", help="rc file location (default: $SLICERRC or ~/.slicerrc.py)")
    p.add_argument("--force", action="store_true", help="replace a hand-written rc file (backup is kept)")
    p.add_argument("--print", action="store_true", help="print the bootstrap instead of writing it")
    p.set_defaults(func=cmd_install_rc)

    p = sub.add_parser("show", help="print the resolved configuration")
    p.set_defaults(func=cmd_show)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "slicer_args", None) and args.slicer_args[:1] == ["--"]:
        args.slicer_args = args.slicer_args[1:]
    try:
        return args.func(args)
    except (spec.SpecError, FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
