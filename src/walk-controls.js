// First-person walking inside the hall. Collisions come from a walkability grid
// (assets/model.json → hall.nav): one character per 8 cm cell, "1" = floor you can stand on.
import { MathUtils } from "three";

const STEP = 0.035; // metres per collision sub-step
const WALK_SPEED = 1.35; // m/s
const CROUCH_SPEED = 0.8;
const KEYS = ["KeyW", "KeyA", "KeyS", "KeyD", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "KeyC"];

function isWalkable(nav, x, z) {
  const col = Math.floor((x - nav.origin[0]) / nav.cell);
  const row = Math.floor((z - nav.origin[1]) / nav.cell);
  return col >= 0 && row >= 0 && col < nav.width && row < nav.height && nav.rows[row][col] === "1";
}

// Moves in small steps; when blocked, slides along whichever axis is still free.
function moveWithCollisions(nav, position, dx, dz) {
  const steps = Math.max(1, Math.ceil(Math.hypot(dx, dz) / STEP));
  const stepX = dx / steps;
  const stepZ = dz / steps;
  let { x, z } = position;
  for (let i = 0; i < steps; i++) {
    if (isWalkable(nav, x + stepX, z + stepZ)) {
      x += stepX;
      z += stepZ;
    } else {
      if (isWalkable(nav, x + stepX, z)) x += stepX;
      if (isWalkable(nav, x, z + stepZ)) z += stepZ;
    }
  }
  return { x, z };
}

export class WalkControls {
  constructor(camera, canvas, joystick, knob, onCrouch) {
    this.camera = camera;
    this.canvas = canvas;
    this.joystick = joystick;
    this.knob = knob;
    this.onCrouch = onCrouch;
    this.active = false;
    this.enabled = true;
    this.keys = new Set();
    this.stick = { x: 0, z: 0 };
    this.yaw = 0;
    this.pitch = 0;
    this.dirty = false;
    this.drag = null;
    this.joyId = null;
    this.crouched = false;

    addEventListener("keydown", event => {
      if (!this.active || !this.enabled) return;
      if (/INPUT|TEXTAREA|SELECT/.test(event.target.tagName) || !KEYS.includes(event.code)) return;
      event.preventDefault();
      if (event.code === "KeyC") {
        if (!event.repeat) this.toggleCrouch();
      } else {
        this.keys.add(event.code);
      }
    });
    addEventListener("keyup", event => this.keys.delete(event.code));
    addEventListener("blur", () => this.clearInput());
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) this.clearInput();
    });

    // Drag anywhere on the scene to look around.
    canvas.addEventListener("pointerdown", event => {
      if (!this.active || !this.enabled || event.button > 0) return;
      event.preventDefault();
      this.drag = { id: event.pointerId, x: event.clientX, y: event.clientY };
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointermove", event => {
      if (!this.active || !this.enabled || this.drag?.id !== event.pointerId) return;
      const sensitivity = event.pointerType === "touch" ? 0.004 : 0.003;
      this.yaw -= (event.clientX - this.drag.x) * sensitivity;
      this.pitch = MathUtils.clamp(this.pitch - (event.clientY - this.drag.y) * sensitivity, -1.25, 1.25);
      this.drag.x = event.clientX;
      this.drag.y = event.clientY;
      this.dirty = true;
    });
    const endDrag = event => {
      if (this.drag?.id === event.pointerId) this.drag = null;
    };
    canvas.addEventListener("pointerup", endDrag);
    canvas.addEventListener("pointercancel", endDrag);
    canvas.addEventListener("lostpointercapture", endDrag);

    // On-screen joystick for touch devices.
    joystick.addEventListener("pointerdown", event => {
      if (!this.active || !this.enabled) return;
      event.preventDefault();
      this.joyId = event.pointerId;
      joystick.setPointerCapture(event.pointerId);
      this.updateStick(event);
    });
    joystick.addEventListener("pointermove", event => {
      if (this.joyId === event.pointerId) this.updateStick(event);
    });
    const endStick = event => {
      if (event.pointerId !== this.joyId) return;
      this.joyId = null;
      this.stick = { x: 0, z: 0 };
      knob.style.transform = "translate(0px,0px)";
    };
    joystick.addEventListener("pointerup", endStick);
    joystick.addEventListener("pointercancel", endStick);
    joystick.addEventListener("lostpointercapture", endStick);
  }

  updateStick(event) {
    const rect = this.joystick.getBoundingClientRect();
    let dx = event.clientX - (rect.left + rect.width / 2);
    let dy = event.clientY - (rect.top + rect.height / 2);
    const radius = rect.width * 0.31;
    const distance = Math.hypot(dx, dy);
    if (distance > radius) {
      dx *= radius / distance;
      dy *= radius / distance;
    }
    this.stick = { x: dx / radius, z: dy / radius };
    this.knob.style.transform = `translate(${dx}px,${dy}px)`;
  }

  clearInput() {
    this.keys.clear();
    this.stick = { x: 0, z: 0 };
    this.knob.style.transform = "translate(0px,0px)";
    this.drag = null;
    this.joyId = null;
  }

  setEnabled(enabled) {
    this.enabled = enabled;
    if (!enabled) this.clearInput();
  }

  enter(nav) {
    this.nav = nav;
    this.active = true;
    this.enabled = true;
    this.reset();
  }

  reset() {
    this.clearInput();
    this.crouched = false;
    this.onCrouch(false);
    this.camera.position.fromArray(this.nav.spawn);
    this.yaw = 0;
    this.pitch = 0.025;
    this.camera.rotation.order = "YXZ";
    this.dirty = true;
    this.update(0);
  }

  exit() {
    this.active = false;
    this.clearInput();
  }

  toggleCrouch() {
    if (!this.active || !this.enabled) return;
    this.crouched = !this.crouched;
    this.onCrouch(this.crouched);
    this.dirty = true;
  }

  // Advances the camera by `dt` seconds; returns true when a new frame is needed.
  update(dt) {
    if (!this.active) return false;
    let changed = this.dirty;
    this.dirty = false;
    const position = this.camera.position;

    if (this.enabled) {
      const keys = this.keys;
      let x = this.stick.x + (keys.has("KeyD") || keys.has("ArrowRight") ? 1 : 0) - (keys.has("KeyA") || keys.has("ArrowLeft") ? 1 : 0);
      let z = this.stick.z + (keys.has("KeyS") || keys.has("ArrowDown") ? 1 : 0) - (keys.has("KeyW") || keys.has("ArrowUp") ? 1 : 0);
      const length = Math.hypot(x, z);
      if (length > 0.06) {
        if (length > 1) {
          x /= length;
          z /= length;
        }
        const distance = (this.crouched ? CROUCH_SPEED : WALK_SPEED) * dt;
        const cos = Math.cos(this.yaw);
        const sin = Math.sin(this.yaw);
        const next = moveWithCollisions(this.nav, position, (x * cos + z * sin) * distance, (-x * sin + z * cos) * distance);
        if (next.x !== position.x || next.z !== position.z) changed = true;
        position.x = next.x;
        position.z = next.z;
      }
    }

    // Ease the eye height when crouching or standing up.
    const eyeY = this.nav.floorY + (this.crouched ? this.nav.crouchHeight : this.nav.eyeHeight);
    const y = position.y;
    position.y = MathUtils.lerp(y, eyeY, 1 - Math.exp(-dt * 14));
    if (Math.abs(eyeY - y) < 0.001) position.y = eyeY;
    else changed = true;

    this.camera.rotation.set(this.pitch, this.yaw, 0, "YXZ");
    return changed;
  }
}
