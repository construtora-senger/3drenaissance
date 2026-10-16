"""Builds the entrance hall in Blender from the architectural drawings.

Architecture follows the plans (A02 térreo, A03 pav. 02, A14/A15 cortes); finishes and
decoration follow the reference render (walnut, ripado ceiling, brass, leather, bouclé).
Furniture meshes are reused from the previous hall model.

Plan coordinates used below (metres, labelled dimensions):
  px: from the inner face of the hall's left wall (seen from the street) to the right, 0 … 9.30
  py: from the elevator-lobby back wall towards the street, 0 … 8.00 (glass façade)
  h : above the hall floor (level −2,30)
They map to the site model as X = 33.21 + px, Y = −(59.04 + py), Z = 4.917 + h (Blender, Z up),
i.e. glTF x = 33.21 + px, z = 59.04 + py, y = 4.917 + h — the same frame as the building model.

Usage: bpyenv/bin/python tools/hall/build_hall.py -- <old-hall-plain.glb> <out.blend>
"""
import math
import os
import sys

import bpy  # noqa: I001 - bpy must be imported before bmesh/mathutils when used as a module
import bmesh
from mathutils import Vector

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TEX = os.path.join(ROOT, "build", "hall", "textures")
OLD_GLB, OUT_BLEND = sys.argv[sys.argv.index("--") + 1:][:2]

bpy.ops.wm.read_factory_settings(use_empty=True)  # before any datablock (materials below) is created

X0, Z0, FLOOR = 33.21, 59.04, 4.917
W = 9.30            # hall width between walls
FACADE = 8.00       # py of the front glass line
LOBBY_CEIL = 2.74   # forro under the mezzanine (corte BB)
MEZZ = 3.24         # pav. 02 floor, +0,94
CEIL = 5.78         # ripado ceiling in the double-height hall
SLAB = 6.48         # pav. 03 slab, +4,18
BAND = (2.00, 7.30, 1.833, 2.650)   # shaft block px0, px1, py0, py1 (mezzanine edge = py1)
SIDE_GLASS = (4.79, 5.83)           # straight glass on the side walls
FRONT = (2.045, 7.255)              # front glass between the diagonal facets
DOOR = (3.75, 5.55)                 # entrance doors (2 x 0.90 x 2.40)


def P(px, py, h=0.0):
    return Vector((X0 + px, -(Z0 + py), FLOOR + h))


# ---------------------------------------------------------------------------
# Materials

def image(name, colorspace):
    path = os.path.join(TEX, name)
    img = bpy.data.images.get(os.path.basename(path)) or bpy.data.images.load(path)
    img.colorspace_settings.name = colorspace
    return img


