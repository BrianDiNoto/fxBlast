"""
layout.py -- where a scene's playblasts go: frames, movies, metadata.

The pipeline owns the folder and file names. Its library (fx_context_utils)
needs a newer Python than Maya 2022 has, so it runs in its own rez
environment (pipeline_paths_worker.py) once per launch context. The worker
resolves each path with marker values (component FXBCOMP, version v987,
frame 7); here the markers are swapped for the real values, so one call
gives every camera and version.

Scenes the pipeline context doesn't describe (opened from another task, or
Off Pipe) use a local copy of the same structure ("mirror").

    frames  <renders>/<component>/<version>/<ext>/<prefix>_<component>_<version>.####.<ext>
    movie   <renders>/<component>/<version>/mov/<prefix>_<component>_<version>_rgb_<res>_<codec>.mov
    meta    <renders>/<component>/<version>/fxblast.json

No Maya imports -- pure Python.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Optional

COMP  = "FXBCOMP"
VER   = "v987"
VER_N = 987
FRAME = 7
COLOR = "rgb"
RES_MARK = "hd"                 # resolution the worker resolves movies with

MOVIE_CODECS = ("h264", "apr", "aprx")
FRAME_EXTS   = ("jpg", "png")
META_NAME    = "fxblast.json"

# Best guess at the pipeline's resolution codes. Sizes not listed here are
# left out of the movie name (the pipeline has no code for them).
RESOLUTION_CODES = {
    (1920, 1080): "hd",
    (3840, 2160): "uhd",
    (960, 540):   "qhd",
}

_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "pipeline_paths_worker.py")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_pipeline_cache: dict = {}      # FX_TASK_DIR -> templates


class LayoutError(Exception):
    """Message is user-facing."""


def _norm(path: str) -> str:
    return path.replace("\\", "/")


class OutputLayout:
    """Paths for one scene. `frames` maps ext -> template, `movies` maps
    codec -> template; both contain the COMP / VER / frame markers."""

    def __init__(self, frames: dict, movies: dict, renders_root: str,
                 scene_key: str, descriptor: str, source: str) -> None:
        self.frames       = {k: _norm(v) for k, v in frames.items()}
        self.movies       = {k: _norm(v) for k, v in movies.items()}
        self.renders_root = os.path.normpath(renders_root)
        self.scene_key    = scene_key        # which scene a blast belongs to
        self.descriptor   = descriptor       # the workfile's part of the component
        self.source       = source           # "pipeline" or "mirror"
        some = next(iter(self.frames.values()))
        frame_tok = os.path.basename(some).rsplit(".", 2)[-2]
        if int(frame_tok) != FRAME:
            raise LayoutError(f"Unexpected frame template from the pipeline:\n\n{some}")
        self.padding = len(frame_tok)

    # ── names ────────────────────────────────────────────────────────────────

    def component(self, camera: str, layer: Optional[str] = None) -> str:
        """<camera>_<descriptor>[_<layer>] -- camera casing kept."""
        parts = [camera] + ([self.descriptor] if self.descriptor else [])
        if layer:
            parts.append(layer)
        return "_".join(parts)

    @staticmethod
    def _fill(template: str, comp: str, version: str) -> str:
        return template.replace(COMP, comp).replace(VER, version)

    # ── paths ────────────────────────────────────────────────────────────────

    def frames_stem(self, comp: str, version: str, ext: str) -> str:
        """Frame path without '.####.ext' -- what Maya's playblast wants."""
        full = self._fill(self.frames[ext], comp, version)
        tail = f".{FRAME:0{self.padding}d}.{ext}"
        if not full.endswith(tail):
            raise LayoutError(f"Unexpected frame template from the pipeline:\n\n{full}")
        return os.path.normpath(full[: -len(tail)])

    def frames_dir(self, comp: str, version: str, ext: str) -> str:
        return os.path.dirname(self.frames_stem(comp, version, ext))

    def frame_file(self, comp: str, version: str, ext: str, frame: int) -> str:
        return f"{self.frames_stem(comp, version, ext)}.{frame:0{self.padding}d}.{ext}"

    def version_dir(self, comp: str, version: str) -> str:
        """The folder holding one blast: frames (per ext), movie, metadata."""
        d = _norm(os.path.dirname(self.frames[next(iter(self.frames))]))
        i = d.rfind(VER)
        d = d[: i + len(VER)] if i >= 0 else d
        return os.path.normpath(self._fill(d, comp, version))

    def movie_path(self, comp: str, version: str, codec: str,
                   width: int, height: int) -> str:
        full = self._fill(self.movies[codec], comp, version)
        code = RESOLUTION_CODES.get((width, height))
        folder, name = os.path.split(full)
        mark = f"_{COLOR}_{RES_MARK}_"
        name = name.replace(mark, f"_{COLOR}_{code}_" if code else f"_{COLOR}_", 1)
        return os.path.normpath(os.path.join(folder, name))

    def meta_path(self, comp: str, version: str) -> str:
        return os.path.join(self.version_dir(comp, version), META_NAME)

    # ── existing blasts ──────────────────────────────────────────────────────

    def scan(self) -> dict:
        """{version: [meta, ...]} for this scene's blasts, found by their
        fxblast.json (renders also holds real renders -- those have none)."""
        found: dict = {}
        root = self.renders_root
        try:
            comps = os.listdir(root)
        except OSError:
            return found
        for comp in comps:
            comp_dir = os.path.join(root, comp)
            try:
                versions = [v for v in os.listdir(comp_dir) if re.fullmatch(r"v\d+", v)]
            except OSError:
                continue
            for ver in versions:
                path = self.meta_path(comp, ver)
                if not os.path.isfile(path):
                    continue
                meta = load_meta(path)
                if meta.get("scene") != self.scene_key:
                    continue
                meta["_component"], meta["_version"], meta["_path"] = comp, ver, path
                found.setdefault(ver, []).append(meta)
        return found

    def existing_versions(self) -> list:
        return sorted(self.scan(), key=lambda v: int(v[1:]))


