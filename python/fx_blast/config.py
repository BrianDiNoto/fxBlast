"""
config.py — Studio pipeline configuration for fxBlast.

Naming convention:
    Filename : {season}_{seq_or_assettype}_{shot_or_asset}_{task}[_{descriptor}]_{version}.ma/.mb
    Path     : Y:/shows/{show}/{season}/assets/{assettype}/{asset}/{task}/maya/scenes/
           or : Y:/shows/{show}/{season}/shots/{sequence}/{shot}/{task}/maya/scenes/

To swap in the studio context library when it arrives, replace the
PATH_CONFIG / PATH_INDICES / FILENAME_REGEX block below with calls
to the context library and map its tokens to the same key names.
"""

from __future__ import annotations

import os
import re

# ── Path structure ─────────────────────────────────────────────────────────────
# Supports both asset and shot pipelines.
# Token positions are 1-based from the drive root split on '/'.
#
#   Y:/shows/{show}/{season}/assets/{assettype}/{asset}/{task}/maya/scenes/
#   Y:/shows/{show}/{season}/shots/{sequence}/{shot}/{task}/maya/scenes/
#
# CONTEXT_TYPE_INDEX points to the folder that distinguishes the two
# ("assets" or "shots") so the parser knows which branch it's in.

PATH_CONFIG = {
    "root_folder":   "shows",
    "dcc":           "maya",
    "scenes_folder": "scenes",
    "output_dir":    "images",
}

PATH_INDICES = {
    "root_folder":    1,   # "shows"
    "show":           2,   # e.g. "Alien"
    "season":         3,   # e.g. "ALI2"
    "context_type":   4,   # "assets" or "shots"
    "type_or_seq":    5,   # assettype ("dev") or sequence ("dev")
    "asset_or_shot":  6,   # asset ("brianDiNoto") or shot ("bri100")
    "task":           7,   # e.g. "rnd", "anim", "model"
    "dcc":            8,   # "maya"
}

# ── Filename regex ─────────────────────────────────────────────────────────────
# Matches both .ma and .mb.
# Descriptor is optional — the version token anchors the end of the name.
#
# Groups:
#   season          ALI2
#   type_or_seq     dev
#   asset_or_shot   brianDiNoto  /  bri100
#   task            rnd
#   descriptor      XenoMacroProbeCam  (optional)
#   version         v003

FILENAME_REGEX = re.compile(
    r"^(?P<season>[^_]+)"
    r"_(?P<type_or_seq>[^_]+)"
    r"_(?P<asset_or_shot>[^_]+)"
    r"_(?P<task>[^_]+)"
    r"(?:_(?P<descriptor>.+?))?"
    r"_(?P<version>v\d+)"
    r"\.[mM][aAbB]$"
)

# ── Resolution ──────────────────────────────────────────────────────────────

DEFAULT_RESOLUTION = (1920, 1080)

# ── Anamorphic ─────────────────────────────────────────────────────────────────

ANAMORPHIC_SQUEEZE_FACTORS = [1.3, 1.5, 1.8, 2.0]
DEFAULT_SQUEEZE_FACTOR      = 2.0

# ── Image format ───────────────────────────────────────────────────────────────

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

# ── Frame padding ───────────────────────────────────────────────────────────────

FRAME_PADDING = 4

# ── RV ─────────────────────────────────────────────────────────────────────────
# RV isn't rez-managed at this studio (checked directly, not assumed), so
# there's no package to resolve it from. FX_RV_PATH lets an artist or a farm
# node override the install location per-machine without editing this file;
# the hardcoded path below is just the fallback default.

RV_PATH = os.environ.get("FX_RV_PATH") or r"C:\Program Files\Autodesk\RV-2024.1.0\bin\rv.exe"