def textured(name, tex, size, kind, tint=None, rough_scale=1.0, normal=1.0):
    """Principled material fed by build/hall/textures/<tex>_{color,orm,normal}.png.
    `size` = metres covered by one texture tile (used when generating UVs)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    col = nt.nodes.new("ShaderNodeTexImage")
    col.image = image(f"{tex}_color.png", "sRGB")
    orm = nt.nodes.new("ShaderNodeTexImage")
    orm.image = image(f"{tex}_orm.png", "Non-Color")
    nrm = nt.nodes.new("ShaderNodeTexImage")
    nrm.image = image(f"{tex}_normal.png", "Non-Color")
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nmap.inputs["Strength"].default_value = normal
    if tint:
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        mix.inputs["B"].default_value = (*tint, 1)
        nt.links.new(col.outputs["Color"], mix.inputs["A"])
        nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    else:
        nt.links.new(col.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(orm.outputs["Color"], sep.inputs["Color"])
    if rough_scale != 1.0:
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = rough_scale
        nt.links.new(sep.outputs["Green"], mul.inputs[0])
        nt.links.new(mul.outputs[0], bsdf.inputs["Roughness"])
    else:
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    nt.links.new(nrm.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    mat["kind"] = kind
    mat["tex_size"] = size
    return mat


def flat(name, color, kind, roughness=0.5, metallic=0.0, emission=None, strength=0.0, alpha=1.0, transmission=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1)
        bsdf.inputs["Emission Strength"].default_value = strength
    if transmission:
        bsdf.inputs["Transmission Weight"].default_value = transmission
        bsdf.inputs["IOR"].default_value = 1.5
    if alpha < 1:
        bsdf.inputs["Alpha"].default_value = alpha
        mat.surface_render_method = "BLENDED"
    mat["kind"] = kind
    mat["tex_size"] = 1.0
    return mat


def srgb(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


WARM = srgb("#ffe2c0")  # 3000 K-ish
M = {
    "walnut": textured("walnut", "walnut", 1.6, "wood"),
    "slats": textured("walnut_slats", "walnut", 1.6, "wood", tint=(0.92, 0.9, 0.88)),
    "plaster": textured("plaster", "plaster", 2.0, "plaster"),
    "band_plaster": textured("plaster_light", "plaster", 2.0, "plaster", tint=(1.08, 1.06, 1.04)),
    "floor": textured("porcelain", "floor", 2.4, "floor"),
    "paving": textured("paving", "floor", 2.4, "paving", tint=(0.78, 0.77, 0.75), rough_scale=2.2),
    "granite": textured("granite", "granite", 0.6, "stone"),
    "brass": textured("brass", "brass", 0.5, "brass"),
    "bronze": textured("bronze", "bronze", 0.5, "bronze"),
    "alu": textured("aluminium", "aluminium_white", 0.5, "frame"),
    "black": textured("black_metal", "black_metal", 0.5, "metal"),
    "facade": flat("facade_render", srgb("#e7e4de"), "facade", 0.85),
    "plenum": flat("plenum", (0.012, 0.010, 0.009), "surface", 0.9),
    "gesso": flat("forro_gesso", srgb("#efece6"), "plaster", 0.92),
    "glass": flat("glass", (0.92, 0.95, 0.94), "glass", 0.02, transmission=1.0),
    "railing": flat("railing_glass", (0.90, 0.95, 0.93), "glass", 0.03, transmission=1.0),
    "led": flat("led_warm", WARM, "luminaire", 0.5, emission=WARM, strength=2.5),
    "sconce": flat("sconce_diffuser", (1, 0.95, 0.88), "luminaire", 0.4, emission=WARM, strength=12.0),
    "alabaster": flat("alabaster", srgb("#efe8de"), "luminaire", 0.35, emission=srgb("#ffe0bc"), strength=1.6),
    "crystal": flat("crystal", (0.95, 0.95, 0.95), "glass", 0.05, transmission=1.0),
    "button": flat("button", (0.9, 0.9, 0.9), "luminaire", 0.3, emission=srgb("#fff2dc"), strength=6.0),
    "exit": flat("exit_sign", srgb("#1f9d55"), "luminaire", 0.4, emission=srgb("#2fd36f"), strength=2.5),
    "grille": flat("floor_grille", (0.02, 0.02, 0.02), "metal", 0.4, metallic=0.8),
}


# ---------------------------------------------------------------------------
# Geometry helpers (all in plan coordinates)

COLL = {}


def collection(name):
    if name not in COLL:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        COLL[name] = c
    return COLL[name]


def mesh_object(name, verts, faces, mat, coll="architecture"):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.validate()
    me.update()
    obj = bpy.data.objects.new(name, me)
    obj.data.materials.append(mat)
    collection(coll).objects.link(obj)
    return obj


def box(name, px0, px1, py0, py1, h0, h1, mat, coll="architecture"):
    v = [P(px0, py0, h0), P(px1, py0, h0), P(px1, py1, h0), P(px0, py1, h0),
         P(px0, py0, h1), P(px1, py0, h1), P(px1, py1, h1), P(px0, py1, h1)]
    # Plan +py maps to −Y, which mirrors the winding: list faces so normals point outwards.
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    obj = mesh_object(name, v, faces, mat, coll)
    recalc_normals(obj)
    return obj


def prism(name, pts, h0, h1, mat, coll="architecture"):
    """Vertical prism over a plan polygon (px, py) list."""
    n = len(pts)
    v = [P(x, y, h0) for x, y in pts] + [P(x, y, h1) for x, y in pts]
    faces = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    faces += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    obj = mesh_object(name, v, faces, mat, coll)
    recalc_normals(obj)
    return obj


def segment(name, a, b, thickness, h0, h1, mat, offset=0.0, coll="architecture"):
    """Slab of `thickness` along the plan segment a→b (offset shifts it sideways)."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    nx, ny = -dy / length, dx / length
    o0, o1 = offset - thickness / 2, offset + thickness / 2
    pts = [(ax + nx * o0, ay + ny * o0), (bx + nx * o0, by + ny * o0), (bx + nx * o1, by + ny * o1), (ax + nx * o1, ay + ny * o1)]
    return prism(name, pts, h0, h1, mat, coll)


