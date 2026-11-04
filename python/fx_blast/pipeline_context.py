"""
pipeline_context.py — fxBlast's bridge to the studio context library.

The pipeline launcher sets FX_* variables when an artist opens a DCC.
fx_context_utils turns those into a shot structure, which is the
authoritative source for show / season / entity / task.

What still comes from the scene file itself (not defined by the context):
  - the scene name ("descriptor", e.g. PlantsLib) and version  -> filename
  - the images/ output root                                    -> scene path

No Maya imports — pure Python.
"""

from __future__ import annotations

import os
from typing import Optional

# FX_ENTITY_TYPE -> (folder name used in paths, parent variable, name variable)
_ENTITIES = {
    "asset":   ("assets",   "FX_ASSET_TYPE", "FX_ASSET"),
    "shot":    ("shots",    "FX_SEQ",        "FX_SHOT"),
    "element": ("elements", "FX_KIT",        "FX_ELEMENT"),
}


def scene_fields() -> Optional[dict]:
    """
    Scene tokens from the pipeline context, or None if the context library
    isn't importable or the launcher variables are incomplete (callers then
    fall back to reading the scene path).

    Returns keys: show, season, context_type, type_or_seq, asset_or_shot,
    task, dcc.
    """
    try:
        from fx_context_utils.shot_structure import shot_structure_from_environment
        structure = shot_structure_from_environment()
    except Exception:
        return None

    entity_type = (os.environ.get("FX_ENTITY_TYPE") or "").lower()
    if entity_type not in _ENTITIES:
        return None                     # v1 / non-entity context: not our layout
    context_type, parent_var, name_var = _ENTITIES[entity_type]

    def _get(attr: str, var: str) -> str:
        # Prefer the resolved structure, fall back to the launcher variable
        value = getattr(structure, attr, None)
        return str(value) if value else os.environ.get(var, "")

    fields = {
        "show":          _get("show", "FX_SHOW"),
        "season":        _get("season", "FX_SEASON"),
        "context_type":  context_type,
        "type_or_seq":   os.environ.get(parent_var, ""),
        "asset_or_shot": os.environ.get(name_var, ""),
        "task":          _get("task", "FX_TASK"),
        "dcc":           _get("dcc", "FX_DCC"),
    }
    required = ("show", "season", "type_or_seq", "asset_or_shot", "task")
    if not all(fields[k] for k in required):
        return None
    return fields
