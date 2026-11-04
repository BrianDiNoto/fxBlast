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
        QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog,
        QDialogButtonBox, QDoubleSpinBox, QFrame, QFormLayout, QGridLayout,
        QGroupBox, QHBoxLayout, QHeaderView, QLabel,
        QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
        QPushButton, QRadioButton, QScrollArea, QSizePolicy, QSpinBox, QStyle,
        QStyledItemDelegate, QTabBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
    )
    from PySide2.QtCore import Qt, QTimer
    from PySide2.QtGui import QColor, QFont, QFontMetrics, QIcon
except ImportError:
    from PySide6.QtWidgets import (
        QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog,
        QDialogButtonBox, QDoubleSpinBox, QFrame, QFormLayout, QGridLayout,
        QGroupBox, QHBoxLayout, QHeaderView, QLabel,
        QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
        QPushButton, QRadioButton, QScrollArea, QSizePolicy, QSpinBox, QStyle,
        QStyledItemDelegate, QTabBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon

try:
    from maya.app.general.mayaMixin import MayaQWidgetDockableMixin as _DockMixin
    _TOOL_BASES = (_DockMixin, QWidget)
except ImportError:
    _TOOL_BASES = (QWidget,)

from .config import (
    ANAMORPHIC_SQUEEZE_FACTORS, BURN_IN_FIELDS, DEFAULT_FORMAT,
    DEFAULT_PRORES_PROFILE, DEFAULT_RESOLUTION, DEFAULT_SQUEEZE_FACTOR,
    FORMAT_EXTENSIONS, FORMAT_LABELS, FRAME_PADDING, IMAGE_FORMATS,
    MOVIE_FORMATS, MOVIE_LABELS, MOVIE_SEQUENCE_FORMAT, PRORES_PROFILES, RV_PATH,
)
from .scene_parser import ParseError, SceneTokens
from .resolver import OutputResolver, ResolveError, build_resolver

# Radio-button ids in the Format section: sequences first, then movies
_ALL_FORMATS = IMAGE_FORMATS + MOVIE_FORMATS
_FRAME_EXTS  = (".jpg", ".png")


class _Stopped(Exception):
    """The artist stopped the blast (Stop button or Esc in Maya)."""


def _frames_in(folder: str) -> list[str]:
    """Image frames directly inside `folder`, any format, sorted."""
    try:
        return sorted(os.path.join(folder, f) for f in os.listdir(folder)
                      if f.lower().endswith(_FRAME_EXTS))
    except OSError:
        return []


_NOTES_FILENAME = "_pb_notes.json"
_META_FILENAME  = "_pb_meta.json"

_COL_PLAY       = 0
_COL_VERSION    = 1
_COL_FRAMERANGE = 2
_COL_FRAMES     = 3
_COL_FPS        = 4
_COL_RESOLUTION = 5
_COL_NOTES      = 6

# ── Palette ────────────────────────────────────────────────────────────────────
_C_SECTION = "#808080"
_C_LABEL   = "#808080"
_C_VALUE   = "#d0d0d0"
_C_DIM     = "#808080"
_C_GREEN   = "#60a878"
_C_RED     = "#e07070"

# Context breadcrumb (matches the other FX tools' top readout)
_C_CRUMB_BG     = "#2e2e2e"
_C_CRUMB_BORDER = "rgba(255,255,255,0.08)"
_C_CRUMB_LABEL  = "#8a8a8a"
_C_CRUMB_VALUE  = "#eaeaea"
_C_CRUMB_ACCENT = "#6fb3e0"   # Version -- called out the same way the other tools do
_C_CRUMB_SEP    = "#5a5a5a"

# ── Styles ─────────────────────────────────────────────────────────────────────
_S_REFRESH = """
    QPushButton {
        background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
        border-radius: 4px; padding: 5px 12px; font-size: 12px; color: #808080;
    }
    QPushButton:hover  { background: rgba(255,255,255,0.10); color: #a0a0a0; }
    QPushButton:pressed{ background: rgba(255,255,255,0.04); }
"""
# Refresh scene button, colored by how the last refresh went
_S_REFRESH_OK = """
    QPushButton {
        background: rgba(96,168,120,0.18); border: 1px solid rgba(96,168,120,0.45);
        border-radius: 4px; padding: 5px 12px; font-size: 12px; color: #a8d8b8;
    }
    QPushButton:hover  { background: rgba(96,168,120,0.28); color: #c0e8cc; }
    QPushButton:pressed{ background: rgba(96,168,120,0.12); }
"""
_S_REFRESH_WARN = """
    QPushButton {
        background: rgba(200,170,60,0.18); border: 1px solid rgba(200,170,60,0.45);
        border-radius: 4px; padding: 5px 12px; font-size: 12px; color: #e0d090;
    }
    QPushButton:hover  { background: rgba(200,170,60,0.28); color: #f0e0a8; }
    QPushButton:pressed{ background: rgba(200,170,60,0.12); }
"""
_S_REFRESH_ERROR = """
    QPushButton {
        background: rgba(224,112,112,0.18); border: 1px solid rgba(224,112,112,0.45);
        border-radius: 4px; padding: 5px 12px; font-size: 12px; color: #f0a0a0;
    }
    QPushButton:hover  { background: rgba(224,112,112,0.28); color: #ffb8b8; }
    QPushButton:pressed{ background: rgba(224,112,112,0.12); }
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
# Blast buttons while a blast runs: they turn into Stop
_S_STOP = """
    QPushButton {
        background: #6a2e2e; color: #ffd0d0; border: 1px solid #a04848;
        border-radius: 4px; padding: 3px 0; font-size: 12px; min-height: 22px;
    }
    QPushButton:hover { background: #7a3636; }
"""
_S_HERO_STOP = """
    QPushButton#fxBlastHero {
        background: #6a2e2e; border: 1px solid #a04848; border-radius: 5px; min-height: 52px;
    }
    QPushButton#fxBlastHero:hover { background: #7a3636; }
    QLabel#fxBlastHeroTitle { color: #ffe0e0; font-size: 16px; font-weight: 600; background: transparent; }
    QLabel#fxBlastHeroSub   { color: #f0b0b0; font-size: 11px; background: transparent; }
"""
# Manual tab: Simple / Advanced toggle and the project box
_S_MODE_BTN = """
    QPushButton {
        background: transparent; color: #8a8a8a; border: 1px solid #5a5a5a;
        padding: 3px 12px; font-size: 11px;
    }
    QPushButton:checked { background: #5a5a5a; color: #eaeaea; }
"""
_S_PROJECT_OK = """
    QFrame#fxBlastProject { border: 1px solid rgba(255,255,255,0.12); border-radius: 3px;
                            background: rgba(0,0,0,0.15); }
    QLabel { border: none; background: transparent; }
"""
_S_PROJECT_MISSING = """
    QFrame#fxBlastProject { border: 1px solid rgba(200,170,60,0.45); border-radius: 3px;
                            background: rgba(200,170,60,0.10); }
    QLabel { border: none; background: transparent; }
