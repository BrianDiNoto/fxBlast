Title: fxBlast
Tooltip: Pipeline-aware Maya playblast tool with RV review handoff.
Tags: playblast, review, RV, burn-in, pipeline, maya
Authors: DINOB002
DCC: Maya

## Overview

fxBlast blasts the current Maya camera or render layer to an image
sequence, encodes a movie next to it, and opens the result in RV. It
reads the scene's pipeline context (show, season, sequence or asset,
shot, task) and writes to the renders tree the pipeline expects. For a
scene the pipeline does not recognize, Off Pipe mode writes to the
Maya project instead.

## How to use it

1. Launch fxBlast from the FXN shelf.
2. Check the breadcrumb at the top: Show / Season / Type-Seq /
   Asset-Shot / Task / Scene / Version. It confirms the scene context
   fxBlast found.
3. Pick a tab:
   - **Simple** -- camera from the active viewport. Fewer controls.
   - **Advanced** -- pick the camera and render layer directly.
   - **Off Pipe** -- for a scene outside the pipeline. Output goes to
     the Maya project, not the renders tree.
4. Set the frame range, the output format, and any burn-in text.
5. Add a note. It is stamped into the burn-in HUD and saved with the
   version.
6. Click Playblast. fxBlast writes the frames, encodes the movie if
   one was requested, and opens the result in RV.
7. From the version list, use "Play in RV" on a sequence row, or
   "Open folder" to jump to the files on disk.

## Notes

- RV is not managed by rez at this studio. If RV does not launch, set
  the `FX_RV_PATH` environment variable to the `rv.exe` path.
- fxBlast keeps the same workspace control name across versions.
  Relaunching from the shelf clears a stale docked instance first, so
  an upgrade never leaves an old UI behind.
- H.264 movies encode from a kept JPG sequence. ProRes movies encode
  from a kept PNG sequence, for 10-bit output.
- Off Pipe mode is for scenes fxBlast cannot place in the pipeline (a
  test file, a scene opened outside the pipeline launcher). It never
  writes to the renders tree.
