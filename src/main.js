// Renaissance Residence — virtual tour.
// Loads the building (assets/model-*.bin), lets visitors orbit it, and on request loads the
// entrance hall (assets/hall-model-*.bin) for a first-person walk.
import {
  ACESFilmicToneMapping,
  Box3,
  Color,
  MathUtils,
  PCFSoftShadowMap,
  PerspectiveCamera,
  SRGBColorSpace,
  Scene,
  Vector3,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import config from "../assets/model.json";
import {
  decompressModel,
  disposeScene,
  downloadModel,
  fetchMobileTextures,
  nextFrame,
  parseModel,
  uploadTextures,
} from "./assets.js";
import { createExteriorLighting, prepareExteriorModel } from "./exterior.js";
import { createHallScene, setDoorsOpen } from "./hall.js";
import { WalkControls } from "./walk-controls.js";

const $ = id => document.getElementById(id);
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
// Phones and tablets get lighter textures, no shadows and a lower pixel budget.
const mobile = matchMedia("(pointer: coarse)").matches;
const DEFAULT_HINT = mobile ? "Um dedo para girar · Dois dedos para aproximar" : "Arraste para girar · Role para aproximar";
const HALL_HINT = mobile
  ? "Use o controle para caminhar · Arraste a cena para olhar"
  : "W A S D ou setas para caminhar · Arraste para olhar · C para agachar";

let renderer, camera, orbit, walk, lighting;
let exteriorScene, exteriorModel, hallScene, hallNav, hallPromise;
let activeScene;
let mode = "exterior"; // "exterior" | "hall"
let lightMode = "day"; // "day" | "sunset"
let quality = "auto"; // "auto" | "light" | "high"
let interactive = false; // false while loading: the render loop idles
let fatal = false;
let needsRender = true;
let tween = null; // camera animation between preset views
let doorOpen = 0; // entrance doors, 0 closed … 1 open
let stageLabel = "Iniciando";
let pixelRatio = 1;
let focusCenter, focusSize, viewDistance;
// Frame timing and adaptive resolution
let lastTime = 0;
let fpsLast = 0;
let fpsFrames = 0;
let fpsElapsed = 0;
let slowStreak = 0;

$("hint").textContent = DEFAULT_HINT;

// ---------------------------------------------------------------------------
// Loading screen, toast and errors

function showToast(text) {
  $("toast").textContent = text;
  $("toast").style.opacity = "1";
  setTimeout(() => ($("toast").style.opacity = "0"), 3000);
}

function setStage(text, percent, detail) {
  stageLabel = text;
  $("loadText").textContent = text;
  if (percent != null) {
    $("bar").style.width = `${Math.max(2, Math.min(100, percent))}%`;
    $("percent").textContent = detail ? `${Math.round(percent)}% · ${detail}` : `${Math.round(percent)}%`;
  }
}

function friendlyError(message) {
  if (/context lost/i.test(message)) return "A memória gráfica foi interrompida. Feche outras abas e tente novamente.";
  if (/creating WebGL context/i.test(message))
    return "Este aparelho ou navegador não conseguiu ativar o 3D. Atualize o navegador ou abra a página no Chrome, Safari ou Edge.";
  if (/^Atualize/.test(message)) return message;
  return "O carregamento não foi concluído. Tente novamente; se persistir, envie os detalhes abaixo.";
}

function showFatalError(error) {
  console.error(error);
  interactive = false;
  fatal = true;
  const stage = stageLabel;
  const message = String(error?.message || error);
  $("loading").classList.remove("done");
  setStage(friendlyError(message));
  $("errorDetails").hidden = false;
  $("errorMessage").textContent = `Versão ${config.version} · ${mobile ? "Celular" : "Computador"}\nEtapa: ${stage}\n${message}`;
  $("percent").textContent = "";
  $("retry").style.display = "block";
}
$("retry").onclick = () => location.reload();

const contextLost = () => fatal || renderer.getContext().isContextLost();

// ---------------------------------------------------------------------------
// Renderer, camera and controls

function computePixelRatio() {
  const budget = quality === "high" ? 4e6 : quality === "light" ? 85e4 : mobile ? 65e4 : 18e5;
  const cap = quality === "high" ? 2 : mobile || quality === "light" ? 1 : 1.5;
  pixelRatio = Math.max(0.5, Math.min(devicePixelRatio, Math.sqrt(budget / (innerWidth * innerHeight)), cap));
  return pixelRatio;
}

// On desktop the building sits slightly right of centre, clear of the side text.
function applyExteriorViewOffset() {
  camera.clearViewOffset();
  if (!mobile) camera.setViewOffset(innerWidth, innerHeight, -Math.min(100, innerWidth * 0.065), 0, innerWidth, innerHeight);
}

// Portrait phones get a taller vertical field of view so the hall keeps at least ~70° across;
// landscape screens keep the original 65°.
function hallFov() {
  const across = MathUtils.degToRad(70);
  const vertical = MathUtils.radToDeg(2 * Math.atan(Math.tan(across / 2) / camera.aspect));
  return MathUtils.clamp(vertical, 65, 85);
}

function initRenderer() {
  renderer = new WebGLRenderer({ antialias: !mobile, alpha: false, powerPreference: mobile ? "default" : "high-performance" });
  renderer.setPixelRatio(computePixelRatio());
  renderer.shadowMap.enabled = !mobile;
  renderer.shadowMap.type = PCFSoftShadowMap;
  renderer.shadowMap.autoUpdate = false;
  renderer.setSize(innerWidth, innerHeight);
  renderer.outputColorSpace = SRGBColorSpace;
  renderer.toneMapping = ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  $("stage").appendChild(renderer.domElement);

  exteriorScene = new Scene();
  exteriorScene.background = new Color("#f3f0e9");
  activeScene = exteriorScene;

  camera = new PerspectiveCamera(36, innerWidth / innerHeight, 0.1, 3000);

  orbit = new OrbitControls(camera, renderer.domElement);
  Object.assign(orbit, {
    enableDamping: true,
    dampingFactor: 0.08,
    maxPolarAngle: Math.PI * 0.495,
    minPolarAngle: 0.04,
    rotateSpeed: 0.55,
    zoomSpeed: 0.65,
    panSpeed: 0.65,
    autoRotateSpeed: 0.45,
  });
  orbit.addEventListener("start", () => {
    tween = null;
    orbit.autoRotate = false;
    $("rotate").setAttribute("aria-pressed", "false");
    document.querySelectorAll("[data-view]").forEach(button => button.classList.remove("active"));
  });

  const eyeLabel = height => `Olhar a ${height.toFixed(2).replace(".", ",")} m`;
  walk = new WalkControls(camera, renderer.domElement, $("joystick"), $("joystickKnob"), crouched => {
    $("crouch").setAttribute("aria-pressed", String(crouched));
    $("crouch").textContent = crouched ? "Levantar" : "Agachar";
    $("eyeLevel").textContent = eyeLabel(crouched ? config.hall.nav.crouchHeight : config.hall.nav.eyeHeight);
  });

  lighting = createExteriorLighting(renderer, exteriorScene, { mobile });

  renderer.domElement.addEventListener("webglcontextlost", event => {
    event.preventDefault();
    interactive = false;
    showFatalError(new Error("WebGL context lost"));
  });

  addEventListener("resize", () => {
    camera.aspect = innerWidth / innerHeight;
    updateViewDistance();
    if (mode === "exterior") applyExteriorViewOffset();
    else camera.fov = hallFov();
    camera.updateProjectionMatrix();
    renderer.setPixelRatio(computePixelRatio());
    renderer.setSize(innerWidth, innerHeight);
    needsRender = true;
  });

  addEventListener("keydown", event => {
    if (event.key === "Escape") {
      closeReferences();
      closeHelp();
      document.body.classList.remove("clean");
    }
    if (!interactive || mode !== "exterior" || /INPUT|SELECT|TEXTAREA/.test(event.target.tagName)) return;
    if (event.key === "+" || event.key === "=") zoomBy(0.82);
    if (event.key === "-") zoomBy(1.22);
    if (event.key === "Home") goToView("overview");
  });

  requestAnimationFrame(frame);
}

// Renders only when something changed, and lowers the resolution if the device struggles.
function frame(time) {
  requestAnimationFrame(frame);
  if (document.hidden || !interactive) return;
  // Capped so a slow frame doesn't teleport the walker; collisions sub-step anyway.
  const dt = lastTime ? Math.min(0.1, (time - lastTime) / 1000) : 1 / 60;
  lastTime = time;

  const animating = !!tween;
  if (tween) {
    const t = Math.min(1, (time - tween.start) / tween.duration);
    const eased = t * t * (3 - 2 * t);
    camera.position.lerpVectors(tween.from, tween.to, eased);
    orbit.target.lerpVectors(tween.targetFrom, tween.targetTo, eased);
    if (t >= 1) tween = null;
  }

  let moved;
  if (mode === "hall") {
    const walked = walk.update(dt);
    moved = updateDoors(dt) || walked;
  } else {
    moved = orbit.update(dt);
  }
  if (!(moved || animating || needsRender || (mode === "exterior" && orbit.autoRotate))) {
    fpsLast = 0;
    return;
  }
  try {
    renderer.render(activeScene, camera);
  } catch (error) {
    showFatalError(error);
    return;
  }
  needsRender = false;

  if (fpsLast && time - fpsLast < 250) {
    fpsElapsed += time - fpsLast;
    fpsFrames++;
    if (fpsElapsed > 1100) {
      const fps = Math.round((fpsFrames * 1000) / fpsElapsed);
      $("fpsValue").textContent = `${fps} FPS`;
      if (quality === "auto" && fps < 40) {
        slowStreak++;
        if (slowStreak >= 2 && pixelRatio > 0.65) {
          pixelRatio = Math.max(0.65, pixelRatio * 0.82);
          renderer.setPixelRatio(pixelRatio);
          renderer.setSize(innerWidth, innerHeight);
          needsRender = true;
          slowStreak = 0;
        }
      } else {
        slowStreak = 0;
      }
      fpsFrames = 0;
      fpsElapsed = 0;
    }
  }
  fpsLast = time;
}

// The entrance doors swing open as the visitor approaches them.
function updateDoors(dt) {
  const doors = hallScene?.userData.doors;
  if (!doors?.length) return false;
  const [cx, cz] = config.hall.door.center;
  const target = Math.hypot(camera.position.x - cx, camera.position.z - cz) < config.hall.door.openDistance ? 1 : 0;
  if (doorOpen === target) return false;
  doorOpen += (target - doorOpen) * Math.min(1, dt * 3.5);
  if (Math.abs(target - doorOpen) < 0.002) doorOpen = target;
  setDoorsOpen(doors, doorOpen);
  return true;
}

function goToViewpoint(name) {
  const view = config.hall.viewpoints[name];
  if (!view || mode !== "hall" || !interactive) return;
  walk.goTo(view.position, view.yaw);
  needsRender = true;
}

function resetFps() {
  fpsFrames = fpsElapsed = fpsLast = 0;
  $("fpsValue").textContent = "—";
}

// Compiles shaders / uploads textures before the loading screen goes away.
async function warmUp(scene) {
  if (mobile) await uploadTextures(scene, renderer, p => setStage("Preparando a visualização leve.", 89 + p * 8));
  else if (renderer.compileAsync) await renderer.compileAsync(scene, camera);
  if (contextLost()) throw new Error("WebGL context lost");
  renderer.shadowMap.needsUpdate = true;
  renderer.render(scene, camera);
  if (contextLost()) throw new Error("WebGL context lost");
}

// Download (progress up to 78%) and gunzip a model; returns the .glb ArrayBuffer.
async function loadModel(manifest, label, startPercent) {
  const bytes = await downloadModel(manifest, config.version, (fraction, detail) =>
    setStage(label, startPercent + fraction * (78 - startPercent), detail),
  );
  setStage("Abrindo o modelo 3D.", 82);
  return decompressModel(manifest, bytes);
}

function mobileTextures(name) {
  if (!mobile) return null;
  const promise = fetchMobileTextures(name, config.version);
  promise.catch(() => {}); // surfaced when parseModel awaits it
  return promise;
}

// ---------------------------------------------------------------------------
// Exterior views

function viewPose(view) {
  const front = new Vector3(...(config.frontDirection || [0, 0, 1]));
  front.y = 0;
  front.normalize();
  const side = new Vector3(front.z, 0, -front.x);
  const target = focusCenter.clone();
  let direction;
  if (view === "front") direction = front.clone().add(new Vector3(0, 0.12, 0));
  else if (view === "rear") direction = front.clone().multiplyScalar(-1).addScaledVector(side, -0.35).add(new Vector3(0, 0.22, 0));
  else if (view === "aerial") direction = front.clone().multiplyScalar(0.65).addScaledVector(side, 0.45).add(new Vector3(0, 1.15, 0));
  else direction = front.clone().addScaledVector(side, 0.42).add(new Vector3(0, 0.29, 0));
  direction.normalize();
  return { position: target.clone().addScaledVector(direction, viewDistance * (view === "aerial" ? 0.94 : 1)), target };
}

function goToView(view, instant = false) {
  if (!interactive || mode !== "exterior") return;
  orbit.autoRotate = false;
  $("rotate").setAttribute("aria-pressed", "false");
  const { position, target } = viewPose(view);
  needsRender = true;
  if (instant || reducedMotion) {
    camera.position.copy(position);
    orbit.target.copy(target);
    tween = null;
  } else {
    tween = {
      from: camera.position.clone(),
      to: position,
      targetFrom: orbit.target.clone(),
      targetTo: target,
      start: performance.now(),
      duration: 850,
    };
  }
  document.querySelectorAll("[data-view]").forEach(button => button.classList.toggle("active", button.dataset.view === view));
}

function zoomBy(factor) {
  if (!interactive || mode !== "exterior") return;
  tween = null;
  const offset = camera.position.clone().sub(orbit.target);
  offset.multiplyScalar(factor);
  offset.setLength(MathUtils.clamp(offset.length(), orbit.minDistance, orbit.maxDistance));
  camera.position.copy(orbit.target).add(offset);
  needsRender = true;
}

// Preset views stand far enough back for the whole building to fit both vertically and
// horizontally at the current screen shape (recomputed when a phone is rotated).
function updateViewDistance() {
  if (!focusSize) return;
  const vertical = MathUtils.degToRad(36);
  const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * (innerWidth / innerHeight));
  viewDistance =
    Math.max(focusSize.y / 2 / Math.tan(vertical / 2), Math.max(focusSize.x, focusSize.z) / 2 / Math.tan(horizontal / 2)) * 1.28 +
    focusSize.z * 0.35;
  orbit.maxDistance = viewDistance * 3;
}

