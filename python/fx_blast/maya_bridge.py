"""
maya_bridge.py — Maya-specific DCC interface for the Playblast Tool.
"""

from __future__ import annotations

import os
import re
import struct
from pathlib import Path
from typing import Optional

import maya.cmds as cmds

from .config import DEFAULT_FORMAT, DEFAULT_SQUEEZE_FACTOR, FORMAT_EXTENSIONS, FRAME_PADDING
from .scene_parser import ParseError, manual_tokens, parse_scene_path, SceneTokens

_DEFAULT_CAMERAS = {"persp", "top", "front", "side", "perspShape",
                    "topShape", "frontShape", "sideShape",
                    "left", "leftShape", "right", "rightShape",
                    "bottom", "bottomShape"}

# Tracks HUD element IDs created by this tool so they can be cleaned up
_ACTIVE_HUD_IDS: list[str] = []


# ── Scene ──────────────────────────────────────────────────────────────────────

def get_scene_path() -> str:
    raw = cmds.file(query=True, sceneName=True)
    if not raw or not raw.strip():
        raise ParseError(
            "No scene file is open.\n\n"
            "Please save your scene to the correct pipeline location before "
            "opening the Playblast Tool."
        )
    return os.path.normpath(raw)


def get_scene_tokens() -> SceneTokens:
    return parse_scene_path(get_scene_path())


# ── Maya project (Manual mode) ─────────────────────────────────────────────────

def get_project_root() -> str:
    return os.path.normpath(cmds.workspace(query=True, rootDirectory=True) or "")


def project_is_set(root: str) -> bool:
    """Maya always has a workspace; its built-in "default" project under
    .../maya/projects/ counts as no project set."""
    norm = root.replace("\\", "/").rstrip("/").lower()
    return bool(norm) and not norm.endswith("/maya/projects/default")


def set_project(path: str) -> None:
    cmds.workspace(path, openWorkspace=True)


def _project_folder(rule: str, fallback: str) -> str:
    try:
        entry = cmds.workspace(fileRuleEntry=rule) or fallback
    except Exception:
        entry = fallback
    return os.path.normpath(cmds.workspace(expandName=entry))


def get_manual_tokens() -> SceneTokens:
    """
    Tokens for Manual (out-of-pipeline) mode: output goes to the Maya
    project's images/ and movies/ folders. A workfile name without a
    version gets the next version after the highest one already blasted.
    """
    scene = get_scene_path()
    root  = get_project_root()
    if not project_is_set(root):
        raise ParseError(
            "No Maya project is set.\n\n"
            "Click Set Project... and pick the project folder. Blasts go to "
            "the project's images/ and movies/ folders.")
    tokens = manual_tokens(scene, os.path.basename(root),
                           _project_folder("images", "images"),
                           _project_folder("movie", "movies"),
                           renders_root=os.path.join(root, "renders"))
    if not tokens.version:
        existing = get_layout(tokens)[0].existing_versions()
        top = max((int(v[1:]) for v in existing), default=0)
        tokens.version = f"v{top + 1:03d}"
    return tokens


def get_layout(tokens: SceneTokens):
    """(OutputLayout, warning or None) for the open scene.

    Pipeline templates when the launch context describes this scene (it is
    inside FX_TASK_DIR); otherwise the same structure built locally. Off
    Pipe mirrors it under <project>/renders, named from the workfile."""
    from .layout import LayoutError, mirror_layout, pipeline_layout
    from .pipeline_context import _scene_in_task
    key = tokens.output_stem
    if tokens.source == "manual":
        return mirror_layout(tokens.renders_root, "", key, tokens.asset_or_shot), None
    prefix = "_".join(p for p in (tokens.season, tokens.type_or_seq,
                                  tokens.asset_or_shot, tokens.task) if p)
    desc = tokens.descriptor or ""
    warning = None
    if os.environ.get("FX_TASK_DIR") and _scene_in_task(get_scene_path()):
        try:
            return pipeline_layout(key, desc), None
        except LayoutError as exc:
            warning = str(exc)
            print("[fxBlast] pipeline paths unavailable, using the local layout: " + warning)
    return mirror_layout(tokens.renders_root, prefix, key, desc), warning


