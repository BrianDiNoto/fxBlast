"""
movie.py -- encode a blasted image sequence into a movie with ffmpeg.

The image sequence is always kept; the movie is an extra file in the
movies folder. No Maya imports -- pure Python.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from typing import Callable, Optional

from .config import FFMPEG_PATH, FFMPEG_REZ_PACKAGE, PRORES_PROFILES


class MovieError(Exception):
    """Message is user-facing."""


class MovieCancelled(Exception):
    """The artist stopped the encode."""


# Exact rates for the NTSC-style frame rates Maya reports as decimals
_RATIONAL_FPS = {
    23.976: "24000/1001",
    29.97:  "30000/1001",
    47.952: "48000/1001",
    59.94:  "60000/1001",
}

# Windows: run ffmpeg without flashing a console window
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _fps_arg(fps: float) -> str:
    for value, rational in _RATIONAL_FPS.items():
        if abs(fps - value) < 0.001:
            return rational
    return str(int(fps)) if fps == int(fps) else str(fps)


def ffmpeg_prefix() -> list[str]:
    """
    Command prefix that runs ffmpeg: FX_FFMPEG_PATH if set, else the rez
    package through rez-env (tested at the studio: arguments, including the
    %04d frame pattern, reach ffmpeg unchanged).
    """
    if FFMPEG_PATH:
        if not os.path.isfile(FFMPEG_PATH):
            raise MovieError(f"FX_FFMPEG_PATH points to a missing file:\n\n{FFMPEG_PATH}")
        return [FFMPEG_PATH]
    rez_env = shutil.which("rez-env")
    if not rez_env:
        raise MovieError(
            "Could not find rez-env, so ffmpeg can't be started.\n\n"
            "Set the FX_FFMPEG_PATH environment variable to the full path "
            "of ffmpeg.exe.")
    return [rez_env, FFMPEG_REZ_PACKAGE, "--", "ffmpeg"]


def build_args(
    frames_stem:    str,
    ext:            str,
    start_frame:    int,
    fps:            float,
    out_path:       str,
    movie_fmt:      str,
    prores_profile: str = "apr",
    squeeze:        Optional[float] = None,
    padding:        int = 4,
) -> list[str]:
    """ffmpeg arguments (without the ffmpeg prefix)."""
    pattern = f"{frames_stem}.%0{padding}d.{ext}"
    args = ["-y", "-hide_banner", "-loglevel", "error",
            "-framerate", _fps_arg(fps), "-start_number", str(start_frame),
            "-i", pattern]

    filters = []
    if movie_fmt == "h264":
        filters.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")   # H.264 needs even sizes
    # Square pixels, or the anamorphic squeeze so players de-squeeze
    filters.append(f"setsar={squeeze}" if squeeze else "setsar=1")
    if filters:
        args += ["-vf", ",".join(filters)]

    if movie_fmt == "h264":
        args += ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    elif movie_fmt == "prores":
        profiles = {pid: num for pid, _, num in PRORES_PROFILES}
        if prores_profile not in profiles:
            raise MovieError(f'Unknown ProRes profile "{prores_profile}".')
        num = profiles[prores_profile]
        pix = "yuv444p10le" if num >= 4 else "yuv422p10le"
        args += ["-c:v", "prores_ks", "-profile:v", str(num),
                 "-vendor", "apl0", "-pix_fmt", pix]
    else:
        raise MovieError(f'Unknown movie format "{movie_fmt}".')

    args.append(out_path)
    return args


def _clean_env() -> dict:
    """Maya's Python/Qt variables can break rez-env's own Python."""
    env = os.environ.copy()
    for var in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP",
                "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        env.pop(var, None)
    return env


def encode(
    args:         list[str],
    keep_waiting: Optional[Callable[[], bool]] = None,
) -> None:
    """
    Run ffmpeg and wait for it. `keep_waiting` is called while ffmpeg runs
    (the UI uses it to process events); when it returns False, ffmpeg is
    stopped, the partial movie is removed, and MovieCancelled is raised.
    """
    cmd = ffmpeg_prefix() + args
    out_path = args[-1]
    print("[fxBlast] ffmpeg: " + subprocess.list2cmdline(cmd))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # stderr to a file, not a pipe: a full pipe would stall ffmpeg
    with tempfile.TemporaryFile() as err:
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=err,
                                    env=_clean_env(), creationflags=_NO_WINDOW)
        except OSError as exc:
            raise MovieError(f"Could not start ffmpeg:\n\n{exc}") from exc

        while proc.poll() is None:
            if keep_waiting is not None and not keep_waiting():
                proc.kill(); proc.wait()
                try: os.remove(out_path)
                except OSError: pass
                raise MovieCancelled()
            time.sleep(0.05)

        err.seek(0)
        detail = err.read().decode("utf-8", "replace").strip()[-1500:]
        print(f"[fxBlast] ffmpeg exit {proc.returncode}; movie exists: "
              f"{os.path.isfile(out_path)}" + (f"\n{detail}" if detail else ""))
        if proc.returncode != 0:
            raise MovieError(
                f"ffmpeg failed (exit code {proc.returncode}):\n\n{detail or 'no output'}")
        # Never report a movie that isn't there
        if not os.path.isfile(out_path) or os.path.getsize(out_path) == 0:
            raise MovieError(
                f"ffmpeg finished but wrote no movie:\n\n{out_path}\n\n{detail or 'no output'}")