function resetExteriorCamera() {
  camera.fov = 36;
  camera.near = Math.max(0.03, focusSize.length() / 5000);
  camera.far = viewDistance * 10;
  applyExteriorViewOffset();
  camera.updateProjectionMatrix();
  lighting.set(lightMode);
  goToView("overview", true);
  orbit.update();
  renderer.shadowMap.needsUpdate = true;
  needsRender = true;
}

// ---------------------------------------------------------------------------
// Hall

// Desktop visitors usually have bandwidth to spare: fetch the hall in the background so
// "Entrar no hall" opens quickly. Phones only download it when asked.
function prefetchHall() {
  if (mobile || hallPromise || navigator.connection?.saveData) return;
  for (const part of config.hall.parts) {
    const link = document.createElement("link");
    link.rel = "prefetch";
    link.href = `${part}?v=${encodeURIComponent(config.version)}`;
    document.head.appendChild(link);
  }
}

async function enterHall() {
  if (!interactive || mode === "hall") return;
  closeHelp();
  closeReferences();
  orbit.autoRotate = false;
  tween = null;
  $("enterHall").disabled = true;
  interactive = false;
  $("loading").classList.remove("done");
  setStage("Preparando sua visita ao hall.", 8);
  try {
    // Phones can't hold both scenes on the GPU; the exterior is re-uploaded on the way back.
    if (mobile) disposeScene(exteriorScene, renderer);
    hallPromise ||= (async () => {
      const textures = mobileTextures("hall");
      const buffer = await loadModel(config.hall, "Carregando o hall de entrada.", 8);
      setStage("Preparando os acabamentos.", 88);
      const gltf = await parseModel(buffer, textures);
      hallNav = config.hall.nav;
      return createHallScene(renderer, gltf.scene, { mobile, hall: config.hall, version: config.version });
    })();
    hallScene = await hallPromise;

    activeScene = hallScene;
    mode = "hall";
    orbit.enabled = false;
    camera.clearViewOffset();
    camera.fov = hallFov();
    camera.near = 0.035;
    camera.far = 180;
    camera.updateProjectionMatrix();
    walk.enter(hallNav);
    renderer.toneMappingExposure = config.hall.exposure ?? 1.0;
    doorOpen = 0;
    setDoorsOpen(hallScene.userData.doors, 0);
    document.body.classList.add("walking");
    $("hint").textContent = HALL_HINT;
    setStage("Iluminando o hall.", 96);
    await warmUp(hallScene);

    interactive = true;
    needsRender = true;
    resetFps();
    window.RENAISSANCE_READY = {
      ...window.RENAISSANCE_READY,
      mode: "hall",
      hall: { triangles: hallScene.userData.triangles, drawObjects: hallScene.userData.drawObjects, spawn: hallNav.spawn },
    };
    setStage("Bem-vindo ao Renaissance.", 100);
    $("loading").classList.add("done");
  } catch (error) {
    if (contextLost()) {
      showFatalError(error);
      return;
    }
    console.error(error);
    hallPromise = null;
    mode = "exterior";
    activeScene = exteriorScene;
    orbit.enabled = true;
    walk.exit();
    document.body.classList.remove("walking");
    $("hint").textContent = DEFAULT_HINT;
    interactive = true;
    resetExteriorCamera();
    $("loading").classList.add("done");
    showToast("Não foi possível abrir o hall. Tente novamente.");
  } finally {
    $("enterHall").disabled = false;
  }
}

