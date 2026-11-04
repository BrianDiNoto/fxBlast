from __future__ import annotations

"""
parser.py — Scene file path and filename parsing for the Playblast Tool.

No Maya or DCC imports here — pure Python.
The DCC bridge calls parse_scene_path() and hands the resulting SceneTokens
object to the rest of the tool.
"""

import os
import re
from pathlib import Path
from typing import Optional

from .config import (
    FILENAME_REGEX,
    PATH_CONFIG,
    PATH_INDICES,
)


# ── Exceptions ─────────────────────────────────────────────────────────────────

class ParseError(Exception):
    """
    Raised when a scene path or filename does not match the expected pipeline
    convention.  The message is user-facing — it will be shown directly in the
    tool's warning dialog, so keep it clear and actionable.
    """


# ── Token container ─────────────────────────────────────────────────────────────

class SceneTokens:
    """
    All pipeline tokens extracted from a saved Maya scene path.

    Attributes
    ----------
    show        : str           e.g. "American_Horror_Story"
    season      : str           e.g. "AHS13"
    dept        : str           e.g. "vfx"
    shot        : str           e.g. "cur_005"
    discipline  : str           e.g. "anim"
    descriptor  : str | None    e.g. "snake"  (absent when None)
    version     : str           e.g. "v004"
    images_root : str           absolute path to the images/ output folder
    """

    __slots__ = (
        "show", "season", "dept", "shot",
        "discipline", "descriptor", "version",
        "images_root", "_raw_path",
    )

    def __init__(self, scene_path: str) -> None:
        self._raw_path  = scene_path
        self.show       = ""
        self.season     = ""
        self.dept       = ""
        self.shot       = ""
        self.discipline = ""
        self.descriptor: Optional[str] = None
        self.version    = ""
        self.images_root = ""

        self._parse(scene_path)

    # ── Public helpers ────────────────────────────────────────────────────────

    def output_folder(self, version_override: Optional[str] = None) -> str:
        """
        Full path to the versioned output folder.

        Parameters
        ----------
        version_override : str, optional
            Supply a different version string (e.g. "v007") to override the
            version parsed from the scene file.  Must match the pattern v\\d+.

        Returns
        -------
        str
            e.g. "Y:\\shows\\...\\maya\\images\\v004"
        """
        version = self._validated_version(version_override) or self.version
        return os.path.join(self.images_root, version)

    def output_basename(self, version_override: Optional[str] = None) -> str:
        """
        Base filename for the image sequence — no frame number, no extension.

        Parameters
        ----------
        version_override : str, optional
            Same semantics as in output_folder().

        Returns
        -------
        str
            e.g. "cur_005_snake_anim_v004"
                 "cur_005_anim_v004"       (no descriptor)
        """
        version = self._validated_version(version_override) or self.version
        tokens = [self.shot]
        if self.descriptor:
            tokens.append(self.descriptor)
        tokens.append(self.discipline)
        tokens.append(version)
        return "_".join(tokens)

    def display_summary(self) -> dict:
        """
        Return a dict of human-readable labels → values for populating the UI's
        read-only info panel.
        """
        return {
            "Show":       self.show,
            "Season":     self.season,
            "Shot":       self.shot,
            "Task":       self.discipline,
            "Descriptor": self.descriptor or "—",
            "Version":    self.version,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _parse(self, scene_path: str) -> None:
        """
        Extract and cross-validate all tokens from the scene path + filename.
        Raises ParseError with a descriptive message on any failure.
        """
        if not scene_path or not scene_path.strip():
            raise ParseError(
                "No scene file is open.\n\n"
                "Please save your scene to the correct pipeline location before "
                "opening the Playblast Tool."
            )

        path = Path(os.path.normpath(scene_path))

        self._parse_filename(path)
        self._parse_and_validate_path(path)
        self._build_images_root(path)

    def _parse_filename(self, path: Path) -> None:
        """Extract shot, descriptor, discipline, and version from the filename."""
        match = FILENAME_REGEX.match(path.name)
        if not match:
            disciplines = ", ".join(
                f'"{d}"' for d in
                __import__("config").KNOWN_DISCIPLINES
            )
            raise ParseError(
                f'Scene filename does not match the expected naming convention.\n\n'
                f'  Got:      {path.name}\n\n'
                f'  Expected: {{shot}}_{{discipline}}_{{version}}.ma\n'
                f'            {{shot}}_{{descriptor}}_{{discipline}}_{{version}}.ma\n\n'
                f'  Known disciplines: {disciplines}'
            )

        self.shot       = match.group("shot")
        self.discipline = match.group("discipline")
        self.version    = match.group("version")
        self.descriptor = match.group("descriptor")   # may be None

    def _parse_and_validate_path(self, path: Path) -> None:
        """
        Validate the fixed spine tokens and extract variable tokens from the
        directory portion of the scene path.  Also cross-validates shot and
        discipline against the values parsed from the filename.
        """
        parts = path.parts   # ('Y:\\', 'shows', show, season, dept, shot, '3D', discipline, 'maya', ...)

        # Minimum depth: drive + 8 fixed/variable tokens + at least the filename
        min_parts = max(PATH_INDICES.values()) + 2   # +1 for dcc folder, +1 for file
        if len(parts) < min_parts:
            raise ParseError(
                f"Scene path is too short to be a valid pipeline path.\n\n"
                f"  Got: {path}\n\n"
                "Make sure the scene is saved inside the correct pipeline folder structure."
            )

        # ── Fixed token checks ────────────────────────────────────────────────

        root_folder = parts[PATH_INDICES["root_folder"]]
        if root_folder.lower() != PATH_CONFIG["root_folder"].lower():
            raise ParseError(
                f'Expected "{PATH_CONFIG["root_folder"]}" at path position '
                f'{PATH_INDICES["root_folder"]}, got "{root_folder}".\n\n'
                f"  Path: {path}"
            )

        dcc_spine = parts[PATH_INDICES["dcc_spine"]]
        if dcc_spine != PATH_CONFIG["dcc_spine"]:
            raise ParseError(
                f'Expected "{PATH_CONFIG["dcc_spine"]}" at path position '
                f'{PATH_INDICES["dcc_spine"]}, got "{dcc_spine}".\n\n'
                f"  Path: {path}"
            )

        dcc = parts[PATH_INDICES["dcc"]]
        if dcc.lower() != PATH_CONFIG["dcc"].lower():
            raise ParseError(
                f'Expected "{PATH_CONFIG["dcc"]}" at path position '
                f'{PATH_INDICES["dcc"]}, got "{dcc}".\n\n'
                f"  Path: {path}"
            )

        # ── Variable token extraction ─────────────────────────────────────────

        self.show   = parts[PATH_INDICES["show"]]
        self.season = parts[PATH_INDICES["season"]]
        self.dept   = parts[PATH_INDICES["dept"]]

        # ── Cross-validation: shot ────────────────────────────────────────────

        path_shot = parts[PATH_INDICES["shot"]]
        if path_shot != self.shot:
            raise ParseError(
                f"Shot mismatch between path and filename.\n\n"
                f"  Path says:     {path_shot}\n"
                f"  Filename says: {self.shot}\n\n"
                f"  Path: {path}"
            )

        # ── Cross-validation: discipline ──────────────────────────────────────

        path_discipline = parts[PATH_INDICES["discipline"]]
        if path_discipline != self.discipline:
            raise ParseError(
                f"Discipline mismatch between path and filename.\n\n"
                f"  Path says:     {path_discipline}\n"
                f"  Filename says: {self.discipline}\n\n"
                f"  Path: {path}"
            )

    def _build_images_root(self, path: Path) -> None:
        """
        Resolve the images/ output directory.

        The scene file can live in two places:
          - Directly in maya/:       .../{shot}/3D/{discipline}/maya/file.ma
          - In a scenes/ subfolder:  .../{shot}/3D/{discipline}/maya/scenes/file.ma

        In both cases we want the sibling images/ folder:
                                     .../{shot}/3D/{discipline}/maya/images/
        """
        parent = path.parent

        if parent.name.lower() == PATH_CONFIG["dcc"]:
            # File is directly inside maya/
            maya_dir = parent
        elif parent.name.lower() in {s.lower() for s in PATH_CONFIG["scenes_subdirs"]}:
            # File is in maya/scenes/ (or another known subdir)
            maya_dir = parent.parent
        else:
            # Unknown nesting — try one level up and validate
            maya_dir = parent.parent
            if maya_dir.name.lower() != PATH_CONFIG["dcc"]:
                raise ParseError(
                    f'Could not locate the "{PATH_CONFIG["dcc"]}" folder in the scene path.\n\n'
                    f"  Path: {path}\n\n"
                    f'  The file should be saved inside a "{PATH_CONFIG["dcc"]}/" folder '
                    f'or a "{PATH_CONFIG["dcc"]}/scenes/" subfolder.'
                )

        self.images_root = str(maya_dir / PATH_CONFIG["output_dir"])

    @staticmethod
    def _validated_version(version_override: Optional[str]) -> Optional[str]:
        """Return version_override if it matches vN+ pattern, else raise."""
        if version_override is None:
            return None
        if not re.fullmatch(r"v\d+", version_override):
            raise ValueError(
                f'Version override must match the pattern "vN" (e.g. "v007"), '
                f'got: "{version_override}"'
            )
        return version_override

    def __repr__(self) -> str:
        return (
            f"SceneTokens("
            f"show={self.show!r}, "
            f"season={self.season!r}, "
            f"shot={self.shot!r}, "
            f"discipline={self.discipline!r}, "
            f"descriptor={self.descriptor!r}, "
            f"version={self.version!r})"
        )


# ── Public API ─────────────────────────────────────────────────────────────────

def parse_scene_path(scene_path: str) -> SceneTokens:
    """
    Parse a raw scene file path into a SceneTokens object.

    This is the entry point called by the DCC bridge.  All validation happens
    inside SceneTokens.__init__ — callers should catch ParseError and surface
    its message in the UI.

    Parameters
    ----------
    scene_path : str
        Absolute path to the saved scene file, as returned by the DCC.

    Returns
    -------
    SceneTokens

    Raises
    ------
    ParseError
        If the path or filename does not conform to the pipeline convention.

    Examples
    --------
    >>> tokens = parse_scene_path(
    ...     r"Y:\\shows\\American_Horror_Story\\AHS13\\vfx\\cur_005\\3D\\anim"
    ...     r"\\maya\\scenes\\cur_005_snake_anim_v004.ma"
    ... )
    >>> print(tokens.output_basename())
    cur_005_snake_anim_v004
    >>> print(tokens.output_folder())
    Y:\\shows\\American_Horror_Story\\AHS13\\vfx\\cur_005\\3D\\anim\\maya\\images\\v004
    """
    return SceneTokens(scene_path)