# ── Cameras ────────────────────────────────────────────────────────────────────

def list_cameras(include_default: bool = False) -> list[dict]:
    camera_shapes = cmds.ls(type="camera") or []
    cameras = []
    for shape in camera_shapes:
        if not include_default and shape in _DEFAULT_CAMERAS:
            continue
        # Skip orthographic cameras (top/front/side and any custom ortho cams)
        if not include_default:
            try:
                if cmds.getAttr(f"{shape}.orthographic"):
                    continue
            except Exception:
                pass
        transforms = cmds.listRelatives(shape, parent=True, fullPath=False) or []
        transform  = transforms[0] if transforms else shape
        cameras.append({"transform": transform, "shape": shape, "label": transform})
    cameras.sort(key=lambda c: c["label"].lower())
    return cameras


def get_selected_camera() -> Optional[dict]:
    """Return the first camera in the current Maya selection, or None."""
    # Check selected transforms that have a camera shape
    for transform in (cmds.ls(selection=True, type="transform") or []):
        shapes = cmds.listRelatives(transform, shapes=True, type="camera") or []
        if shapes:
            return {"transform": transform, "shape": shapes[0], "label": transform}
    # Check directly selected camera shapes
    for shape in (cmds.ls(selection=True, type="camera") or []):
        transforms = cmds.listRelatives(shape, parent=True, fullPath=False) or []
        transform  = transforms[0] if transforms else shape
        return {"transform": transform, "shape": shape, "label": transform}
    return None


# ── Image planes ───────────────────────────────────────────────────────────────

def list_image_planes(camera_shape: str) -> list[dict]:
    planes = cmds.listConnections(camera_shape, type="imagePlane") or []
    result = []
    for node in set(planes):
        raw_path = _safe_get_attr(node, "imageName") or ""
        abs_path = _resolve_image_path(raw_path) if raw_path else None
        result.append({
            "node":       node,
            "image_path": abs_path,
            "label":      node if not abs_path else Path(abs_path).name,
        })
    return result


def get_image_plane_resolution(image_plane_node: str) -> Optional[tuple[int, int]]:
    raw_path = _safe_get_attr(image_plane_node, "imageName") or ""
    abs_path = _resolve_image_path(raw_path) if raw_path else None
    if not abs_path or not Path(abs_path).is_file():
        return None
    return read_image_dimensions(abs_path)


# ── Render / playback helpers ──────────────────────────────────────────────────

def get_render_resolution() -> tuple[int, int]:
    return (
        int(cmds.getAttr("defaultResolution.width")),
        int(cmds.getAttr("defaultResolution.height")),
    )


def open_render_settings() -> None:
    """Open Maya's Render Settings window."""
    import maya.mel as mel
    mel.eval("unifiedRenderGlobalsWindow")


def watch_render_resolution(callback) -> list[int]:
    """Call `callback` whenever the render width/height change.
    Returns the scriptJob ids (pass them to kill_script_jobs)."""
    jobs = []
    for attr in ("defaultResolution.width", "defaultResolution.height"):
        try:
            jobs.append(cmds.scriptJob(attributeChange=[attr, callback]))
        except Exception:
            pass
    return jobs


def kill_script_jobs(jobs: list[int]) -> None:
    for j in jobs or []:
        try:
            if cmds.scriptJob(exists=j):
                cmds.scriptJob(kill=j, force=True)
        except Exception:
            pass


def get_frame_range() -> tuple[int, int]:
    return (
        int(cmds.playbackOptions(query=True, minTime=True)),
        int(cmds.playbackOptions(query=True, maxTime=True)),
    )


def get_fps() -> float:
    """Return the current scene frame rate in frames per second."""
    fps_map = {
        "game":      15.0,
        "film":      24.0,
        "pal":       25.0,
        "ntsc":      30.0,
        "show":      48.0,
        "palf":      50.0,
        "ntscf":     60.0,
        "23.976fps": 23.976,
        "29.97fps":  29.97,
        "47.952fps": 47.952,
        "59.94fps":  59.94,
    }
    unit = cmds.currentUnit(query=True, time=True)
    return fps_map.get(unit, 24.0)


