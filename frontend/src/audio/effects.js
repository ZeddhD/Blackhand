// One-shot event sounds (section 4.10's table). Every one of these is
// built from filtered noise, paper, wood, or room air, except the one
// named exception at the bottom of this file. No oscillator plays a
// musical note anywhere in this file.

import { getCtx, getMaster, isSoundEnabled } from "./context";
import { whiteNoiseBuffer, pinkNoiseBuffer, brownNoiseBuffer } from "./noise";

// Cache noise source buffers: they're pure random data, regenerating one
// on every single cue would be wasted work for no audible benefit, since
// nothing here relies on the buffer's specific content repeating.
const bufferCache = new Map();
function cachedBuffer(kind, seconds) {
  const key = `${kind}:${seconds}`;
  if (bufferCache.has(key)) return bufferCache.get(key);
  const ctx = getCtx();
  const buffer =
    kind === "white"
      ? whiteNoiseBuffer(ctx, seconds)
      : kind === "pink"
        ? pinkNoiseBuffer(ctx, seconds)
        : brownNoiseBuffer(ctx, seconds);
  bufferCache.set(key, buffer);
  return buffer;
}

function noiseBurst({
  kind = "white",
  startOffset = 0,
  duration,
  attack = 0.004,
  gain = 0.2,
  filterType = "bandpass",
  freq,
  freqEnd,
  Q = 1,
  destination,
} = {}) {
  const ctx = getCtx();
  const src = ctx.createBufferSource();
  src.buffer = cachedBuffer(kind, duration + attack + 0.1);
  const filter = ctx.createBiquadFilter();
  filter.type = filterType;
  filter.Q.value = Q;
  const g = ctx.createGain();
  const t0 = ctx.currentTime + startOffset;

  filter.frequency.setValueAtTime(freq, t0);
  if (freqEnd != null) filter.frequency.linearRampToValueAtTime(freqEnd, t0 + duration);

  g.gain.setValueAtTime(0, t0);
  g.gain.linearRampToValueAtTime(gain, t0 + attack);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);

  src.connect(filter).connect(g).connect(destination || getMaster());
  src.start(t0);
  src.stop(t0 + duration + 0.05);
}

// A short resonant knock: noise exciting a narrow bandpass, the way a
// struck solid object rings at its own resonant frequency rather than
// across the whole spectrum. This is the wood voice used for the vote
// stamp and the Crossing's footsteps and door.
function woodKnock({ startOffset = 0, freq = 220, duration = 0.1, gain = 0.3, Q = 9 } = {}) {
  noiseBurst({
    kind: "white",
    startOffset,
    duration,
    attack: 0.002,
    gain,
    filterType: "bandpass",
    freq,
    Q,
  });
}

// Letter opens: paper unfold, 380ms.
export function letterUnfold() {
  if (!isSoundEnabled()) return;
  noiseBurst({
    kind: "pink",
    duration: 0.38,
    attack: 0.03,
    gain: 0.16,
    filterType: "bandpass",
    freq: 1400,
    freqEnd: 2600,
    Q: 0.6,
  });
  // Two small irregular crinkle transients layered on top: paper doesn't
  // unfold as one smooth sweep, it catches and releases.
  [0.06, 0.19].forEach((offset, i) => {
    noiseBurst({
      kind: "white",
      startOffset: offset,
      duration: 0.05 + i * 0.01,
      attack: 0.002,
      gain: 0.06,
      filterType: "highpass",
      freq: 3000,
    });
  });
}

// Vote lands: wooden stamp on table, 120ms.
export function voteStamp() {
  if (!isSoundEnabled()) return;
  noiseBurst({
    kind: "white",
    duration: 0.02,
    attack: 0.001,
    gain: 0.22,
    filterType: "highpass",
    freq: 800,
  });
  woodKnock({ freq: 190, duration: 0.11, gain: 0.28, Q: 7 });
  woodKnock({ freq: 340, duration: 0.08, gain: 0.14, Q: 10 });
}

// Night action submitted: a single pen stroke, 90ms.
export function penStroke() {
  if (!isSoundEnabled()) return;
  noiseBurst({
    kind: "white",
    duration: 0.09,
    attack: 0.01,
    gain: 0.05,
    filterType: "highpass",
    freq: 3500,
    Q: 0.7,
  });
}

// Phase change: paper sliding across wood, 600ms.
export function phaseChange() {
  if (!isSoundEnabled()) return;
  noiseBurst({
    kind: "pink",
    duration: 0.6,
    attack: 0.12,
    gain: 0.13,
    filterType: "bandpass",
    freq: 2200,
    freqEnd: 700,
    Q: 0.8,
  });
}

// Timer under 10s: mechanical clock, one call per tick. The caller owns
// the once-per-second interval; this plays exactly one tick.
export function clockTick() {
  if (!isSoundEnabled()) return;
  noiseBurst({
    kind: "white",
    duration: 0.02,
    attack: 0.001,
    gain: 0.1,
    filterType: "bandpass",
    freq: 2600,
    Q: 6,
  });
}

// The Crossing: chairs, footsteps, a door, 2800ms total.
export function theCrossing() {
  if (!isSoundEnabled()) return;
  // Chairs: two broader, rougher scrapes near the start.
  noiseBurst({
    kind: "pink",
    startOffset: 0,
    duration: 0.4,
    attack: 0.05,
    gain: 0.1,
    filterType: "bandpass",
    freq: 500,
    freqEnd: 300,
    Q: 0.5,
  });
  noiseBurst({
    kind: "pink",
    startOffset: 0.3,
    duration: 0.35,
    attack: 0.05,
    gain: 0.08,
    filterType: "bandpass",
    freq: 450,
    freqEnd: 280,
    Q: 0.5,
  });
  // Footsteps: muffled low thonks, unevenly spaced like an actual gait.
  [0.9, 1.28, 1.7, 2.05].forEach((offset, i) => {
    woodKnock({
      startOffset: offset,
      freq: 130 + (i % 2) * 15,
      duration: 0.14,
      gain: 0.16,
      Q: 3.5,
    });
  });
  // The door: a longer low resonance, then a short high latch click.
  woodKnock({ startOffset: 2.35, freq: 90, duration: 0.45, gain: 0.24, Q: 4 });
  noiseBurst({
    kind: "white",
    startOffset: 2.7,
    duration: 0.06,
    attack: 0.002,
    gain: 0.14,
    filterType: "bandpass",
    freq: 3200,
    Q: 8,
  });
}

// The one sound in the game that is not paper, wood, or air (section
// 4.10, rule 3): the recruitment offer's struck wire. Deliberately built
// from oscillators, not noise, so it resembles nothing else in the game
// and is instantly recognizable the one time it's heard.
export function struckWire() {
  if (!isSoundEnabled()) return;
  const ctx = getCtx();
  const t0 = ctx.currentTime;
  const fundamental = 660;
  // Slightly inharmonic partials, the way a real struck wire's overtones
  // don't sit at clean integer multiples the way a tuned note would.
  const partials = [1, 2.76, 5.4];
  partials.forEach((ratio, i) => {
    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.value = fundamental * ratio;
    const g = ctx.createGain();
    const peak = 0.16 / (i + 1);
    const duration = 1.8 - i * 0.4;
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(peak, t0 + 0.004);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);
    osc.connect(g).connect(getMaster());
    osc.start(t0);
    osc.stop(t0 + duration + 0.05);
  });
}
