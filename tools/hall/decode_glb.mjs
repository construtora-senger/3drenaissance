// Turns the earlier hall model (meshopt-compressed, quantized) into a plain .glb Blender can import.
// The furniture and the street furniture of tools/hall/build_hall.py come from it.
// Usage: git show 37088ee:assets/hall-model-01.bin | gunzip > build/hall/hall-old.glb
//        node tools/hall/decode_glb.mjs build/hall/hall-old.glb build/hall/hall-plain.glb
import { NodeIO } from "@gltf-transform/core";
import { ALL_EXTENSIONS } from "@gltf-transform/extensions";
import { dequantize } from "@gltf-transform/functions";
import { MeshoptDecoder } from "meshoptimizer";

await MeshoptDecoder.ready;
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ "meshopt.decoder": MeshoptDecoder });
const doc = await io.read(process.argv[2]);
for (const ext of doc.getRoot().listExtensionsUsed()) {
  if (ext.extensionName === "EXT_meshopt_compression" || ext.extensionName === "KHR_mesh_quantization") ext.dispose();
}
await doc.transform(dequantize());
await io.write(process.argv[3], doc);
console.log("ok");