# ── Film gate / Pan-Zoom ───────────────────────────────────────────────────────

def disable_film_gate_pan_zoom(camera_shape: str) -> dict:
    """
    Put the camera into No Gate mode for a clean playblast.
    Returns a snapshot for restoration.
    """
    snapshot = {
        "displayFilmGate":   bool(_safe_get_attr(camera_shape, "displayFilmGate")   or False),
        "displayGateMask":   bool(_safe_get_attr(camera_shape, "displayGateMask")   or False),
        "displayResolution": bool(_safe_get_attr(camera_shape, "displayResolution") or False),
        "panZoomEnabled":    bool(_safe_get_attr(camera_shape, "panZoomEnabled")    or False),
        "overscan":          float(_safe_get_attr(camera_shape, "overscan")         or 1.0),
    }
    cmds.setAttr(f"{camera_shape}.displayFilmGate",   False)
    cmds.setAttr(f"{camera_shape}.displayGateMask",   False)
    cmds.setAttr(f"{camera_shape}.displayResolution", False)
    cmds.setAttr(f"{camera_shape}.panZoomEnabled",    False)
    cmds.setAttr(f"{camera_shape}.overscan",          1.0)
    return snapshot


def restore_film_gate_pan_zoom(camera_shape: str, snapshot: dict) -> None:
    cmds.setAttr(f"{camera_shape}.displayFilmGate",   snapshot["displayFilmGate"])
    cmds.setAttr(f"{camera_shape}.displayGateMask",   snapshot["displayGateMask"])
    cmds.setAttr(f"{camera_shape}.displayResolution", snapshot["displayResolution"])
    cmds.setAttr(f"{camera_shape}.panZoomEnabled",    snapshot["panZoomEnabled"])
    cmds.setAttr(f"{camera_shape}.overscan",          snapshot["overscan"])


# ── Anamorphic ─────────────────────────────────────────────────────────────────

def configure_anamorphic(camera_shape: str, squeeze_factor: float = DEFAULT_SQUEEZE_FACTOR) -> dict:
    prev = {
        "lensSqueezeRatio":  _safe_get_attr(camera_shape, "lensSqueezeRatio") or 1.0,
        "deviceAspectRatio": cmds.getAttr("defaultResolution.deviceAspectRatio"),
        "pixelAspect":       cmds.getAttr("defaultResolution.pixelAspect"),
    }
    cmds.setAttr(f"{camera_shape}.lensSqueezeRatio", squeeze_factor)
    cmds.setAttr("defaultResolution.pixelAspect", squeeze_factor)
    w, h = get_render_resolution()
    cmds.setAttr("defaultResolution.deviceAspectRatio", (w / h) * squeeze_factor)
    return prev


def restore_camera_settings(camera_shape: str, snapshot: dict) -> None:
    cmds.setAttr(f"{camera_shape}.lensSqueezeRatio",    snapshot["lensSqueezeRatio"])
    cmds.setAttr("defaultResolution.pixelAspect",       snapshot["pixelAspect"])
    cmds.setAttr("defaultResolution.deviceAspectRatio", snapshot["deviceAspectRatio"])


def calculate_anamorphic_blast_size(
    delivery_width: int, delivery_height: int, squeeze_factor: float,
) -> tuple[int, int]:
    return max(1, round(delivery_width / squeeze_factor)), delivery_height


# ── HUD ────────────────────────────────────────────────────────────────────────

