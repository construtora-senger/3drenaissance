"""Bakes the hall lighting into lightmaps and exports everything the web viewer needs.

Steps (all from build/hall/hall.blend):
  1. join static geometry into a few meshes, add a second UV set ("lightmap") and atlas it
  2. Cycles diffuse bake (direct + indirect, no colour) → denoise → lightmap images
  3. equirectangular capture of the hall for reflections (Radiance .hdr)
  4. walkability grid from downward ray casts → nav.json
  5. glTF export (two UV sets, materials with extras, entrance door leaves as separate nodes)

Usage: bpyenv/bin/python tools/hall/bake_export.py -- <hall.blend> <out_dir> [samples] [lightmap_size]
"""
import faulthandler
import json
import math
import os
import sys

import bpy  # noqa: I001
import numpy as np
from mathutils import Vector

faulthandler.enable()
args = sys.argv[sys.argv.index("--") + 1:]
BLEND, OUT = args[0], args[1]
SAMPLES = int(args[2]) if len(args) > 2 else 128
LM_SIZE = int(args[3]) if len(args) > 3 else 2048
os.makedirs(OUT, exist_ok=True)

X0, Z0, FLOOR = 33.21, 59.04, 4.917
W, FACADE, DOOR = 9.30, 8.00, (3.75, 5.55)


def P(px, py, h=0.0):
    return Vector((X0 + px, -(Z0 + py), FLOOR + h))


bpy.ops.wm.open_mainfile(filepath=BLEND)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.max_bounces = 6
scene.cycles.diffuse_bounces = 4
scene.cycles.glossy_bounces = 2
scene.cycles.transmission_bounces = 4


def objects_in(*names):
    out = []
    for n in names:
        coll = bpy.data.collections.get(n)
        if coll:
            out += [o for o in coll.objects if o.type == "MESH"]
    return out


def kind(obj):
    mats = [m for m in obj.data.materials if m]
    return mats[0].get("kind", "surface") if mats else "surface"


