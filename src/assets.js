// Download, decode and GPU-upload helpers for the glTF models in assets/.
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/examples/jsm/libs/meshopt_decoder.module.js";

export const nextFrame = () => new Promise(requestAnimationFrame);

export function materialsOf(object) {
  if (!object.material) return [];
  return Array.isArray(object.material) ? object.material : [object.material];
}

const MB = 1e6;
const formatMB = bytes => (bytes / MB).toFixed(bytes < 10 * MB ? 1 : 0).replace(".", ",");

// Streams every part of a model manifest into one buffer, reporting real download
// progress as `onProgress(fraction, "12,3 de 37 MB")`.
export async function downloadModel(manifest, version, onProgress) {
  const bytes = new Uint8Array(manifest.bytes);
  let offset = 0;
  const report = () => onProgress(offset / manifest.bytes, `${formatMB(offset)} de ${formatMB(manifest.bytes)} MB`);
  for (const part of manifest.parts) {
    const response = await fetch(`${part}?v=${encodeURIComponent(version)}`);
    if (!response.ok) throw new Error(`Asset response ${response.status} (${part})`);
    if (response.body) {
      const reader = response.body.getReader();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        bytes.set(value, offset);
        offset += value.length;
        report();
      }
    } else {
      const chunk = new Uint8Array(await response.arrayBuffer());
      bytes.set(chunk, offset);
      offset += chunk.length;
      report();
    }
  }
  if (offset !== manifest.bytes) throw new Error("Incomplete model");
  return bytes;
}

export async function decompressModel(manifest, bytes) {
  if (!manifest.compressed) return bytes.buffer;
  if (!window.DecompressionStream) throw new Error("Atualize seu navegador para abrir o modelo.");
  return new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer();
}

// Lightweight JPEG replacements for every image in a model, used on phones and tablets.
export async function fetchMobileTextures(name, version) {
  const response = await fetch(`assets/${name}-mobile-textures.json?v=${encodeURIComponent(version)}`);
  if (!response.ok) throw new Error(`Mobile textures response ${response.status}`);
  return response.json();
}

// GLTFLoader plugin that swaps the embedded images for the mobile ones before parsing.
function mobileTexturesPlugin(images) {
  return parser => ({
    name: "RenaissanceMobileTextures",
    beforeRoot() {
      if (images.length !== (parser.json.images || []).length) throw new Error("Mobile texture count mismatch");
      parser.json.images = parser.json.images.map((image, index) => {
        const { bufferView, uri, mimeType, ...rest } = image;
        return { ...rest, ...images[index] };
      });
    },
  });
}

export async function parseModel(buffer, mobileTextures) {
  const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
  if (mobileTextures) loader.register(mobileTexturesPlugin(await mobileTextures));
  return loader.parseAsync(buffer, "");
}

// Frees the GPU copies of everything in `root`; the CPU data stays, so the scene can be
// uploaded again later.
export function disposeScene(root, renderer) {
  if (!root) return;
  const geometries = new Set();
  const materials = new Set();
  const textures = new Set();
  root.traverse(object => {
    if (object.geometry) geometries.add(object.geometry);
    for (const material of materialsOf(object)) {
      materials.add(material);
      for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
    }
  });
  for (const texture of textures) texture.dispose();
  for (const geometry of geometries) geometry.dispose();
  for (const material of materials) material.dispose();
  renderer.renderLists.dispose();
}

// Uploads textures a few per frame so phones keep responding while the scene warms up.
export async function uploadTextures(scene, renderer, onProgress) {
  const textures = new Set();
  scene.traverse(object => {
    for (const material of materialsOf(object)) {
      for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
    }
  });
  let uploaded = 0;
  for (const texture of textures) {
    if (renderer.getContext().isContextLost()) throw new Error("WebGL context lost");
    renderer.initTexture(texture);
    uploaded++;
    if (uploaded % 4 === 0) {
      onProgress(uploaded / textures.size);
      await nextFrame();
    }
  }
}
