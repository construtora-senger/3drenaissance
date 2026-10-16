// Packs the baked hall (build/hall/out) into the site's assets/ folder.
//   - meshopt + quantised GLB, gzip'd and split into ≤ 8 MB parts (web upload limit is 25 MB)
//   - lightmaps as JPEG (desktop 2048 / mobile 1024) and a small HDR reflection probe
//   - lightweight texture set for phones (same image order as the GLB)
//   - assets/model.json "hall" entry (sizes, hashes, walk grid, viewpoints)
// Usage: node tools/hall/package.mjs   (needs python3 with numpy + Pillow)
import { NodeIO } from "@gltf-transform/core";
import { ALL_EXTENSIONS } from "@gltf-transform/extensions";
import { dedup, meshopt } from "@gltf-transform/functions";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";
import { MeshoptEncoder } from "meshoptimizer";

const SRC = "build/hall/out";
const TMP = "build/hall/pack";
const PART = 8 * 1024 * 1024;
const X0 = 33.21, Z0 = 59.04, FLOOR = 4.917, EYE = 1.65;
const gl = (px, py) => [+(X0 + px).toFixed(3), +(FLOOR + EYE).toFixed(3), +(Z0 + py).toFixed(3)];

rmSync(TMP, { recursive: true, force: true });
mkdirSync(TMP, { recursive: true });
await MeshoptEncoder.ready;
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ "meshopt.encoder": MeshoptEncoder });
const doc = await io.read(join(SRC, "hall.glb"));

// No prune(): it would drop the lightmap UV set (TEXCOORD_1) and the node extras.
await doc.transform(dedup(), meshopt({ encoder: MeshoptEncoder, level: "medium", quantizeTexcoord: 14 }));

// The phone texture set replaces the GLB images one for one, in the order they are written.
const images = doc.getRoot().listTextures().map((t, i) => {
  const ext = t.getMimeType() === "image/png" ? "png" : "jpg";
  const file = join(TMP, `img-${String(i).padStart(3, "0")}.${ext}`);
  writeFileSync(file, t.getImage());
  return file;
});
const glb = Buffer.from(await io.writeBinary(doc));
const gz = gzipSync(glb, { level: 9 });
const parts = [];
for (let i = 0, n = 1; i < gz.length; i += PART, n++) {
  const path = `assets/hall-model-${String(n).padStart(2, "0")}.bin`;
  writeFileSync(path, gz.subarray(i, i + PART));
  parts.push(path);
}
console.log(`hall.glb ${(glb.length / 1e6).toFixed(1)} MB → gzip ${(gz.length / 1e6).toFixed(1)} MB in ${parts.length} part(s)`);

execFileSync("python3", ["tools/hall/pack_images.py", SRC, TMP, ...images], { stdio: "inherit" });

const nav = JSON.parse(readFileSync(join(SRC, "nav.json"), "utf8"));
const config = JSON.parse(readFileSync("assets/model.json", "utf8"));
const [major] = String(config.version).split(".");
config.version = String(Number(major) + 1);
config.hall = {
  bytes: gz.length,
  expandedBytes: glb.length,
  compressed: true,
  parts,
  assetSHA256: createHash("sha256").update(gz).digest("hex"),
  lightmaps: {
    "hall-lightmap": { desktop: "assets/hall-lightmap.jpg", mobile: "assets/hall-lightmap-mobile.jpg" },
    "hall-lightmap-exterior": { desktop: "assets/hall-lightmap-exterior.jpg", mobile: "assets/hall-lightmap-exterior-mobile.jpg" },
  },
  environment: "assets/hall-env.hdr",
  exposure: 1.5, // tone-mapping exposure for the baked evening light
  exteriorBoost: 4, // the outside reads too dark at the bake's night-sky level
  // gl coordinates of the hinge-side jambs; the leaves swing out towards the street
  door: { center: [+(X0 + 4.65).toFixed(3), +(Z0 + 8.0).toFixed(3)], openDistance: 2.0 },
  viewpoints: {
    entrada: { position: gl(4.65, 10.3), yaw: 0 },
    estar: { position: gl(4.65, 7.35), yaw: 0 },
    elevadores: { position: gl(0.95, 2.05), yaw: -0.72 },
  },
  // real-time key lights for the furniture and metals (tools/hall/export_lights.py)
  lights: JSON.parse(readFileSync(join(SRC, "lights.json"), "utf8")),
  nav: { ...nav, spawn: gl(4.65, 10.3) },
  status: "Hall: arquitetura das pranchas A02/A03/A14/A15; acabamentos e decoração do render de referência; iluminação calculada (bake).",
};
writeFileSync("assets/model.json", JSON.stringify(config, null, 1) + "\n");
console.log("assets/model.json updated, version", config.version);
