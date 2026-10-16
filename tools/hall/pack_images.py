"""Image side of tools/hall/package.mjs: lightmaps → JPEG, reflection probe → small HDR,
GLB textures → phone-sized data URIs (assets/hall-mobile-textures.json).

Usage: python3 tools/hall/pack_images.py <bake_out_dir> <tmp_dir> <glb image files...>
"""
import base64
import io
import json
import os
import sys

import numpy as np
from PIL import Image

src, tmp, images = sys.argv[1], sys.argv[2], sys.argv[3:]


def jpeg(img, path, quality=92):
    img.convert("RGB").save(path, "JPEG", quality=quality, subsampling=0, optimize=True)
    print(path, f"{os.path.getsize(path) / 1e3:.0f} kB")


for name in ("hall-lightmap", "hall-lightmap-exterior"):
    lm = Image.open(os.path.join(src, f"{name}.png"))
    jpeg(lm, f"assets/{name}.jpg")
    jpeg(lm.resize((lm.width // 2, lm.height // 2), Image.LANCZOS), f"assets/{name}-mobile.jpg", 90)


# --- Radiance HDR (RGBE) read / write, enough for Blender's output -------------------------
def read_hdr(path):
    with open(path, "rb") as f:
        data = f.read()
    header_end = data.index(b"\n\n") + 2
    line_end = data.index(b"\n", header_end)
    dims = data[header_end:line_end].split()
    h, w = int(dims[1]), int(dims[3])
    pos = line_end + 1
    out = np.zeros((h, w, 4), np.uint8)
    for y in range(h):
        if data[pos] == 2 and data[pos + 1] == 2:  # new-style RLE scanline
            pos += 4
            for c in range(4):
                x = 0
                while x < w:
                    count = data[pos]
                    pos += 1
                    if count > 128:
                        count -= 128
                        out[y, x:x + count, c] = data[pos]
                        pos += 1
                    else:
                        out[y, x:x + count, c] = np.frombuffer(data, np.uint8, count, pos)
                        pos += count
                    x += count
        else:
            out[y] = np.frombuffer(data, np.uint8, w * 4, pos).reshape(w, 4)
            pos += w * 4
    e = out[..., 3].astype(np.int32)
    scale = np.where(e > 0, np.ldexp(1.0, e - 136), 0.0)
    return out[..., :3].astype(np.float32) * scale[..., None]


def write_hdr(path, rgb):
    h, w, _ = rgb.shape
    m = rgb.max(axis=2)
    mant, exp = np.frexp(m)
    scale = np.where(m > 1e-32, mant * 256.0 / np.maximum(m, 1e-32), 0)
    rgbe = np.zeros((h, w, 4), np.uint8)
    rgbe[..., :3] = np.clip(rgb * scale[..., None], 0, 255).astype(np.uint8)
    rgbe[..., 3] = np.where(m > 1e-32, exp + 128, 0).astype(np.uint8)
    with open(path, "wb") as f:
        f.write(b"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n")
        f.write(f"-Y {h} +X {w}\n".encode())
        f.write(rgbe.tobytes())
    print(path, f"{os.path.getsize(path) / 1e3:.0f} kB")


env = read_hdr(os.path.join(src, "hall-env.hdr"))
small = env.reshape(env.shape[0] // 2, 2, env.shape[1] // 2, 2, 3).mean(axis=(1, 3))
write_hdr("assets/hall-env.hdr", small)

# --- phone textures: halve everything above 512 px, keep PNG only where alpha matters --------
mobile = []
for path in images:
    img = Image.open(path)
    w, h = img.size
    if max(w, h) > 512:
        img = img.resize((max(1, w // 2), max(1, h // 2)), Image.LANCZOS)
    buf = io.BytesIO()
    if img.mode in ("RGBA", "LA") or path.endswith(".png") and "transparency" in img.info:
        img.save(buf, "PNG", optimize=True)
        mime = "image/png"
    else:
        img.convert("RGB").save(buf, "JPEG", quality=85, optimize=True)
        mime = "image/jpeg"
    mobile.append({"uri": f"data:{mime};base64,{base64.b64encode(buf.getvalue()).decode()}", "mimeType": mime})
with open("assets/hall-mobile-textures.json", "w") as f:
    json.dump(mobile, f, separators=(",", ":"))
print("assets/hall-mobile-textures.json", len(mobile), "images", f"{os.path.getsize('assets/hall-mobile-textures.json') / 1e6:.1f} MB")
