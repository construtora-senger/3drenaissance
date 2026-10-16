// Building exterior: sky-based lighting (day / sunset) and material tuning for the model.
import {
  CanvasTexture,
  DirectionalLight,
  HemisphereLight,
  MathUtils,
  PMREMGenerator,
  SRGBColorSpace,
  Scene,
  Vector3,
} from "three";
import { Sky } from "three/examples/jsm/objects/Sky.js";
import { materialsOf } from "./assets.js";

export function createExteriorLighting(renderer, scene, { mobile = false } = {}) {
  const focus = new Vector3(38, 30, 55);

  const sun = new DirectionalLight(0xffe0ad, 3);
  sun.position.set(-25, 105, 130);
  sun.target.position.copy(focus);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -57, right: 57, top: 57, bottom: -57, near: 1, far: 230 });
  sun.shadow.bias = -0.00012;
  sun.shadow.normalBias = 0.035;
  sun.shadow.radius = 2;
  scene.add(sun, sun.target);

  const hemisphere = new HemisphereLight(0xcbe4ff, 0xc1b399, 1.35);
  scene.add(hemisphere);

  const fill = new DirectionalLight(0xcbdcff, 0.45);
  fill.position.set(60, 45, -20);
  scene.add(fill);

  // The sky only feeds the environment map; the visible background is a soft gradient.
  const skyScene = new Scene();
  const sky = new Sky();
  sky.scale.setScalar(450000);
  skyScene.add(sky);

  const pmrem = new PMREMGenerator(renderer);
  let environment;
  let background;
  let current;

  function set(mode) {
    const sunset = mode === "sunset";
    if (current === mode) {
      renderer.toneMappingExposure = sunset ? 1.05 : 1;
      return;
    }
    current = mode;

    const uniforms = sky.material.uniforms;
    uniforms.turbidity.value = sunset ? 8 : 3;
    uniforms.rayleigh.value = sunset ? 2 : 1.7;
    uniforms.mieCoefficient.value = 0.005;
    uniforms.mieDirectionalG.value = 0.8;
    const elevation = MathUtils.degToRad(90 - (sunset ? 12 : 36));
    uniforms.sunPosition.value.setFromSphericalCoords(1, elevation, MathUtils.degToRad(230));

    const previous = environment;
    environment = pmrem.fromScene(skyScene, 0.04, 0.1, 100, { size: mobile ? 64 : 256 });
    scene.environment = environment.texture;
    previous?.dispose();
    scene.environmentIntensity = sunset ? 0.65 : 0.8;

    const canvas = document.createElement("canvas");
    canvas.width = 2;
    canvas.height = 256;
    const context = canvas.getContext("2d");
    const gradient = context.createLinearGradient(0, 0, 0, 256);
    gradient.addColorStop(0, sunset ? "#7a90a6" : "#a9c4d5");
    gradient.addColorStop(0.65, sunset ? "#e7c6a5" : "#e5e4dd");
    gradient.addColorStop(1, "#ece8dd");
    context.fillStyle = gradient;
    context.fillRect(0, 0, 2, 256);
    background?.dispose();
    background = new CanvasTexture(canvas);
    background.colorSpace = SRGBColorSpace;
    scene.background = background;

    sun.color.set(sunset ? 0xffc17b : 0xffe3b7);
    sun.intensity = sunset ? 3.1 : 3;
    sun.position.set(sunset ? -40 : -25, sunset ? 65 : 105, sunset ? 150 : 130);
    hemisphere.intensity = sunset ? 1.05 : 1.35;
    fill.intensity = sunset ? 0.38 : 0.45;
    renderer.toneMappingExposure = sunset ? 1.05 : 1;

    // Windows pick up a warm glow at sunset.
    scene.traverse(object => {
      if (!object.isMesh) return;
      for (const material of materialsOf(object)) {
        if (material.userData.kind !== "glass") continue;
        material.emissive.set(sunset ? 0xffb45f : 0xefd4a0);
        material.emissiveIntensity = sunset ? 0.22 : 0.025;
      }
    });
    renderer.shadowMap.needsUpdate = true;
  }

  return {
    set,
    sun,
    dispose() {
      environment?.dispose();
      background?.dispose();
      pmrem.dispose();
      sky.geometry.dispose();
      sky.material.dispose();
    },
  };
}

// Material names in the exterior model encode their kind, e.g. "glass|None|True".
export function prepareExteriorModel(root) {
  root.updateMatrixWorld(true);
  let triangles = 0;
  let drawObjects = 0;
  root.traverse(mesh => {
    if (!mesh.isMesh) return;
    drawObjects++;
    triangles += (mesh.geometry.index?.count || mesh.geometry.attributes.position.count) / 3;
    mesh.matrixAutoUpdate = false;
    for (const material of materialsOf(mesh)) {
      if (material.map) material.map.anisotropy = 2;
      material.forceSinglePass = true;
      const kind = material.userData.kind || material.name.split("|")[0];
      material.userData.kind = kind;
      if (kind === "glass") {
        material.envMapIntensity = 1.25;
        material.depthWrite = false;
        material.roughness = 0.18;
        material.metalness = 0.2;
      } else {
        material.envMapIntensity = kind === "metal" ? 0.85 : 0.35;
      }
      mesh.castShadow = kind !== "glass";
      mesh.receiveShadow = kind !== "glass";
    }
  });
  root.updateMatrixWorld(true);
  root.userData = { triangles, drawObjects, prebatched: true };
  return root;
}