def setup_hud(
    fields:       set,
    section:      int,
    align:        str,
    shot_info:    str,
    camera_name:  str,
    camera_shape: str,
    width:        int,
    height:       int,
    fps:          float,
    version:      str,
    start_frame:  int,
    end_frame:    int,
) -> dict:
    """
    Paint the burn-in as one stack of lines in one corner (`section`).
    Every HUD the artist has on is hidden (the burn-in replaces it) and
    restored by teardown_hud(snapshot).

    Focal length and frame number are read on every frame, so a zoom shows.
    Values come from Python callables: a string command would be run as
    Python (the HUD is made from Python), and MEL there is a syntax error.
    """
    teardown_hud()

    # Hide every HUD the artist has on -- built-in or from other tools
    snapshot: dict = {}
    for hud_id in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        try:
            if cmds.headsUpDisplay(hud_id, query=True, visible=True):
                snapshot[hud_id] = True
                cmds.headsUpDisplay(hud_id, edit=True, visible=False)
        except Exception:
            pass

    def focal() -> str:
        value = _safe_get_attr(camera_shape, "focalLength")
        return f"{value:.1f}mm".replace(".0mm", "mm") if value else "--"

    def frame() -> str:
        return f"{int(round(cmds.currentTime(query=True)))}   ({start_frame}-{end_frame})"

    fps_txt = f"{int(fps)}" if fps == int(fps) else f"{fps}"
    # (id, label, static value or callable, refresh every frame)
    lines = [
        ("shot",    shot_info,       "",                    False),
        ("camera",  "Camera:",       camera_name,           False),
        ("focal",   "Focal length:", focal,                 True),
        ("res",     "Resolution:",   f"{width}x{height}",   False),
        ("fps",     "FPS:",          fps_txt,               False),
        ("version", "Version:",      version,               False),
        ("frame",   "Frame:",        frame,                 True),
    ]
    lines = [ln for ln in lines if ln[0] in fields and (ln[1] or ln[2])]
    # Bottom sections stack upward from block 0: add bottom line first
    if section >= 5:
        lines.reverse()
    for fid, label, value, _per_frame in lines:
        command = value if callable(value) else (lambda v=value: v)
        # Every command needs a trigger, or Maya warns and leaves the line
        # inactive: refresh all of them each frame (cheap for fixed text).
        _add_hud(f"FXpblast_{fid}", section=section, label=label,
                 command=command if value != "" else None,
                 attach=True, align=align)

    return snapshot


def teardown_hud(snapshot: Optional[dict] = None) -> None:
    """Remove all HUD elements created by this tool and restore the
    artist's own HUDs."""
    for hud_id in list(_ACTIVE_HUD_IDS):
        try:
            if cmds.headsUpDisplay(hud_id, exists=True):
                cmds.headsUpDisplay(hud_id, remove=True)
        except Exception:
            pass
    _ACTIVE_HUD_IDS.clear()

    if snapshot:
        for hud_id, was_visible in snapshot.items():
            try:
                cmds.headsUpDisplay(hud_id, edit=True, visible=was_visible)
            except Exception:
                pass


def _add_hud(
    hud_id:  str,
    section: int,
    label:   str,
    command=None,
    attach:  bool = False,
    align:   str  = "left",
) -> None:
    """Create a single HUD element and register it for cleanup.

    The block is the section's next free one: Maya's own HUDs (e.g. camera
    names in section 7) keep their block even while hidden, and creating
    an element on a taken block fails."""
    try:
        if cmds.headsUpDisplay(hud_id, exists=True):
            cmds.headsUpDisplay(hud_id, remove=True)
        block = cmds.headsUpDisplay(nextFreeBlock=section)
    except Exception as exc:
        print(f"[fxBlast] burn-in: no free HUD block in section {section}: {exc}")
        return
    kwargs = dict(
        section        = section,
        block          = block,
        blockSize      = "large",
        blockAlignment = align,
        label          = label,
        labelFontSize  = "large",
        dataFontSize   = "large",
    )
    if command is not None:
        kwargs["command"]         = command
        kwargs["attachToRefresh"] = attach
    try:
        cmds.headsUpDisplay(hud_id, **kwargs)
        _ACTIVE_HUD_IDS.append(hud_id)
    except Exception as exc:
        print(f"[fxBlast] burn-in: could not add {hud_id}: {exc}")


# ── Playblast execution ────────────────────────────────────────────────────────

