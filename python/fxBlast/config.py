"""
config.py — Studio pipeline configuration for the Playblast Tool.
"""

from __future__ import annotations

import re

# ── Path Structure ─────────────────────────────────────────────────────────────

PATH_CONFIG = {
    "root_folder":    "shows",
    "dept":           "vfx",
    "dcc_spine":      "3D",
    "dcc":            "maya",
    "output_dir":     "images",
    "scenes_subdirs": {"scenes"},
}

PATH_INDICES = {
    "root_folder": 1,
    "show":        2,
    "season":      3,
    "dept":        4,
    "shot":        5,
    "dcc_spine":   6,
    "discipline":  7,
    "dcc":         8,
}

# ── Naming Convention ──────────────────────────────────────────────────────────

# Reference list of known disciplines — not used for matching,
# just kept here for documentation purposes.
KNOWN_DISCIPLINES = [
    "anim", "layout", "fx", "lighting", "comp",
    "previs", "techvis", "matchmove", "rigging", "cfx",
]

# Discipline matches any single word (letters and digits, no underscores).
# This means the tool works with any task name without needing code changes.
FILENAME_REGEX = re.compile(
    r"^(?P<shot>[a-zA-Z0-9]+_\d+)"
    r"(?:_(?P<descriptor>.+?))?"
    r"_(?P<discipline>[a-zA-Z][a-zA-Z0-9]*)"
    r"_(?P<version>v\d+)"
    r"\.[mM][bB]$"        # .mb only — studio uses binary format
)

# ── Resolution ─────────────────────────────────────────────────────────────────

DEFAULT_RESOLUTION = (1920, 1080)

# ── Anamorphic ─────────────────────────────────────────────────────────────────

ANAMORPHIC_SQUEEZE_FACTORS = [1.3, 1.5, 1.8, 2.0]
DEFAULT_SQUEEZE_FACTOR     = 2.0

# ── Image Format ───────────────────────────────────────────────────────────────
#   JPEG is first and default — fastest to write, smallest on disk.
#   PNG and PNG+Alpha available when transparency is needed.

IMAGE_FORMATS = ["jpg", "png", "png_alpha"]
DEFAULT_FORMAT = "jpg"

FORMAT_LABELS = {
    "jpg":       "JPG",
    "png":       "PNG",
    "png_alpha": "PNG + Alpha",
}

FORMAT_EXTENSIONS = {
    "jpg":       "jpg",
    "png":       "png",
    "png_alpha": "png",
}

# ── Frame Padding ──────────────────────────────────────────────────────────────

FRAME_PADDING = 4

# ── RV ─────────────────────────────────────────────────────────────────────────

RV_PATH = r"C:\Program Files\Autodesk\RV-2024.1.0\bin\rv.exe"
