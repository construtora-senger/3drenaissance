// Entrance hall. Lighting is baked in Blender/Cycles (tools/hall): every static surface carries a
// lightmap on its second UV set, and a reflection probe captured in the hall provides the
// specular part (floor sheen, brass, glass). Furniture and metals are not lightmapped: the
// bake's track spots and pendant are recreated as real-time lights that only they respond to.
import {
  AmbientLight,
  Color,
  EquirectangularReflectionMapping,
  MeshStandardMaterial,
  PMREMGenerator,
  PointLight,
  SRGBColorSpace,
  ShaderChunk,
  SpotLight,
  TextureLoader,
} from "three";
import { HDRLoader } from "three/examples/jsm/loaders/HDRLoader.js";
import { materialsOf } from "./assets.js";

// How much of the reflection probe each finish shows (for unbaked finishes this also scales
// their diffuse ambient).
const REFLECTION = {
  floor: 0.9, paving: 0.35, wood: 0.45, plaster: 0.2, stone: 0.6, facade: 0.25,
  brass: 1.2, bronze: 1.0, frame: 1.0, metal: 0.8, leather: 1.3, linen: 1.8, rug: 0.05, surface: 1.0,
};
// Metals have no diffuse response, so their lightmap texels are black: light them like furniture.
const UNBAKED = new Set(["luminaire", "brass", "bronze", "metal", "frame"]);
// Finishes that read better with some diffuse response than as pure mirrors at night.
const METALNESS = { frame: 0.1, bronze: 0.55 }; // white powder-coated aluminium, satin bronze
// Furniture reused from the earlier model, tuned towards the render: bright bouclé, satin leather.
const FURNITURE = { linen: { brightness: 1.35, roughness: 0.95 }, leather: { roughness: 0.55 } };
// Lights kept on phones: the spots on the sofa, armchairs and sculpture, plus one pendant point.
const MOBILE_LIGHTS = new Set(["spot_0", "spot_2", "spot_4", "spot_6", "spot_8", "spot_9", "pendant_1", "elevator_accent_0", "elevator_accent_1"]);

// The lightmap already holds all diffuse light: drop real-time lights, ambient and the diffuse
// part of the probe from baked materials, keeping only the probe's reflections.
const LIGHTS_BEGIN_BAKED = ShaderChunk.lights_fragment_begin
  .replaceAll("defined( RE_Direct )", "defined( RE_Direct_BAKED_OFF )")
  .replaceAll("defined( RE_Direct_RectArea )", "defined( RE_Direct_BAKED_OFF )")
  .replace("vec3 irradiance = getAmbientLightIrradiance( ambientLightColor );", "vec3 irradiance = vec3( 0.0 );");
const LIGHTS_MAPS_BAKED = ShaderChunk.lights_fragment_maps.replace("iblIrradiance += getIBLIrradiance( geometryNormal );", "");

function useBakedLighting(material, lightMap, intensity) {
  material.lightMap = lightMap;
  material.lightMapIntensity = intensity;
  material.envMapIntensity = REFLECTION[material.userData.kind] ?? 0.35;
  material.onBeforeCompile = shader => {
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <lights_fragment_begin>", LIGHTS_BEGIN_BAKED)
      .replace("#include <lights_fragment_maps>", LIGHTS_MAPS_BAKED);
  };
  material.customProgramCacheKey = () => "baked";
}

function addKeyLights(scene, lights, mobile) {
  for (const def of lights) {
    if (mobile && !MOBILE_LIGHTS.has(def.name)) continue;
    const color = new Color().setRGB(...def.color);
    let light;
    if (def.type === "spot") {
      light = new SpotLight(color, def.intensity, 0, def.angle, def.penumbra, 2);
      light.target.position.fromArray(def.target);
      scene.add(light.target);
    } else {
      light = new PointLight(color, def.intensity, 0, 2);
    }
    light.name = def.name;
    light.position.fromArray(def.position);
    scene.add(light);
  }
  // soft warm fill standing in for the bounce light the probe can't give furniture facing the glass
  scene.add(new AmbientLight(new Color().setRGB(1.0, 0.78, 0.58), 0.25));
}