def execute_playblast(
    camera:                str,
    width:                 int,
    height:                int,
    image_format:          str           = DEFAULT_FORMAT,
    frame_padding:         int           = FRAME_PADDING,
    show_ornaments:        bool          = False,
    start_frame:           Optional[int] = None,
    end_frame:             Optional[int] = None,
    output_path_override:  Optional[str] = None,
    panel:                 Optional[str] = None,
    offscreen:             bool          = True,
) -> str:
    """
    Execute a Maya playblast.

    Parameters
    ----------
    output_path_override : str, optional
        Full stem path (no frame number, no extension) for the output frames,
        from the output layout. Required.
    panel : str, optional
        Model panel to blast through. When None, the focused panel (or the
        first model panel) is used, as before.
    offscreen : bool
        Offscreen playblast (default, as before). Render-layer stepping blasts
        onscreen through the viewport the artist is looking at.

    Returns
    -------
    str
        The folder that received the frames.
    """
    if start_frame is None or end_frame is None:
        start_frame, end_frame = get_frame_range()

    if output_path_override:
        os.makedirs(os.path.dirname(output_path_override), exist_ok=True)
        blast_path    = output_path_override
        result_folder = os.path.dirname(output_path_override)
    else:
        raise ValueError("execute_playblast needs output_path_override")

    ext         = FORMAT_EXTENSIONS.get(image_format, "jpg")
    compression = ext

    if panel:
        cmds.modelPanel(panel, edit=True, camera=camera)
        cmds.setFocus(panel)
    else:
        _set_viewport_camera(camera)

    # The burn-in only shows if the panel's own HUD display is on
    # (viewport menu Display > Heads Up Display). Turn it on, then restore.
    hud_panel = panel or get_active_model_panel()
    hud_was   = None
    if show_ornaments and hud_panel:
        try:
            hud_was = cmds.modelEditor(hud_panel, query=True, hud=True)
            cmds.modelEditor(hud_panel, edit=True, hud=True)
        except Exception as exc:
            print(f"[fxBlast] burn-in: could not turn on HUD in {hud_panel}: {exc}")

    print(f"[fxBlast] playblast {blast_path}.####.{ext}  {start_frame}-{end_frame}  "
          f"{width}x{height}  panel={hud_panel}  ornaments={show_ornaments}")
    try:
        cmds.playblast(
            filename       = blast_path,
            format         = "image",
            compression    = compression,
            widthHeight    = (width, height),
            percent        = 100,
            quality        = 100,
            startTime      = start_frame,
            endTime        = end_frame,
            forceOverwrite = True,
            framePadding   = frame_padding,
            viewer         = False,
            showOrnaments  = show_ornaments,
            offScreen      = offscreen,
        )
    finally:
        if hud_was is False:
            try: cmds.modelEditor(hud_panel, edit=True, hud=False)
            except Exception: pass

    return result_folder


# ── Render layers ──────────────────────────────────────────────────────────────

_MASTER_LAYERS = {"defaultRenderLayer", "masterLayer"}


def _use_render_setup() -> bool:
    try:
        return bool(cmds.mayaHasRenderSetup())
    except AttributeError:
        return False


def list_render_layers() -> list[str]:
    """Scene render layers, master layer excluded (legacy or Render Setup)."""
    if _use_render_setup():
        import maya.app.renderSetup.model.renderSetup as rsm
        return [l.name() for l in rsm.instance().getRenderLayers()]
    layers = cmds.ls(type="renderLayer") or []
    return [l for l in layers if l not in _MASTER_LAYERS and ":" not in l]


def get_current_render_layer() -> str:
    if _use_render_setup():
        import maya.app.renderSetup.model.renderSetup as rsm
        return rsm.instance().getVisibleRenderLayer().name()
    return cmds.editRenderLayerGlobals(query=True, currentRenderLayer=True)


