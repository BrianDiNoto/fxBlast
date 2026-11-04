from __future__ import annotations

"""
resolver.py — Output path resolution for the Playblast Tool.

Takes a SceneTokens object plus user-chosen settings and produces everything
the blast call needs: folder path, frame pattern, and a ready-to-use output
directory.  Also handles version discovery so the UI can offer sensible
defaults and overwrite warnings.

No Maya or DCC imports — pure Python.
"""

import os
import re
from pathlib import Path
from typing import Optional

from .config import DEFAULT_FORMAT, FRAME_PADDING, IMAGE_FORMATS
from .scene_parser import ParseError, SceneTokens


# ── Exceptions ─────────────────────────────────────────────────────────────────

class ResolveError(Exception):
    """
    Raised when the output path cannot be resolved or created.
    Message is user-facing.
    """


# ── Main resolver ───────────────────────────────────────────────────────────────

class OutputResolver:
    """
    Resolves a fully-qualified output path from SceneTokens and user settings,
    and prepares the output directory.

    Parameters
    ----------
    tokens          : SceneTokens   Parsed tokens from the open scene file.
    version_override: str, optional If set, use this version instead of the
                                    one parsed from the scene (e.g. "v007").
    image_format    : str           "png" or "jpg".  Defaults to config value.
    frame_padding   : int           Number of digits in frame numbers (default 4).
    """

    def __init__(
        self,
        tokens: SceneTokens,
        version_override: Optional[str] = None,
        image_format: str               = DEFAULT_FORMAT,
        frame_padding: int              = FRAME_PADDING,
    ) -> None:
        self._tokens   = tokens
        self._format   = self._validated_format(image_format)
        self._padding  = frame_padding
        self._version  = self._resolved_version(tokens, version_override)

    # ── Read-only properties ──────────────────────────────────────────────────

    @property
    def version(self) -> str:
        """The version string that will be used for output (e.g. "v004")."""
        return self._version

    @property
    def output_folder(self) -> str:
        """
        Absolute path to the versioned output folder, named after the scene.

        e.g. Y:\\...\\maya\\images\\ALI2_dev_brianDiNoto_rnd_PlantsLib_v001
        """
        return self._tokens.output_folder(self._version)

    @property
    def output_basename(self) -> str:
        """
        Filename stem — no frame number, no extension.

        e.g. cur_005_snake_anim_v004
        """
        return self._tokens.output_basename(self._version)

    @property
    def frame_pattern(self) -> str:
        """
        Full frame-sequence path as expected by Maya's playblast command.

        Maya takes the path up to (but not including) the frame padding, then
        appends the frame number and extension itself.  We pass the folder +
        basename; Maya handles the rest.

        e.g. Y:\\...\\images\\v004\\cur_005_snake_anim_v004

        Note: the '#' padding notation is stored separately in `hash_pattern`
        for display purposes in the UI.
        """
        return os.path.join(self.output_folder, self.output_basename)

    @property
    def hash_pattern(self) -> str:
        """
        Human-readable frame pattern shown in the UI output preview.

        e.g. cur_005_snake_anim_v004.####.png
        """
        from .config import FORMAT_EXTENSIONS
        hashes = "#" * self._padding
        ext    = FORMAT_EXTENSIONS.get(self._format, self._format)
        return f"{self.output_basename}.{hashes}.{ext}"

    @property
    def full_display_path(self) -> str:
        """
        Full display string shown in the UI output path field.

        e.g. Y:\\...\\images\\v004\\cur_005_snake_anim_v004.####.png
        """
        return os.path.join(self.output_folder, self.hash_pattern)

    @property
    def image_format(self) -> str:
        return self._format

    # ── Directory management ──────────────────────────────────────────────────

    def folder_exists(self) -> bool:
        """Return True if the output folder already exists on disk."""
        return Path(self.output_folder).exists()

    def folder_has_existing_frames(self) -> bool:
        """
        Return True if the output folder exists AND already contains image
        files.  Used to drive the overwrite-warning in the UI.
        """
        folder = Path(self.output_folder)
        if not folder.exists():
            return False
        return any(
            f.suffix.lower() in {".png", ".jpg", ".jpeg", ".exr"}
            for f in folder.iterdir()
            if f.is_file()
        )

    def prepare_output_folder(self) -> str:
        """
        Create the output folder (and any missing parents) if it doesn't exist.

        Returns
        -------
        str
            The resolved output folder path.

        Raises
        ------
        ResolveError
            If the folder cannot be created (permissions, bad drive, etc.).
        """
        folder = Path(self.output_folder)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ResolveError(
                f"Could not create output folder:\n\n"
                f"  {folder}\n\n"
                f"  {exc}"
            ) from exc
        return str(folder)

    # ── Version utilities ─────────────────────────────────────────────────────

    def existing_versions(self) -> list[str]:
        """
        Scan the images/ root and return a sorted list of versions that
        already exist on disk FOR THIS SCENE (e.g. ["v001", "v002", "v004"]).

        Only folders named <scene stem>_vNNN count, so other scenes saved
        in the same task keep their own version tracks.
        """
        images_root = Path(self._tokens.images_root)
        if not images_root.exists():
            return []

        pattern = re.compile(
            r"^" + re.escape(self._tokens.output_stem) + r"_(v\d+)$")
        versions = []
        for d in images_root.iterdir():
            if not d.is_dir():
                continue
            m = pattern.match(d.name)
            if m:
                versions.append(m.group(1))
        return sorted(versions, key=lambda v: int(v[1:]))

    def next_available_version(self) -> str:
        """
        Return the next version string that does not yet exist on disk.

        If v001, v002, and v004 exist, this returns "v003" (fills the gap).
        If all are contiguous, it returns the next integer after the highest.
        """
        existing = self.existing_versions()
        if not existing:
            return "v001"

        existing_nums = sorted(int(v[1:]) for v in existing)
        # Fill gaps first
        for i, n in enumerate(existing_nums, start=1):
            if n != i:
                return f"v{i:03d}"
        # No gaps — return next after highest
        return f"v{existing_nums[-1] + 1:03d}"

    # ── Validation helpers ────────────────────────────────────────────────────

    @staticmethod
    def _validated_format(fmt: str) -> str:
        valid = {f.lower() for f in IMAGE_FORMATS}
        if fmt.lower() not in valid:
            raise ResolveError(
                f'Unsupported image format "{fmt}". '
                f'Supported: {", ".join(IMAGE_FORMATS)}'
            )
        return fmt.lower()

    @staticmethod
    def _resolved_version(tokens: SceneTokens, override: Optional[str]) -> str:
        """Return override if provided and valid, otherwise use the scene version."""
        if override is None:
            return tokens.version
        if not re.fullmatch(r"v\d+", override):
            raise ResolveError(
                f'Version override must match the pattern "vNNN" (e.g. "v007"), '
                f'got: "{override}"'
            )
        return override


# ── Convenience factory ─────────────────────────────────────────────────────────

def build_resolver(
    tokens: SceneTokens,
    version_override: Optional[str] = None,
    image_format: str               = DEFAULT_FORMAT,
    frame_padding: int              = FRAME_PADDING,
) -> OutputResolver:
    """
    Convenience wrapper — construct an OutputResolver from SceneTokens.

    Parameters
    ----------
    tokens           : SceneTokens
    version_override : str, optional   e.g. "v007"
    image_format     : str             "png" or "jpg"
    frame_padding    : int             digit count for frame numbers

    Returns
    -------
    OutputResolver

    Example
    -------
    >>> from parser import parse_scene_path
    >>> from resolver import build_resolver
    >>>
    >>> tokens   = parse_scene_path(r"Y:\\...\\cur_005_snake_anim_v004.ma")
    >>> resolver = build_resolver(tokens, image_format="png")
    >>>
    >>> print(resolver.full_display_path)
    Y:\\...\\images\\v004\\cur_005_snake_anim_v004.####.png
    >>>
    >>> print(resolver.next_available_version())
    v005
    """
    return OutputResolver(
        tokens,
        version_override=version_override,
        image_format=image_format,
        frame_padding=frame_padding,
    )