def join(objs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    obj.data.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def set_origin(obj, point):
    """Moves the object origin to `point` (world) without moving the geometry."""
    offset = obj.matrix_world.inverted() @ point
    obj.data.transform(__import__("mathutils").Matrix.Translation(-offset))
    obj.location = point


# ---------------------------------------------------------------------------
# 1. Grouping

# Organic, high-poly furniture would shatter the atlas into thousands of tiny islands: it stays
# out of the lightmap (lit by the hall's reflection probe on the web) but still casts its shadow
# into the bake. Emissive fixtures don't need a lightmap either.
FURNITURE_IBL = {"hall-365", "hall-366", "hall-368", "hall-369", "hall-370", "hall-371"}
glass = [o for o in objects_in("architecture", "decor", "lights", "exterior") if kind(o) == "glass"]
door_l = objects_in("door_l")
door_r = objects_in("door_r")
fixtures = [o for o in objects_in("architecture", "decor", "lights") if kind(o) == "luminaire"]
furniture = [o for o in objects_in("furniture") if o.name in FURNITURE_IBL]
static = [o for o in objects_in("architecture", "decor", "lights", "furniture")
          if kind(o) not in ("glass", "luminaire") and o.name not in FURNITURE_IBL]
exterior = [o for o in objects_in("exterior") if kind(o) != "glass"]

# ray-cast walkability before joining (door leaves are ignored: they open)
NAV_CELL = 0.08


def build_nav():
    for o in door_l + door_r:
        o.hide_set(True)
        o.hide_viewport = True
    depsgraph = bpy.context.evaluated_depsgraph_get()
    px0, px1, py0, py1 = -0.30, W + 0.30, -0.10, 11.20
    cols, rows = int((px1 - px0) / NAV_CELL), int((py1 - py0) / NAV_CELL)
    free = np.zeros((rows, cols), bool)
    for r in range(rows):
        for c in range(cols):
            px, py = px0 + (c + 0.5) * NAV_CELL, py0 + (r + 0.5) * NAV_CELL
            hit, loc, normal, _, obj, _ = scene.ray_cast(depsgraph, P(px, py, 1.95), Vector((0, 0, -1)), distance=3.0)
            free[r, c] = bool(hit) and normal.z > 0.7 and abs(loc.z - FLOOR) < 0.06
    # keep a body radius away from obstacles (and from the grid edge)
    radius = int(round(0.25 / NAV_CELL))
    blocked = ~free
    grown = blocked.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                grown |= np.roll(np.roll(blocked, dy, 0), dx, 1)
    walk = free & ~grown
    walk[:radius, :] = walk[-radius:, :] = False
    walk[:, :radius] = walk[:, -radius:] = False
    for o in door_l + door_r:
        o.hide_set(False)
        o.hide_viewport = False
    nav = {
        "origin": [round(X0 + px0, 3), round(Z0 + py0, 3)],
        "cell": NAV_CELL, "width": cols, "height": rows,
        "rows": ["".join("1" if v else "0" for v in row) for row in walk],
        "floorY": FLOOR, "eyeHeight": 1.65, "crouchHeight": 1.12, "radius": 0.25,
    }
    print("nav walkable m2:", round(walk.sum() * NAV_CELL ** 2, 1), flush=True)
    return nav


nav = build_nav()

# Lightmap texel budget per object (relative); hidden faces are dropped before atlasing.
WEIGHTS = [("ceiling_plenum", 0.12), ("mezz_slab", 0.05), ("ceiling_slats", 0.45), ("beam_", 0.3), ("wall_", 0.6),
           ("frame_", 0.4), ("sill_", 0.6), ("bead_", 0.4), ("spacer_", 0.2), ("rail_", 0.4), ("shaft_block", 0.8),
           ("floor_hall", 1.7), ("central_panel", 1.7), ("column_", 1.3), ("shaft_face", 1.3), ("lining_", 1.1),
           ("hall-365", 1.6), ("hall-366", 1.6), ("hall-368", 1.2), ("hall-369", 1.2), ("hall-370", 1.6), ("hall-371", 1.2),
           ("hall-372", 1.6), ("hall-373", 1.6), ("paving_", 1.0), ("pillar_", 0.6)]
CEIL_H = 5.78


def prepare_for_lightmap(objs):
    import bmesh
    for o in objs:
        weight = next((w for prefix, w in WEIGHTS if o.name.startswith(prefix)), 1.0)
        bm = bmesh.new()
        bm.from_mesh(o.data)
        mw = o.matrix_world
        dead = []
        for f in bm.faces:
            n = (mw.to_3x3() @ f.normal).normalized()
            h = (mw @ f.calc_center_median()).z - FLOOR
            if (n.z > 0.5 and h > CEIL_H + 0.02) or (n.z < -0.5 and h < -0.02):
                dead.append(f)
        bmesh.ops.delete(bm, geom=dead, context="FACES")
        layer = bm.faces.layers.float.get("lm_weight") or bm.faces.layers.float.new("lm_weight")
        for f in bm.faces:
            f[layer] = weight
        bm.to_mesh(o.data)
        bm.free()


prepare_for_lightmap(static + exterior)
static_obj = join(static, "hall_static")
exterior_obj = join(exterior, "hall_exterior")
glass_obj = join(glass, "hall_glass")
fixtures_obj = join(fixtures, "hall_fixtures")
furniture_obj = join(furniture, "hall_furniture")
door_l_obj = join(door_l, "door_l")
door_r_obj = join(door_r, "door_r")
set_origin(door_l_obj, P(DOOR[0], FACADE, 0))
set_origin(door_r_obj, P(DOOR[1], FACADE, 0))


def lightmap_uvs(obj, margin):
    me = obj.data
    uv = me.uv_layers.get("lightmap") or me.uv_layers.new(name="lightmap")
    me.uv_layers.active = uv
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    scene.tool_settings.use_uv_select_sync = True
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=margin, area_weight=1.0, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    # scale every face's islands by its texel weight; packing below rearranges them anyway
    weights = me.attributes.get("lm_weight")
    if weights:
        data = me.uv_layers["lightmap"].data  # layer references go stale across edit-mode toggles
        for poly in me.polygons:
            k = math.sqrt(max(weights.data[poly.index].value, 0.01))
            for li in poly.loop_indices:
                data[li].uv = data[li].uv * k
    bpy.ops.object.mode_set(mode="EDIT")
    scene.tool_settings.use_uv_select_sync = True  # pack every island, not just UV-selected ones
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(margin=margin, rotate=True, scale=True, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    me.uv_layers.active = me.uv_layers[0]
    # glTF export order: UVMap → TEXCOORD_0, lightmap → TEXCOORD_1
    for i, layer in enumerate(me.uv_layers):
        layer.active_render = i == 0


lightmap_uvs(static_obj, 0.004)
lightmap_uvs(exterior_obj, 0.006)


# ---------------------------------------------------------------------------
# 2. Bake

def bake(obj, name, size, samples):
    img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=True)
    for mat in obj.data.materials:
        if not mat:
            continue
        nt = mat.node_tree
        node = nt.nodes.get("__bake__") or nt.nodes.new("ShaderNodeTexImage")
        node.name = "__bake__"
        node.image = img
        nt.nodes.active = node
    obj.data.uv_layers.active = obj.data.uv_layers["lightmap"]
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene.cycles.samples = samples
    scene.render.bake.use_pass_direct = True
    scene.render.bake.use_pass_indirect = True
    scene.render.bake.use_pass_color = False
    scene.render.bake.margin = 8
    scene.render.bake.margin_type = "EXTEND"
    scene.render.bake.target = "IMAGE_TEXTURES"
    print("baking", name, size, samples, flush=True)
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, use_clear=True)
    obj.data.uv_layers.active = obj.data.uv_layers[0]
    for mat in obj.data.materials:
        if mat and mat.node_tree.nodes.get("__bake__"):
            mat.node_tree.nodes.remove(mat.node_tree.nodes["__bake__"])
    return img


