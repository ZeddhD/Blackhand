// The in-game ambient bed (section 4.10, rules 1 and 2): four room-tone
// layers, always playing, crossfaded between phases, never hard cut, and
// eroded one layer at a time, permanently, on every death. By the final
// round the room sounds hollow. No player consciously notices; every
// player feels it.
//
// Separately, the Waiting Room has its own single ambient layer (section
// 6.1): the only ambient bed in the game with human sound in it, and it
// never returns once the game starts. It is a different system entirely,
// not one of the four layers, and is not eroded by deaths.

import { getCtx, getMaster } from "./context";
import { brownNoiseBuffer, pinkNoiseBuffer, whiteNoiseBuffer } from "./noise";

const LAYER_COUNT = 4;
const LOOP_SECONDS = 6;
const CROSSFADE_SECONDS = 1.4;

// Per-phase target level for each of the four layers (rumble, mid hum,
// air, texture), before that layer's own base level and before any
// death has silenced it. Deliberately close together across phases: this
// is still room tone throughout, not a different soundscape per screen.
const PHASE_MIX = {
  night: [0.9, 0.55, 0.25, 0.35],
  day_discussion: [0.7, 0.85, 0.45, 0.55],
  voting: [0.6, 0.9, 0.3, 0.6],
  show_hands: [0.8, 0.5, 0.2, 0.3],
  offer: [1.0, 0.35, 0.15, 0.2],
  game_over: [0.5, 0.4, 0.2, 0.2],
  default: [0.75, 0.7, 0.3, 0.4],
};

let layers = null;
let bedStarted = false;
let layersRemoved = 0;
let lastKnownDeadCount = null;
let currentPhaseKey = "default";

function buildLayer(kind, freq, filterType, baseLevel) {
  const ctx = getCtx();
  const buffer =
    kind === "brown"
      ? brownNoiseBuffer(ctx, LOOP_SECONDS)
      : kind === "pink"
        ? pinkNoiseBuffer(ctx, LOOP_SECONDS)
        : whiteNoiseBuffer(ctx, LOOP_SECONDS);
  const src = ctx.createBufferSource();
  src.buffer = buffer;
  src.loop = true;
  const filter = ctx.createBiquadFilter();
  filter.type = filterType;
  filter.frequency.value = freq;
  filter.Q.value = 0.7;
  const gain = ctx.createGain();
  gain.gain.value = 0;
  src.connect(filter).connect(gain).connect(getMaster());
  src.start();
  return { src, filter, gain, baseLevel, removed: false };
}

export function startBed() {
  if (bedStarted) return;
  bedStarted = true;
  layers = [
    buildLayer("brown", 180, "lowpass", 0.05),
    buildLayer("pink", 500, "bandpass", 0.035),
    buildLayer("white", 3000, "highpass", 0.012),
    buildLayer("pink", 1000, "bandpass", 0.02),
  ];
}

export function crossfadeBedTo(phaseKey) {
  currentPhaseKey = phaseKey;
  if (!bedStarted || !layers) return;
  const mix = PHASE_MIX[phaseKey] || PHASE_MIX.default;
  const ctx = getCtx();
  const t = ctx.currentTime;
  layers.forEach((layer, i) => {
    if (layer.removed) return;
    const target = mix[i] * layer.baseLevel;
    layer.gain.gain.cancelScheduledValues(t);
    layer.gain.gain.setValueAtTime(layer.gain.gain.value, t);
    layer.gain.gain.linearRampToValueAtTime(target, t + CROSSFADE_SECONDS);
  });
}

function silentlyRemoveLayersUpTo(count) {
  if (!layers) return;
  const target = Math.min(count, LAYER_COUNT);
  const ctx = getCtx();
  while (layersRemoved < target) {
    const layer = layers[layersRemoved];
    layer.gain.gain.cancelScheduledValues(ctx.currentTime);
    layer.gain.gain.setValueAtTime(0, ctx.currentTime);
    layer.removed = true;
    layersRemoved++;
  }
}

