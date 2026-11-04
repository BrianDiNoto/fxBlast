"""Thin launcher for fxBlast, called by its shelf button.

Does what R3.7 allows: import from fx_blast, call it, show UI. No business
logic lives here -- that's all in fx_blast.main_window.

One extra safety step: fxBlast's workspace control deliberately keeps the
same object name (fxBlastWorkspaceControl) across versions, so existing
docked layouts keep working. That means Maya can restore an old, already-
built control on startup *before* this launcher ever runs -- so without
this guard, the shelf button can silently redisplay stale UI instead of
whatever is actually on disk. Deleting it first forces a clean rebuild
every time.
"""


def launch():
    import maya.cmds as cmds
    if cmds.workspaceControl("fxBlastWorkspaceControl", exists=True):
        cmds.deleteUI("fxBlastWorkspaceControl")

    from fx_blast.main_window import PlayblastTool
    PlayblastTool.launch()