def recalc_normals(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()


def cylinder(name, center, radius, h0, h1, mat, segments=24, coll="architecture"):
    cx, cy = center
    ring = [(cx + radius * math.cos(2 * math.pi * i / segments), cy + radius * math.sin(2 * math.pi * i / segments)) for i in range(segments)]
    return prism(name, ring, h0, h1, mat, coll)


# ---------------------------------------------------------------------------
# Architecture

def build_floors():
    hall = [(0, 0), (W, 0), (W, SIDE_GLASS[1]), (FRONT[1], FACADE), (FRONT[0], FACADE), (0, SIDE_GLASS[1])]
    prism("floor_hall", hall, -0.15, 0.0, M["floor"])
    # pav. 02 hall above the elevator lobby (mezzanine), split around the shaft block
    box("floor_mezzanine_l", 0, BAND[0], 0, BAND[3], MEZZ - 0.02, MEZZ, M["floor"])
    box("floor_mezzanine_r", BAND[1], W, 0, BAND[3], MEZZ - 0.02, MEZZ, M["floor"])
    box("floor_mezzanine_back", BAND[0], BAND[1], 0, BAND[2], MEZZ - 0.02, MEZZ, M["floor"])
    # external hall (acesso social) in front of the façade
    prism("paving_outside", [(-0.20, SIDE_GLASS[1]), (0, SIDE_GLASS[1]), (FRONT[0], FACADE), (FRONT[1], FACADE), (W, SIDE_GLASS[1]),
                             (W + 0.20, SIDE_GLASS[1]), (W + 0.20, 11.30), (-0.20, 11.30)], -0.15, -0.005, M["paving"], "exterior")


def build_walls():
    t = 0.20
    # side walls up to the side glass; inner faces: walnut under the mezzanine, plaster in the hall
    for side, x0, x1 in (("l", -t, 0.0), ("r", W, W + t)):
        box(f"wall_{side}", x0, x1, -0.20, SIDE_GLASS[0], 0, SLAB, M["plaster"])
        inner = x1 if side == "l" else x0
        sgn = 1 if side == "l" else -1
        # walnut lining under and above the mezzanine (passages + pav. 02 hall)
        box(f"lining_passage_{side}", min(inner, inner + sgn * 0.02), max(inner, inner + sgn * 0.02), 0, BAND[3], 0, CEIL, M["walnut"])
        # walnut pilaster near the glass with the linear sconce (render)
        p0, p1 = SIDE_GLASS[0] - 0.55, SIDE_GLASS[0] - 0.05
        box(f"pilaster_{side}", min(inner, inner + sgn * 0.06), max(inner, inner + sgn * 0.06), p0, p1, 0, CEIL, M["walnut"])
        # granite skirting on the plaster stretch
        box(f"skirting_{side}", min(inner, inner + sgn * 0.012), max(inner, inner + sgn * 0.012), BAND[3], p0, 0, 0.10, M["granite"])
        sx = inner + sgn * 0.11
        cylinder(f"sconce_{side}", (sx, (p0 + p1) / 2), 0.028, 1.30, 2.50, M["sconce"], 20, "lights")
        cylinder(f"sconce_cap_lo_{side}", (sx, (p0 + p1) / 2), 0.032, 1.26, 1.30, M["brass"], 20, "lights")
        cylinder(f"sconce_cap_hi_{side}", (sx, (p0 + p1) / 2), 0.032, 2.50, 2.54, M["brass"], 20, "lights")
        box(f"sconce_arm_{side}", min(inner + sgn * 0.06, sx), max(inner + sgn * 0.06, sx), (p0 + p1) / 2 - 0.012, (p0 + p1) / 2 + 0.012, 1.86, 1.94, M["brass"], "lights")
        # floor grille along the side glass (render)
        gx0 = 0.25 if side == "l" else W - 0.40
        box(f"floor_grille_{side}", gx0, gx0 + 0.15, SIDE_GLASS[0] + 0.05, SIDE_GLASS[1] - 0.05, 0.0, 0.004, M["grille"])

    # elevator-lobby back wall with its openings (walnut lining on the lobby side)
    box("wall_back", -0.20, W + 0.20, -0.25, 0.0, 0, SLAB, M["plaster"])
    box("lining_back", 0.0, W, 0.0, 0.02, 0, CEIL, M["walnut"])
    # mezzanine slab edge (fascia) and soffit, both in walnut, split around the shaft block
    for name, x0, x1 in (("l", 0.0, BAND[0]), ("r", BAND[1], W)):
        box(f"mezz_soffit_{name}", x0, x1, 0.0, BAND[3], LOBBY_CEIL - 0.02, LOBBY_CEIL, M["walnut"])
        box(f"mezz_slab_{name}", x0, x1, 0.0, BAND[3], LOBBY_CEIL, MEZZ - 0.02, M["plenum"])
        box(f"mezz_fascia_{name}", x0, x1, BAND[3] - 0.02, BAND[3] + 0.02, LOBBY_CEIL, MEZZ + 0.02, M["walnut"])
        # glass guard-rail h = 1,10 m with a bronze shoe and small lit brass posts
        box(f"rail_shoe_{name}", x0, x1, BAND[3] - 0.09, BAND[3] - 0.02, MEZZ, MEZZ + 0.08, M["bronze"])
        box(f"rail_glass_{name}", x0, x1, BAND[3] - 0.062, BAND[3] - 0.050, MEZZ + 0.08, MEZZ + 1.10, M["railing"])
        n = max(2, round((x1 - x0) / 1.0))
        for i in range(1, n):
            x = x0 + (x1 - x0) * i / n
            cylinder(f"rail_post_{name}{i}", (x, BAND[3] - 0.03), 0.012, MEZZ + 0.08, MEZZ + 0.24, M["brass"], 12, "lights")
            cylinder(f"rail_glow_{name}{i}", (x, BAND[3] - 0.03), 0.010, MEZZ + 0.24, MEZZ + 0.26, M["led"], 12, "lights")
    # elevator corridor behind the shaft block: plain gesso ceiling (memorial 9.1)
    box("mezz_soffit_back", BAND[0], BAND[1], 0.0, BAND[2], LOBBY_CEIL - 0.02, LOBBY_CEIL, M["gesso"])


def build_shaft_block():
    """Shaft/T.Q.P. block between the hall and the lobby: walnut columns, backlit central panel."""
    x0, x1, y0, y1 = BAND
    box("shaft_block", x0, x1, y0, y1, 0, CEIL, M["walnut"])
    box("shaft_face", x0 + 0.60, x1 - 0.60, y1, y1 + 0.01, 0, CEIL, M["band_plaster"])
    # two tall walnut columns at the block ends, stopping short of the ripado with an uplight
    for name, c0, c1 in (("l", x0, x0 + 0.60), ("r", x1 - 0.60, x1)):
        box(f"column_{name}", c0, c1, y1, y1 + 0.55, 0, CEIL - 0.16, M["walnut"])
        box(f"column_uplight_{name}", c0 + 0.08, c1 - 0.08, y1 + 0.08, y1 + 0.47, CEIL - 0.16, CEIL - 0.155, M["led"], "lights")
    # floating central panel carrying the sculpture; LED strips on its edges wash the face behind
    px0, px1 = x0 + 0.86, x1 - 0.86
    box("central_panel", px0, px1, y1 + 0.06, y1 + 0.18, 0.0, CEIL - 0.34, M["walnut"])
    for name, x in (("l", px0 - 0.012), ("r", px1 + 0.002)):
        box(f"panel_led_{name}", x, x + 0.01, y1 + 0.07, y1 + 0.17, 0.05, CEIL - 0.40, M["led"], "lights")


def build_ceiling():
    """Walnut ripado: slats along the room depth with dark gaps, over the whole double height."""
    box("ceiling_plenum", -0.20, W + 0.20, -0.20, FACADE + 0.20, CEIL + 0.045, CEIL + 0.07, M["plenum"])
    slat, gap = 0.065, 0.022
    n = int(W // (slat + gap))
    margin = (W - n * (slat + gap) + gap) / 2
    bm = bmesh.new()
    for i in range(n):
        x0 = margin + i * (slat + gap)
        # slats follow the façade facets: clip their length to the hall outline
        y_end = FACADE
        xc = x0 + slat / 2
        if xc < FRONT[0]:
            y_end = SIDE_GLASS[1] + (FACADE - SIDE_GLASS[1]) * xc / FRONT[0]
        elif xc > FRONT[1]:
            y_end = SIDE_GLASS[1] + (FACADE - SIDE_GLASS[1]) * (W - xc) / (W - FRONT[1])
        verts = [P(x0, 0, CEIL), P(x0 + slat, 0, CEIL), P(x0 + slat, y_end, CEIL), P(x0, y_end, CEIL),
                 P(x0, 0, CEIL + 0.045), P(x0 + slat, 0, CEIL + 0.045), P(x0 + slat, y_end, CEIL + 0.045), P(x0, y_end, CEIL + 0.045)]
        vs = [bm.verts.new(v) for v in verts]
        for f in [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]:
            bm.faces.new([vs[k] for k in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("ceiling_slats")
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("ceiling_slats", me)
    obj.data.materials.append(M["slats"])
    collection("architecture").objects.link(obj)
    # black tracks with spot heads (render)
    for name, x in (("l", 1.45), ("r", W - 1.45)):
        box(f"track_{name}", x - 0.018, x + 0.018, 2.95, 7.40, CEIL - 0.035, CEIL, M["black"], "lights")
    box("track_cross", 1.45, W - 1.45, 2.932, 2.968, CEIL - 0.035, CEIL, M["black"], "lights")


def spot_head(name, px, py, target):
    """Black cylindrical track spot aimed at `target` (px, py, h)."""
    base = P(px, py, CEIL - 0.04)
    aim = (P(*target) - base).normalized()
    bpy.ops.mesh.primitive_cylinder_add(radius=0.035, depth=0.13, vertices=16, location=base + aim * 0.075)
    obj = bpy.context.active_object
    obj.name = name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = Vector((0, 0, -1)).rotation_difference(aim)
    obj.data.materials.append(M["black"])
    for c in obj.users_collection:
        c.objects.unlink(obj)
    collection("lights").objects.link(obj)
    return base + aim * 0.14, aim


def build_lobby_wall():
    """Doors on the elevator-lobby back wall (py = 0): lavabo, elevator 1, stair PCF, elevator 2, reservatórios."""
    face = 0.02
    for name, x0, x1 in (("door_a", 0.08, 0.88), ("door_pcf", 3.52, 4.42), ("door_b", 8.20, 9.00)):
        h = 2.10
        box(f"{name}_leaf", x0, x1, face, face + 0.012, 0.0, h, M["walnut"])
        box(f"{name}_gap_l", x0 - 0.006, x0, face, face + 0.004, 0.0, h + 0.006, M["plenum"])
        box(f"{name}_gap_r", x1, x1 + 0.006, face, face + 0.004, 0.0, h + 0.006, M["plenum"])
        box(f"{name}_gap_t", x0 - 0.006, x1 + 0.006, face, face + 0.004, h, h + 0.006, M["plenum"])
        hx = x1 - 0.10 if name != "door_b" else x0 + 0.08
        box(f"{name}_pull", hx, hx + 0.02, face + 0.012, face + 0.05, 0.85, 1.25, M["black"])
    box("exit_sign", 3.82, 4.12, face, face + 0.03, 2.22, 2.36, M["exit"], "lights")
    for name, cx in (("elevator_1", 2.35), ("elevator_2", 6.95)):
        # bronze portal + two-panel centre-opening doors 0,90 x 2,20 (Sûr / Atlas or similar)
        box(f"{name}_portal_l", cx - 0.62, cx - 0.47, face, face + 0.04, 0.0, 2.38, M["bronze"])
        box(f"{name}_portal_r", cx + 0.47, cx + 0.62, face, face + 0.04, 0.0, 2.38, M["bronze"])
        box(f"{name}_portal_t", cx - 0.62, cx + 0.62, face, face + 0.04, 2.20, 2.38, M["bronze"])
        box(f"{name}_door_l", cx - 0.45, cx - 0.002, face, face + 0.015, 0.0, 2.20, M["bronze"])
        box(f"{name}_door_r", cx + 0.002, cx + 0.45, face, face + 0.015, 0.0, 2.20, M["bronze"])
        box(f"{name}_sill", cx - 0.47, cx + 0.47, face, face + 0.06, 0.0, 0.004, M["bronze"])
        box(f"{name}_panel", cx + 0.74, cx + 0.84, face, face + 0.008, 1.00, 1.24, M["bronze"])
        cylinder(f"{name}_btn_up", (cx + 0.79, face + 0.010), 0.012, 1.14, 1.15, M["button"], 12, "lights")


def build_facade():
    """Faceted glass front: white anodised aluminium (memorial), glass to 5,78 m (A02)."""
    sill = 0.70
    left = [(0.0, SIDE_GLASS[0]), (0.0, SIDE_GLASS[1]), (FRONT[0], FACADE)]
    right = [(W, SIDE_GLASS[0]), (W, SIDE_GLASS[1]), (FRONT[1], FACADE)]
    runs = []
    for pts in (left, right):
        for a, b in zip(pts, pts[1:]):
            runs.append((a, b, sill))
    front = [((FRONT[0], FACADE), (DOOR[0], FACADE), 0.0), ((DOOR[1], FACADE), (FRONT[1], FACADE), 0.0)]
    runs += front
    for i, (a, b, s) in enumerate(runs):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if s > 0:
            segment(f"sill_wall_{i}", a, b, 0.20, 0.0, s, M["plaster"], offset=0.0)
            segment(f"sill_cap_{i}", a, b, 0.24, s, s + 0.03, M["granite"], offset=0.0)
        segment(f"glass_{i}", a, b, 0.012, s + 0.03 if s else 0.0, CEIL, M["glass"])
        # frame: sill/head rails, transom at 2,40, mullions every ~1,6 m
        segment(f"frame_head_{i}", a, b, 0.10, CEIL - 0.06, CEIL, M["alu"])
        segment(f"frame_foot_{i}", a, b, 0.10, (s + 0.03) if s else 0.0, ((s + 0.03) if s else 0.0) + 0.06, M["alu"])
        segment(f"frame_transom_{i}", a, b, 0.10, 2.40, 2.46, M["alu"])
        k = max(1, round(length / 1.6))
        for j in range(k + 1):
            t = j / k
            cx, cy = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            dx, dy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
            p0 = (cx - dx * 0.03, cy - dy * 0.03)
            p1 = (cx + dx * 0.03, cy + dy * 0.03)
            segment(f"frame_mullion_{i}_{j}", p0, p1, 0.10, (s + 0.03) if s else 0.0, CEIL, M["alu"])
    # above the glass: beam band to the pav. 03 slab
    hall_out = [(0, SIDE_GLASS[0]), (0, SIDE_GLASS[1]), (FRONT[0], FACADE), (FRONT[1], FACADE), (W, SIDE_GLASS[1]), (W, SIDE_GLASS[0])]
    for i, (a, b) in enumerate(zip(hall_out, hall_out[1:])):
        segment(f"beam_{i}", a, b, 0.22, CEIL, SLAB + 0.30, M["facade"], offset=0.0)
    # entrance: transom glass over the doors and the two leaves (pivoting on the outer jambs)
    segment("door_transom_glass", (DOOR[0], FACADE), (DOOR[1], FACADE), 0.012, 2.46, CEIL, M["glass"])
    segment("door_transom_frame", (DOOR[0], FACADE), (DOOR[1], FACADE), 0.10, 2.40, 2.46, M["alu"])
    for name, x0, x1 in (("l", DOOR[0], (DOOR[0] + DOOR[1]) / 2), ("r", (DOOR[0] + DOOR[1]) / 2, DOOR[1])):
        coll = f"door_{name}"
        segment(f"entrance_{name}_glass", (x0 + 0.04, FACADE), (x1 - 0.04, FACADE), 0.012, 0.06, 2.36, M["glass"], coll=coll)
        for k, (a0, a1, h0, h1) in enumerate(((x0, x0 + 0.04, 0, 2.40), (x1 - 0.04, x1, 0, 2.40), (x0, x1, 0, 0.06), (x0, x1, 2.34, 2.40))):
            segment(f"entrance_{name}_frame{k}", (a0, FACADE), (a1, FACADE), 0.06, h0, h1, M["alu"], coll=coll)
        hx = x1 - 0.12 if name == "l" else x0 + 0.10
        for side in (-1, 1):
            cylinder(f"entrance_{name}_pull{side}", (hx + 0.01, FACADE + side * 0.06), 0.014, 0.55, 1.75, M["bronze"], 12, coll)
    # structural pillars of the external hall (A02: 3,00 | 40 | 2,50 | 40 | 3,00)
    for name, x0 in (("l", 3.00), ("r", 5.90)):
        box(f"pillar_out_{name}", x0, x0 + 0.40, 8.42, 9.24, 0, SLAB + 0.30, M["facade"], "exterior")


# ---------------------------------------------------------------------------
# Decoration that follows the render

SCULPTURE = [
    [[(-0.18, 1.1, 0.03), (-0.35, 0.77, 0.11), (0.02, 0.42, 0.21), (-0.18, 0.06, 0.06), (0.18, -0.35, 0.19), (0.03, -0.7, 0.04), (0.25, -0.97, 0.16)], 0.25],
    [[(0.23, 1.5, 0.08), (0.4, 1.2, 0.18), (0.2, 0.93, 0.06), (0.49, 0.68, 0.17), (0.36, 0.4, 0.04)], 0.18],
    [[(-0.48, 0.95, 0.05), (-0.61, 0.69, 0.17), (-0.4, 0.46, 0.05)], 0.22],
]


def build_sculpture():
    """Folded brass ribbons on the central panel (render), thickened so they cast shadows."""
    cx, cy, ch = (BAND[0] + BAND[1]) / 2, BAND[3] + 0.18, 2.75
    s = 1.15
    for k, (pts, width) in enumerate(SCULPTURE):
        bm = bmesh.new()
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            wa, wb = width * (0.65 if i % 2 else 1) * s, width * (1 if i % 2 else 0.65) * s
            quad = [(a[0] * s - wa / 2, a[1] * s, a[2] - 0.04), (a[0] * s + wa / 2, a[1] * s, a[2] + 0.04),
                    (b[0] * s + wb / 2, b[1] * s, b[2] - 0.04), (b[0] * s - wb / 2, b[1] * s, b[2] + 0.04)]
            vs = [bm.verts.new(P(cx + x, cy + z, ch + y)) for x, y, z in quad]
            bm.faces.new(vs)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
        me = bpy.data.meshes.new(f"sculpture_{k}")
        bm.to_mesh(me)
        bm.free()
        obj = bpy.data.objects.new(f"sculpture_{k}", me)
        obj.data.materials.append(M["brass"])
        collection("decor").objects.link(obj)
        mod = obj.modifiers.new("thickness", "SOLIDIFY")
        mod.thickness = 0.008
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.modifier_apply(modifier="thickness")
        obj.select_set(False)


def catenary(p0, p1, sag, n):
    """Points of a hanging chain between two (px, py, h) anchors."""
    pts = []
    for i in range(n + 1):
        t = i / n
        x = p0[0] + (p1[0] - p0[0]) * t
        y = p0[1] + (p1[1] - p0[1]) * t
        h = p0[2] + (p1[2] - p0[2]) * t - sag * 4 * t * (1 - t)
        pts.append(Vector((x, y, h)))
    return pts


def build_pendant():
    """Two strands of large alabaster beads with crystal spacers hanging in front of the panel."""
    py = BAND[3] + 0.75
    strands = [((4.00, py, CEIL - 0.25), (5.30, py, CEIL - 0.25), 2.15), ((4.90, py + 0.14, CEIL - 0.25), (5.90, py + 0.14, CEIL - 0.25), 1.45)]
    k = 0
    for p0, p1, sag in strands:
        dense = catenary(p0, p1, sag, 400)
        # walk the curve placing beads every ~0,21 m
        acc, last = 0.0, dense[0]
        spacing = 0.25
        for i in range(1, len(dense)):
            acc += (dense[i] - last).length
            last = dense[i]
            if acc < spacing:
                continue
            acc = 0.0
            tangent = (dense[min(i + 1, len(dense) - 1)] - dense[i - 1]).normalized()
            loc = P(dense[i].x, dense[i].y, dense[i].z)
            bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=1, location=loc)
            bead = bpy.context.active_object
            bead.name = f"bead_{k}"
            bead.scale = (0.085, 0.085, 0.115)
            bead.rotation_mode = "QUATERNION"
            world_tangent = Vector((tangent.x, -tangent.y, tangent.z))
            bead.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(world_tangent)
            bead.data.materials.append(M["alabaster"])
            for c in bead.users_collection:
                c.objects.unlink(bead)
            collection("lights").objects.link(bead)
            bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.024, location=loc + world_tangent * 0.14)
            sp = bpy.context.active_object
            sp.name = f"spacer_{k}"
            sp.data.materials.append(M["crystal"])
            for c in sp.users_collection:
                c.objects.unlink(sp)
            collection("decor").objects.link(sp)
            k += 1
        # suspension cables from the ceiling to both ends of the strand
        for end in (p0, p1):
            cylinder(f"pendant_cable_{k}_{end[0]:.2f}", (end[0], end[1]), 0.002, end[2], CEIL, M["brass"], 6, "decor")
            cylinder(f"pendant_canopy_{k}_{end[0]:.2f}", (end[0], end[1]), 0.06, CEIL - 0.02, CEIL, M["brass"], 20, "decor")


# ---------------------------------------------------------------------------
# Lighting (evening, 2700 K): what the render shows, as Cycles lights for the bake

LIGHT = (1.0, 0.80, 0.60)  # 3000 K


def light(name, kind, at, energy, target=None, size=0.05, size_y=None, spot=None, color=LIGHT):
    data = bpy.data.lights.new(name, kind)
    data.energy = energy
    data.color = color
    if kind == "SPOT":
        data.spot_size = math.radians(spot)
        data.spot_blend = 0.45
        data.shadow_soft_size = size
    elif kind == "POINT":
        data.shadow_soft_size = size
    elif kind == "AREA":
        data.shape = "RECTANGLE"
        data.size = size
        data.size_y = size_y or size
    obj = bpy.data.objects.new(name, data)
    collection("light_sources").objects.link(obj)
    obj.location = at
    if target is not None:
        obj.rotation_euler = (target - at).normalized().to_track_quat("-Z", "Y").to_euler()
    return obj


# track spots: (px, py on the track, aimed at px, py, h)
SPOTS = [
    (1.45, 3.45, (3.55, 2.83, 2.6)), (1.45, 4.85, (2.30, 3.20, 2.2)), (1.45, 6.25, (3.90, 4.40, 0.5)), (1.45, 7.20, (0.07, 4.49, 2.6)),
    (W - 1.45, 3.45, (5.75, 2.83, 2.6)), (W - 1.45, 4.85, (7.00, 3.20, 2.2)), (W - 1.45, 6.25, (6.90, 5.30, 0.5)), (W - 1.45, 7.20, (W - 0.07, 4.49, 2.6)),
    (3.20, 2.95, (4.45, 2.83, 3.4)), (6.10, 2.95, (4.85, 2.83, 2.2)),
]
DOWNLIGHTS = [(1.00, 0.95), (1.00, 2.15), (W - 1.00, 0.95), (W - 1.00, 2.15), (3.00, 0.95), (4.65, 0.95), (6.30, 0.95)]


def build_lights():
    for i, (px, py, tgt) in enumerate(SPOTS):
        tip, aim = spot_head(f"spot_head_{i}", px, py, tgt)
        light(f"spot_{i}", "SPOT", tip, 130.0, target=P(*tgt), size=0.02, spot=40)
    for i, (px, py) in enumerate(DOWNLIGHTS):
        cylinder(f"downlight_{i}", (px, py), 0.045, LOBBY_CEIL - 0.025, LOBBY_CEIL - 0.02, M["led"], 20, "lights")
        light(f"down_{i}", "SPOT", P(px, py, LOBBY_CEIL - 0.03), 38.0, target=P(px, py, 0), size=0.03, spot=80)
    for i, cx in enumerate((2.35, 6.95)):
        light(f"elevator_accent_{i}", "SPOT", P(cx, 1.25, LOBBY_CEIL - 0.03), 30.0, target=P(cx, 0.02, 1.1), size=0.03, spot=55)
    for i, (px, py) in enumerate([(1.0, 1.3), (W - 1.0, 1.3)]):
        light(f"pav02_{i}", "SPOT", P(px, py, CEIL - 0.06), 25.0, target=P(px, py, MEZZ), size=0.03, spot=70)
    # uplights on top of the columns graze the ripado
    for name, c in (("l", BAND[0] + 0.30), ("r", BAND[1] - 0.30)):
        light(f"column_up_{name}", "AREA", P(c, BAND[3] + 0.275, CEIL - 0.15), 70.0, target=P(c, BAND[3] + 0.275, CEIL + 1), size=0.40, size_y=0.40)
    # hidden LED on the panel edges washing the light face behind
    for name, x in (("l", BAND[0] + 0.86 - 0.02), ("r", BAND[1] - 0.86 + 0.02)):
        light(f"panel_wash_{name}", "AREA", P(x, BAND[3] + 0.12, 2.7), 9.0, target=P(x, BAND[3] - 1.0, 2.7), size=0.03, size_y=5.2)
    # wall washers hidden behind the first slat, grazing the plaster
    for name, x, d in (("l", 0.25, -1), ("r", W - 0.25, 1)):
        light(f"wash_{name}", "AREA", P(x, (BAND[3] + SIDE_GLASS[0]) / 2, CEIL - 0.08), 90.0,
              target=P(x + d * 0.6, (BAND[3] + SIDE_GLASS[0]) / 2, 0.0), size=0.05, size_y=SIDE_GLASS[0] - BAND[3])
    # linear sconces
    for name, x, d in (("l", 0.11, 1), ("r", W - 0.11, -1)):
        y = SIDE_GLASS[0] - 0.30
        light(f"sconce_{name}", "AREA", P(x + d * 0.03, y, 1.90), 30.0, target=P(x + d * 2, y, 1.90), size=0.05, size_y=1.2)
    # pendant: the beads are emissive; a few soft points give it real throw
    for i, (px, h) in enumerate([(4.35, 4.2), (4.75, 3.6), (5.45, 4.5)]):
        light(f"pendant_{i}", "POINT", P(px, BAND[3] + 0.82, h), 18.0, size=0.18, color=(1.0, 0.82, 0.62))
    # garden uplights outside
    for i, (px, py) in enumerate([(1.4, 9.6), (W - 1.4, 9.6)]):
        light(f"garden_{i}", "SPOT", P(px, py, 0.05), 35.0, target=P(px, py - 0.3, 3.0), size=0.05, spot=50, color=(1.0, 0.85, 0.65))

    world = bpy.data.worlds.new("dusk")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.018, 0.032, 0.070, 1)
    bg.inputs["Strength"].default_value = 1.0
    bpy.context.scene.world = world


# ---------------------------------------------------------------------------
# Old model: furniture + exterior landscaping

FURNITURE = {"hall-365", "hall-366", "hall-368", "hall-369", "hall-370", "hall-371", "hall-372", "hall-373"}
EXTERIOR = {"hall-158", "hall-159", "hall-160", "hall-161", "hall-162", "hall-163", "hall-164", "hall-165", "hall-166",
            "hall-167", "hall-25", "hall-26", "hall-27", "hall-354", "hall-359"}


def import_old():
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=OLD_GLB)
    for obj in set(bpy.data.objects) - before:
        if obj.type != "MESH" or obj.name not in FURNITURE | EXTERIOR:
            bpy.data.objects.remove(obj, do_unlink=True)
            continue
        for c in obj.users_collection:
            c.objects.unlink(obj)
        collection("furniture" if obj.name in FURNITURE else "exterior").objects.link(obj)
        if obj.name in ("hall-372", "hall-373"):
            obj.location.y -= 0.30  # rug: keep it clear of the columns
            # single-sided rug faces came in facing down: turn them up
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bmesh.ops.reverse_faces(bm, faces=[f for f in bm.faces if f.normal.z < 0])
            bm.to_mesh(obj.data)
            bm.free()
        for mat in obj.data.materials:
            if mat and "kind" not in mat:
                mat["kind"] = "surface"
    for obj in bpy.data.objects:
        if obj.type == "EMPTY":
            bpy.data.objects.remove(obj, do_unlink=True)


