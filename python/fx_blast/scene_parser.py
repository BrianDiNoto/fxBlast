"""
scene_parser.py — Parse the Maya scene path into pipeline tokens.

Supports both asset and shot pipeline paths:

  Asset : Y:/shows/{show}/{season}/assets/{assettype}/{asset}/{task}/maya/scenes/
  Shot  : Y:/shows/{show}/{season}/shots/{sequence}/{shot}/{task}/maya/scenes/

Filename convention:
  {season}_{type_or_seq}_{asset_or_shot}_{task}[_{descriptor}]_{version}.ma/.mb

Show / season / entity / task come from the studio pipeline context
(pipeline_context.py) when the DCC was launched through the pipeline
launcher. The scene path is only parsed for them as a fallback.
The scene name (descriptor), version and images root always come from
the scene file.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

from .config import FILENAME_REGEX, PATH_CONFIG, PATH_INDICES
from .pipeline_context import scene_fields


class ParseError(Exception):
    """Raised when the scene path or filename does not match the pipeline convention."""
    pass


@dataclass
class SceneTokens:
    """All pipeline tokens extracted from a saved Maya scene."""

    # From the folder path
    show:          str
    season:        str
    context_type:  str            # "assets" or "shots"
    type_or_seq:   str            # assettype or sequence
    asset_or_shot: str            # asset name or shot name
    task:          str

    # From the filename
    version:       str
    descriptor:    Optional[str]  = None

    # Resolved paths
    images_root:   str            = field(default="", repr=False)

    # Where show/season/entity/task came from: "pipeline" or "scene path"
    source:        str            = "scene path"   # or "pipeline" / "manual"
    dcc:           Optional[str]  = None

    # Movies folder (FX_MOVIES_DIR, <task>/movies, or the Maya project's)
    movies_root:   str            = field(default="", repr=False)

    # Renders folder: <task>/renders, or <project>/renders for Off Pipe
    renders_root:  str            = field(default="", repr=False)

    # Manual (out-of-pipeline) mode: the scene name is the whole output stem
    stem_override: Optional[str]  = None

    # ── Convenience display labels ─────────────────────────────────────────────

    @property
    def is_asset(self) -> bool:
        return self.context_type.lower() == "assets"

    @property
    def is_shot(self) -> bool:
        return self.context_type.lower() == "shots"

    @property
    def discipline(self) -> str:
        """Alias for task — used by the UI and HUD."""
        return self.task

    # Kept for backward compat with the UI which still references .shot and .show
    @property
    def shot(self) -> str:
        return self.asset_or_shot

    @property
    def output_stem(self) -> str:
        """
        Scene name without the version — identifies this scene's outputs.
        e.g.  ALI2_dev_brianDiNoto_rnd_PlantsLib
        """
        if self.stem_override:
            return self.stem_override
        parts = [self.season, self.type_or_seq, self.asset_or_shot, self.task]
        if self.descriptor:
            parts.append(self.descriptor)
        return "_".join(parts)

    def output_basename(self, version: Optional[str] = None) -> str:
        """
        Build the output frame filename stem.
        Version argument accepted for resolver.py compatibility.
        e.g.  ALI2_dev_bri100_rnd_XenoMacroProbeCam_v003
              ALI2_dev_bri100_rnd_v003
        """
        return "{}_{}".format(self.output_stem, version or self.version)

    def output_folder(self, version: Optional[str] = None) -> str:
        """
        Return the versioned output folder path — named after the scene so
        several scenes in the same task never share a folder.
        Called by resolver.py.
        e.g.  .../maya/images/ALI2_dev_brianDiNoto_rnd_PlantsLib_v001/
        """
        return os.path.join(self.images_root, self.output_basename(version))


# ── Public API ─────────────────────────────────────────────────────────────────

def parse_scene_path(scene_path: str) -> SceneTokens:
    """
    Parse a full Maya scene file path into a SceneTokens object.

    Raises ParseError with a user-readable message if the path or
    filename does not match the expected pipeline convention.
    """
    scene_path = os.path.normpath(scene_path)
    _validate_saved(scene_path)

    fields = scene_fields(scene_path)
    if fields:
        tokens = SceneTokens(
            show          = fields["show"],
            season        = fields["season"],
            context_type  = fields["context_type"],
            type_or_seq   = fields["type_or_seq"],
            asset_or_shot = fields["asset_or_shot"],
            task          = fields["task"],
            version       = "",
            source        = "pipeline",
            dcc           = fields["dcc"] or None,
        )
    else:
        tokens = _parse_path(scene_path)
    tokens = _parse_filename(scene_path, tokens)
    tokens.images_root = _resolve_images_root(scene_path)
    tokens.movies_root = _resolve_movies_root(scene_path, tokens.source)
    tokens.renders_root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(scene_path))), "renders")
    return tokens


# Manual mode: <scene name>[_]vNNN.ma -- separator before the version optional
_MANUAL_NAME = re.compile(r"^(?P<stem>.+?)[_.\-]?(?P<version>v\d+)$")


def manual_tokens(scene_path: str, project_name: str,
                  images_root: str, movies_root: str,
                  renders_root: str = "") -> SceneTokens:
    """
    Tokens for a scene outside the pipeline. Output goes to the Maya
    project; the scene name and version come from the workfile name.
    A name with no version gets version "" -- the caller picks the next
    free one.
    """
    scene_path = os.path.normpath(scene_path)
    _validate_saved(scene_path)
    name = os.path.splitext(os.path.basename(scene_path))[0]
    m = _MANUAL_NAME.match(name)
    stem, version = (m.group("stem"), m.group("version")) if m else (name, "")
    return SceneTokens(
        show          = project_name,
        season        = "",
        context_type  = "manual",
        type_or_seq   = "",
        asset_or_shot = stem,
        task          = "",
        version       = version,
        images_root   = images_root,
        source        = "manual",
        movies_root   = movies_root,
        renders_root  = renders_root,
        stem_override = stem,
    )


# ── Internal helpers ───────────────────────────────────────────────────────────

def _validate_saved(path: str) -> None:
    if not path or not path.strip():
        raise ParseError(
            "No scene file is open.\n\n"
            "Please save your scene to the correct pipeline location before "
            "opening fxBlast."
        )


def _parse_path(scene_path: str) -> SceneTokens:
    """Extract pipeline tokens from the folder path."""
    parts = re.split(r"[\\/]", scene_path)

    # Find "shows" root
    try:
        root_idx = next(
            i for i, p in enumerate(parts)
            if p.lower() == PATH_CONFIG["root_folder"].lower()
        )
    except StopIteration:
        raise ParseError(
            f"Could not find a '{PATH_CONFIG['root_folder']}' folder in the scene path.\n\n"
            f"Scene path:\n{scene_path}\n\n"
            "Make sure the scene is saved to the correct pipeline location."
        )

    def _get(offset: int, label: str) -> str:
        idx = root_idx + offset
        if idx >= len(parts) or not parts[idx]:
            raise ParseError(
                f"Could not read '{label}' from the scene path.\n\n"
                f"Scene path:\n{scene_path}"
            )
        return parts[idx]

    show          = _get(1, "show")
    season        = _get(2, "season")
    context_type  = _get(3, "context type (assets/shots)")
    type_or_seq   = _get(4, "asset type or sequence")
    asset_or_shot = _get(5, "asset or shot")
    task          = _get(6, "task")

    if context_type.lower() not in ("assets", "shots"):
        raise ParseError(
            f"Expected 'assets' or 'shots' in the path, found '{context_type}'.\n\n"
            f"Scene path:\n{scene_path}"
        )

    return SceneTokens(
        show          = show,
        season        = season,
        context_type  = context_type,
        type_or_seq   = type_or_seq,
        asset_or_shot = asset_or_shot,
        task          = task,
        version       = "",
    )


def _parse_filename(scene_path: str, tokens: SceneTokens) -> SceneTokens:
    """Extract version and descriptor from the filename."""
    filename = os.path.basename(scene_path)
    match    = FILENAME_REGEX.match(filename)

    if not match:
        raise ParseError(
            f"Filename does not match the expected naming convention:\n\n"
            f"  {filename}\n\n"
            f"Expected:\n"
            f"  {{season}}_{{type}}_{{asset}}_{{task}}[_{{descriptor}}]_{{version}}.ma/.mb\n\n"
            f"Example:\n"
            f"  ALI2_dev_brianDiNoto_rnd_XenoMacroProbeCam_v003.ma"
        )

    tokens.version    = match.group("version")
    tokens.descriptor = match.group("descriptor") or None
    return tokens


def _resolve_movies_root(scene_path: str, source: str) -> str:
    """FX_MOVIES_DIR when the pipeline context describes this scene,
    otherwise <task>/movies (the same folder the pipeline uses).

      .../{task}/maya/scenes/filename.ma  ->  .../{task}/movies
    """
    if source == "pipeline" and os.environ.get("FX_MOVIES_DIR"):
        return os.path.normpath(os.environ["FX_MOVIES_DIR"])
    task_dir = os.path.dirname(os.path.dirname(os.path.dirname(scene_path)))
    return os.path.join(task_dir, "movies")


def _resolve_images_root(scene_path: str) -> str:
    """
    Build the images root folder from the scene path.

    Walks up from the scenes file to the maya/ folder, then appends images/.

      .../maya/scenes/filename.ma  →  .../maya/images/
    """
    scenes_dir = os.path.dirname(scene_path)   # .../maya/scenes
    maya_dir   = os.path.dirname(scenes_dir)   # .../maya
    return os.path.join(maya_dir, PATH_CONFIG["output_dir"])