def switch_render_layer(name: str) -> None:
    """Make `name` the active render layer ("defaultRenderLayer" = master)."""
    if _use_render_setup():
        import maya.app.renderSetup.model.renderSetup as rsm
        rs = rsm.instance()
        if name in _MASTER_LAYERS:
            rs.switchToLayer(rs.getDefaultRenderLayer())
            return
        for l in rs.getRenderLayers():
            if l.name() == name:
                rs.switchToLayer(l)
                return
        raise RuntimeError(f"Render layer not found: {name}")
    cmds.editRenderLayerGlobals(currentRenderLayer=name)


def _camera_dict(transform: str) -> Optional[dict]:
    if not transform or not cmds.objExists(transform):
        return None
    shapes = cmds.listRelatives(transform, shapes=True, type="camera") or []
    if not shapes:
        return None
    return {"transform": transform, "shape": shapes[0], "label": transform}


def find_layer_camera(layer: str) -> Optional[dict]:
    """
    The camera a render layer should be blasted through:
      1. the camera tagged by the Megascans turntable tool for this layer
      2. a camera named <layer>_CAM
    Returns None when neither exists (caller falls back).
    """
    for shp in cmds.ls(type="locator") or []:
        loc = (cmds.listRelatives(shp, parent=True) or [None])[0]
        if not loc:
            continue
        try:
            if (cmds.attributeQuery("fxTTLayer", node=loc, exists=True)
                    and cmds.getAttr(f"{loc}.fxTTLayer") == layer):
                cam = _camera_dict(cmds.getAttr(f"{loc}.fxTTCam"))
                if cam:
                    return cam
        except Exception:
            pass
    return _camera_dict(f"{layer}_CAM")


def get_active_model_panel() -> Optional[str]:
    """The viewport the artist last worked in."""
    p = cmds.getPanel(withFocus=True)
    if p and cmds.getPanel(typeOf=p) == "modelPanel":
        return p
    try:
        ed = cmds.playblast(activeEditor=True)
        if ed and cmds.getPanel(typeOf=ed) == "modelPanel":
            return ed
    except Exception:
        pass
    for p in cmds.getPanel(visiblePanels=True) or []:
        if cmds.getPanel(typeOf=p) == "modelPanel":
            return p
    return None


def set_panel_hud(panel: str, on: bool) -> Optional[bool]:
    """Turn a model panel's HUD display on/off; returns the previous state."""
    try:
        was = cmds.modelEditor(panel, query=True, hud=True)
        cmds.modelEditor(panel, edit=True, hud=on)
        return was
    except Exception:
        return None


def get_active_viewport_camera() -> Optional[dict]:
    """The camera the artist is looking through in the active viewport."""
    panel = get_active_model_panel()
    if not panel:
        return None
    cam = cmds.modelPanel(panel, query=True, camera=True)
    if cam and cmds.objExists(cam) and cmds.nodeType(cam) == "camera":
        cam = (cmds.listRelatives(cam, parent=True) or [cam])[0]
    return _camera_dict(cam)


def get_panel_camera(panel: str) -> str:
    return cmds.modelPanel(panel, query=True, camera=True)


def set_panel_camera(panel: str, camera: str) -> None:
    cmds.modelPanel(panel, edit=True, camera=camera)


# ── Scene note reader ──────────────────────────────────────────────────────────