def denoise(img):
    """OIDN through the compositor: Image → Denoise → Composite."""
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    src = tree.nodes.new("CompositorNodeImage")
    src.image = img
    dn = tree.nodes.new("CompositorNodeDenoise")
    dn.prefilter = "NONE"
    comp = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(src.outputs["Image"], dn.inputs["Image"])
    tree.links.new(dn.outputs["Image"], comp.inputs["Image"])
    scene.render.resolution_x, scene.render.resolution_y = img.size
    scene.render.resolution_percentage = 100
    if not scene.camera:
        cam = bpy.data.objects.new("bake_cam", bpy.data.cameras.new("bake_cam"))
        scene.collection.objects.link(cam)
        scene.camera = cam
    scene.render.use_compositing = True
    scene.render.use_sequencer = False
    hidden = []
    for o in scene.objects:
        if not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    scene.cycles.samples = 1
    path = os.path.join(OUT, f"{img.name}_dn.exr")
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_depth = "32"
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for o in hidden:
        o.hide_render = False
    scene.use_nodes = False
    out = bpy.data.images.load(path)
    return np.array(out.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], 4)[..., :3]


def encode_srgb(lin):
    lin = np.clip(lin, 0, 1)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(lin, 1 / 2.4) - 0.055)


def save_lightmap(pixels, name):
    """8-bit sRGB PNG of pixels / scale (rows flipped: Blender stores bottom-up). Returns the scale."""
    from PIL import Image

    scale = float(np.percentile(pixels, 99.7)) or 1.0
    enc = encode_srgb(pixels / scale)
    Image.fromarray((np.flipud(enc) * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, f"{name}.png"))
    print("lightmap", name, "scale", round(scale, 4), "mean", round(float(pixels.mean()), 4), flush=True)
    return scale


lm_static = denoise(bake(static_obj, "hall-lightmap", LM_SIZE, SAMPLES))
static_scale = save_lightmap(lm_static, "hall-lightmap")
lm_ext = denoise(bake(exterior_obj, "hall-lightmap-exterior", LM_SIZE // 2, max(32, SAMPLES // 2)))
ext_scale = save_lightmap(lm_ext, "hall-lightmap-exterior")
static_obj["lightmap"] = "hall-lightmap"
static_obj["lightmapIntensity"] = static_scale * math.pi
exterior_obj["lightmap"] = "hall-lightmap-exterior"
exterior_obj["lightmapIntensity"] = ext_scale * math.pi


# ---------------------------------------------------------------------------
# 3. Reflection probe

def capture_env(at, name, width=1024):
    cam_data = bpy.data.cameras.new(name)
    cam_data.type = "PANO"
    cam_data.panorama_type = "EQUIRECTANGULAR"
    cam = bpy.data.objects.new(name, cam_data)
    scene.collection.objects.link(cam)
    cam.location = at
    cam.rotation_euler = (math.pi / 2, 0, -math.pi / 2)  # looks along −Y (into the hall) at the image centre
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = width, width // 2
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    scene.render.use_compositing = False
    scene.render.image_settings.file_format = "HDR"
    scene.render.filepath = os.path.join(OUT, f"{name}.hdr")
    bpy.ops.render.render(write_still=True)
    print("env", name, flush=True)


capture_env(P(4.65, 5.2, 1.6), "hall-env")

# ---------------------------------------------------------------------------
# 4/5. Export

with open(os.path.join(OUT, "nav.json"), "w") as f:
    json.dump(nav, f)
bpy.ops.object.select_all(action="DESELECT")
for o in (static_obj, exterior_obj, glass_obj, fixtures_obj, furniture_obj, door_l_obj, door_r_obj):
    o.select_set(True)
bpy.ops.export_scene.gltf(
    filepath=os.path.join(OUT, "hall.glb"),
    use_selection=True,
    export_format="GLB",
    export_extras=True,
    export_lights=False,
    export_cameras=False,
    export_yup=True,
    export_texcoords=True,
    export_normals=True,
    export_tangents=False,
    export_image_format="JPEG",
    export_image_quality=88,
    export_materials="EXPORT",
)
sys.path.insert(0, os.path.dirname(__file__))
from export_lights import write_lights  # noqa: E402

write_lights(OUT)
print("exported", flush=True)