def load_meta(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_meta(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    clean = {k: v for k, v in data.items() if not k.startswith("_")}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2)


# ── Builders ─────────────────────────────────────────────────────────────────

def mirror_layout(renders_root: str, prefix: str, scene_key: str,
                  descriptor: str) -> OutputLayout:
    """The pipeline's structure, built locally. `prefix` is the context part
    of the file name (e.g. ALI2_character_xenomorphLegacy_anim), "" for
    Off Pipe."""
    root = _norm(renders_root)
    lead = f"{prefix}_" if prefix else ""
    frames = {ext: f"{root}/{COMP}/{VER}/{ext}/{lead}{COMP}_{VER}.{FRAME:04d}.{ext}"
              for ext in FRAME_EXTS}
    movies = {c: f"{root}/{COMP}/{VER}/mov/{lead}{COMP}_{VER}_{COLOR}_{RES_MARK}_{c}.mov"
              for c in MOVIE_CODECS}
    return OutputLayout(frames, movies, renders_root, scene_key, descriptor, "mirror")


def pipeline_layout(scene_key: str, descriptor: str) -> OutputLayout:
    """Templates from the pipeline library, through rez-env. Cached per
    launch context (FX_TASK_DIR): the templates only depend on it."""
    task = os.environ.get("FX_TASK_DIR", "")
    if task not in _pipeline_cache:
        try:
            _pipeline_cache[task] = _run_worker()
        except LayoutError as exc:
            _pipeline_cache[task] = exc      # don't wait for rez again on every refresh
    t = _pipeline_cache[task]
    if isinstance(t, LayoutError):
        raise t
    return OutputLayout(t["frames"], t["movies"], t["renders_root"],
                        scene_key, descriptor, "pipeline")


def _run_worker() -> dict:
    rez_env = shutil.which("rez-env")
    if not rez_env:
        raise LayoutError("rez-env not found, so the pipeline paths can't be read.")
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")}
    env["FXBLAST_ARGS"] = json.dumps(dict(
        comp=COMP, version=VER_N, frame=FRAME, exts=list(FRAME_EXTS),
        codecs=list(MOVIE_CODECS), color=COLOR, resolution=RES_MARK))
    cmd = [rez_env, "fx_context_utils", "--", "python", _WORKER]
    print("[fxBlast] reading pipeline paths: " + subprocess.list2cmdline(cmd))
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=env, timeout=180, creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LayoutError(f"Could not read the pipeline paths:\n\n{exc}") from exc
    out = r.stdout.decode("utf-8", "replace")
    for line in out.splitlines():
        if line.startswith("FXBLAST_JSON "):
            data = json.loads(line[len("FXBLAST_JSON "):])
            if data.get("error"):
                raise LayoutError(f"The pipeline could not resolve a path:\n\n{data['error']}")
            return data
    err = r.stderr.decode("utf-8", "replace").strip()[-1500:]
    raise LayoutError(f"No answer from the pipeline paths reader (exit {r.returncode}).\n\n"
                      f"{err or out[-1500:] or 'no output'}")
