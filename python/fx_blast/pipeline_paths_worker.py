"""
pipeline_paths_worker.py -- run by layout.py, NOT imported by Maya.

Runs in the fx_context_utils rez environment (newer Python than Maya 2022),
with the Maya session's FX_* variables. Reads its arguments from the
FXBLAST_ARGS environment variable (JSON) and prints one line:

    FXBLAST_JSON {"frames": {ext: path}, "movies": {codec: path}, "renders_root": path}
"""

import json
import os
import sys


def main():
    args = json.loads(os.environ["FXBLAST_ARGS"])
    out = {"frames": {}, "movies": {}, "renders_root": ""}
    try:
        from fx_context_utils.shot_structure import (
            create_context, shot_structure_from_environment)

        def get(key, **fields):
            ctx = create_context(shot_structure_from_environment())
            ctx.set(component=args["comp"], version_number=args["version"], **fields)
            return ctx[key].get()

        for ext in args["exts"]:
            out["frames"][ext] = get("render_output_frame_file",
                                     ext=ext, frame_number=args["frame"])
        for codec in args["codecs"]:
            out["movies"][codec] = get("quicktime_render_output_file",
                                       ext="mov", video_codec=codec,
                                       color_encoding=args["color"],
                                       resolution=args["resolution"])
        out["renders_root"] = get("renders_root_dir", ext=args["exts"][0])
    except Exception as exc:
        out = {"error": "%s: %s" % (type(exc).__name__, exc)}
    sys.stdout.write("FXBLAST_JSON " + json.dumps(out) + "\n")


if __name__ == "__main__":
    main()
