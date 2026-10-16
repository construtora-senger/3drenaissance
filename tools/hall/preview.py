"""Cycles preview renders of build/hall/hall.blend from a few walk-through viewpoints.

Usage: bpyenv/bin/python tools/hall/preview.py -- <hall.blend> <out_dir> [samples] [view,...]
"""
import math
import os
import sys

import bpy  # noqa: I001
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
BLEND, OUT = args[0], args[1]
SAMPLES = int(args[2]) if len(args) > 2 else 64
ONLY = set(args[3].split(",")) if len(args) > 3 else None

X0, Z0, FLOOR = 33.21, 59.04, 4.917


def P(px, py, h=0.0):
    return Vector((X0 + px, -(Z0 + py), FLOOR + h))


VIEWS = {
    # name: (eye px, py, h), (target px, py, h), focal length mm
    "render_match": ((4.65, 7.55, 1.55), (4.65, 2.8, 2.7), 18),
    "outside": ((4.65, 10.8, 1.60), (4.65, 5.0, 2.2), 20),
    "passage": ((1.10, 6.80, 1.60), (0.9, 0.3, 1.4), 20),
    "lobby": ((6.20, 1.10, 1.60), (1.5, 0.2, 1.3), 18),
    "sofa": ((7.6, 6.6, 1.60), (3.6, 3.3, 1.6), 20),
}

bpy.ops.wm.open_mainfile(filepath=BLEND)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 6
scene.render.resolution_x, scene.render.resolution_y = int(os.environ.get("RES_X", "1200")), int(os.environ.get("RES_Y", "750"))
scene.render.image_settings.file_format = "JPEG"
scene.render.image_settings.quality = 90
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = float(os.environ.get("EXPOSURE", "0"))

cam_data = bpy.data.cameras.new("preview")
cam = bpy.data.objects.new("preview", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
os.makedirs(OUT, exist_ok=True)
for name, (eye, target, lens) in VIEWS.items():
    if ONLY and name not in ONLY:
        continue
    cam.location = P(*eye)
    cam.rotation_euler = (P(*target) - P(*eye)).to_track_quat("-Z", "Y").to_euler()
    cam_data.lens = lens
    cam_data.clip_start = 0.05
    scene.render.filepath = os.path.join(OUT, f"{name}.jpg")
    bpy.ops.render.render(write_still=True)
    print("rendered", name, flush=True)