// Death, section 4.10: two seconds of nothing, then the bed returns with
// one fewer layer, permanently. The whole bed goes to zero fast enough
// to read as an actual silence rather than a fade, holds there for the
// full 2000ms, then the removed layer is dropped and the rest come back
// at whatever level the current phase calls for.
function playDeathSilenceThenRemove(deadCount) {
  if (!layers) return;
  const ctx = getCtx();
  const t = ctx.currentTime;
  layers.forEach((layer) => {
    layer.gain.gain.cancelScheduledValues(t);
    layer.gain.gain.setValueAtTime(layer.gain.gain.value, t);
    layer.gain.gain.linearRampToValueAtTime(0, t + 0.05);
  });
  setTimeout(() => {
    silentlyRemoveLayersUpTo(deadCount);
    crossfadeBedTo(currentPhaseKey);
  }, 2000);
}

// Called on every state update with the true, server-reported number of
// dead players. The first observation this session catches up silently
// (those deaths already happened before this client was listening); any
// increase after that plays the real death silence, live.
export function reconcileDeadCount(deadCount) {
  if (!bedStarted) return;
  if (lastKnownDeadCount === null) {
    silentlyRemoveLayersUpTo(deadCount);
    lastKnownDeadCount = deadCount;
    return;
  }
  if (deadCount <= lastKnownDeadCount) {
    lastKnownDeadCount = deadCount;
    return;
  }
  lastKnownDeadCount = deadCount;
  playDeathSilenceThenRemove(deadCount);
}

export function stopBed() {
  if (!layers) return;
  layers.forEach((l) => {
    try {
      l.src.stop();
    } catch {
      // already stopped
    }
  });
  layers = null;
  bedStarted = false;
  layersRemoved = 0;
  lastKnownDeadCount = null;
  currentPhaseKey = "default";
}

// The Waiting Room's own ambient (section 6.1): a room with people in it,
// voices too low to make out words. Approximated as band-passed noise
// with a slow, irregular amplitude wobble rather than a steady tone,
// since a fixed level reads as machinery, not a room full of people.
let lobbySource = null;
let lobbyLfo = null;
let lobbyGain = null;

export function startLobbyAmbient() {
  if (lobbySource) return;
  const ctx = getCtx();
  const src = ctx.createBufferSource();
  src.buffer = pinkNoiseBuffer(ctx, 8);
  src.loop = true;
  const filter = ctx.createBiquadFilter();
  filter.type = "bandpass";
  filter.frequency.value = 550;
  filter.Q.value = 0.8;
  const gain = ctx.createGain();
  gain.gain.value = 0;

  // This oscillator is never audible on its own: it drives the gain
  // parameter below, not the output, shaping the noise layer's volume
  // into a slow wobble instead of playing as a tone. The only audible
  // signal in this layer is still the pink noise buffer.
  const lfo = ctx.createOscillator();
  lfo.type = "sine";
  lfo.frequency.value = 0.3;
  const lfoGain = ctx.createGain();
  lfoGain.gain.value = 0.01;
  lfo.connect(lfoGain).connect(gain.gain);
  lfo.start();

  src.connect(filter).connect(gain).connect(getMaster());
  src.start();
  gain.gain.linearRampToValueAtTime(0.03, ctx.currentTime + 1.5);

  lobbySource = src;
  lobbyLfo = lfo;
  lobbyGain = gain;
}

// Never returns once the game starts (section 6.1): callers stop this
// exactly once, leaving the lobby, and never start it again this game.
export function stopLobbyAmbient() {
  if (!lobbySource) return;
  const ctx = getCtx();
  const t = ctx.currentTime;
  lobbyGain.gain.cancelScheduledValues(t);
  lobbyGain.gain.setValueAtTime(lobbyGain.gain.value, t);
  lobbyGain.gain.linearRampToValueAtTime(0, t + 1.0);
  const src = lobbySource;
  const lfo = lobbyLfo;
  setTimeout(() => {
    try {
      src.stop();
    } catch {
      // already stopped
    }
    try {
      lfo.stop();
    } catch {
      // already stopped
    }
  }, 1100);
  lobbySource = null;
  lobbyLfo = null;
  lobbyGain = null;
}
