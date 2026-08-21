// A single shared AudioContext and a master gain node every sound in the
// game passes through, so muting is one gain change, not tracking every
// live node. Browsers block audio until a user gesture; the first click
// on Host/Join resumes the context, so by the time any cue fires during
// a game the context is already unlocked.

let ctx = null;
let master = null;
let enabled = true;

export function getCtx() {
  if (!ctx) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    ctx = new AudioCtx();
    master = ctx.createGain();
    master.gain.value = 1;
    master.connect(ctx.destination);
  }
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}

export function getMaster() {
  getCtx();
  return master;
}

export function setSoundEnabled(value) {
  enabled = value;
  if (master) {
    const t = ctx.currentTime;
    master.gain.cancelScheduledValues(t);
    master.gain.linearRampToValueAtTime(value ? 1 : 0, t + 0.05);
  }
}

export function isSoundEnabled() {
  return enabled;
}

export function unlockAudio() {
  if (enabled) getCtx();
}
