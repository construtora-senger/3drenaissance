"""Writes the hall's spot and point lights (positions in glTF/site coordinates) to lights.json.

The web viewer recreates the track spots and the pendant's points as real-time lights so that
furniture and metals — which are not lightmapped — get the same key light as in the bake.
Intensity is converted like Cycles does: a light of P "watts" has radiant intensity P / 4π.

Usage: bpyenv/bin/python tools/hall/export_lights.py -- <hall.blend> <out_dir>
       (bake_export.py also calls write_lights() at the end of the bake)
"""
import json
import math
import os
import sys

import bpy  # noqa: I001
from mathutils import Vector

KEEP = ("spot_", "pendant_", "elevator_accent_")


def to_gl(v):
    return [round(v.x, 3), round(v.z, 3), round(-v.y, 3)]


def write_lights(out_dir):
    lights = []
    for obj in bpy.data.objects:
        if obj.type != "LIGHT" or not obj.name.startswith(KEEP) or obj.data.type not in ("SPOT", "POINT"):
            continue
        data = obj.data
        entry = {
            "name": obj.name,
            "type": data.type.lower(),
            "position": to_gl(obj.matrix_world.translation),
            "color": [round(c, 4) for c in data.color],
            "intensity": round(data.energy / (4 * math.pi), 4),
        }
        if data.type == "SPOT":
            direction = (obj.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()
            entry["target"] = to_gl(obj.matrix_world.translation + direction * 3.0)
            entry["angle"] = round(data.spot_size / 2, 4)
            entry["penumbra"] = round(data.spot_blend, 3)
        lights.append(entry)
    with open(os.path.join(out_dir, "lights.json"), "w") as f:
        json.dump(lights, f, indent=1)
    print("lights", len(lights), flush=True)


if __name__ == "__main__" and "--" in sys.argv:
    blend, out = sys.argv[sys.argv.index("--") + 1:][:2]
    bpy.ops.wm.open_mainfile(filepath=blend)
    write_lights(out)