async function leaveHall() {
  if (mode !== "hall" || !interactive) return;
  walk.exit();
  if (mobile) disposeScene(hallScene, renderer);
  mode = "exterior";
  activeScene = exteriorScene;
  orbit.enabled = true;
  document.body.classList.remove("walking");
  $("hint").textContent = DEFAULT_HINT;
  resetExteriorCamera();
  interactive = false;
  $("loading").classList.remove("done");
  setStage("Voltando à fachada.", 88);
  try {
    await warmUp(exteriorScene);
    interactive = true;
    needsRender = true;
    window.RENAISSANCE_READY.mode = "exterior";
    $("loading").classList.add("done");
  } catch (error) {
    showFatalError(error);
  }
}

// ---------------------------------------------------------------------------
// Panels: help and reference renders

function closeHelp() {
  $("helpPanel").classList.remove("open");
  $("help").setAttribute("aria-expanded", "false");
  walk?.setEnabled(!$("references").open);
}

$("help").onclick = () => {
  const open = $("helpPanel").classList.toggle("open");
  $("help").setAttribute("aria-expanded", String(open));
  walk?.setEnabled(!open);
};
$("closeHelp").onclick = closeHelp;

function showReference(which) {
  const image = $("referenceImage");
  const hall = which === "hall";
  const src = hall ? image.dataset.hall : image.dataset.facade;
  if (image.getAttribute("src") !== src) image.src = src; // loaded on first view only
  image.alt = hall ? "Render de referência do hall enviado pelo proprietário" : "Render de referência da fachada enviado pelo proprietário";
  $("referenceTitle").textContent = hall ? "Hall de entrada" : "A chegada ao Renaissance";
  document.querySelectorAll("[data-reference]").forEach(button => button.classList.toggle("active", button.dataset.reference === which));
}

