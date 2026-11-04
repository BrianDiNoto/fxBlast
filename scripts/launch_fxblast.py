"""
launch_fxblast.py
-----------------
Place in the pipeline scripts/ folder.
This is the only file in the package that references the package name directly.
Add to a shelf button or call from userSetup.py.
"""
from fxBlast.main_window import PlayblastTool
PlayblastTool.launch()