"""
# Small per-row "Play in RV" button used in the version list
_S_RV_MINI = """
    QPushButton {
        background: #3e3e3e; color: #a0a0a0; border: 1px solid #585858;
        border-radius: 3px; font-size: 10px; padding: 0px;
    }
    QPushButton:hover   { background: #4a4a4a; color: #c0c0c0; }
    QPushButton:pressed { background: #333333; }
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
        border-radius: 3px; font-size: 12px; color: #808080;
    }
    QPushButton:hover { background: rgba(255,255,255,0.06); color: #a0a0a0; }
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
# Mode tabs under the breadcrumb: Simple / Advanced / Manual
_S_TABS = """
    QFrame#fxBlastTabs { background: #3c3c3c; border-bottom: 1px solid #2a2a2a; }
    QTabBar { background: transparent; }
    QTabBar::tab {
        background: transparent; color: #8a8a8a; font-size: 12px;
        padding: 7px 0; min-width: 60px; border: none;
        border-bottom: 2px solid transparent;
    }
    QTabBar::tab:selected { color: #eaeaea; background: #444444; border-bottom-color: #6fb3e0; }
    QTabBar::tab:hover:!selected { color: #b8b8b8; }
    QTabBar::tab:disabled { color: #5a5a5a; }
"""
# Simple tab: the one big Playblast button
_S_HERO = """
    QPushButton#fxBlastHero {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4b7fa3, stop:1 #3d6a8a);
        border: 1px solid #5a93ba; border-radius: 5px; min-height: 52px;
    }
    QPushButton#fxBlastHero:hover {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5389ae, stop:1 #437294);
    }
    QPushButton#fxBlastHero:pressed  { background: #36607d; }
    QPushButton#fxBlastHero:disabled { background: #333333; border-color: #444444; }
    QLabel#fxBlastHeroTitle { color: #eaf4fb; font-size: 16px; font-weight: 600; background: transparent; }
    QLabel#fxBlastHeroSub   { color: #b6d3e6; font-size: 11px; background: transparent; }
    QLabel#fxBlastHeroTitle:disabled { color: #666666; }
    QLabel#fxBlastHeroSub:disabled   { color: #555555; }
"""
_S_SUB_LBL   = f"font-size: 11px; color: {_C_DIM}; margin-left: 20px;"
_S_DOCK_BTN  = """
    QPushButton {
        background: rgba(255,255,255,0.05); color: #808080;
        border: 1px solid rgba(255,255,255,0.14); border-radius: 3px;
        padding: 2px 8px; font-size: 11px;
    }
    QPushButton:hover { background: rgba(255,255,255,0.10); color: #a0a0a0; }
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
    # Preserves the camera/layer's own casing from the scene -- only
    # non-alphanumeric characters are swapped for underscores.
    return re.sub(r"[^a-zA-Z0-9]+", "_", label).strip("_")


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
# Camera list: right-aligned resolution (+ hint on hover)
# ══════════════════════════════════════════════════════════════════════════════

_ROLE_RIGHT_TEXT = Qt.UserRole + 1


class _RightTextDelegate(QStyledItemDelegate):
    """Draws the item normally, then a dim right-aligned note (the camera's
    resolution). The hovered row also shows the right-click hint."""

    HINT = "right-click to set"

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        text = index.data(_ROLE_RIGHT_TEXT)
        if not text:
            return
        hover = bool(option.state & QStyle.State_MouseOver)
        f = QFont(option.font)
        if f.pixelSize() > 0:
            f.setPixelSize(max(f.pixelSize() - 1, 9))
        elif f.pointSizeF() > 0:
            f.setPointSizeF(max(f.pointSizeF() - 1.0, 7.0))
        f.setItalic(True)
        if hover:
            # only add the hint when it fits beside the camera name
            name_w = option.fontMetrics.horizontalAdvance(index.data(Qt.DisplayRole) or "")
            with_hint = f"{text}    {self.HINT}"
            if name_w + 40 + QFontMetrics(f).horizontalAdvance(with_hint) <= option.rect.width():
                text = with_hint
        painter.save()
        painter.setFont(f)
        painter.setPen(QColor(_C_LABEL if hover else _C_DIM))
        painter.drawText(option.rect.adjusted(0, 0, -8, 0),
                         Qt.AlignRight | Qt.AlignVCenter, text)
        painter.restore()


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
        self._cam_resolution_overrides: dict[str, tuple[int, int]] = {}
        self._cam_res_custom:           set[str]                 = set()
        self._cam_follow_rg:            set[str]                 = set()
        self._rg_jobs:                  list[int]                = []
        self._rg_update_pending:        bool                     = False
        self._lb:                       Optional[dict]           = None

        self._setup_window()
        self._build_ui()
        self._refresh_scene()

    def closeEvent(self, event):
        try:
            from .maya_bridge import kill_script_jobs
            kill_script_jobs(self._rg_jobs); self._rg_jobs = []
        except Exception:
            pass
        PlayblastTool._instance = None
        super().closeEvent(event)

    def _setup_window(self) -> None:
        self.setWindowTitle("fxBlast")
        self.setObjectName("fxBlast")   # workspace control = "fxBlastWorkspaceControl"
        self.setMinimumWidth(460)
        self._apply_window_icon()

    def _apply_window_icon(self) -> None:
        """Matches the other FX tools, which all show their own icon in the
        title bar. Deployment layout is .../fxBlast/icons/FX_blast.png,
        sitting next to this package's .../fxBlast/python/ folder."""
        try:
            package_dir = os.path.dirname(os.path.abspath(__file__))        # .../fxBlast/python/fxBlast
            deploy_root = os.path.dirname(os.path.dirname(package_dir))     # .../fxBlast
            icon_path = os.path.join(deploy_root, "icons", "FX_blast.png")
            if os.path.isfile(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    # UI
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 10)

        # Context breadcrumb sits above the scroll area, like the other FX
        # tools' top readout -- it stays visible no matter what's scrolled.
        outer.addWidget(self._build_context_bar())
        outer.addWidget(self._build_tab_bar())

        # Sections live in a scroll area so opening a panel (e.g. render
        # layers) never squashes the rest - the window scrolls instead.
        content = QWidget()
        root = QVBoxLayout(content)
        root.setSpacing(6)
        root.setContentsMargins(12, 10, 12, 4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        self._error_banner = QLabel()
        self._error_banner.setStyleSheet(_S_ERROR)
        self._error_banner.setWordWrap(True)
        self._error_banner.setVisible(False)
        root.addWidget(self._error_banner)

        self._refresh_btn = QPushButton("Refresh scene")
        self._refresh_btn.setStyleSheet(_S_REFRESH)
        self._refresh_btn.setToolTip(
            "Green = refreshed from the pipeline context.\n"
            "Yellow = refreshed from the scene path (pipeline context not "
            "available, or the scene is outside the task Maya was launched in)."
            "\nRed = could not read this scene.")
        self._refresh_btn.clicked.connect(self._refresh_scene)
        root.addWidget(self._refresh_btn)
        root.addWidget(self._build_manual_box())

        root.addWidget(self._build_scene_section())
        # Advanced-only widgets are kept so the tab switch can show/hide them
        self._cam_hline      = _hline()
        self._cam_section    = self._build_camera_section()
        self._layers_section = self._build_layers_section()
        root.addWidget(self._cam_hline)
        root.addWidget(self._cam_section)
        root.addWidget(self._layers_section)
        root.addWidget(_hline())
        root.addWidget(self._build_anamorphic_section())
        root.addWidget(_hline())
        root.addWidget(self._build_format_section())
        root.addWidget(_hline())
        root.addWidget(self._build_note_section())
        self._po_section = self._build_playblast_options_section()
        root.addWidget(self._po_section)

        # Simple tab: which camera will be blasted, then the big button
        self._simple_cam_lbl = QLabel()
        self._simple_cam_lbl.setStyleSheet(f"font-size:11px; color:{_C_DIM};")
        root.addWidget(self._simple_cam_lbl)
        root.addWidget(self._build_hero_button())

        self._blast_row = QWidget()
        btn_row = QHBoxLayout(self._blast_row); btn_row.setSpacing(8)
        btn_row.setContentsMargins(0, 0, 0, 0)
        self._blast_btn = QPushButton("Playblast")
        self._blast_btn.setStyleSheet(_S_BLAST)
        self._blast_btn.setFixedWidth(140)
        self._blast_btn.clicked.connect(self._on_blast_clicked)
        btn_row.addStretch()
        btn_row.addWidget(self._blast_btn)
        btn_row.addStretch()
        root.addWidget(self._blast_row)

        root.addWidget(self._build_output_section())
        self._versions_section = self._build_versions_section()
        root.addWidget(self._versions_section)
        root.addStretch()

        footer = QHBoxLayout(); footer.setSpacing(6)
        footer.setContentsMargins(12, 0, 12, 0)
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
        outer.addLayout(footer)

        self._apply_tab_mode()

    # ── Scene ─────────────────────────────────────────────────────────────────

    # ── Mode tabs ─────────────────────────────────────────────────────────────

    _TAB_SIMPLE, _TAB_ADVANCED, _TAB_MANUAL = 0, 1, 2

    def _build_tab_bar(self) -> QWidget:
        frame = QFrame(); frame.setObjectName("fxBlastTabs")
        frame.setStyleSheet(_S_TABS)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tab_bar = QTabBar()
        self._tab_bar.setExpanding(True)
        self._tab_bar.setDrawBase(False)
        for name in ("Simple", "Advanced", "Manual"):
            self._tab_bar.addTab(name)
        self._tab_bar.setTabToolTip(
            self._TAB_MANUAL, "Blast a scene that is not in the pipeline, into the Maya project")
        self._last_tab_manual = False
        self._tab_bar.setCurrentIndex(self._TAB_SIMPLE)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tab_bar)
        return frame

    def _is_manual(self) -> bool:
        bar = getattr(self, "_tab_bar", None)
        return bool(bar and bar.currentIndex() == self._TAB_MANUAL)

    def _is_simple(self) -> bool:
        """Simple tab, or the Manual tab with its toggle on Simple."""
        bar = getattr(self, "_tab_bar", None)
        if not bar:
            return False
        if bar.currentIndex() == self._TAB_MANUAL:
            return self._man_simple_btn.isChecked()
        return bar.currentIndex() == self._TAB_SIMPLE

    def _on_tab_changed(self, _index: int) -> None:
        manual = self._is_manual()
        self._apply_tab_mode()
        if manual != self._last_tab_manual:
            # Pipeline <-> Maya project: the scene info comes from elsewhere
            self._last_tab_manual = manual
            self._refresh_scene()
        else:
            self._update_output_preview()

    def _on_manual_mode_changed(self, *_):
        self._apply_tab_mode()
        self._update_output_preview()

    def _apply_tab_mode(self) -> None:
        """Simple hides the Advanced-only sections. Both tabs share the same
        widgets, so frame range, format, note etc. never go out of sync."""
        simple = self._is_simple()
        for w in (self._cam_hline, self._cam_section, self._layers_section,
                  self._po_section, self._blast_row, self._versions_section):
            w.setVisible(not simple)
        for w in (self._simple_cam_lbl, self._hero_btn):
            w.setVisible(simple)
        self._manual_box.setVisible(self._is_manual())

    def _build_manual_box(self) -> QWidget:
        """Manual tab only: the Maya project, and the Simple/Advanced toggle."""
        self._manual_box = QWidget()
        lay = QVBoxLayout(self._manual_box)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(6)

        self._project_frame = QFrame(); self._project_frame.setObjectName("fxBlastProject")
        self._project_frame.setStyleSheet(_S_PROJECT_OK)
        pl = QVBoxLayout(self._project_frame)
        pl.setContentsMargins(8, 8, 8, 8); pl.setSpacing(6)
        top = QHBoxLayout(); top.setSpacing(10)
        set_btn = QPushButton("Set Project..."); set_btn.setStyleSheet(_S_SMALL_BTN)
        set_btn.clicked.connect(self._on_set_project)
        top.addWidget(set_btn); top.addWidget(_lbl("Maya project")); top.addStretch()
        pl.addLayout(top)
        self._project_lbl = QLabel("--")
        self._project_lbl.setWordWrap(True)
        self._project_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._project_lbl.setStyleSheet(
            f"font-family: monospace; font-size:11px; color:{_C_VALUE};")
        pl.addWidget(self._project_lbl)
        lay.addWidget(self._project_frame)

        row = QHBoxLayout(); row.setSpacing(0)
        self._man_mode_group = QButtonGroup(self)
        self._man_simple_btn = QPushButton("Simple")
        self._man_adv_btn    = QPushButton("Advanced")
        for b in (self._man_simple_btn, self._man_adv_btn):
            b.setCheckable(True); b.setStyleSheet(_S_MODE_BTN)
            self._man_mode_group.addButton(b); row.addWidget(b)
        self._man_simple_btn.setChecked(True)
        self._man_mode_group.buttonClicked.connect(self._on_manual_mode_changed)
        row.addSpacing(10)
        hint = QLabel("Output goes to the Maya project, named from the workfile.")
        hint.setStyleSheet(f"font-size:11px; color:{_C_DIM};")
        row.addWidget(hint); row.addStretch()
        lay.addLayout(row)
        lay.addWidget(_hline())
        return self._manual_box

    def _update_project_box(self) -> None:
        try:
            from .maya_bridge import get_project_root, project_is_set
            root = get_project_root(); ok = project_is_set(root)
        except Exception:
            root, ok = "", False
        self._project_lbl.setText(
            root if ok else "No project set. Output needs a Maya project.")
        self._project_frame.setStyleSheet(_S_PROJECT_OK if ok else _S_PROJECT_MISSING)

    def _on_set_project(self) -> None:
        try:
            from .maya_bridge import get_project_root, set_project
            start = get_project_root()
        except Exception:
            start = ""
        path = QFileDialog.getExistingDirectory(self, "Set Maya project", start)
        if not path:
            return
        try:
            set_project(path)
        except Exception as exc:
            self._set_status(f"Could not set project: {exc}", error=True); return
        self._refresh_scene()

    def _build_hero_button(self) -> QPushButton:
        self._hero_btn = QPushButton()
        self._hero_btn.setObjectName("fxBlastHero")
        self._hero_btn.setStyleSheet(_S_HERO)
        self._hero_btn.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self._hero_btn)
        lay.setContentsMargins(8, 8, 8, 8); lay.setSpacing(1)
        self._hero_title = QLabel("Playblast"); self._hero_title.setObjectName("fxBlastHeroTitle")
        self._hero_sub   = QLabel("");          self._hero_sub.setObjectName("fxBlastHeroSub")
        for lbl in (self._hero_title, self._hero_sub):
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
            lay.addWidget(lbl)
        self._hero_btn.clicked.connect(self._on_blast_clicked)
        return self._hero_btn

    def _update_hero_sub(self) -> None:
        if not hasattr(self, "_hero_sub") or self._busy:
            return
        cams = self._blast_cameras() if self._tokens else []
        if self._tokens is None or not cams:
            self._hero_sub.setText("")
            return
        version = self._resolver.version if self._resolver else self._tokens.version
        self._hero_sub.setText(
            f"{version}   \u2022   {cams[0]['label']}   \u2022   "
            f"{self._start_spin.value()}-{self._end_spin.value()}")

    # Both Playblast buttons (Advanced + Simple hero) change together.
    # While a blast runs they become Stop buttons.
    _busy = False
    _stop_requested = False

    def _set_blast_enabled(self, enabled: bool) -> None:
        if self._busy:
            return                      # the Stop button stays clickable
        self._blast_btn.setEnabled(enabled)
        self._hero_btn.setEnabled(enabled)

    def _on_blast_clicked(self) -> None:
        if self._busy:
            self._stop_requested = True
            self._progress("Stopping...")
            return
        self._on_playblast()

    def _begin_busy(self) -> None:
        self._busy, self._stop_requested = True, False
        self._blast_btn.setEnabled(True); self._hero_btn.setEnabled(True)
        self._blast_btn.setText("\u25a0  Stop"); self._blast_btn.setStyleSheet(_S_STOP)
        self._blast_btn.setToolTip("Stops before the next camera or layer, and cancels "
                                   "a movie encode. Press Esc in Maya to stop the "
                                   "camera being blasted now.")
        self._hero_title.setText("\u25a0  Stop"); self._hero_btn.setStyleSheet(_S_HERO_STOP)
        self._hero_sub.setVisible(True)

    def _end_busy(self) -> None:
        self._busy = False
        self._blast_btn.setText("Playblast"); self._blast_btn.setStyleSheet(_S_BLAST)
        self._blast_btn.setToolTip("")
        self._hero_title.setText("Playblast"); self._hero_btn.setStyleSheet(_S_HERO)
        self._update_output_preview()

    def _progress(self, text: str) -> None:
        """Show what the blast is doing now, under Stop and in the footer."""
        self._hero_sub.setText(f"{text}   (Esc in Maya stops this camera)"
                               if text.startswith("Blasting") else text)
        self._status_lbl.setStyleSheet(f"font-size:11px; color:{_C_DIM};")
        self._status_lbl.setText(text)
        QApplication.processEvents()

    def _build_context_bar(self) -> QWidget:
        """Show / Season / Type / Asset / Task / Scene / Version, as one
        breadcrumb line matching the other FX tools' top readout."""
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{_C_CRUMB_BG}; "
            f"border:none; border-bottom:1px solid {_C_CRUMB_BORDER}; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 9, 12, 9)
        self._context_lbl = QLabel()
        self._context_lbl.setTextFormat(Qt.RichText)
        self._context_lbl.setWordWrap(True)
        layout.addWidget(self._context_lbl)
        self._set_context_bar(None)
        return frame

    def _set_context_bar(self, t) -> None:
        def crumb(label: str, value: str) -> str:
            return (f'<span style="color:{_C_CRUMB_LABEL};">{label}</span> '
                     f'<b style="color:{_C_CRUMB_VALUE};">{value}</b>')

        sep = f'&nbsp;&nbsp;<span style="color:{_C_CRUMB_SEP};">/</span>&nbsp;&nbsp;'
        if t is not None and t.source == "manual":
            parts = [
                '<b style="color:#e0d090;">Out of pipeline</b>',
                crumb("Project", t.show),
                crumb("Scene", t.asset_or_shot),
                (f'<span style="color:{_C_CRUMB_LABEL};">Version</span> '
                 f'<b style="color:{_C_CRUMB_ACCENT};">{t.version}</b>'),
            ]
            self._context_lbl.setText(
                f'<span style="font-size:13px;">{sep.join(parts)}</span>')
            return
        if t is None:
            parts = [crumb(lbl, "--") for lbl in
                     ("Show", "Season", "Type/Seq", "Asset/Shot", "Task", "Scene")]
            version_html = (f'<span style="color:{_C_CRUMB_LABEL};">Version</span> '
                             f'<b style="color:{_C_CRUMB_ACCENT};">--</b>')
        else:
            parts = [
                crumb("Show", t.show),
                crumb("Season", t.season),
                crumb("Type/Seq", t.type_or_seq),
                crumb("Asset/Shot", t.asset_or_shot),
                crumb("Task", t.task),
                crumb("Scene", t.descriptor or "none"),
            ]
            version_html = (f'<span style="color:{_C_CRUMB_LABEL};">Version</span> '
                             f'<b style="color:{_C_CRUMB_ACCENT};">{t.version}</b>')
        parts.append(version_html)
        self._context_lbl.setText(
            f'<span style="font-size:13px;">{sep.join(parts)}</span>')

    def _build_scene_section(self) -> QWidget:
        # Show/Season/Type/Asset/Task/Scene/Version now live in the context
        # breadcrumb above the scroll area -- this section is just frame range.
        w    = QWidget()
        row  = QHBoxLayout(w)
        row.setContentsMargins(0, 4, 0, 4); row.setSpacing(5)

        row.addWidget(_lbl("Frame range:"))
        self._start_spin = QSpinBox(); self._start_spin.setRange(-10000, 100000); self._start_spin.setMaximumWidth(70)
        self._end_spin   = QSpinBox(); self._end_spin.setRange(-10000, 100000);   self._end_spin.setMaximumWidth(70)
        fr_btn = QPushButton("From scene"); fr_btn.setStyleSheet(_S_REFRESH)
        fr_btn.setMaximumHeight(24); fr_btn.clicked.connect(self._refresh_frame_range)
        self._start_spin.valueChanged.connect(self._update_hero_sub)
        self._end_spin.valueChanged.connect(self._update_hero_sub)
        row.addWidget(self._start_spin); row.addWidget(_lbl("to"))
        row.addWidget(self._end_spin); row.addSpacing(6); row.addWidget(fr_btn); row.addStretch()
        return w

    # ── Camera ────────────────────────────────────────────────────────────────

    def _build_camera_section(self) -> QWidget:
        w      = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(5)

        # Header row: Camera + global resolution option
        hdr = QHBoxLayout(); hdr.setSpacing(12)
        hdr.addWidget(_section_header("Camera"))
        self._use_rg_chk = _chk(
            "Render global resolution for all cameras", True,
            "Every camera blasts at the Render Settings resolution (read live).\n"
            "Cameras you set by right-click keep their own size (marked custom).")
        self._use_rg_chk.toggled.connect(self._on_use_rg_toggled)
        hdr.addWidget(self._use_rg_chk)
        self._rg_res_lbl = QLabel("")
        self._rg_res_lbl.setStyleSheet(f"font-size:11px; color:{_C_DIM};")
        self._rg_res_lbl.setTextFormat(Qt.RichText)
        self._rg_res_lbl.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        self._rg_res_lbl.setCursor(Qt.PointingHandCursor)
        self._rg_res_lbl.setToolTip("Open Render Settings")
        self._rg_res_lbl.linkActivated.connect(self._open_render_settings)
        hdr.addWidget(self._rg_res_lbl); hdr.addStretch()
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
        self._cam_list.setMouseTracking(True)
        self._cam_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._cam_list.setTextElideMode(Qt.ElideMiddle)
        self._cam_list.setItemDelegate(_RightTextDelegate(self._cam_list))
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

    # ── Render layers ─────────────────────────────────────────────────────────

    def _build_layers_section(self) -> QWidget:
        w      = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(5)

        self._layers_chk = _chk(
            "Step through render layers", False,
            "Blast each checked render layer through its own camera.\n"
            "The master layer is never blasted.")
        self._layers_chk.toggled.connect(self._on_layers_toggled)
        layout.addWidget(self._layers_chk)

        self._layers_body = QWidget()
        body = QVBoxLayout(self._layers_body)
        body.setContentsMargins(0, 0, 0, 0); body.setSpacing(5)

        frame = QFrame(); frame.setStyleSheet(_S_CAM_FRAME)
        frame.setFixedHeight(112)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        frame_layout = QHBoxLayout(frame)
        frame_layout.setContentsMargins(6, 6, 6, 6); frame_layout.setSpacing(6)

        self._layer_list = QListWidget()
        self._layer_list.setMaximumHeight(100)
        self._layer_list.setStyleSheet(_S_CAM_LIST)
        self._layer_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._layer_list.setTextElideMode(Qt.ElideMiddle)
        self._layer_list.itemChanged.connect(self._on_layer_check_changed)
        frame_layout.addWidget(self._layer_list)

        side = QVBoxLayout(); side.setSpacing(3)
        for label, slot in (("All",     lambda: self._set_all_layers(True)),
                            ("None",    lambda: self._set_all_layers(False)),
                            ("Refresh", self._refresh_layers)):
            btn = QPushButton(label); btn.setStyleSheet(_S_SMALL_BTN)
            btn.setMinimumWidth(58); btn.clicked.connect(slot); side.addWidget(btn)
        side.addStretch()
        frame_layout.addLayout(side)
        body.addWidget(frame)

        row = QHBoxLayout(); row.setSpacing(6)
        row.addWidget(_lbl("Settle (s)"))
        self._settle_spin = _dbl_spin(0.0, 10.0, 0.25, 2, 1.0)
        self._settle_spin.setToolTip(
            "Pause after each layer switch so the viewport redraws before blasting.")
        row.addWidget(self._settle_spin)
        hint = QLabel("Blasts through the viewport you last clicked in.")
        hint.setStyleSheet(f"font-size:11px; color:{_C_DIM}; font-style:italic;")
        row.addWidget(hint); row.addStretch()
        body.addLayout(row)

        self._layers_body.setVisible(False)
        layout.addWidget(self._layers_body)
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
        # Grid, so every row of options lines up in the same columns
        grid = QGridLayout(); grid.setContentsMargins(20, 0, 0, 0)
        grid.setHorizontalSpacing(10); grid.setVerticalSpacing(5)
        seq_lbl = QLabel("Sequence"); seq_lbl.setStyleSheet(f"font-size:11px; color:{_C_DIM};")
        seq_lbl.setFixedWidth(72)
        grid.addWidget(seq_lbl, 0, 0)
        self._fmt_btn_group = QButtonGroup(self)
        for i, fmt in enumerate(IMAGE_FORMATS):
            rb = QRadioButton(FORMAT_LABELS.get(fmt, fmt.upper()))
            rb.setStyleSheet(f"font-size:12px; color:{_C_VALUE};")
            if fmt == DEFAULT_FORMAT: rb.setChecked(True)
            self._fmt_btn_group.addButton(rb, i)
            rb.toggled.connect(self._update_output_preview)
            grid.addWidget(rb, 0, i + 1)
        mov_lbl = QLabel("Movie"); mov_lbl.setStyleSheet(f"font-size:11px; color:{_C_DIM};")
        grid.addWidget(mov_lbl, 1, 0)
        for j, fmt in enumerate(MOVIE_FORMATS):
            rb = QRadioButton(MOVIE_LABELS[fmt])
            rb.setStyleSheet(f"font-size:12px; color:{_C_VALUE};")
            rb.setToolTip("Blasts an image sequence (kept), then encodes it into the movies folder.")
            self._fmt_btn_group.addButton(rb, len(IMAGE_FORMATS) + j)
            rb.toggled.connect(self._on_format_changed)
            grid.addWidget(rb, 1, j + 1)

        # ProRes profiles: only shown while ProRes is picked
        self._prores_lbl = QLabel("ProRes"); self._prores_lbl.setStyleSheet(f"font-size:11px; color:{_C_DIM};")
        grid.addWidget(self._prores_lbl, 2, 0)
        self._prores_group = QButtonGroup(self)
        self._prores_btns = []
        for k, (pid, label, _num) in enumerate(PRORES_PROFILES):
            rb = QRadioButton(label)
            rb.setStyleSheet(f"font-size:12px; color:{_C_VALUE};")
            rb.setChecked(pid == DEFAULT_PRORES_PROFILE)
            self._prores_group.addButton(rb, k)
            grid.addWidget(rb, 2, k + 1)
            self._prores_btns.append(rb)
        grid.setColumnStretch(4, 1)
        layout.addLayout(grid)
        self._on_format_changed()
        return w

    def _selected_format(self) -> str:
        """jpg / png / png_alpha / h264 / prores"""
        return _ALL_FORMATS[max(self._fmt_btn_group.checkedId(), 0)]

    def _movie_format(self) -> Optional[str]:
        f = self._selected_format()
        return f if f in MOVIE_FORMATS else None

    def _sequence_format(self) -> str:
        """The image format actually blasted (movies blast a sequence first)."""
        f = self._selected_format()
        return MOVIE_SEQUENCE_FORMAT.get(f, f)

    def _prores_profile(self) -> str:
        return PRORES_PROFILES[max(self._prores_group.checkedId(), 0)][0]

    def _on_format_changed(self, *_):
        prores = self._selected_format() == "prores"
        for w in [self._prores_lbl] + self._prores_btns:
            w.setVisible(prores)
        if self._tokens is not None:
            self._update_output_preview()

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
        body_layout.addWidget(self._disable_filmgate_chk)

        # Burn-in: one setting for every tab, on by default. Same on the
        # image sequence and the movie (the movie is encoded from it).
        self._hud_chk = _chk("Burn-in HUD", checked=True,
                             tooltip="Burned into the frames, so it is in the sequence and the movie.")
        body_layout.addWidget(self._hud_chk)
        burn = QGridLayout(); burn.setContentsMargins(20, 0, 0, 0)
        burn.setHorizontalSpacing(10); burn.setVerticalSpacing(4)
        self._burn_chks = {}
        for n, (fid, label) in enumerate(BURN_IN_FIELDS):
            cb = _chk(label, checked=True)
            self._burn_chks[fid] = cb
            burn.addWidget(cb, n // 3, n % 3)
        burn.setColumnStretch(3, 1)
        body_layout.addLayout(burn)
        self._hud_chk.toggled.connect(
            lambda on: [cb.setEnabled(on) for cb in self._burn_chks.values()])

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
        self._output_path_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._output_path_lbl.setMinimumWidth(1)
        self._output_path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row = QHBoxLayout(); row.setSpacing(6)
        row.addWidget(self._output_path_lbl, 1)
        open_btn = QPushButton("Open folder")
        open_btn.setStyleSheet(_S_REFRESH)
        open_btn.setToolTip("Open this scene's output folder in Explorer")
        open_btn.clicked.connect(self._on_open_folder)
        row.addWidget(open_btn, 0, Qt.AlignTop)
        layout.addLayout(row)
        return w

    def _on_open_folder(self) -> None:
        """Open the current version folder, or the images folder above it
        when this version has not been blasted yet."""
        if self._tokens is None:
            self._set_status("No scene info - nothing to open.", error=True); return
        candidates = [self._resolver.output_folder] if self._resolver else []
        candidates.append(self._tokens.images_root)
        for folder in candidates:
            if folder and os.path.isdir(folder):
                self._open_file_location(folder); return
        self._set_status("Output folder does not exist yet - blast first.", error=True)

    # ── Version list ──────────────────────────────────────────────────────────

    def _build_versions_section(self) -> QWidget:
        w      = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

        self._ver_tree = QTreeWidget()
        self._ver_tree.setColumnCount(7)
        self._ver_tree.setHeaderLabels(
            ["", "Version", "Range", "Frames", "FPS", "Resolution", "Notes"])
        self._ver_tree.setFixedHeight(224)
        self._ver_tree.setAlternatingRowColors(True)
        self._ver_tree.setRootIsDecorated(True)
        self._ver_tree.setIndentation(8)   # small, so the play column stays wide enough at 2 depth levels
        self._ver_tree.setStyleSheet("font-size:12px;")
        self._ver_tree.setSelectionMode(QTreeWidget.SingleSelection)

        hdr = self._ver_tree.header()
        hdr.resizeSection(_COL_PLAY, 40); hdr.resizeSection(_COL_VERSION, 62)
        hdr.resizeSection(_COL_FRAMERANGE, 72); hdr.resizeSection(_COL_FRAMES, 52)
        hdr.resizeSection(_COL_FPS, 52); hdr.resizeSection(_COL_RESOLUTION, 90)
        hdr.setSectionResizeMode(_COL_PLAY, QHeaderView.Fixed)
        hdr.setSectionResizeMode(_COL_NOTES, QHeaderView.Stretch)

        self._ver_tree.itemChanged.connect(self._on_notes_changed)
        self._ver_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._ver_tree.customContextMenuRequested.connect(self._on_version_context_menu)
        layout.addWidget(self._ver_tree)
        return w

    def _make_rv_button(self, folder: str) -> QPushButton:
        """Small per-row button that plays that row's sequence in RV."""
        btn = QPushButton("\u25b6")
        btn.setFixedSize(22, 20)
        btn.setStyleSheet(_S_RV_MINI)
        btn.setToolTip("Play in RV")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda checked=False, f=folder: self._launch_rv(f))
        return btn

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

    def _ver_key(self, version: str) -> str:
        """Notes/meta key: the full version folder name, so scenes sharing a
        task never overwrite each other's entries."""
        return self._tokens.output_basename(version) if self._tokens else version

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
        key   = self._ver_key(version)
        if note: notes[key] = note
        else:    notes.pop(key, None)
        self._save_notes(notes)

    # ══════════════════════════════════════════════════════════════════════════
    # Data refresh
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_scene(self) -> None:
        manual = self._is_manual()
        if manual:
            self._update_project_box()
        try:
            if manual:
                from .maya_bridge import get_manual_tokens
                self._tokens = get_manual_tokens()
            else:
                from .maya_bridge import get_scene_tokens
                self._tokens = get_scene_tokens()
            self._error_banner.setVisible(False)
        except (ParseError, Exception) as exc:
            self._tokens = None; self._resolver = None
            msg = str(exc)
            if not manual and "No scene file is open" not in msg:
                msg += "\n\nTo blast this scene anyway, use the Manual tab."
            self._error_banner.setText(msg); self._error_banner.setVisible(True)
            self._set_context_bar(None)
            self._set_blast_enabled(False); self._output_path_lbl.setText("--")
            self._refresh_btn.setStyleSheet(_S_REFRESH_ERROR)
            self._ver_tree.clear(); self._update_hero_sub()
            self._set_status("Could not read this scene - see the message above", error=True)
            return
        src = self._tokens.source
        self._refresh_btn.setStyleSheet(
            _S_REFRESH_WARN if src == "scene path" else _S_REFRESH_OK)
        self._set_status(
            {"pipeline": "Scene info from the pipeline context",
             "manual":   "Output goes to the Maya project"}.get(
                src, "Scene info from the scene path (no pipeline context for this scene)"),
            error=src == "scene path")
        self._cam_resolution_overrides.clear()
        self._cam_res_custom.clear()
        self._cam_follow_rg.clear()
        self._watch_render_resolution()
        self._populate_scene_info()
        self._refresh_frame_range()
        self._refresh_note()
        self._refresh_cameras()
        if self._layers_chk.isChecked():
            self._refresh_layers()
        self._refresh_version_list()

    def _populate_scene_info(self) -> None:
        self._set_context_bar(self._tokens)

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
        stored = self._load_notes().get(
            self._ver_key(self._tokens.version) if self._tokens else "", "")
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
        rw, rh = rg_res
        self._set_rg_label(rw, rh)

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

        current_version = self._tokens.version if self._tokens else ""
        notes = self._load_notes(); meta = self._load_meta()

        for ver in resolver.existing_versions():
            folder   = self._tokens.output_folder(ver)
            key      = self._ver_key(ver)
            ver_meta = meta.get(key, {}); note = notes.get(key, "")

            flat_frames = _frames_in(folder)       # any format, not just the selected one
            cam_subfolders = []
            try:
                cam_subfolders = sorted([
                    d for d in os.listdir(folder)
                    if os.path.isdir(os.path.join(folder, d))
                    and not d.startswith("_")
                    and _frames_in(os.path.join(folder, d))
                ])
            except Exception: pass

            is_multi = bool(cam_subfolders) and not flat_frames
            if is_multi:
                all_frames = sorted(
                    f for sf in cam_subfolders
                    for f in _frames_in(os.path.join(folder, sf))
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
            ver_item = QTreeWidgetItem(["", ver, range_str, str(count), fps_str, res_str, note])
            ver_item.setData(_COL_VERSION, Qt.UserRole, ver)
            ver_item.setData(_COL_FRAMES,  Qt.UserRole, folder)
            ver_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)

            if ver == current_version:
                for col in range(7): ver_item.setBackground(col, _COLOR_CURRENT)
                ver_item.setText(_COL_VERSION, f"{ver}  *")

            for col in (_COL_FRAMERANGE, _COL_FRAMES, _COL_FPS, _COL_RESOLUTION):
                ver_item.setTextAlignment(col, Qt.AlignCenter)

            child_folders = []
            if is_multi:
                for sf in cam_subfolders:
                    sf_folder = os.path.join(folder, sf)
                    sf_frames = _frames_in(sf_folder)
                    sf_range  = (f"{_frame_nums(sf_frames)[0]}-{_frame_nums(sf_frames)[1]}"
                                 if sf_frames else "--")
                    child = QTreeWidgetItem(["", sf, sf_range, str(len(sf_frames)),
                                             fps_str, self._res_str({}, sf_frames), ""])
                    child.setData(_COL_VERSION, Qt.UserRole, sf)
                    child.setData(_COL_FRAMES,  Qt.UserRole, sf_folder)
                    child.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    for col in range(7): child.setBackground(col, _COLOR_CHILD)
                    for col in (_COL_FRAMERANGE, _COL_FRAMES, _COL_FPS, _COL_RESOLUTION):
                        child.setTextAlignment(col, Qt.AlignCenter)
                    ver_item.addChild(child)
                    child_folders.append((child, sf_folder))
                ver_item.setExpanded(True)

            # Widgets can only be set once the item is actually inside the tree.
            # A multi-cam version row is just a container folder (no frames of
            # its own) — only its per-camera children are real sequences, so
            # the play button belongs on them, not on that parent row. A
            # single-camera version row IS the sequence, so it gets the button.
            self._ver_tree.addTopLevelItem(ver_item)
            if not is_multi:
                self._ver_tree.setItemWidget(ver_item, _COL_PLAY, self._make_rv_button(folder))
            for child, sf_folder in child_folders:
                self._ver_tree.setItemWidget(child, _COL_PLAY, self._make_rv_button(sf_folder))
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

    # ── Resolution: global render-globals default + per-camera custom ────────

    def _cam_res(self, label: str) -> tuple[int, int]:
        """Resolution a camera blasts at.
        Custom (right-click) sizes always win; otherwise the live render
        globals when the global option is on, else the camera's stored size."""
        if label in self._cam_res_custom and label in self._cam_resolution_overrides:
            return self._cam_resolution_overrides[label]
        rg = self._render_globals_resolution()
        if self._use_rg_chk.isChecked() or label in self._cam_follow_rg:
            return rg
        return self._cam_resolution_overrides.get(label, rg)

    def _set_cam_custom_res(self, item, cam, res: tuple[int, int]) -> None:
        self._cam_resolution_overrides[cam["label"]] = tuple(res)
        self._cam_res_custom.add(cam["label"])
        self._cam_follow_rg.discard(cam["label"])
        self._update_cam_item_text(item, cam)
        self._update_output_preview()

    def _set_rg_label(self, w: int, h: int) -> None:
        self._rg_res_lbl.setText(
            f'<a href="rg" style="color:{_C_DIM}; text-decoration:underline;">'
            f'({w} x {h})</a>')

    def _open_render_settings(self, *_):
        try:
            from .maya_bridge import open_render_settings
            open_render_settings()
        except Exception as exc:
            self._set_status(f"Could not open Render Settings: {exc}", error=True)

    def _watch_render_resolution(self) -> None:
        """Keep the readout + cameras in sync with Render Settings, live."""
        try:
            from .maya_bridge import kill_script_jobs, watch_render_resolution
            kill_script_jobs(self._rg_jobs)
            self._rg_jobs = watch_render_resolution(self._on_render_res_changed)
        except Exception:
            self._rg_jobs = []

    def _on_render_res_changed(self) -> None:
        # width and height fire separately - coalesce into one UI update
        if self._rg_update_pending:
            return
        self._rg_update_pending = True
        QTimer.singleShot(50, self._apply_render_res_change)

    def _apply_render_res_change(self) -> None:
        self._rg_update_pending = False
        try:
            self._update_all_cam_texts()
            self._update_output_preview()
        except RuntimeError:            # window already closed
            pass

    def _clear_all_custom_res(self) -> None:
        self._cam_res_custom.clear()
        rg = self._render_globals_resolution()
        for k in list(self._cam_resolution_overrides):
            self._cam_resolution_overrides[k] = rg
        self._update_all_cam_texts()
        self._update_output_preview()
        self._set_status("All cameras back to the global resolution")

    def _update_all_cam_texts(self) -> None:
        self._cam_list.blockSignals(True)
        for i in range(self._cam_list.count()):
            item = self._cam_list.item(i)
            self._update_cam_item_text(item, item.data(Qt.UserRole))
        self._cam_list.blockSignals(False)
        rw, rh = self._render_globals_resolution()
        self._set_rg_label(rw, rh)

    def _on_use_rg_toggled(self, checked: bool) -> None:
        self._update_all_cam_texts()
        self._update_output_preview()

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
        if self._cam_res_custom:
            menu.addSeparator()
            menu.addAction("Clear all custom resolutions").triggered.connect(
                self._clear_all_custom_res)
        menu.exec_(self._cam_list.viewport().mapToGlobal(pos))

    def _set_cam_res_from_render_globals(self, item, cam):
        # Follows Render Settings live (not a frozen copy)
        self._cam_res_custom.discard(cam["label"])
        self._cam_follow_rg.add(cam["label"])
        self._update_cam_item_text(item, cam)
        self._update_output_preview()
        res = self._render_globals_resolution()
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
                self._set_cam_custom_res(item, cam, dims)
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
        current = self._cam_res(cam["label"])
        dlg = _ResolutionDialog(cam["label"], current, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._set_cam_custom_res(item, cam, dlg.resolution)

    def _update_cam_item_text(self, item, cam):
        w, h = self._cam_res(cam["label"])
        custom = cam["label"] in self._cam_res_custom
        follows = (not custom and not self._use_rg_chk.isChecked()
                   and cam["label"] in self._cam_follow_rg)
        item.setText(cam["label"])
        item.setData(_ROLE_RIGHT_TEXT,
                     f"{w} x {h}" + ("  \u2022 custom" if custom else
                                     "  \u2022 render globals" if follows else ""))
        item.setToolTip("Custom resolution (right-click > Resolution from Render "
                        "Globals to follow Render Settings again)" if custom
                        else "Follows Render Settings")

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
        menu.addSeparator()
        if not is_child:
            menu.addAction(f"Delete {version}...").triggered.connect(
                lambda: self._delete_version(version, folder))
        else:
            menu.addAction(f"Delete {version}...").triggered.connect(
                lambda: self._delete_sequence(version, folder))
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
                d = load(); key = self._ver_key(version)
                if key in d: d.pop(key); save(d)
            self._set_status(f"Deleted {version}")
        except Exception as exc:
            QMessageBox.critical(self, "Delete failed", f"Could not delete:\n\n{exc}"); return
        self._refresh_version_list(); self._update_output_preview()

    def _delete_sequence(self, name: str, folder: str) -> None:
        """Delete a single camera/layer's frames within a multi-cam version.
        The version's notes/meta stay put -- they belong to the version as a
        whole, and its other cameras/layers are unaffected."""
        reply = QMessageBox.warning(
            self, f"Delete {name}?",
            f"This will permanently delete all frames in:\n\n{folder}\n\nThis cannot be undone.  Continue?",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if reply != QMessageBox.Yes: return
        try:
            shutil.rmtree(folder)
            self._set_status(f"Deleted {name}")
        except Exception as exc:
            QMessageBox.critical(self, "Delete failed", f"Could not delete:\n\n{exc}"); return
        self._refresh_version_list(); self._update_output_preview()

    # ══════════════════════════════════════════════════════════════════════════
    # Slots
    # ══════════════════════════════════════════════════════════════════════════

    def _on_anamorphic_toggled(self) -> None:
        self._sync_anamorphic_controls(); self._update_output_preview()

    # ══════════════════════════════════════════════════════════════════════════
    # Output preview
    # ══════════════════════════════════════════════════════════════════════════

    def _update_output_preview(self) -> None:
        if self._tokens is None:
            self._output_path_lbl.setText("--"); return
        fmt = self._sequence_format()
        try:
            self._resolver = build_resolver(
                self._tokens,
                image_format=fmt, frame_padding=FRAME_PADDING,
            )
        except (ResolveError, ValueError) as exc:
            self._output_path_lbl.setText(f"  {exc}"); self._set_blast_enabled(False); return

        if self._layers_mode():
            jobs  = self._layer_jobs()
            lines = []
            for layer, cam in jobs[:4]:
                folder = os.path.join(self._resolver.output_folder, _cam_slug(layer))
                res = self._cam_res(cam["label"])
                lines.append(f"{folder}  [{res[0]}x{res[1]}]")
            if len(jobs) > 4:
                lines.append(f"... and {len(jobs) - 4} more layers")
            self._set_output_paths(lines or [self._resolver.output_folder])
            self._set_blast_enabled(bool(jobs))
            return

        cams = self._blast_cameras()
        if self._is_simple():
            self._simple_cam_lbl.setText(
                f"Camera:  {cams[0]['label']}  (active viewport)" if cams else
                "No camera in the active viewport - click in a viewport, then Refresh scene.")
        lines = []
        for cam in cams:
            slug = _cam_slug(cam["label"])
            folder = os.path.join(self._resolver.output_folder, slug)
            res = self._cam_res(cam["label"])
            tag = f"  [{res[0]}x{res[1]}]"
            lines.append(f"{folder}{tag}")
        movie_fmt = self._movie_format()
        if movie_fmt and cams:
            from .movie import movie_path
            for cam in cams:
                lines.append("Movie: " + movie_path(
                    self._tokens.movies_root, self._resolver.output_basename,
                    _cam_slug(cam["label"]), movie_fmt))
        self._set_output_paths(lines or [self._resolver.output_folder])

        self._set_blast_enabled(bool(cams))

        if self._ana_chk.isChecked() and cams:
            from .maya_bridge import calculate_anamorphic_blast_size
            sq = self._squeeze_combo.currentData()
            cam_res = self._cam_res(cams[0]["label"])
            bw, bh = calculate_anamorphic_blast_size(cam_res[0], cam_res[1], sq)
            self._blast_size_lbl.setText(f"\u2192  blast at {bw} x {bh} px  (PAR {sq}:1)")
        self._update_hero_sub()

    def _set_output_paths(self, lines: list[str]) -> None:
        """Show output paths so they wrap at folder separators (they have no
        spaces) and never force the window wider. Clean paths in tooltip."""
        zw = "\u200b"
        shown = [re.sub(r"([\\/_])", r"\1" + zw, ln) for ln in lines]
        self._output_path_lbl.setText("\n".join(shown))
        self._output_path_lbl.setToolTip("\n".join(lines))

    # ══════════════════════════════════════════════════════════════════════════
    # Playblast
    # ══════════════════════════════════════════════════════════════════════════

    def _blast_settings(self) -> dict:
        anam = self._ana_chk.isChecked()
        return dict(
            fmt     = self._sequence_format(),
            movie   = self._movie_format(),
            prores  = self._prores_profile(),
            burn    = {fid for fid, cb in self._burn_chks.items() if cb.isChecked()},
            anam    = anam,
            squeeze = self._squeeze_combo.currentData() if anam else None,
            start   = self._start_spin.value(),
            end     = self._end_spin.value(),
            use_hud = self._hud_chk.isChecked(),
            note    = self._note_edit.text().strip(),
        )

    def _confirm_overwrite(self, folders: list[str]) -> bool:
        folders_with_frames = [
            f for f in folders
            if os.path.isdir(f) and any(
                os.path.splitext(x)[1].lower() in (".jpg", ".png", ".exr")
                for x in os.listdir(f))
        ]
        if not folders_with_frames:
            return True
        folder_list = "\n".join(folders_with_frames)
        reply = QMessageBox.question(
            self, "Overwrite existing frames?",
            f"The following output folders already contain frames:\n\n"
            f"{folder_list}\n\nExisting files will be overwritten.  Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def _blast_one(self, cam: dict, slug: str, s: dict, fps: float,
                   hud_camera_name: Optional[str] = None,
                   panel: Optional[str] = None, offscreen: bool = True) -> str:
        """One blast through one camera into <version folder>/<slug>/:
        film gate, anamorphic, burn-in HUD, blast, restore -- then the movie
        encode when a movie format is picked. Raises _Stopped when the
        artist stopped it (Esc in Maya, or Stop before the encode)."""
        from .maya_bridge import (
            calculate_anamorphic_blast_size, configure_anamorphic,
            disable_film_gate_pan_zoom, execute_playblast,
            restore_camera_settings, restore_film_gate_pan_zoom,
            setup_hud, teardown_hud,
        )
        deliver_w, deliver_h = self._cam_res(cam["label"])
        cam_w, cam_h = deliver_w, deliver_h
        if s["anam"] and s["squeeze"] is not None:
            cam_w, cam_h = calculate_anamorphic_blast_size(cam_w, cam_h, s["squeeze"])

        cam_folder = os.path.join(self._resolver.output_folder, slug)
        # The per-camera/per-layer subfolder (slug) already disambiguates
        # these frames -- repeating it in the filename too just inflates
        # the path length for no benefit, and can tip long asset/descriptor
        # names over Windows' 260-char path limit ("Failed to open output
        # file" on every frame). The version folder + subfolder name is
        # already a unique, readable location without it.
        stem        = self._resolver.output_basename
        frames_stem = os.path.join(cam_folder, stem)
        burn_in     = s["use_hud"] and bool(s["burn"])
        before      = {f: os.path.getmtime(f) for f in _frames_in(cam_folder)}

        anam_snap = gate_snap = hud_snap = None
        try:
            if self._disable_filmgate_chk.isChecked():
                gate_snap = disable_film_gate_pan_zoom(cam["shape"])
            if s["anam"] and s["squeeze"] is not None:
                anam_snap = configure_anamorphic(cam["shape"], s["squeeze"])
            if burn_in:
                hud_snap = setup_hud(
                    camera_name=hud_camera_name or cam["label"],
                    camera_shape=cam["shape"],
                    width=deliver_w, height=deliver_h, fps=fps,
                    start_frame=s["start"], end_frame=s["end"],
                    fields=s["burn"],
                )
            folder = execute_playblast(
                resolver=self._resolver, camera=cam["transform"],
                width=cam_w, height=cam_h, image_format=s["fmt"],
                frame_padding=FRAME_PADDING, show_ornaments=burn_in,
                start_frame=s["start"], end_frame=s["end"],
                output_path_override=frames_stem,
                panel=panel, offscreen=offscreen,
            )
        finally:
            if hud_snap:
                try: teardown_hud(hud_snap)
                except Exception: pass
            if gate_snap:
                try: restore_film_gate_pan_zoom(cam["shape"], gate_snap)
                except Exception: pass
            if anam_snap:
                try: restore_camera_settings(cam["shape"], anam_snap)
                except Exception: pass

        # Esc in Maya ends a playblast early without an error. Every frame of
        # the range is new or rewritten after a full blast; fewer = stopped.
        written = sum(1 for f in _frames_in(cam_folder)
                      if before.get(f) != os.path.getmtime(f))
        if written < s["end"] - s["start"] + 1:
            raise _Stopped()

        if s["movie"]:
            if self._stop_requested:
                raise _Stopped()
            self._encode_movie(frames_stem, slug, s, fps)
        return folder

    def _encode_movie(self, frames_stem: str, slug: str, s: dict, fps: float) -> None:
        from .movie import MovieCancelled, MovieError, build_args, encode, movie_path
        out = movie_path(self._tokens.movies_root, self._resolver.output_basename,
                         slug, s["movie"])
        self._progress(f"Encoding movie \u2014 {slug}...")
        args = build_args(frames_stem, FORMAT_EXTENSIONS[s["fmt"]], s["start"], fps,
                          out, s["movie"], s["prores"],
                          squeeze=s["squeeze"] if s["anam"] else None)

        def keep_waiting() -> bool:
            QApplication.processEvents()          # keeps Stop clickable
            return not self._stop_requested
        try:
            encode(args, keep_waiting)
        except MovieCancelled:
            raise _Stopped()
        except MovieError as exc:
            raise RuntimeError(f"Movie encode failed for {slug}.\n\n{exc}") from exc
        self._movies.append(out)

    def _after_blast(self, last_folder: Optional[str], s: dict, fps: float,
                     cams: list[dict], layers: Optional[list[str]] = None,
                     stopped: bool = False) -> None:
        # Frames live in the camera/layer subfolder, not the version folder
        blast_folder = last_folder or self._resolver.output_folder
        self._blast_btn.setStyleSheet(_S_BLAST_DONE)

        key = self._ver_key(self._resolver.version)
        if s["note"]:
            notes = self._load_notes(); notes[key] = s["note"]
            self._save_notes(notes)
        try:
            first_res = self._cam_res(cams[0]["label"])
            meta = self._load_meta()
            entry = {
                "frame_range": [s["start"], s["end"]], "fps": fps,
                "resolution": list(first_res), "format": s["fmt"],
                "movie": s["movie"],
                "cameras": [c["label"] for c in cams],
            }
            if layers:
                entry["layers"] = layers
            meta[key] = entry
            self._save_meta(meta)
        except Exception: pass

        what = ", ".join(layers) if layers else ", ".join(c["label"] for c in cams)
        movies = f"  + {len(self._movies)} movie(s)" if self._movies else ""
        if stopped:
            self._set_status(f"Stopped - finished: [{what}]{movies}", error=True)
        else:
            self._set_status(f"Done  [{what}]{movies}  \u2192  {self._resolver.output_folder}")
        self._refresh_version_list()
        if not stopped:
            self._launch_rv(blast_folder)   # fresh blast -> open it in RV automatically

    def _on_playblast(self) -> None:
        if self._tokens is None or self._resolver is None: return
        if self._layers_mode():
            self._start_layer_blast(); return

        cams = self._blast_cameras()
        if not cams:
            QMessageBox.warning(
                self, "No camera",
                "Click in a viewport so fxBlast can use its camera." if self._is_simple()
                else "Please check at least one camera."); return
        # Simple: blast through the same viewport the camera was read from
        panel = None
        if self._is_simple():
            from .maya_bridge import get_active_model_panel
            panel = get_active_model_panel()

        # Always check each camera's subfolder for existing frames
        if not self._confirm_overwrite([
                os.path.join(self._resolver.output_folder, _cam_slug(c["label"]))
                for c in cams]):
            return

        s        = self._blast_settings()
        is_multi = len(cams) > 1

        self._begin_busy(); self._movies = []
        done, last_folder, stopped, failed, fps = [], None, False, False, 24.0
        try:
            from .maya_bridge import get_fps
            fps = get_fps()
            for idx, cam in enumerate(cams):
                if self._stop_requested:
                    stopped = True; break
                self._progress(f"Blasting {idx+1}/{len(cams)} \u2014 {cam['label']}..."
                               if is_multi else f"Blasting \u2014 {cam['label']}...")
                try:
                    last_folder = self._blast_one(cam, _cam_slug(cam["label"]), s, fps,
                                                  panel=panel)
                except _Stopped:
                    stopped = True; break
                done.append(cam)
        except Exception as exc:
            failed = True
            QMessageBox.critical(self, "Playblast failed", f"The playblast did not complete:\n\n{exc}")
            self._set_status(f"Blast failed: {exc}", error=True)
        finally:
            self._end_busy()

        if failed:
            return
        if done:
            self._after_blast(last_folder, s, fps, done, stopped=stopped)
        elif stopped:
            self._set_status("Stopped - nothing finished", error=True)

    # ── Render-layer stepping ─────────────────────────────────────────────────
    # Each layer is switched in its own event-loop step, then blasted after a
    # settle pause, so the viewport has redrawn the new layer (a single
    # blocking loop captured the first layer every time).

    def _start_layer_blast(self) -> None:
        jobs = self._layer_jobs()
        if not jobs:
            QMessageBox.warning(
                self, "No layers",
                "Check at least one render layer. Layers without their own "
                "camera need a camera checked in the Camera section.")
            return
        if not self._confirm_overwrite([
                os.path.join(self._resolver.output_folder, _cam_slug(layer))
                for layer, _ in jobs]):
            return
        from .maya_bridge import (get_active_model_panel, get_current_render_layer,
                                  get_fps, get_panel_camera)
        panel = get_active_model_panel()
        if not panel:
            QMessageBox.warning(self, "No viewport",
                                "Click in the viewport you want to blast through, "
                                "then try again.")
            return
        self._lb = dict(
            jobs=jobs, i=0, panel=panel,
            orig_layer=get_current_render_layer(),
            orig_cam=get_panel_camera(panel),
            s=self._blast_settings(), fps=get_fps(),
            settle=self._settle_spin.value(),
            done=[], errors=[], last=None, stopped=False,
        )
        self._begin_busy(); self._movies = []
        self._set_status(f"Stepping {len(jobs)} layers through {panel}...")
        QTimer.singleShot(0, self._layer_step_switch)

    def _layer_step_switch(self) -> None:
        lb = self._lb
        if self._stop_requested:
            lb["stopped"] = True
        if lb["stopped"] or lb["i"] >= len(lb["jobs"]):
            self._layer_finish(); return
        layer, cam = lb["jobs"][lb["i"]]
        self._progress(f"Blasting layer {lb['i']+1}/{len(lb['jobs'])} \u2014 {layer}...")
        try:
            from .maya_bridge import set_panel_camera, switch_render_layer
            switch_render_layer(layer)
            set_panel_camera(lb["panel"], cam["transform"])
        except Exception as exc:
            lb["errors"].append(f"{layer}: could not switch ({exc})")
            lb["i"] += 1
            QTimer.singleShot(0, self._layer_step_switch); return
        QTimer.singleShot(int(lb["settle"] * 1000), self._layer_step_blast)

    def _layer_step_blast(self) -> None:
        lb = self._lb
        layer, cam = lb["jobs"][lb["i"]]
        try:
            from .maya_bridge import get_current_render_layer
            active = get_current_render_layer()
            if active != layer:
                lb["errors"].append(f"{layer}: active layer was '{active}' at blast time")
            lb["last"] = self._blast_one(
                cam, _cam_slug(layer), lb["s"], lb["fps"],
                hud_camera_name=f"{layer}   {cam['label']}",
                panel=lb["panel"], offscreen=False,
            )
            lb["done"].append((layer, cam))
        except _Stopped:
            lb["stopped"] = True
        except Exception as exc:
            lb["errors"].append(f"{layer}: {exc}")
        lb["i"] += 1
        QTimer.singleShot(50, self._layer_step_switch)

    def _layer_finish(self) -> None:
        lb = self._lb
        try:
            from .maya_bridge import set_panel_camera, switch_render_layer
            switch_render_layer(lb["orig_layer"])
            set_panel_camera(lb["panel"], lb["orig_cam"])
        except Exception:
            pass
        self._end_busy()
        if lb["done"]:
            self._after_blast(lb["last"], lb["s"], lb["fps"],
                              [c for _, c in lb["done"]],
                              layers=[l for l, _ in lb["done"]],
                              stopped=lb["stopped"])
        elif lb["stopped"]:
            self._set_status("Stopped - nothing finished", error=True)
        if lb["errors"]:
            QMessageBox.warning(self, "Render layer blast",
                                "Some layers had problems:\n\n" + "\n".join(lb["errors"]))
            self._set_status(f"{len(lb['errors'])} layer issue(s) - see message", error=True)
        self._lb = None
        self._update_output_preview()

    # ── RV ────────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_sequence_folder(folder: str) -> Optional[str]:
        """
        Return a folder that directly contains image frames.

        If the given folder has images, it is returned unchanged. If it only
        contains subfolders (the camera-subfolder layout), the first subfolder
        holding images is returned. Returns None if no frames are found.
        """
        exts = (".jpg", ".jpeg", ".png", ".exr", ".tif", ".tiff")

        def _has_frames(d: str) -> bool:
            try:
                return any(f.lower().endswith(exts) for f in os.listdir(d))
            except Exception:
                return False

        if not folder or not os.path.isdir(folder):
            return None
        if _has_frames(folder):
            return folder
        try:
            for entry in sorted(os.listdir(folder)):
                sub = os.path.join(folder, entry)
                if os.path.isdir(sub) and _has_frames(sub):
                    return sub
        except Exception:
            pass
        return None

    def _launch_rv(self, folder: Optional[str]) -> None:
        """
        Launch RV with a cleaned environment.

        Maya and Rez set PYTHONPATH / PYTHONHOME / Qt vars to their own
        packages. RV bundles its own Python and Qt, and crashes during
        playback if it inherits these, so they are stripped before launch.

        TODO: switch to the studio Rez package once the package name and
        rez executable path are confirmed, so RV version is managed centrally.
        """
        if not folder:
            self._set_status("No output folder to open.", error=True)
            return

        if not os.path.isfile(RV_PATH):
            QMessageBox.warning(
                self, "RV not found",
                f"RV not found at:\n\n{RV_PATH}\n\n"
                "Set the FX_RV_PATH environment variable to point at your "
                "install, or update the fallback path in config.py."
            )
            return

        # Frames live in camera subfolders. If we were handed a folder with
        # no images directly inside it, drop into the first subfolder that
        # does have images -- RV crashes when given a directory of directories.
        folder = self._resolve_sequence_folder(folder)
        if folder is None:
            self._set_status("No image frames found to play.", error=True)
            return

        try:
            env = os.environ.copy()

            # Strip Python / Qt vars that conflict with RV's bundled runtime
            for var in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP",
                        "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH",
                        "QT_QPA_PLATFORM", "QT_HARFBUZZ",
                        "LD_LIBRARY_PATH", "PYSIDE6_OPTION_PYTHON_ENUM"):
                env.pop(var, None)

            # Strip Rez and Maya package manager vars
            for var in list(env.keys()):
                if var.startswith("REZ_") or var.startswith("MAYA_"):
                    env.pop(var, None)

            subprocess.Popen(
                [RV_PATH, folder],
                env           = env,
                close_fds     = True,
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP,
            )

            # Modal confirmation so the artist knows RV is starting
            msg = QMessageBox(self)
            msg.setWindowTitle("Launching RV")
            msg.setIcon(QMessageBox.Information)
            msg.setText("RV is launching...")
            msg.setInformativeText(f"Loading frames from:\n{folder}")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()

            self._set_status(f"Launched RV  \u2192  {folder}")

        except Exception as exc:
            QMessageBox.critical(
                self, "RV launch failed", f"Could not launch RV:\n\n{exc}"
            )

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

    def _blast_cameras(self) -> list[dict]:
        """Cameras the next blast uses: Simple = the active viewport's
        camera, Advanced = the checked cameras."""
        if not self._is_simple():
            return self._selected_cameras()
        try:
            from .maya_bridge import get_active_viewport_camera
            cam = get_active_viewport_camera()
        except Exception:
            cam = None
        return [cam] if cam else []

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

    # ── Render layer list ─────────────────────────────────────────────────────

    def _on_layers_toggled(self, checked: bool) -> None:
        self._layers_body.setVisible(checked)
        if checked:
            self._refresh_layers()
        self._update_output_preview()

    def _refresh_layers(self) -> None:
        prev = {}
        for i in range(self._layer_list.count()):
            it = self._layer_list.item(i)
            prev[it.data(Qt.UserRole)["layer"]] = it.checkState() == Qt.Checked
        try:
            from .maya_bridge import find_layer_camera, list_render_layers
            layers = list_render_layers()
        except Exception as exc:
            layers = []; self._set_status(f"Could not list render layers: {exc}", error=True)

        self._layer_list.blockSignals(True)
        self._layer_list.clear()
        for layer in layers:
            try:
                cam = find_layer_camera(layer)
            except Exception:
                cam = None
            item = QListWidgetItem()
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            state = Qt.Checked if prev.get(layer, True) else Qt.Unchecked
            item.setCheckState(state)
            item.setData(Qt.UserRole, {"layer": layer, "camera": cam})
            item.setText(f"{layer}   \u2192  {cam['label']}" if cam
                         else f"{layer}   \u2192  (checked camera)")
            item.setToolTip(f"Camera: {cam['label']}" if cam else
                            "No camera found for this layer - uses the first "
                            "camera checked in the Camera section.")
            item.setForeground(QColor(_C_CAM_CHECKED if state == Qt.Checked
                                      else _C_CAM_UNCHECKED))
            self._layer_list.addItem(item)
        self._layer_list.blockSignals(False)
        self._update_output_preview()

    def _on_layer_check_changed(self, item: QListWidgetItem) -> None:
        if item is not None:
            item.setForeground(QColor(_C_CAM_CHECKED if item.checkState() == Qt.Checked
                                      else _C_CAM_UNCHECKED))
        self._update_output_preview()

    def _set_all_layers(self, checked: bool) -> None:
        self._layer_list.blockSignals(True)
        for i in range(self._layer_list.count()):
            item = self._layer_list.item(i)
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            item.setForeground(QColor(_C_CAM_CHECKED if checked else _C_CAM_UNCHECKED))
        self._layer_list.blockSignals(False)
        self._update_output_preview()

    def _layers_mode(self) -> bool:
        chk = getattr(self, "_layers_chk", None)
        return bool(chk and chk.isChecked()) and not self._is_simple()

    def _layer_jobs(self) -> list[tuple[str, dict]]:
        """(layer, camera) for every checked layer that has a camera to use."""
        fallback = self._first_checked_camera()
        jobs = []
        for i in range(self._layer_list.count()):
            item = self._layer_list.item(i)
            if item.checkState() != Qt.Checked:
                continue
            d   = item.data(Qt.UserRole)
            cam = d["camera"] or fallback
            if cam:
                jobs.append((d["layer"], cam))
        return jobs

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
