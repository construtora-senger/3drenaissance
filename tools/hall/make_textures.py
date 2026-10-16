"""Generates the seamless PBR textures used by the hall (walnut, floor, plaster, stone, metals).

Every texture is built from periodic noise (random spectra + inverse FFT), so it tiles
without seams. Output: build/hall/textures/<name>_{color,orm,normal}.png
  color  - sRGB base colour
  orm    - R occlusion (1), G roughness, B metallic (glTF layout)
  normal - tangent-space normal map, OpenGL (+Y) convention, as glTF expects

Usage: python3 tools/hall/make_textures.py
"""
import os

import numpy as np
from PIL import Image

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "build", "hall", "textures")
os.makedirs(OUT, exist_ok=True)


def noise(size, beta, seed, stretch=(1.0, 1.0), lo=1.0):
    """Periodic fractal noise, zero mean / unit std. beta = spectral slope (higher = smoother).
    stretch = (sx, sy): frequencies along x / y are penalised by these factors, so sy > 1
    suppresses vertical variation and elongates features vertically."""
    rng = np.random.default_rng(seed)
    h, w = size
    fy = np.fft.fftfreq(h)[:, None] * h
    fx = np.fft.fftfreq(w)[None, :] * w
    k = np.sqrt((fx * stretch[0]) ** 2 + (fy * stretch[1]) ** 2)
    k[0, 0] = 1
    amp = 1.0 / np.maximum(k, lo) ** beta
    amp[0, 0] = 0
    spectrum = amp * np.exp(2j * np.pi * rng.random((h, w)))
    field = np.real(np.fft.ifft2(spectrum))
    return (field - field.mean()) / (field.std() + 1e-9)


def unit(a):
    a = a - a.min()
    return a / (a.max() + 1e-9)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t[..., None]


def hex_rgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


