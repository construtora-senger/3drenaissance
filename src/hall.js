// Entrance hall: studio lighting, contact shadows and the brass wall sculpture.
import {
  BufferGeometry,
  CanvasTexture,
  Color,
  DirectionalLight,
  DoubleSide,
  Float32BufferAttribute,
  HemisphereLight,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  PMREMGenerator,
  PlaneGeometry,
  PointLight,
  Scene,
  SpotLight,
} from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { materialsOf } from "./assets.js";

// Hall materials carry their kind in glTF extras (material.userData.kind).
function tuneMaterials(model, mobile) {
  let triangles = 0;
  let drawObjects = 0;
  model.updateMatrixWorld(true);
  model.traverse(mesh => {
    if (!mesh.isMesh) return;
    triangles += (mesh.geometry.index?.count || mesh.geometry.attributes.position.count) / 3;
    drawObjects++;
    mesh.matrixAutoUpdate = false;
    for (const material of materialsOf(mesh)) {
      const kind = material.userData.kind;
      material.forceSinglePass = true;
      if (material.map) material.map.anisotropy = mobile ? 1 : 4;
      mesh.castShadow = !["glass", "luminaire", "mirror"].includes(kind);
      mesh.receiveShadow = kind !== "glass";
      material.envMapIntensity = kind === "brass" || kind === "mirror" ? 1 : 0.45;
      if (kind === "glass") {
        material.depthWrite = false;
        material.side = DoubleSide;
      }
      if (kind === "leather") {
        material.side = DoubleSide;
        material.roughness = 0.62;
      }
      if (kind === "luminaire") material.emissiveIntensity = 0.6;
    }
  });
  return { triangles, drawObjects };
}

function addLights(scene) {
  scene.add(new HemisphereLight(0xffeed3, 0x8d7761, 1));

  const key = new DirectionalLight(0xffead1, 2);
  key.position.set(37.8, 8.5, 69);
  key.target.position.set(37.8, 6, 61.5);
  scene.add(key, key.target);

  const spot = new SpotLight(0xffd49b, 65, 18, Math.PI * 0.37, 0.65, 2);
  spot.position.set(37.8, 10.45, 64.6);
  spot.target.position.set(37.8, 4.9, 63.4);
  spot.castShadow = true;
  spot.shadow.mapSize.set(1024, 1024);
  spot.shadow.camera.near = 0.3;
  spot.shadow.camera.far = 16;
  spot.shadow.bias = -0.00015;
  spot.shadow.normalBias = 0.015;
  scene.add(spot, spot.target);

  const glow = new PointLight(0xffdcaf, 12, 10, 2);
  glow.position.set(37.8, 7.7, 65.8);
  scene.add(glow);
}

// Soft dark blobs under the furniture.
function addContactShadows(scene) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 64;
  const context = canvas.getContext("2d");
  const gradient = context.createRadialGradient(32, 32, 2, 32, 32, 32);
  gradient.addColorStop(0, "rgba(36,23,14,.33)");
  gradient.addColorStop(1, "rgba(36,23,14,0)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, 64, 64);
  const texture = new CanvasTexture(canvas);
  for (const [x, z, width, depth] of [
    [37.8, 63.5, 4, 1.9],
    [39.96, 63.8, 1.3, 1.3],
    [39.96, 64.9, 1.3, 1.3],
  ]) {
    const shadow = new Mesh(
      new PlaneGeometry(width, depth),
      new MeshBasicMaterial({ map: texture, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 }),
    );
    shadow.rotation.x = -Math.PI / 2;
    shadow.position.set(x, 4.95, z);
    scene.add(shadow);
  }
}

// Zig-zag brass ribbons on the main wall: [points along the ribbon, ribbon width].
const SCULPTURE = [
  [[[-0.18, 1.1, 0.03], [-0.35, 0.77, 0.11], [0.02, 0.42, 0.21], [-0.18, 0.06, 0.06], [0.18, -0.35, 0.19], [0.03, -0.7, 0.04], [0.25, -0.97, 0.16]], 0.25],
  [[[0.23, 1.5, 0.08], [0.4, 1.2, 0.18], [0.2, 0.93, 0.06], [0.49, 0.68, 0.17], [0.36, 0.4, 0.04]], 0.18],
  [[[-0.48, 0.95, 0.05], [-0.61, 0.69, 0.17], [-0.4, 0.46, 0.05]], 0.22],
];

function addSculpture(scene) {
  const brass = new MeshStandardMaterial({ color: 0xb9944b, metalness: 0.88, roughness: 0.27, side: DoubleSide });
  for (const [points, width] of SCULPTURE) {
    const positions = [];
    for (let i = 0; i < points.length - 1; i++) {
      const a = points[i];
      const b = points[i + 1];
      const widthA = width * (i % 2 ? 0.65 : 1);
      const widthB = width * (i % 2 ? 1 : 0.65);
      const a1 = [a[0] - widthA / 2, a[1], a[2] - 0.04];
      const a2 = [a[0] + widthA / 2, a[1], a[2] + 0.04];
      const b2 = [b[0] + widthB / 2, b[1], b[2] - 0.04];
      const b1 = [b[0] - widthB / 2, b[1], b[2] + 0.04];
      positions.push(...a1, ...a2, ...b2, ...a1, ...b2, ...b1);
    }
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
    geometry.computeVertexNormals();
    const ribbon = new Mesh(geometry, brass);
    ribbon.position.set(37.86, 8, 61.76);
    ribbon.castShadow = true;
    scene.add(ribbon);
  }
}

export function createHallScene(renderer, model, { mobile = false } = {}) {
  const scene = new Scene();
  scene.background = new Color("#c6bdb0");

  const pmrem = new PMREMGenerator(renderer);
  const room = new RoomEnvironment();
  const environment = pmrem.fromScene(room, 0.04, 0.1, 100, { size: mobile ? 64 : 256 });
  scene.environment = environment.texture;
  scene.environmentIntensity = 0.35;
  room.dispose();
  pmrem.dispose();

  const stats = tuneMaterials(model, mobile);
  scene.add(model);
  addLights(scene);
  addContactShadows(scene);
  addSculpture(scene);

  scene.userData = { ...stats, mode: "hall", environment, decorativeStudy: true };
  return scene;
}