# ---------------------------------------------------------------------------
# UVs: world-space box mapping scaled per material (texture tile size in metres)

def box_uvs(obj):
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uv = me.uv_layers[0].data
    mw = obj.matrix_world
    for poly in me.polygons:
        mat = me.materials[poly.material_index] if me.materials else None
        size = float(mat.get("tex_size", 1.0)) if mat else 1.0
        n = (mw.to_3x3() @ poly.normal).normalized()
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in poly.loop_indices:
            co = mw @ me.vertices[me.loops[li].vertex_index].co
            if ax == 2:      # floor / ceiling: u = X, v = Y (slats run along Y)
                u, v = co.x, co.y
            elif ax == 0:    # walls facing ±X
                u, v = co.y, co.z
            else:            # walls facing ±Y
                u, v = co.x, co.z
            uv[li].uv = (u / size, v / size)


def main():
    build_floors()
    build_walls()
    build_shaft_block()
    build_ceiling()
    build_lobby_wall()
    build_facade()
    build_sculpture()
    build_pendant()
    build_lights()
    import_old()
    bpy.context.view_layer.update()
    for coll in ("architecture", "lights", "decor", "exterior") + tuple(f"door_{s}" for s in "lr"):
        for obj in collection(coll).objects:
            if obj.type == "MESH" and not obj.name.startswith("hall-"):
                box_uvs(obj)
    os.makedirs(os.path.dirname(OUT_BLEND), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    counts = {c.name: len(c.objects) for c in bpy.data.collections}
    print("saved", OUT_BLEND, counts)


main()
