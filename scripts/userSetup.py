"""Startup hook for the Blast tool (fxBlast): registers its shelf button.

Runs at Maya startup (R4.1), so this stays cheap: no heavy imports at module
level, no UI work outside the deferred call (R4.2), and nothing here may
raise -- an exception at this point breaks startup for the artist (R4.7).
"""
import maya.utils


def register_shelf_button():
    try:
        import maya.cmds as cmds  # imported here, not at module level (R4.3)

        shelf_name = "FXN"
        button_name = "launchBlastButton"
        full_path = f"{shelf_name}|{button_name}"

        if not cmds.shelfLayout(shelf_name, exists=True):
            return
        if cmds.shelfButton(full_path, exists=True):
            return

        cmds.shelfButton(
            button_name,
            parent=shelf_name,
            label="fxBlast",
            annotation="fxBlast -- pipeline-aware Maya playblast tool",
            image="fx_blast.png",
            command="import launch_blast; launch_blast.launch()",
            sourceType="python",
        )
    except Exception as exc:
        try:
            import maya.cmds as cmds
            cmds.warning(f"fxBlast: could not register shelf button: {exc}")
        except Exception:
            pass


maya.utils.executeDeferred(register_shelf_button)
