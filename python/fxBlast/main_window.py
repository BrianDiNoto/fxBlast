"""
main_window.py — PySide2 UI for fxBlast.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
from typing import Optional

try:
    from PySide2.QtWidgets import (
        QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
        QDialogButtonBox, QDoubleSpinBox, QFrame, QFormLayout,
        QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
        QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
        QPushButton, QRadioButton, QSizePolicy, QSpinBox, QTreeWidget,
        QTreeWidgetItem, QVBoxLayout, QWidget,
    )
    from PySide2.QtCore import Qt, QTimer
    from PySide2.QtGui import QColor
except ImportError:
    from PySide6.QtWidgets import (
        QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
        QDialogButtonBox, QDoubleSpinBox, QFrame, QFormLayout,
        QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
        QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
        QPushButton, QRadioButton, QSizePolicy, QSpinBox, QTreeWidget,
        QTreeWidgetItem, QVBoxLayout, QWidget,
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor

try:
    from maya.app.general.mayaMixin import MayaQWidgetDockableMixin as _DockMixin
    _TOOL_BASES = (_DockMixin, QWidget)
except ImportError:
    _TOOL_BASES = (QWidget,)

from .config import (
    ANAMORPHIC_SQUEEZE_FACTORS, DEFAULT_FORMAT, DEFAULT_RESOLUTION,
    DEFAULT_SQUEEZE_FACTOR, FORMAT_EXTENSIONS, FORMAT_LABELS,
    FRAME_PADDING, IMAGE_FORMATS, RV_PATH,
)
from .scene_parser import ParseError, SceneTokens
from .resolver import OutputResolver, ResolveError, build_resolver

_NOTES_FILENAME = "_pb_notes.json"
_META_FILENAME  = "_pb_meta.json"

_COL_VERSION    = 0
_COL_FRAMERANGE = 1
_COL_FRAMES     = 2
_COL_FPS        = 3
_COL_RESOLUTION = 4
_COL_NOTES      = 5

# ── Palette ────────────────────────────────────────────────────────────────────
_C_SECTION = "#8faabf"
_C_LABEL   = "#6888a0"
_C_VALUE   = "#c0d4e0"
_C_DIM     = "#506070"
_C_GREEN   = "#60a878"
_C_RED     = "#e07070"

# ── Styles ─────────────────────────────────────────────────────────────────────
_S_REFRESH = """
    QPushButton {
        background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
        border-radius: 4px; padding: 5px 12px; font-size: 12px; color: #90aabf;
    }
    QPushButton:hover  { background: rgba(255,255,255,0.10); color: #b0c8d8; }
    QPushButton:pressed{ background: rgba(255,255,255,0.04); }
"""
_S_ERROR = """
    QLabel {
        background: #5a1a1a; color: #ff9a9a;
        border: 1px solid #8b3333; border-radius: 4px;
        padding: 6px 10px; font-size: 12px;
    }
"""
_S_BLAST = """
    QPushButton {
        background: #454545; color: #b8b8b8; border: 1px solid #606060;
        border-radius: 4px; padding: 3px 0; font-size: 12px;
        font-weight: normal; min-height: 22px;
    }
    QPushButton:hover   { background: #525252; }
    QPushButton:pressed { background: #383838; }
    QPushButton:disabled{ background: #282828; color: #484848; border-color: #383838; }
"""
_S_BLAST_DONE = """
    QPushButton {
        background: #334d33; color: #c8e0c8; border: 1px solid #3e5e3e;
        border-radius: 4px; padding: 3px 0; font-size: 12px;
        font-weight: normal; min-height: 22px;
    }
    QPushButton:hover   { background: #3d5e3d; }
    QPushButton:pressed { background: #28402a; }
    QPushButton:disabled{ background: #222e22; color: #445044; border-color: #2e3e2e; }
"""
_S_RV = """
    QPushButton {
        background: #3e3e3e; color: #909090; border: 1px solid #585858;
        border-radius: 3px; padding: 3px 0; font-size: 12px;
        font-weight: normal; min-height: 22px;
    }
    QPushButton:hover   { background: #4a4a4a; color: #b0b0b0; }
    QPushButton:pressed { background: #333333; }
    QPushButton:disabled{ background: #282828; color: #484848; border-color: #383838; }
"""
"""
    QPushButton {
        background: #3e3e3e; color: #909090; border: 1px solid #585858;
        border-radius: 3px; padding: 3px 0; font-size: 12px;
        font-weight: normal; min-height: 22px;
    }
    QPushButton:hover   { background: #4a4a4a; color: #b0b0b0; }
    QPushButton:pressed { background: #333333; }
    QPushButton:disabled{ background: #282828; color: #484848; border-color: #383838; }
"""
_S_CAM_FRAME = """
    QFrame {
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 3px; background: rgba(0,0,0,0.15);
    }
"""
# Styled checkboxes — white indicator when checked, green text for selected camera
_S_CAM_LIST = f"""
    QListWidget {{
        font-size: 12px; border: none; background: transparent;
    }}
    QListWidget::item {{ padding: 2px 0; color: {_C_VALUE}; }}
    QListWidget::item:selected {{ background: transparent; }}
    QListWidget::indicator {{
        width: 13px; height: 13px;
        border: 1px solid rgba(255,255,255,0.28);
        border-radius: 2px;
        background: rgba(255,255,255,0.05);
    }}
    QListWidget::indicator:checked {{
        background: rgba(255,255,255,0.88);
        border-color: rgba(255,255,255,0.70);
        image: none;
    }}
    QListWidget::indicator:unchecked:hover {{
        background: rgba(255,255,255,0.12);
        border-color: rgba(255,255,255,0.50);
    }}
"""
_C_CAM_CHECKED   = "#7ab87a"   # green text for checked cameras
_C_CAM_UNCHECKED = _C_VALUE    # normal text for unchecked
_S_PATH = """
    QLabel {
        background: rgba(0,0,0,0.2); color: #90c890;
        border: 1px solid rgba(255,255,255,0.07); border-radius: 3px;
        padding: 5px 8px; font-family: monospace; font-size: 11px;
    }
"""
_S_TWIRL = """
    QPushButton {
        text-align: left; padding: 3px 8px;
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 3px; font-size: 12px; color: #6888a0;
    }
    QPushButton:hover { background: rgba(255,255,255,0.06); color: #8aaabf; }
"""
_S_NOTE_EDIT = f"""
    QLineEdit {{
        background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.10);
        border-radius: 3px; padding: 5px 8px;
        font-size: 12px; color: {_C_VALUE};
    }}
    QLineEdit:focus {{ border-color: rgba(255,255,255,0.22); }}
"""
_S_SMALL_BTN = "font-size: 11px; padding: 3px 8px;"
_S_SUB_LBL   = f"font-size: 11px; color: {_C_DIM}; margin-left: 20px;"
_S_DOCK_BTN  = """
    QPushButton {
        background: rgba(255,255,255,0.05); color: #7090a8;
        border: 1px solid rgba(255,255,255,0.14); border-radius: 3px;
        padding: 2px 8px; font-size: 11px;
    }
    QPushButton:hover { background: rgba(255,255,255,0.10); color: #90b0c4; }
    QPushButton:pressed { background: rgba(255,255,255,0.03); }
"""

_COLOR_CURRENT = QColor("#334d33")
_COLOR_CHILD   = QColor("#1a2a3a")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _maya_main_window() -> Optional[QWidget]:
    try:
        from maya import OpenMayaUI as omui
        try:
            from shiboken2 import wrapInstance
        except ImportError:
            from shiboken6 import wrapInstance
        return wrapInstance(int(omui.MQtUtil.mainWindow()), QWidget)
    except Exception:
        return None


def _cam_slug(label: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", label).strip("_").lower()


def _frame_nums(files: list[str]) -> tuple[int, int]:
    def _n(f):
        nums = re.findall(r"\d+", os.path.basename(os.path.splitext(f)[0]))
        return int(nums[-1]) if nums else 0
    return _n(files[0]), _n(files[-1])


def _lbl(text: str) -> QLabel:
    w = QLabel(text); w.setStyleSheet(f"color:{_C_LABEL}; font-size:12px;"); return w


def _val(text: str = "--") -> QLabel:
    w = QLabel(text); w.setStyleSheet(f"color:{_C_VALUE}; font-size:12px;"); return w


def _section_header(text: str) -> QLabel:
    w = QLabel(text)
    w.setStyleSheet(f"color:{_C_SECTION}; font-size:12px; margin-top:4px; margin-bottom:2px;")
    return w


def _hline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("color: rgba(255,255,255,0.07);"); return f


def _chk(label: str, checked: bool = False, tooltip: str = "") -> QCheckBox:
    cb = QCheckBox(label)
    cb.setChecked(checked)
    cb.setStyleSheet(f"font-size:12px; color:{_C_VALUE};")
    if tooltip: cb.setToolTip(tooltip)
    return cb


def _dbl_spin(lo: float, hi: float, step: float, decimals: int, val: float,
              width: int = 72) -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi); sb.setSingleStep(step); sb.setDecimals(decimals)
    sb.setValue(val); sb.setMaximumWidth(width); sb.setStyleSheet("font-size:11px;")
    return sb


# ══════════════════════════════════════════════════════════════════════════════
# Resolution dialog
# ══════════════════════════════════════════════════════════════════════════════

class _ResolutionDialog(QDialog):
    def __init__(self, cam_label: str, current: tuple[int, int], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Custom resolution  —  {cam_label}")
        self.setFixedWidth(230)
        layout = QVBoxLayout(self)
        form   = QFormLayout()
        self._w = QSpinBox(); self._w.setRange(1, 8192); self._w.setValue(current[0])
        self._h = QSpinBox(); self._h.setRange(1, 8192); self._h.setValue(current[1])
        form.addRow("W:", self._w); form.addRow("H:", self._h)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    @property
    def resolution(self) -> tuple[int, int]:
        return self._w.value(), self._h.value()


# ══════════════════════════════════════════════════════════════════════════════
# Main window
# ══════════════════════════════════════════════════════════════════════════════

class PlayblastTool(*_TOOL_BASES):

    _instance: Optional[PlayblastTool] = None

    @classmethod
    def launch(cls) -> PlayblastTool:
        import maya.cmds as cmds

        ctrl = "fxBlastWorkspaceControl"

        # If the workspace control already exists (open OR closed), restore it.
        # Always restore as floating — docking is an explicit artist choice.
        if cmds.workspaceControl(ctrl, query=True, exists=True):
            cmds.workspaceControl(ctrl, edit=True,
                                  restore=True, floating=True, visible=True)
            if cls._instance is not None:
                try:
                    cls._instance.raise_()
                    cls._instance.activateWindow()
                except RuntimeError:
                    cls._instance = None
            return cls._instance

        # No workspace control exists yet — create fresh instance.
        if cls._instance is not None:
            try:
                cls._instance.close()
            except Exception:
                pass
            cls._instance = None

        inst = cls()
        try:
            inst.show(dockable=True, floating=True)
        except TypeError:
            inst.show()
        cls._instance = inst
        return inst

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens:                   Optional[SceneTokens]   = None
        self._resolver:                 Optional[OutputResolver] = None
        self._cameras:                  list[dict]               = []
        self._last_blast_folder:        Optional[str]            = None
        self._cam_resolution_overrides: dict[str, tuple[int, int]] = {}

        self._setup_window()
        self._build_ui()
        self._refresh_scene()

    def closeEvent(self, event):
        PlayblastTool._instance = None
        super().closeEvent(event)

    def _setup_window(self) -> None:
        self.setWindowTitle("fxBlast")
        self.setObjectName("fxBlast")   # workspace control = "fxBlastWorkspaceControl"
        self.setFixedWidth(460)

    # ══════════════════════════════════════════════════════════════════════════
    # UI
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(12, 10, 12, 10)

        self._error_banner = QLabel()
        self._error_banner.setStyleSheet(_S_ERROR)
        self._error_banner.setWordWrap(True)
        self._error_banner.setVisible(False)
        root.addWidget(self._error_banner)

        btn_ref = QPushButton("Refresh scene")
        btn_ref.setStyleSheet(_S_REFRESH)
        btn_ref.clicked.connect(self._refresh_scene)
        root.addWidget(btn_ref)

        root.addWidget(self._build_scene_section())
        root.addWidget(_hline())
        root.addWidget(self._build_camera_section())
        root.addWidget(_hline())
        root.addWidget(self._build_anamorphic_section())
        root.addWidget(_hline())
        root.addWidget(self._build_format_section())
        root.addWidget(_hline())
        root.addWidget(self._build_note_section())
        root.addWidget(self._build_playblast_options_section())

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        self._blast_btn = QPushButton("Playblast")
        self._blast_btn.setStyleSheet(_S_BLAST)
        self._blast_btn.clicked.connect(self._on_playblast)
        self._rv_btn = QPushButton("Play in RV")
        self._rv_btn.setStyleSheet(_S_RV)
        self._rv_btn.setEnabled(False)
        self._rv_btn.clicked.connect(self._on_play_in_rv)
        btn_row.addWidget(self._blast_btn); btn_row.addWidget(self._rv_btn)
        root.addLayout(btn_row)

        root.addWidget(self._build_output_section())
        root.addWidget(self._build_versions_section())

        footer = QHBoxLayout(); footer.setSpacing(6)
        self._undock_btn = QPushButton("⊣  Undock")
        self._undock_btn.setStyleSheet(_S_DOCK_BTN)
        self._undock_btn.setMaximumWidth(70)
        self._undock_btn.clicked.connect(self._undock)
        footer.addWidget(self._undock_btn)
        self._status_lbl = QLabel()
        self._status_lbl.setStyleSheet(f"font-size:11px; color:{_C_DIM};")
        footer.addWidget(self._status_lbl)
        footer.addStretch()
        self._dock_btn = QPushButton("⊢  Dock right")
        self._dock_btn.setStyleSheet(_S_DOCK_BTN)
        self._dock_btn.setMaximumWidth(84)
        self._dock_btn.clicked.connect(self._dock_to_right)
        footer.addWidget(self._dock_btn)
        root.addLayout(footer)

    # ── Scene ─────────────────────────────────────────────────────────────────

    def _build_scene_section(self) -> QWidget:
        w    = QWidget()
        grid = QGridLayout(w)
        grid.setSpacing(5); grid.setContentsMargins(0, 4, 0, 4)
        grid.setColumnStretch(1, 1); grid.setColumnStretch(3, 1)

        grid.addWidget(_lbl("Show:"),   0, 0, Qt.AlignRight)
        self._lbl_show = _val(); grid.addWidget(self._lbl_show, 0, 1)
        grid.addWidget(_lbl("Shot:"),   0, 2, Qt.AlignRight)
        self._lbl_shot = _val(); grid.addWidget(self._lbl_shot, 0, 3)

        grid.addWidget(_lbl("Season:"), 1, 0, Qt.AlignRight)
        self._lbl_season = _val(); grid.addWidget(self._lbl_season, 1, 1)
        grid.addWidget(_lbl("Task:"),   1, 2, Qt.AlignRight)
        self._lbl_task = _val(); grid.addWidget(self._lbl_task, 1, 3)

        grid.addWidget(_lbl("Descriptor:"), 2, 0, Qt.AlignRight)
        self._lbl_descriptor = _val()
        grid.addWidget(self._lbl_descriptor, 2, 1, 1, 3)

        # Version + override
        grid.addWidget(_lbl("Version:"), 3, 0, Qt.AlignRight)
        self._lbl_version = _val()
        self._ver_override_chk = QCheckBox("Override")
        self._ver_override_chk.setStyleSheet(f"font-size:12px; color:{_C_LABEL};")
        self._ver_override_chk.toggled.connect(self._on_version_override_toggled)
        self._ver_override_edit = QLineEdit()
        self._ver_override_edit.setPlaceholderText("v001")
        self._ver_override_edit.setMaximumWidth(58)
        self._ver_override_edit.setEnabled(False)
        self._ver_override_edit.setStyleSheet(f"font-size:12px; color:{_C_VALUE}; padding:1px 4px;")
        self._ver_override_edit.textChanged.connect(self._update_output_preview)
        ver_row = QHBoxLayout(); ver_row.setSpacing(8)
        ver_row.addWidget(self._lbl_version); ver_row.addStretch()
        ver_row.addWidget(self._ver_override_chk); ver_row.addWidget(self._ver_override_edit)
        ver_c = QWidget(); ver_c.setLayout(ver_row)
        grid.addWidget(ver_c, 3, 1, 1, 3)

        # Frame range
        grid.addWidget(_lbl("Frame range:"), 4, 0, Qt.AlignRight)
        self._start_spin = QSpinBox(); self._start_spin.setRange(-10000, 100000); self._start_spin.setMaximumWidth(70)
        self._end_spin   = QSpinBox(); self._end_spin.setRange(-10000, 100000);   self._end_spin.setMaximumWidth(70)
        fr_btn = QPushButton("From scene"); fr_btn.setStyleSheet(_S_REFRESH)
        fr_btn.setMaximumHeight(24); fr_btn.clicked.connect(self._refresh_frame_range)
        fr_row = QHBoxLayout(); fr_row.setSpacing(5)
        fr_row.addWidget(self._start_spin); fr_row.addWidget(_lbl("to"))
        fr_row.addWidget(self._end_spin); fr_row.addSpacing(6); fr_row.addWidget(fr_btn); fr_row.addStretch()
        fr_c = QWidget(); fr_c.setLayout(fr_row)
        grid.addWidget(fr_c, 4, 1, 1, 3)
        return w

    # ── Camera ────────────────────────────────────────────────────────────────

    def _build_camera_section(self) -> QWidget:
        w      = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(5)

        # Header row with inline hint
        hdr = QHBoxLayout(); hdr.setSpacing(10)
        hdr.addWidget(_section_header("Camera"))
        hint = QLabel("Right-click a camera to set its resolution.")
        hint.setStyleSheet(f"font-size:11px; color:{_C_DIM}; font-style:italic;")
        hdr.addWidget(hint); hdr.addStretch()
        layout.addLayout(hdr)

        # Bordered frame — fixed height so it doesn't stretch on window resize
        frame = QFrame(); frame.setStyleSheet(_S_CAM_FRAME)
        frame.setFixedHeight(112)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        frame_layout = QHBoxLayout(frame)
        frame_layout.setContentsMargins(6, 6, 6, 6); frame_layout.setSpacing(6)

        self._cam_list = QListWidget()
        self._cam_list.setMaximumHeight(100)
        self._cam_list.setStyleSheet(_S_CAM_LIST)
        self._cam_list.itemChanged.connect(self._on_camera_check_changed)
        self._cam_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._cam_list.customContextMenuRequested.connect(self._on_camera_context_menu)
        frame_layout.addWidget(self._cam_list)

        side = QVBoxLayout(); side.setSpacing(3)
        for label, slot in (("All",      lambda: self._set_all_cameras(True)),
                             ("None",    lambda: self._set_all_cameras(False)),
                             ("Add sel.", self._add_selected_camera),
                             ("Refresh",  self._refresh_cameras)):
            btn = QPushButton(label); btn.setStyleSheet(_S_SMALL_BTN)
            btn.setMinimumWidth(58); btn.clicked.connect(slot); side.addWidget(btn)
        side.addStretch()
        frame_layout.addLayout(side)
        layout.addWidget(frame)
        return w

    # ── Anamorphic ────────────────────────────────────────────────────────────

    def _build_anamorphic_section(self) -> QWidget:
        w      = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(5)
        layout.addWidget(_section_header("Anamorphic"))
        self._ana_chk = _chk("Enable")
        self._ana_chk.toggled.connect(self._on_anamorphic_toggled)
        layout.addWidget(self._ana_chk)
        sq_row = QHBoxLayout(); sq_row.setSpacing(8)
        sq_row.addWidget(_lbl("Squeeze:"))
        self._squeeze_combo = QComboBox(); self._squeeze_combo.setMaximumWidth(78)
        self._squeeze_combo.setStyleSheet("font-size:12px;")
        for f in ANAMORPHIC_SQUEEZE_FACTORS:
            self._squeeze_combo.addItem(f"{f}x", userData=f)
        self._squeeze_combo.setCurrentIndex(ANAMORPHIC_SQUEEZE_FACTORS.index(DEFAULT_SQUEEZE_FACTOR))
        self._squeeze_combo.currentIndexChanged.connect(self._update_output_preview)
        self._blast_size_lbl = QLabel(); self._blast_size_lbl.setStyleSheet(f"font-size:11px; color:{_C_DIM};")
        sq_row.addWidget(self._squeeze_combo); sq_row.addWidget(self._blast_size_lbl); sq_row.addStretch()
        layout.addLayout(sq_row)
        self._sync_anamorphic_controls()
        return w

    # ── Format ────────────────────────────────────────────────────────────────

    def _build_format_section(self) -> QWidget:
        w      = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(5)
        layout.addWidget(_section_header("Format"))
        fmt_row = QHBoxLayout(); fmt_row.setSpacing(16)
        self._fmt_btn_group = QButtonGroup(self)
        for i, fmt in enumerate(IMAGE_FORMATS):
            rb = QRadioButton(FORMAT_LABELS.get(fmt, fmt.upper()))
            rb.setStyleSheet(f"font-size:12px; color:{_C_VALUE};")
            if fmt == DEFAULT_FORMAT: rb.setChecked(True)
            self._fmt_btn_group.addButton(rb, i)
            rb.toggled.connect(self._update_output_preview)
            fmt_row.addWidget(rb)
        fmt_row.addStretch()
        layout.addLayout(fmt_row)
        return w

    # ── Note ─────────────────────────────────────────────────────────────────

    def _build_note_section(self) -> QWidget:
        w      = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(5)
        layout.addWidget(_section_header("Note"))
        self._note_edit = QLineEdit()
        self._note_edit.setPlaceholderText(
            "Pre-populated from file save tool if available, or type a note here..."
        )
        self._note_edit.setStyleSheet(_S_NOTE_EDIT)
        layout.addWidget(self._note_edit)
        self._note_source_lbl = QLabel()
        self._note_source_lbl.setStyleSheet(f"font-size:11px; color:{_C_DIM};")
        layout.addWidget(self._note_source_lbl)
        return w

    # ── Playblast Options (collapsible) ───────────────────────────────────────

    def _build_playblast_options_section(self) -> QWidget:
        container = QWidget()
        layout    = QVBoxLayout(container)
        layout.setContentsMargins(0, 2, 0, 2); layout.setSpacing(2)

        self._po_toggle = QPushButton("\u25b6  Playblast Options")
        self._po_toggle.setCheckable(True)
        self._po_toggle.setChecked(False)
        self._po_toggle.setStyleSheet(_S_TWIRL)
        self._po_toggle.toggled.connect(self._on_po_toggle)

        body        = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(8, 6, 0, 4); body_layout.setSpacing(6)

        # Film gate + HUD
        self._disable_filmgate_chk = _chk(
            "Disable Film Gate and Pan/Zoom  (No Gate mode)", checked=True
        )
        self._hud_chk = _chk("Show HUD overlay  (shot info, frame counter, note)")
        body_layout.addWidget(self._disable_filmgate_chk)
        body_layout.addWidget(self._hud_chk)

        # VP2 sub-header
        vp2_hdr = QLabel("Viewport 2.0")
        vp2_hdr.setStyleSheet(f"font-size:11px; color:{_C_DIM}; margin-top:6px;")
        body_layout.addWidget(vp2_hdr)
        body_layout.addWidget(_hline())

        # ── Motion Blur ───────────────────────────────────────────────────────
        self._mb_chk = _chk("Motion Blur")
        body_layout.addWidget(self._mb_chk)

        mb_params = QHBoxLayout(); mb_params.setContentsMargins(20, 0, 0, 0); mb_params.setSpacing(8)
        mb_params.addWidget(QLabel("Shutter fraction:"))
        self._mb_shutter = _dbl_spin(0.0, 1.0, 0.05, 2, 0.2)
        mb_params.addWidget(self._mb_shutter)
        mb_params.addWidget(QLabel("Samples:"))
        self._mb_samples = QSpinBox()
        self._mb_samples.setRange(1, 32); self._mb_samples.setValue(8)
        self._mb_samples.setMaximumWidth(55); self._mb_samples.setStyleSheet("font-size:11px;")
        mb_params.addWidget(self._mb_samples); mb_params.addStretch()
        for w in [mb_params.itemAt(i).widget() for i in range(mb_params.count()) if mb_params.itemAt(i).widget()]:
            if isinstance(w, QLabel): w.setStyleSheet(f"font-size:11px; color:{_C_LABEL};")
        mb_w = QWidget(); mb_w.setLayout(mb_params)
        body_layout.addWidget(mb_w)

        # ── Depth of Field ────────────────────────────────────────────────────
        self._dof_chk = _chk("Depth of Field")
        body_layout.addWidget(self._dof_chk)
        self._dof_info_lbl = QLabel("  Focus distance and F-Stop are read from the active camera.")
        self._dof_info_lbl.setStyleSheet(_S_SUB_LBL)
        self._dof_info_lbl.setWordWrap(True)
        body_layout.addWidget(self._dof_info_lbl)
        self._dof_detail_lbl = QLabel()
        self._dof_detail_lbl.setStyleSheet(_S_SUB_LBL)
        body_layout.addWidget(self._dof_detail_lbl)

        # ── SSAO ─────────────────────────────────────────────────────────────
        self._ssao_chk = _chk("Screen Space Ambient Occlusion")
        body_layout.addWidget(self._ssao_chk)

        ssao_row = QHBoxLayout(); ssao_row.setContentsMargins(20, 0, 0, 0); ssao_row.setSpacing(8)
        ssao_row.addWidget(QLabel("Amount:"))
        self._ssao_amount = _dbl_spin(0.0, 16.0, 0.1, 2, 1.0)
        ssao_row.addWidget(self._ssao_amount)
        ssao_row.addWidget(QLabel("Radius:"))
        self._ssao_radius = _dbl_spin(0.0, 256.0, 1.0, 1, 16.0)
        ssao_row.addWidget(self._ssao_radius)
        ssao_row.addWidget(QLabel("Filter:"))
        self._ssao_filter = QSpinBox()
        self._ssao_filter.setRange(0, 256); self._ssao_filter.setValue(16)
        self._ssao_filter.setMaximumWidth(52); self._ssao_filter.setStyleSheet("font-size:11px;")
        ssao_row.addWidget(self._ssao_filter)
        ssao_row.addWidget(QLabel("Samples:"))
        self._ssao_samples = QSpinBox()
        self._ssao_samples.setRange(1, 256); self._ssao_samples.setValue(16)
        self._ssao_samples.setMaximumWidth(52); self._ssao_samples.setStyleSheet("font-size:11px;")
        ssao_row.addWidget(self._ssao_samples); ssao_row.addStretch()
        for w in [ssao_row.itemAt(i).widget() for i in range(ssao_row.count()) if ssao_row.itemAt(i).widget()]:
            if isinstance(w, QLabel): w.setStyleSheet(f"font-size:11px; color:{_C_LABEL};")
        ssao_w = QWidget(); ssao_w.setLayout(ssao_row)
        body_layout.addWidget(ssao_w)

        # ── Anti-Aliasing ─────────────────────────────────────────────────────
        self._aa_chk = _chk("Anti-Aliasing")
        body_layout.addWidget(self._aa_chk)

        aa_row = QHBoxLayout(); aa_row.setContentsMargins(20, 0, 0, 0); aa_row.setSpacing(8)
        aa_row.addWidget(QLabel("Samples:"))
        self._aa_samples = QComboBox()
        self._aa_samples.setMaximumWidth(70); self._aa_samples.setStyleSheet("font-size:11px;")
        for s in [2, 4, 8, 16]:
            self._aa_samples.addItem(f"{s}x", userData=s)
        self._aa_samples.setCurrentIndex(1)   # default 4x
        aa_lbl = QLabel("Samples:"); aa_lbl.setStyleSheet(f"font-size:11px; color:{_C_LABEL};")
        aa_row.itemAt(0).widget().setStyleSheet(f"font-size:11px; color:{_C_LABEL};")
        aa_row.addWidget(self._aa_samples); aa_row.addStretch()
        aa_w = QWidget(); aa_w.setLayout(aa_row)
        body_layout.addWidget(aa_w)

        # Connect VP2 widgets to live-sync with Maya's Hardware Render 2.0 settings
        self._mb_chk.toggled.connect(lambda v: self._set_vp2("motionBlur", v))
        self._mb_shutter.valueChanged.connect(lambda v: self._set_vp2("motionBlurShutter", v))
        self._mb_samples.valueChanged.connect(lambda v: self._set_vp2("motionBlurSamples", int(v)))
        self._dof_chk.toggled.connect(self._apply_dof_to_cameras)
        self._ssao_chk.toggled.connect(lambda v: self._set_vp2("ssao", v))
        self._ssao_amount.valueChanged.connect(lambda v: self._set_vp2("ssaoAmount", v))
        self._ssao_radius.valueChanged.connect(lambda v: self._set_vp2("ssaoRadius", v))
        self._ssao_filter.valueChanged.connect(lambda v: self._set_vp2("ssaoFilterRadius", int(v)))
        self._ssao_samples.valueChanged.connect(lambda v: self._set_vp2("ssaoSamples", int(v)))
        self._aa_chk.toggled.connect(self._set_vp2_aa)
        self._aa_samples.currentIndexChanged.connect(
            lambda: self._set_vp2("multiSampleCount", self._aa_samples.currentData())
        )

        body.setVisible(False)
        layout.addWidget(self._po_toggle)
        layout.addWidget(body)
        self._po_body = body
        return container

    def _on_po_toggle(self, expanded: bool) -> None:
        self._po_body.setVisible(expanded)
        self._po_toggle.setText(
            ("\u25bc" if expanded else "\u25b6") + "  Playblast Options"
        )
        if expanded:
            self._refresh_vp2_settings()

    def _refresh_vp2_settings(self) -> None:
        """Read current Viewport 2.0 settings from Maya and populate the widgets."""
        try:
            from .maya_bridge import get_viewport2_settings
            s = get_viewport2_settings()
            # Motion blur
            self._mb_shutter.setValue(s.get("motionBlurShutter", 0.2))
            self._mb_samples.setValue(int(s.get("motionBlurSamples", 8)))
            # SSAO
            self._ssao_amount.setValue(s.get("ssaoAmount", 1.0))
            self._ssao_radius.setValue(s.get("ssaoRadius", 2.0))
            self._ssao_filter.setValue(int(s.get("ssaoFilterRadius", 16)))
            self._ssao_samples.setValue(int(s.get("ssaoSamples", 16)))
            # AA samples
            sample_map = {2: 0, 4: 1, 8: 2, 16: 3}
            self._aa_samples.setCurrentIndex(
                sample_map.get(int(s.get("multiSampleCount", 4)), 1)
            )
        except Exception:
            pass

        # Update DOF info from first checked camera
        self._refresh_dof_info()

    def _refresh_dof_info(self) -> None:
        """Show DOF camera values as an informational read-out."""
        cam = self._first_checked_camera()
        if cam is None:
            self._dof_detail_lbl.setText("")
            return
        try:
            from .maya_bridge import get_camera_dof_info
            info = get_camera_dof_info(cam["shape"])
            self._dof_detail_lbl.setText(
                f"  Focus distance: {info['focusDistance']:.3f}   "
                f"F-Stop: {info['fStop']:.1f}   "
                f"Focus region scale: {info['focusRegionScale']:.2f}"
            )
        except Exception:
            self._dof_detail_lbl.setText("")

    # ── Output path ───────────────────────────────────────────────────────────

    def _build_output_section(self) -> QWidget:
        w      = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(3)
        self._output_path_lbl = QLabel("--")
        self._output_path_lbl.setStyleSheet(_S_PATH)
        self._output_path_lbl.setWordWrap(True)
        self._output_path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._output_path_lbl)
        return w

    # ── Version list ──────────────────────────────────────────────────────────

    def _build_versions_section(self) -> QWidget:
        w      = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

        self._ver_tree = QTreeWidget()
        self._ver_tree.setColumnCount(6)
        self._ver_tree.setHeaderLabels(["Version", "Range", "Frames", "FPS", "Resolution", "Notes"])
        self._ver_tree.setFixedHeight(224)
        self._ver_tree.setAlternatingRowColors(True)
        self._ver_tree.setRootIsDecorated(True)
        self._ver_tree.setStyleSheet("font-size:12px;")
        self._ver_tree.setSelectionMode(QTreeWidget.SingleSelection)

        hdr = self._ver_tree.header()
        hdr.resizeSection(0, 62); hdr.resizeSection(1, 72); hdr.resizeSection(2, 52)
        hdr.resizeSection(3, 52); hdr.resizeSection(4, 90)
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)

        self._ver_tree.itemChanged.connect(self._on_notes_changed)
        self._ver_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._ver_tree.customContextMenuRequested.connect(self._on_version_context_menu)
        layout.addWidget(self._ver_tree)
        return w

    # ══════════════════════════════════════════════════════════════════════════
    # Persistence
    # ══════════════════════════════════════════════════════════════════════════

    def _notes_path(self) -> Optional[str]:
        return os.path.join(self._tokens.images_root, _NOTES_FILENAME) if self._tokens else None

    def _meta_path(self) -> Optional[str]:
        return os.path.join(self._tokens.images_root, _META_FILENAME) if self._tokens else None

    def _load_json(self, path: Optional[str]) -> dict:
        if not path or not os.path.isfile(path): return {}
        try:
            with open(path, encoding="utf-8") as f: return json.load(f)
        except Exception: return {}

    def _save_json(self, path: Optional[str], data: dict) -> None:
        if not path: return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)
        except Exception as exc:
            self._set_status(f"Could not save: {exc}", error=True)

    def _load_notes(self) -> dict: return self._load_json(self._notes_path())
    def _save_notes(self, d): self._save_json(self._notes_path(), d)
    def _load_meta(self)  -> dict: return self._load_json(self._meta_path())
    def _save_meta(self,  d): self._save_json(self._meta_path(), d)

    def _on_notes_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != _COL_NOTES or item.parent() is not None: return
        version = item.data(_COL_VERSION, Qt.UserRole)
        if not version: return
        note  = item.text(_COL_NOTES).strip()
        notes = self._load_notes()
        if note: notes[version] = note
        else:    notes.pop(version, None)
        self._save_notes(notes)

    # ══════════════════════════════════════════════════════════════════════════
    # Data refresh
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_scene(self) -> None:
        try:
            from .maya_bridge import get_scene_tokens
            self._tokens = get_scene_tokens()
            self._error_banner.setVisible(False)
        except (ParseError, Exception) as exc:
            self._tokens = None; self._resolver = None
            self._error_banner.setText(str(exc)); self._error_banner.setVisible(True)
            self._blast_btn.setEnabled(False); self._output_path_lbl.setText("--")
            return
        self._cam_resolution_overrides.clear()
        self._populate_scene_info()
        self._refresh_frame_range()
        self._refresh_note()
        self._refresh_cameras()
        self._refresh_version_list()

    def _populate_scene_info(self) -> None:
        t = self._tokens
        self._lbl_show.setText(t.show);   self._lbl_shot.setText(t.shot)
        self._lbl_season.setText(t.season); self._lbl_task.setText(t.discipline)
        self._lbl_descriptor.setText(t.descriptor or "none")
        self._lbl_version.setText(t.version)
        self._ver_override_chk.blockSignals(True)
        self._ver_override_chk.setChecked(False)
        self._ver_override_chk.blockSignals(False)
        self._ver_override_edit.setText(t.version)
        self._ver_override_edit.setEnabled(False)

    def _refresh_frame_range(self) -> None:
        try:
            from .maya_bridge import get_frame_range
            s, e = get_frame_range()
            self._start_spin.setValue(s); self._end_spin.setValue(e)
        except Exception: pass

    def _refresh_note(self) -> None:
        try:
            from .maya_bridge import read_scene_note, get_scene_path
            note = read_scene_note(get_scene_path())
            if note:
                self._note_edit.setText(note)
                self._note_source_lbl.setText("  from file save tool"); return
        except Exception: pass
        stored = self._load_notes().get(self._tokens.version if self._tokens else "", "")
        self._note_edit.setText(stored)
        self._note_source_lbl.setText("  from stored notes" if stored else "")

    def _refresh_cameras(self) -> None:
        if self._tokens is None: return
        try:
            from .maya_bridge import list_cameras
            self._cameras = list_cameras(include_default=False)
        except Exception as exc:
            self._cameras = []; self._set_status(f"Could not list cameras: {exc}", error=True)

        rg_res = self._render_globals_resolution()

        prev_checked = set()
        for i in range(self._cam_list.count()):
            item = self._cam_list.item(i)
            if item.checkState() == Qt.Checked:
                prev_checked.add(item.data(Qt.UserRole)["label"])

        self._cam_list.blockSignals(True)
        self._cam_list.clear()
        for cam in self._cameras:
            if cam["label"] not in self._cam_resolution_overrides:
                self._cam_resolution_overrides[cam["label"]] = rg_res
            item = QListWidgetItem()
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            state = Qt.Checked if (
                cam["label"] in prev_checked or
                (not prev_checked and self._cameras.index(cam) == 0)
            ) else Qt.Unchecked
            item.setCheckState(state)
            item.setData(Qt.UserRole, cam)
            self._update_cam_item_text(item, cam)
            item.setForeground(QColor(_C_CAM_CHECKED if state == Qt.Checked else _C_CAM_UNCHECKED))
            self._cam_list.addItem(item)
        self._cam_list.blockSignals(False)

        self._update_output_preview()
        # Refresh DOF info if options panel is open
        if self._po_toggle.isChecked():
            self._refresh_dof_info()

    def _refresh_version_list(self) -> None:
        self._ver_tree.blockSignals(True)
        self._ver_tree.clear()
        if self._tokens is None:
            self._ver_tree.blockSignals(False); return
        try:
            resolver = self._resolver or build_resolver(self._tokens, image_format=DEFAULT_FORMAT)
        except Exception:
            self._ver_tree.blockSignals(False); return

        current_version = (
            self._ver_override_edit.text().strip()
            if self._ver_override_chk.isChecked()
            else (self._tokens.version if self._tokens else "")
        )
        fmt   = IMAGE_FORMATS[self._fmt_btn_group.checkedId()]
        ext   = FORMAT_EXTENSIONS.get(fmt, fmt)
        notes = self._load_notes(); meta = self._load_meta()

        for ver in resolver.existing_versions():
            folder   = os.path.join(self._tokens.images_root, ver)
            ver_meta = meta.get(ver, {}); note = notes.get(ver, "")

            flat_frames = sorted(glob.glob(os.path.join(folder, f"*.{ext}")))
            cam_subfolders = []
            try:
                cam_subfolders = sorted([
                    d for d in os.listdir(folder)
                    if os.path.isdir(os.path.join(folder, d))
                    and not d.startswith("_")
                    and glob.glob(os.path.join(folder, d, f"*.{ext}"))
                ])
            except Exception: pass

            is_multi = bool(cam_subfolders) and not flat_frames
            if is_multi:
                all_frames = sorted(
                    f for sf in cam_subfolders
                    for f in glob.glob(os.path.join(folder, sf, f"*.{ext}"))
                )
                count = len(all_frames)
                range_str = (f"{_frame_nums(all_frames)[0]}-{_frame_nums(all_frames)[1]}"
                             if all_frames else "--")
                res_str = "multi-cam"
            else:
                frames    = flat_frames; count = len(frames)
                range_str = (f"{_frame_nums(frames)[0]}-{_frame_nums(frames)[1]}"
                             if frames else "--")
                res_str   = self._res_str(ver_meta, frames)

            fps_str = self._fps_str(ver_meta)
            ver_item = QTreeWidgetItem([ver, range_str, str(count), fps_str, res_str, note])
            ver_item.setData(_COL_VERSION, Qt.UserRole, ver)
            ver_item.setData(_COL_FRAMES,  Qt.UserRole, folder)
            ver_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)

            if ver == current_version:
                for col in range(6): ver_item.setBackground(col, _COLOR_CURRENT)
                ver_item.setText(_COL_VERSION, f"{ver}  *")

            for col in (_COL_FRAMERANGE, _COL_FRAMES, _COL_FPS, _COL_RESOLUTION):
                ver_item.setTextAlignment(col, Qt.AlignCenter)

            if is_multi:
                for sf in cam_subfolders:
                    sf_folder = os.path.join(folder, sf)
                    sf_frames = sorted(glob.glob(os.path.join(sf_folder, f"*.{ext}")))
                    sf_range  = (f"{_frame_nums(sf_frames)[0]}-{_frame_nums(sf_frames)[1]}"
                                 if sf_frames else "--")
                    child = QTreeWidgetItem([sf, sf_range, str(len(sf_frames)),
                                             fps_str, self._res_str({}, sf_frames), ""])
                    child.setData(_COL_VERSION, Qt.UserRole, sf)
                    child.setData(_COL_FRAMES,  Qt.UserRole, sf_folder)
                    child.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    for col in range(6): child.setBackground(col, _COLOR_CHILD)
                    for col in (_COL_FRAMERANGE, _COL_FRAMES, _COL_FPS, _COL_RESOLUTION):
                        child.setTextAlignment(col, Qt.AlignCenter)
                    ver_item.addChild(child)
                ver_item.setExpanded(True)

            self._ver_tree.addTopLevelItem(ver_item)
        self._ver_tree.blockSignals(False)

    def _fps_str(self, m: dict) -> str:
        if "fps" not in m: return "--"
        v = m["fps"]; return f"{int(v)}fps" if v == int(v) else f"{v}fps"

    def _res_str(self, m: dict, frames: list[str]) -> str:
        if "resolution" in m:
            rw, rh = m["resolution"]; return f"{rw}x{rh}"
        if frames:
            try:
                from .maya_bridge import read_image_dimensions
                dims = read_image_dimensions(frames[0])
                return f"{dims[0]}x{dims[1]}" if dims else "--"
            except Exception: pass
        return "--"

    # ══════════════════════════════════════════════════════════════════════════
    # Camera context menu
    # ══════════════════════════════════════════════════════════════════════════

    def _on_camera_check_changed(self, item: QListWidgetItem) -> None:
        """Update text colour when a camera is checked/unchecked, then refresh preview."""
        if item is not None:
            if item.checkState() == Qt.Checked:
                item.setForeground(QColor(_C_CAM_CHECKED))
            else:
                item.setForeground(QColor(_C_CAM_UNCHECKED))
        self._update_output_preview()
        if self._po_toggle.isChecked():
            self._refresh_dof_info()

    def _on_camera_context_menu(self, pos) -> None:
        item = self._cam_list.itemAt(pos)
        if item is None: return
        cam  = item.data(Qt.UserRole)
        menu = QMenu(self)
        menu.addAction("Resolution from Render Globals").triggered.connect(
            lambda: self._set_cam_res_from_render_globals(item, cam))
        menu.addAction("Resolution from Image Plane").triggered.connect(
            lambda: self._set_cam_res_from_image_plane(item, cam))
        menu.addAction("Custom resolution...").triggered.connect(
            lambda: self._set_cam_res_custom(item, cam))
        menu.exec_(self._cam_list.viewport().mapToGlobal(pos))

    def _set_cam_res_from_render_globals(self, item, cam):
        res = self._render_globals_resolution()
        self._cam_resolution_overrides[cam["label"]] = res
        self._update_cam_item_text(item, cam)
        self._update_output_preview()
        self._set_status(f"{cam['label']}  \u2192  {res[0]} x {res[1]}  (Render Globals)")

    def _set_cam_res_from_image_plane(self, item, cam):
        try:
            from .maya_bridge import list_image_planes, get_image_plane_resolution
            planes = list_image_planes(cam["shape"])
        except Exception as exc:
            self._set_status(f"Could not query image planes: {exc}", error=True); return
        if not planes:
            self._set_status(f"No image plane found on {cam['label']}.", error=True); return

        def _apply(node, label):
            dims = get_image_plane_resolution(node)
            if dims:
                self._cam_resolution_overrides[cam["label"]] = dims
                self._update_cam_item_text(item, cam)
                self._update_output_preview()
                self._set_status(f"{cam['label']}  \u2192  {dims[0]} x {dims[1]}  ({label})")
            else:
                self._set_status("Could not read image plane dimensions.", error=True)

        if len(planes) == 1:
            _apply(planes[0]["node"], planes[0]["label"])
        else:
            menu = QMenu(self)
            for p in planes:
                menu.addAction(p["label"]).triggered.connect(
                    lambda checked=False, n=p["node"], l=p["label"]: _apply(n, l))
            menu.exec_(self._cam_list.viewport().mapToGlobal(
                self._cam_list.visualItemRect(item).topRight()))

    def _set_cam_res_custom(self, item, cam):
        current = self._cam_resolution_overrides.get(cam["label"], self._render_globals_resolution())
        dlg = _ResolutionDialog(cam["label"], current, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._cam_resolution_overrides[cam["label"]] = dlg.resolution
            self._update_cam_item_text(item, cam)
            self._update_output_preview()

    def _update_cam_item_text(self, item, cam):
        res = self._cam_resolution_overrides.get(cam["label"])
        item.setText(f"{cam['label']}   {res[0]} x {res[1]}" if res else cam["label"])

    # ══════════════════════════════════════════════════════════════════════════
    # Version list context menu
    # ══════════════════════════════════════════════════════════════════════════

    def _on_version_context_menu(self, pos) -> None:
        item = self._ver_tree.itemAt(pos)
        if item is None:
            menu = QMenu(self)
            menu.addAction("Refresh Version List").triggered.connect(self._refresh_version_list)
            menu.exec_(self._ver_tree.viewport().mapToGlobal(pos))
            return
        is_child = item.parent() is not None
        version  = item.data(_COL_VERSION, Qt.UserRole)
        folder   = item.data(_COL_FRAMES,  Qt.UserRole)
        menu = QMenu(self)
        menu.addAction("Play in RV").triggered.connect(lambda: self._launch_rv(folder))
        menu.addAction("Open file location").triggered.connect(lambda: self._open_file_location(folder))
        if not is_child:
            menu.addSeparator()
            menu.addAction(f"Delete {version}...").triggered.connect(
                lambda: self._delete_version(version, folder))
        menu.exec_(self._ver_tree.viewport().mapToGlobal(pos))

    def _delete_version(self, version: str, folder: str) -> None:
        reply = QMessageBox.warning(
            self, f"Delete {version}?",
            f"This will permanently delete all frames in:\n\n{folder}\n\nThis cannot be undone.  Continue?",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if reply != QMessageBox.Yes: return
        try:
            shutil.rmtree(folder)
            for load, save in ((self._load_notes, self._save_notes), (self._load_meta, self._save_meta)):
                d = load()
                if version in d: d.pop(version); save(d)
            self._set_status(f"Deleted {version}")
        except Exception as exc:
            QMessageBox.critical(self, "Delete failed", f"Could not delete:\n\n{exc}"); return
        self._refresh_version_list(); self._update_output_preview()

    # ══════════════════════════════════════════════════════════════════════════
    # Slots
    # ══════════════════════════════════════════════════════════════════════════

    def _on_anamorphic_toggled(self) -> None:
        self._sync_anamorphic_controls(); self._update_output_preview()

    def _on_version_override_toggled(self, checked: bool) -> None:
        self._ver_override_edit.setEnabled(checked)
        if checked:
            self._ver_override_edit.setFocus(); self._ver_override_edit.selectAll()
        else:
            if self._tokens: self._ver_override_edit.setText(self._tokens.version)
        self._update_output_preview()

    # ══════════════════════════════════════════════════════════════════════════
    # Output preview
    # ══════════════════════════════════════════════════════════════════════════

    def _update_output_preview(self) -> None:
        if self._tokens is None:
            self._output_path_lbl.setText("--"); return
        version_override = (
            self._ver_override_edit.text().strip() or None
            if self._ver_override_chk.isChecked() else None
        )
        fmt = IMAGE_FORMATS[self._fmt_btn_group.checkedId()]
        try:
            self._resolver = build_resolver(
                self._tokens, version_override=version_override,
                image_format=fmt, frame_padding=FRAME_PADDING,
            )
        except (ResolveError, ValueError) as exc:
            self._output_path_lbl.setText(f"  {exc}"); self._blast_btn.setEnabled(False); return

        cams = self._selected_cameras()
        if len(cams) > 1:
            lines = []
            for cam in cams:
                slug = _cam_slug(cam["label"])
                folder = os.path.join(self._resolver.output_folder, slug)
                res = self._cam_resolution_overrides.get(cam["label"])
                tag = f"  [{res[0]}x{res[1]}]" if res else ""
                lines.append(f"{folder}{tag}")
            self._output_path_lbl.setText("\n".join(lines))
        else:
            self._output_path_lbl.setText(self._resolver.output_folder)

        self._blast_btn.setEnabled(bool(cams))

        if self._ana_chk.isChecked() and cams:
            from .maya_bridge import calculate_anamorphic_blast_size
            sq = self._squeeze_combo.currentData()
            cam_res = self._cam_resolution_overrides.get(
                cams[0]["label"], self._render_globals_resolution()
            )
            bw, bh = calculate_anamorphic_blast_size(cam_res[0], cam_res[1], sq)
            self._blast_size_lbl.setText(f"\u2192  blast at {bw} x {bh} px  (PAR {sq}:1)")

        self._rv_btn.setEnabled(self._last_blast_folder is not None)

    # ══════════════════════════════════════════════════════════════════════════
    # Playblast
    # ══════════════════════════════════════════════════════════════════════════

    def _on_playblast(self) -> None:
        if self._tokens is None or self._resolver is None: return
        cams = self._selected_cameras()
        if not cams:
            QMessageBox.warning(self, "No camera", "Please check at least one camera."); return

        if self._resolver.folder_has_existing_frames():
            reply = QMessageBox.question(
                self, "Overwrite existing frames?",
                f"The output folder already contains frames:\n\n{self._resolver.output_folder}\n\n"
                f"Existing files will be overwritten.  Continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes: return

        fmt      = IMAGE_FORMATS[self._fmt_btn_group.checkedId()]
        anam     = self._ana_chk.isChecked()
        squeeze  = self._squeeze_combo.currentData() if anam else None
        start    = self._start_spin.value(); end = self._end_spin.value()
        is_multi = len(cams) > 1
        use_hud  = self._hud_chk.isChecked()
        note     = self._note_edit.text().strip()




        self._blast_btn.setEnabled(False); self._rv_btn.setEnabled(False)
        QApplication.processEvents()

        last_folder = None
        try:
            from .maya_bridge import (
                calculate_anamorphic_blast_size, configure_anamorphic,
                disable_film_gate_pan_zoom, execute_playblast, get_fps,
                restore_camera_settings, restore_film_gate_pan_zoom,
                setup_hud, teardown_hud,
            )
            fps = get_fps()

            for idx, cam in enumerate(cams):
                label = (f"Blasting {idx+1}/{len(cams)} \u2014 {cam['label']}..."
                         if is_multi else "Blasting...")
                self._blast_btn.setText(label); QApplication.processEvents()

                cam_w, cam_h = self._cam_resolution_overrides.get(
                    cam["label"], self._render_globals_resolution()
                )
                if anam and squeeze is not None:
                    cam_w, cam_h = calculate_anamorphic_blast_size(cam_w, cam_h, squeeze)

                anam_snap = gate_snap = hud_snap = None
                try:
                    if self._disable_filmgate_chk.isChecked():
                        gate_snap = disable_film_gate_pan_zoom(cam["shape"])
                    if anam and squeeze is not None:
                        anam_snap = configure_anamorphic(cam["shape"], squeeze)
                    if use_hud:
                        hud_snap = setup_hud(
                            tokens=self._tokens, version=self._resolver.version,
                            camera_name=cam["label"], camera_shape=cam["shape"],
                            width=cam_w, height=cam_h, fps=fps, note=note,
                            start_frame=start, end_frame=end,
                        )

                    path_override = None
                    if is_multi:
                        slug = _cam_slug(cam["label"])
                        cam_folder = os.path.join(self._resolver.output_folder, slug)
                        stem = f"{self._resolver.output_basename}_{slug}"
                        path_override = os.path.join(cam_folder, stem)

                    last_folder = execute_playblast(
                        resolver=self._resolver, camera=cam["transform"],
                        width=cam_w, height=cam_h, image_format=fmt,
                        frame_padding=FRAME_PADDING, show_ornaments=use_hud,
                        start_frame=start, end_frame=end,
                        output_path_override=path_override,
                    )
                finally:
                    if use_hud and hud_snap:
                        try: teardown_hud(hud_snap)
                        except Exception: pass
                    if gate_snap:
                        try: restore_film_gate_pan_zoom(cam["shape"], gate_snap)
                        except Exception: pass
                    if anam_snap:
                        try: restore_camera_settings(cam["shape"], anam_snap)
                        except Exception: pass

            self._last_blast_folder = last_folder or self._resolver.output_folder
            self._blast_btn.setStyleSheet(_S_BLAST_DONE); self._rv_btn.setEnabled(True)

            if note:
                notes = self._load_notes(); notes[self._resolver.version] = note
                self._save_notes(notes)
            try:
                first_res = self._cam_resolution_overrides.get(
                    cams[0]["label"], self._render_globals_resolution()
                )
                meta = self._load_meta()
                meta[self._resolver.version] = {
                    "frame_range": [start, end], "fps": fps,
                    "resolution": list(first_res), "format": fmt,
                    "cameras": [c["label"] for c in cams],
                }
                self._save_meta(meta)
            except Exception: pass

            cam_str = ", ".join(c["label"] for c in cams)
            self._set_status(f"Done  [{cam_str}]  \u2192  {self._resolver.output_folder}")
            self._refresh_version_list()

        except Exception as exc:
            QMessageBox.critical(self, "Playblast failed", f"The playblast did not complete:\n\n{exc}")
            self._set_status(f"Blast failed: {exc}", error=True)
        finally:
            self._blast_btn.setText("Playblast"); self._blast_btn.setEnabled(True)
            self._update_output_preview()

    # ── RV ────────────────────────────────────────────────────────────────────

    def _on_play_in_rv(self) -> None:
        self._launch_rv(self._last_blast_folder or (
            self._resolver.output_folder if self._resolver else None))

    def _launch_rv(self, folder: Optional[str]) -> None:
        if not folder:
            self._set_status("No output folder to open.", error=True); return
        if not os.path.isfile(RV_PATH):
            QMessageBox.warning(self, "RV not found",
                f"RV not found at:\n\n{RV_PATH}\n\nUpdate RV_PATH in config.py."); return
        try:
            subprocess.Popen([RV_PATH, folder])
            self._set_status(f"Launched RV  \u2192  {folder}")
        except Exception as exc:
            QMessageBox.critical(self, "RV launch failed", f"Could not launch RV:\n\n{exc}")

    # ══════════════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _render_globals_resolution(self) -> tuple[int, int]:
        try:
            from .maya_bridge import get_render_resolution
            return get_render_resolution()
        except Exception:
            return DEFAULT_RESOLUTION

    def _selected_cameras(self) -> list[dict]:
        result = []
        for i in range(self._cam_list.count()):
            item = self._cam_list.item(i)
            if item.checkState() == Qt.Checked:
                result.append(item.data(Qt.UserRole))
        return result

    def _first_checked_camera(self) -> Optional[dict]:
        cams = self._selected_cameras()
        return cams[0] if cams else None

    def _add_selected_camera(self) -> None:
        """Add the currently selected Maya camera to the list if not already present."""
        try:
            from .maya_bridge import get_selected_camera
            cam = get_selected_camera()
        except Exception as exc:
            self._set_status(f"Could not get selection: {exc}", error=True)
            return

        if cam is None:
            self._set_status("No camera selected in Maya.", error=True)
            return

        # Don't add duplicates
        for i in range(self._cam_list.count()):
            if self._cam_list.item(i).data(Qt.UserRole)["label"] == cam["label"]:
                self._set_status(f"{cam['label']} is already in the list.")
                return

        # Default resolution from render globals
        if cam["label"] not in self._cam_resolution_overrides:
            self._cam_resolution_overrides[cam["label"]] = self._render_globals_resolution()

        item = QListWidgetItem()
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        item.setData(Qt.UserRole, cam)
        self._update_cam_item_text(item, cam)
        item.setForeground(QColor(_C_CAM_CHECKED))
        self._cam_list.addItem(item)
        self._cameras.append(cam)

        self._update_output_preview()
        self._set_status(f"Added  {cam['label']}")

    def _set_all_cameras(self, checked: bool) -> None:
        self._cam_list.blockSignals(True)
        for i in range(self._cam_list.count()):
            item = self._cam_list.item(i)
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            item.setForeground(QColor(_C_CAM_CHECKED if checked else _C_CAM_UNCHECKED))
        self._cam_list.blockSignals(False)
        self._update_output_preview()

    def _sync_anamorphic_controls(self) -> None:
        enabled = self._ana_chk.isChecked()
        self._squeeze_combo.setEnabled(enabled)
        self._blast_size_lbl.setVisible(enabled)
        if not enabled: self._blast_size_lbl.clear()

    @staticmethod
    def _open_file_location(folder: str) -> None:
        try:    subprocess.Popen(["explorer", os.path.normpath(folder)])
        except Exception:
            try: os.startfile(os.path.normpath(folder))
            except Exception: pass

    def _set_vp2(self, key: str, value) -> None:
        """Write a VP2 attribute to Maya's Hardware Render 2.0 settings immediately."""
        try:
            import maya.cmds as cmds
            from .maya_bridge import _VP2_ATTRS
            attr = _VP2_ATTRS.get(key)
            if attr:
                cmds.setAttr(attr, value)
        except Exception:
            pass

    def _set_vp2_aa(self, enabled: bool) -> None:
        """AA needs two attrs set together."""
        self._set_vp2("msaa",   enabled)
        self._set_vp2("lineAA", enabled)

    def _apply_dof_to_cameras(self, enabled: bool) -> None:
        """Enable/disable depthOfField on all checked cameras immediately."""
        try:
            import maya.cmds as cmds
            for cam in self._selected_cameras():
                cmds.setAttr(f"{cam['shape']}.depthOfField", enabled)
        except Exception:
            pass

    def _undock(self) -> None:
        """Float fxBlast back out as a standalone window."""
        try:
            import maya.cmds as cmds
            ctrl = self.objectName() + "WorkspaceControl"
            if cmds.workspaceControl(ctrl, query=True, exists=True):
                cmds.workspaceControl(ctrl, edit=True, floating=True)
                self._set_status("")
        except Exception as exc:
            self._set_status(f"Undock error: {exc}", error=True)

    def _dock_to_right(self) -> None:
        """
        Dock fxBlast as a tab inside Maya's right-side panel area.
        Uses tabToControl so no existing panels are displaced.
        """
        try:
            import maya.cmds as cmds

            # Workspace control name = objectName + "WorkspaceControl"
            ctrl = self.objectName() + "WorkspaceControl"

            if not cmds.workspaceControl(ctrl, query=True, exists=True):
                # Fall back: search all controls for anything fxBlast-related
                all_wc = cmds.lsUI(type="workspaceControl") or []
                for wc in all_wc:
                    if "fxblast" in wc.lower() or "playblast" in wc.lower():
                        ctrl = wc
                        break
                else:
                    short = ", ".join(all_wc[:8]) or "none"
                    self._set_status(
                        f"Could not find workspace control.  Found: {short}",
                        error=True
                    )
                    return

            # tabToControl inserts fxBlast as a tab inside an existing panel --
            # nothing is pushed or displaced.
            docked = False
            for target in ("AttributeEditor", "ChannelBoxLayerEditor", "outlinerPanel1"):
                try:
                    if cmds.workspaceControl(target, query=True, exists=True):
                        cmds.workspaceControl(ctrl, edit=True,
                                              tabToControl=(target, -1))
                        docked = True
                        break
                except Exception:
                    continue

            if not docked:
                cmds.workspaceControl(ctrl, edit=True, floating=False)

            # Defer restore so Maya finishes the tab layout before raising it
            def _raise(c=ctrl):
                try:
                    cmds.workspaceControl(c, edit=True, restore=True, visible=True)
                except Exception:
                    pass
            cmds.evalDeferred(_raise)
            self._set_status("")

        except Exception as exc:
            self._set_status(f"Dock error: {exc}", error=True)

    def _set_status(self, message: str, error: bool = False) -> None:
        colour = _C_RED if error else _C_GREEN
        self._status_lbl.setStyleSheet(f"font-size:11px; color:{colour};")
        self._status_lbl.setText(message)
        if not error:
            QTimer.singleShot(7000, lambda: self._status_lbl.setText(""))