def normal_from_height(height, strength):
    """Wrap-around Sobel so the normal map tiles too."""
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * 0.5
    dy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * 0.5
    # Image rows go down while +V goes up: flip dy for the OpenGL convention.
    n = np.dstack([-dx * strength, dy * strength, np.ones_like(height)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5


def save(name, color, roughness, metallic, height, normal_strength):
    srgb = np.clip(color, 0, 1) ** (1 / 2.2) if False else np.clip(color, 0, 1)
    Image.fromarray((srgb * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, f"{name}_color.png"))
    orm = np.dstack([np.ones_like(roughness), np.clip(roughness, 0.02, 1), np.full_like(roughness, metallic)])
    Image.fromarray((orm * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, f"{name}_orm.png"))
    nrm = normal_from_height(height, normal_strength)
    Image.fromarray((nrm * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, f"{name}_normal.png"))
    print(name, color.shape)


def walnut(size=2048, seed=11):
    """Flat-cut American walnut veneer, grain running along the image height."""
    h = w = size
    x = np.arange(w)[None, :] / w
    warp = noise((h, w), 3.2, seed, stretch=(1, 6)) * 0.022 + noise((h, w), 2.4, seed + 1, stretch=(1, 3)) * 0.006
    rings = (26 * (x + warp)) % 1.0
    fine = (97 * (x + warp * 1.3 + noise((h, w), 2.8, seed + 2, stretch=(1, 5)) * 0.003)) % 1.0
    line = np.exp(-((rings - 0.5) / 0.11) ** 2)
    fine_line = np.exp(-((fine - 0.5) / 0.14) ** 2)
    streak = unit(noise((h, w), 1.6, seed + 3, stretch=(1, 40)))  # pore streaks
    tone = noise((h, w), 2.8, seed + 4, stretch=(1, 10))  # broad colour flitches
    # not every growth line is equally marked: modulate them so the veneer doesn't look ribbed
    weight = 0.25 + 0.75 * smoothstep(-0.6, 1.2, noise((h, w), 2.6, seed + 6, stretch=(1, 4)))
    dark = np.clip(0.26 * line * weight + 0.06 * fine_line + 0.26 * smoothstep(0.55, 1.0, streak) + 0.30 * tone + 0.22, 0, 1)
    light, mid, deep = hex_rgb("#86603f"), hex_rgb("#5b3e28"), hex_rgb("#2f1f14")
    color = lerp(lerp(light, mid, np.clip(dark * 1.4, 0, 1)), deep, np.clip(dark - 0.45, 0, 1) * 1.3)
    color *= (1 + 0.06 * noise((h, w), 2.0, seed + 5))[..., None]
    rough = 0.38 + 0.12 * smoothstep(0.5, 1.0, streak) + 0.04 * line
    height = -0.6 * smoothstep(0.65, 1.0, streak) - 0.25 * fine_line
    save("walnut", color, rough, 0.0, height, 2.2)


def floor_porcelain(size=2048, seed=21, tiles=2, joint_px=4):
    """Light cement-look porcelain, 120 x 120 cm tiles: the image covers 2 x 2 different tiles."""
    h = w = size
    cloud = noise((h, w), 2.4, seed) * 0.6 + noise((h, w), 1.6, seed + 1) * 0.25
    speck = noise((h, w), 0.2, seed + 2)
    t = unit(cloud)
    base, light = hex_rgb("#a9a8a5"), hex_rgb("#c6c5c2")
    color = lerp(base, light, t)
    color *= (1 - 0.05 * smoothstep(1.6, 3.0, speck))[..., None]
    # tiles shifted slightly in tone so the repetition reads as different pieces
    yy, xx = np.mgrid[0:h, 0:w]
    tile_id = (yy * tiles // h) * tiles + (xx * tiles // w)
    shade = np.array([1.0, 0.975, 1.02, 0.99])[tile_id % 4]
    color *= shade[..., None]
    step = w // tiles
    joint = np.zeros((h, w), bool)
    for k in range(tiles + 1):
        joint[:, max(0, k * step - joint_px // 2): k * step + joint_px // 2] = True
        joint[max(0, k * step - joint_px // 2): k * step + joint_px // 2, :] = True
    joint |= np.roll(joint, 0)
    color[joint] = hex_rgb("#8f8e8b")
    rough = 0.30 + 0.06 * unit(noise((h, w), 1.8, seed + 3)) + 0.04 * smoothstep(1.5, 3.0, speck)
    rough[joint] = 0.75
    height = 0.15 * cloud
    height[joint] -= 2.0
    save("floor", color, rough, 0.0, height, 1.6)


def plaster(size=1024, seed=31):
    """Mineral limewash wall, warm light grey with soft trowel clouds."""
    h = w = size
    big = noise((h, w), 2.6, seed)
    mid = noise((h, w), 2.0, seed + 1)
    t = unit(big * 0.7 + mid * 0.3)
    color = lerp(hex_rgb("#c8c4bd"), hex_rgb("#e2dfd9"), t)
    rough = 0.82 + 0.08 * unit(mid)
    height = big * 0.5 + noise((h, w), 1.2, seed + 2) * 0.15
    save("plaster", color, rough, 0.0, height, 1.2)


def granite(size=512, seed=41):
    """Grey speckled granite for the 10 cm skirting (memorial)."""
    h = w = size
    grains = noise((h, w), 0.0, seed)
    dark = smoothstep(0.8, 1.6, grains)
    light = smoothstep(0.9, 1.8, -grains)
    color = np.tile(hex_rgb("#8e8b88"), (h, w, 1))
    color = lerp(color, hex_rgb("#3a3836"), dark)
    color = lerp(color, hex_rgb("#d7d3cd"), light * 0.8)
    rough = 0.25 + 0.1 * dark
    save("granite", color, rough, 0.0, grains * 0.05, 0.5)


def brushed(name, tint, roughness, seed, size=512):
    """Brushed metal: horizontal hairlines in roughness and normal."""
    h = w = size
    hair = noise((h, w), 1.0, seed, stretch=(0.01, 1))
    color = np.tile(hex_rgb(tint), (h, w, 1)) * (1 + 0.04 * hair)[..., None]
    rough = roughness + 0.06 * unit(hair)
    save(name, color, rough, 1.0, hair * 0.3, 0.6)


def oak_slat_end(size=256, seed=51):
    """Matte black for tracks / fixtures (kept as a texture set for uniform material handling)."""
    h = w = size
    n = noise((h, w), 1.0, seed)
    color = np.tile(hex_rgb("#141414"), (h, w, 1)) * (1 + 0.03 * n)[..., None]
    save("black_metal", color, 0.45 + 0.05 * unit(n), 0.8, n * 0.05, 0.3)


if __name__ == "__main__":
    walnut()
    floor_porcelain()
    plaster()
    granite()
    brushed("brass", "#c9a250", 0.22, 61)
    brushed("bronze", "#8a6a48", 0.30, 62)
    brushed("aluminium_white", "#e9e8e4", 0.40, 63)
    oak_slat_end()