function openReferences(which = mode === "hall" ? "hall" : "facade") {
  closeHelp();
  showReference(which);
  $("references").showModal();
  walk?.setEnabled(false);
  if (orbit) orbit.enabled = false;
}

function closeReferences() {
  if ($("references").open) $("references").close();
  walk?.setEnabled(!$("helpPanel").classList.contains("open"));
  if (orbit) orbit.enabled = mode === "exterior";
}

$("references").addEventListener("close", () => {
  walk?.setEnabled(!$("helpPanel").classList.contains("open"));
  if (orbit) orbit.enabled = mode === "exterior";
});
$("closeReferences").onclick = closeReferences;
$("references").addEventListener("click", event => {
  if (event.target === $("references")) closeReferences(); // backdrop
});
document.querySelectorAll("[data-reference]").forEach(button => (button.onclick = () => showReference(button.dataset.reference)));
$("showReferences").onclick = () => openReferences();
$("hallReference").onclick = () => openReferences("hall");

// ---------------------------------------------------------------------------
// Buttons

$("enterHall").onclick = enterHall;
$("leaveHall").onclick = leaveHall;
$("goEntrance").onclick = () => goToViewpoint("entrada");
$("goElevators").onclick = () => goToViewpoint("elevadores");
$("crouch").onclick = () => walk.toggleCrouch();
$("zoomIn").onclick = () => zoomBy(0.82);
$("zoomOut").onclick = () => zoomBy(1.22);
$("rotate").onclick = () => {
  if (!interactive || mode !== "exterior") return;
  tween = null;
  orbit.autoRotate = !orbit.autoRotate;
  $("rotate").setAttribute("aria-pressed", String(orbit.autoRotate));
  showToast(orbit.autoRotate ? "Giro automático ativado" : "Giro automático pausado");
};
$("present").onclick = () => {
  document.body.classList.add("clean");
  closeHelp();
  document.documentElement.requestFullscreen?.().catch(() => {});
};
$("exitClean").onclick = () => {
  document.body.classList.remove("clean");
  if (document.fullscreenElement) document.exitFullscreen?.();
};
addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement) document.body.classList.remove("clean");
});
$("capture").onclick = () => {
  if (!interactive) return;
  renderer.render(activeScene, camera);
  const link = document.createElement("a");
  link.download = mode === "hall" ? "Renaissance-hall-3D.png" : "Renaissance-vista-3D.png";
  link.href = renderer.domElement.toDataURL("image/png");
  link.click();
  showToast("Vista salva");
};
document.querySelectorAll("[data-view]").forEach(button => (button.onclick = () => goToView(button.dataset.view)));
$("lightMode").onclick = () => {
  if (!interactive || mode !== "exterior") return;
  lightMode = lightMode === "day" ? "sunset" : "day";
  lighting.set(lightMode);
  const day = lightMode === "day";
  $("lightMode").textContent = day ? "☀ Dia" : "◐ Entardecer";
  $("lightMode").dataset.icon = day ? "☀" : "◐";
  $("lightMode").setAttribute(
    "aria-label",
    day ? "Iluminação diurna. Alternar para entardecer" : "Iluminação ao entardecer. Alternar para dia",
  );
  needsRender = true;
};
$("quality").onchange = event => {
  quality = event.target.value;
  renderer.setPixelRatio(computePixelRatio());
  renderer.setSize(innerWidth, innerHeight);
  needsRender = true;
};