def read_scene_note(scene_path: str) -> str:
    """
    Read the artist note from the file save tool sidecar .txt file.

    Sidecar format (one value per line):
        line 1 -- username
        line 2 -- date/time
        line 3 -- note text

    Returns empty string if the sidecar does not exist or cannot be read.
    """
    sidecar = scene_path + ".txt"
    if not os.path.isfile(sidecar):
        return ""
    try:
        with open(sidecar, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        return lines[2].strip() if len(lines) >= 3 else ""
    except Exception:
        return ""


# ── Image dimension reader ─────────────────────────────────────────────────────

def read_image_dimensions(path: str) -> Optional[tuple[int, int]]:
    try:
        with open(path, "rb") as fh:
            header = fh.read(26)
        if header[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", header[16:24])
            return int(w), int(h)
        if header[:2] == b"\xff\xd8":
            return _jpeg_dimensions(path)
        if header[:4] == b"\x76\x2f\x31\x01":
            return _exr_dimensions(path)
        if header[:2] in (b"II", b"MM"):
            return _tiff_dimensions(path)
    except (OSError, struct.error):
        pass
    return None


def _jpeg_dimensions(path: str) -> Optional[tuple[int, int]]:
    try:
        with open(path, "rb") as fh:
            fh.read(2)
            while True:
                marker, = struct.unpack(">H", fh.read(2))
                if marker in (0xFFC0, 0xFFC2):
                    fh.read(3)
                    h, w = struct.unpack(">HH", fh.read(4))
                    return int(w), int(h)
                size, = struct.unpack(">H", fh.read(2))
                fh.read(size - 2)
    except (OSError, struct.error):
        return None


def _exr_dimensions(path: str) -> Optional[tuple[int, int]]:
    try:
        with open(path, "rb") as fh:
            fh.read(8)
            while True:
                name = _read_null_terminated(fh)
                if not name:
                    break
                _read_null_terminated(fh)
                size, = struct.unpack("<I", fh.read(4))
                data  = fh.read(size)
                if name == b"dataWindow":
                    x_min, y_min, x_max, y_max = struct.unpack("<iiii", data)
                    return (x_max - x_min + 1), (y_max - y_min + 1)
    except (OSError, struct.error):
        return None


def _tiff_dimensions(path: str) -> Optional[tuple[int, int]]:
    try:
        with open(path, "rb") as fh:
            bom    = fh.read(2)
            endian = "<" if bom == b"II" else ">"
            fh.read(2)
            offset, = struct.unpack(f"{endian}I", fh.read(4))
            fh.seek(offset)
            num_entries, = struct.unpack(f"{endian}H", fh.read(2))
            width = height = None
            for _ in range(num_entries):
                tag, type_id, count, value_raw = struct.unpack(f"{endian}HHI4s", fh.read(12))
                if type_id in (3, 4):
                    fmt = f"{endian}H" if type_id == 3 else f"{endian}I"
                    value, = struct.unpack(fmt, value_raw[:struct.calcsize(fmt)])
                    if tag == 256:   width  = int(value)
                    elif tag == 257: height = int(value)
                if width is not None and height is not None:
                    return width, height
    except (OSError, struct.error):
        return None


def _read_null_terminated(fh) -> bytes:
    result = bytearray()
    while True:
        byte = fh.read(1)
        if not byte or byte == b"\x00":
            return bytes(result)
        result.extend(byte)


# ── Viewport / attribute helpers ───────────────────────────────────────────────

def _set_viewport_camera(camera_transform: str) -> None:
    panels  = cmds.getPanel(type="modelPanel") or []
    focused = cmds.getPanel(withFocus=True)
    target  = focused if focused in panels else (panels[0] if panels else None)
    if target:
        cmds.modelPanel(target, edit=True, camera=camera_transform)


def _safe_get_attr(node: str, attr: str):
    try:
        return cmds.getAttr(f"{node}.{attr}")
    except Exception:
        return None


def _resolve_image_path(raw_path: str) -> Optional[str]:
    if not raw_path:
        return None
    return os.path.abspath(os.path.expandvars(raw_path.strip()))




# ── Viewport 2.0 render settings ───────────────────────────────────────────────
# Attribute names confirmed from hardwareRenderingGlobals in Maya 2022.

_VP2_ATTRS = {
    # Motion Blur
    "motionBlur":         "hardwareRenderingGlobals.motionBlurEnable",
    "motionBlurShutter":  "hardwareRenderingGlobals.motionBlurShutterOpenFraction",
    "motionBlurSamples":  "hardwareRenderingGlobals.motionBlurSampleCount",
    # SSAO
    "ssao":               "hardwareRenderingGlobals.ssaoEnable",
    "ssaoAmount":         "hardwareRenderingGlobals.ssaoAmount",
    "ssaoRadius":         "hardwareRenderingGlobals.ssaoRadius",
    "ssaoFilterRadius":   "hardwareRenderingGlobals.ssaoFilterRadius",
    "ssaoSamples":        "hardwareRenderingGlobals.ssaoSamples",
    # Anti-Aliasing
    "msaa":               "hardwareRenderingGlobals.multiSampleEnable",
    "multiSampleCount":   "hardwareRenderingGlobals.multiSampleCount",
    "lineAA":             "hardwareRenderingGlobals.lineAAEnable",
}


def get_viewport2_settings() -> dict:
    """Return a dict of current Viewport 2.0 hardware rendering settings."""
    result = {}
    for key, attr in _VP2_ATTRS.items():
        try:
            result[key] = cmds.getAttr(attr)
        except Exception:
            pass
    # Provide defaults for any attrs that failed
    result.setdefault("motionBlurShutter",  0.2)
    result.setdefault("motionBlurSamples",  8)
    result.setdefault("ssaoAmount",         1.0)
    result.setdefault("ssaoRadius",         16.0)
    result.setdefault("ssaoFilterRadius",   16)
    result.setdefault("ssaoSamples",        16)
    result.setdefault("multiSampleCount",   8)
    return result


def apply_viewport2_settings(
    camera_shape:  str            = "",
    motion_blur:   Optional[bool] = None,
    dof:           Optional[bool] = None,
    ssao:          Optional[bool] = None,
    anti_alias:    Optional[bool] = None,
    ssao_amount:   Optional[float]= None,
    ssao_radius:   Optional[float]= None,
    ssao_filter:   Optional[int]  = None,
    ssao_samples:  Optional[int]  = None,
    aa_samples:    Optional[int]  = None,
    mb_shutter:    Optional[float]= None,
    mb_samples:    Optional[int]  = None,
) -> dict:
    """
    Apply Viewport 2.0 settings before a blast and return a full snapshot
    of previous values for restoration.
    """
    snapshot = get_viewport2_settings()

    if camera_shape:
        try:
            snapshot["cameraDoF"] = bool(_safe_get_attr(camera_shape, "depthOfField") or False)
        except Exception:
            pass

    def _set(attr_key, value):
        if value is None:
            return
        try:
            cmds.setAttr(_VP2_ATTRS[attr_key], value)
        except Exception:
            pass

    _set("motionBlur",        motion_blur)
    _set("motionBlurShutter", mb_shutter)
    _set("motionBlurSamples", int(mb_samples) if mb_samples is not None else None)
    _set("ssao",              ssao)
    _set("ssaoAmount",        ssao_amount)
    _set("ssaoRadius",        ssao_radius)
    _set("ssaoFilterRadius",  int(ssao_filter) if ssao_filter is not None else None)
    _set("ssaoSamples",       int(ssao_samples) if ssao_samples is not None else None)
    _set("msaa",              anti_alias)
    _set("lineAA",            anti_alias)
    _set("multiSampleCount",  int(aa_samples) if aa_samples is not None else None)

    if dof is not None and camera_shape:
        try:
            cmds.setAttr(f"{camera_shape}.depthOfField", dof)
        except Exception:
            pass

    return snapshot


def restore_viewport2_settings(snapshot: dict, camera_shape: str = "") -> None:
    """Restore Viewport 2.0 settings from a snapshot."""
    for key, attr in _VP2_ATTRS.items():
        if key not in snapshot:
            continue
        try:
            val = snapshot[key]
            # Ensure int attrs stay int
            if key in ("motionBlurSamples", "ssaoFilterRadius", "ssaoSamples", "multiSampleCount"):
                val = int(val)
            cmds.setAttr(attr, val)
        except Exception:
            pass

    if "cameraDoF" in snapshot and camera_shape:
        try:
            cmds.setAttr(f"{camera_shape}.depthOfField", snapshot["cameraDoF"])
        except Exception:
            pass


def get_camera_dof_info(camera_shape: str) -> dict:
    """Return the camera's Depth of Field settings for informational display."""
    return {
        "focusDistance":    float(_safe_get_attr(camera_shape, "focusDistance")   or 5.0),
        "fStop":            float(_safe_get_attr(camera_shape, "fStop")            or 5.6),
        "focusRegionScale": float(_safe_get_attr(camera_shape, "focusRegionScale") or 1.0),
    }
