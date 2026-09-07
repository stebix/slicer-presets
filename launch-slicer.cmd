@echo off
rem Starts Slicer with the segment-preset hook. Drop scene files onto this file
rem or pass them as arguments; extra Slicer options go after "--".
rem   launch-slicer.cmd                       plain start, default preset
rem   launch-slicer.cmd case.mrb              open a scene
rem   launch-slicer.cmd --preset InnerEar --sanitize case.mrb
setlocal
set "SLICER_PRESETS_HOME=%~dp0"
set "SLICER_PRESETS_HOME=%SLICER_PRESETS_HOME:~0,-1%"
set "PYTHONPATH=%SLICER_PRESETS_HOME%;%PYTHONPATH%"
python -m slicer_presets launch %*
endlocal