// ---------------------------------------------------------------------------
// Start

(async () => {
  try {
    initRenderer();
    const textures = mobileTextures("exterior");
    const buffer = await loadModel(config, "Carregando o empreendimento.", 0);
    setStage("Preparando materiais e geometria.", 85);
    await nextFrame();
    const gltf = await parseModel(buffer, textures);
    exteriorModel = prepareExteriorModel(gltf.scene);
    exteriorScene.add(exteriorModel);

    const focus = new Box3(new Vector3(...config.focusBounds.min), new Vector3(...config.focusBounds.max));
    focusCenter = focus.getCenter(new Vector3());
    focusSize = focus.getSize(new Vector3());
    updateViewDistance();
    orbit.minDistance = Math.max(1.5, focusSize.y * 0.025);

    interactive = true; // goToView() needs this
    resetExteriorCamera();
    interactive = false;
    setStage("Finalizando a apresentação.", 96);
    await warmUp(exteriorScene);
    interactive = true;
    setStage("Tudo pronto para explorar.", 100);
    setTimeout(() => $("loading").classList.add("done"), 300);
    window.RENAISSANCE_READY = {
      ...exteriorModel.userData,
      source: config.source,
      mode: "exterior",
      bounds: { min: focus.min.toArray(), max: focus.max.toArray() },
    };
    setTimeout(prefetchHall, 3000);
  } catch (error) {
    showFatalError(error);
  }
})();

// Test hook (only with ?debug): place the walker at an exact spot, e.g. renaissanceDebug.walkTo(37.9, 66, 0).
if (new URLSearchParams(location.search).has("debug")) {
  window.renaissanceDebug = {
    goToViewpoint,
    walkTo(x, z, yaw = 0) {
      walk.goTo([x, 0, z], yaw);
      needsRender = true;
    },
    state: () => ({ position: camera.position.toArray().map(v => +v.toFixed(3)), doorOpen: +doorOpen.toFixed(3), mode }),
  };
}