async function loadLightmaps(hall, mobile, version) {
  const loader = new TextureLoader();
  const entries = await Promise.all(
    Object.entries(hall.lightmaps).map(async ([name, files]) => {
      const texture = await loader.loadAsync(`${mobile ? files.mobile : files.desktop}?v=${encodeURIComponent(version)}`);
      texture.flipY = false; // glTF UV convention
      texture.colorSpace = SRGBColorSpace;
      texture.channel = 1; // TEXCOORD_1
      return [name, texture];
    }),
  );
  return Object.fromEntries(entries);
}

async function loadReflections(renderer, hall, version) {
  const equirect = await new HDRLoader().loadAsync(`${hall.environment}?v=${encodeURIComponent(version)}`);
  equirect.mapping = EquirectangularReflectionMapping;
  const pmrem = new PMREMGenerator(renderer);
  const target = pmrem.fromEquirectangular(equirect);
  equirect.dispose();
  pmrem.dispose();
  return target;
}

export async function createHallScene(renderer, scene, { mobile = false, hall, version }) {
  const [lightmaps, environment] = await Promise.all([loadLightmaps(hall, mobile, version), loadReflections(renderer, hall, version)]);
  scene.background = new Color("#0b1422"); // evening sky through the façade
  scene.environment = environment.texture;
  scene.environmentIntensity = 1;

  const glass = new MeshStandardMaterial({
    color: 0xffffff,
    roughness: 0.04,
    metalness: 0,
    transparent: true,
    opacity: 0.12,
    envMapIntensity: 1.4,
    depthWrite: false,
  });
  glass.userData.kind = "glass";

  let triangles = 0;
  let drawObjects = 0;
  scene.updateMatrixWorld(true);
  scene.traverse(node => {
    const lightmap = lightmaps[node.userData.lightmap];
    if (!node.userData.lightmap && !node.isMesh) return;
    // Materials are shared between nodes in the glTF; each lightmapped node gets its own copies.
    const copies = new Map();
    const meshes = [];
    if (node.isMesh) meshes.push(node);
    else node.traverse(child => child.isMesh && child.parent === node && meshes.push(child));
    for (const mesh of meshes) {
      if (mesh.userData.hallPrepared) continue;
      mesh.userData.hallPrepared = true;
      triangles += (mesh.geometry.index?.count || mesh.geometry.attributes.position.count) / 3;
      drawObjects++;
      mesh.matrixAutoUpdate = node.name.startsWith("door_");
      mesh.castShadow = mesh.receiveShadow = false;
      const materials = materialsOf(mesh).map(material => {
        const kind = material.userData.kind;
        if (kind === "glass") return glass;
        material.forceSinglePass = true;
        if (material.map) material.map.anisotropy = mobile ? 2 : 8;
        if (UNBAKED.has(kind) || !lightmap) {
          material.envMapIntensity = REFLECTION[kind] ?? 0.35;
          if (kind in METALNESS) {
            material.metalnessMap = null;
            material.metalness = METALNESS[kind];
          }
          const tune = FURNITURE[kind];
          if (tune && !material.userData.tuned) {
            material.userData.tuned = true;
            if (tune.brightness) material.color.multiplyScalar(tune.brightness);
            if (tune.roughness) material.roughness = tune.roughness;
          }
          return material;
        }
        if (!copies.has(material)) {
          const copy = material.clone();
          // the exterior is lit by an evening sky the bake keeps very dim: lift it a little
          const boost = node.name === "hall_exterior" ? hall.exteriorBoost ?? 1 : 1;
          useBakedLighting(copy, lightmap, node.userData.lightmapIntensity * boost);
          copies.set(material, copy);
        }
        return copies.get(material);
      });
      mesh.material = Array.isArray(mesh.material) ? materials : materials[0];
    }
  });

  addKeyLights(scene, hall.lights || [], mobile);
  const doors = ["door_l", "door_r"].map(name => scene.getObjectByName(name)).filter(Boolean);
  scene.userData = { triangles, drawObjects, mode: "hall", environment, doors, baked: true };
  return scene;
}

// Leaves swing outwards (towards the street) around their outer jambs.
export function setDoorsOpen(doors, amount) {
  const angle = amount * 1.65;
  for (const door of doors) {
    door.rotation.y = door.name === "door_l" ? -angle : angle;
    door.updateMatrixWorld(true);
  }
}
