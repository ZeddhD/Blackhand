// Synthesized tones via Web Audio -- no audio files to ship or load.
// Browsers block audio until a user gesture; the first click on Host/Join
// resumes the context, so by the time any cue fires during a game the
// context is already unlocked.

let ctx = null;
let enabled = true;

function getCtx() {
  if (!ctx) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    ctx = new AudioCtx();
  }
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}

export function setSoundEnabled(value) {
  enabled = value;
}

export function isSoundEnabled() {
  return enabled;
}

function tone(freq, startOffset, duration, { type = "sine", gain = 0.15 } = {}) {
  if (!enabled) return;
  const audio = getCtx();
  const osc = audio.createOscillator();
  const g = audio.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  const t0 = audio.currentTime + startOffset;
  g.gain.setValueAtTime(0, t0);
  g.gain.linearRampToValueAtTime(gain, t0 + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);
  osc.connect(g).connect(audio.destination);
  osc.start(t0);
  osc.stop(t0 + duration + 0.05);
}

// Two-note descending tone: night falling, moody and low.
export function playNightChime() {
  tone(440, 0, 0.5, { type: "sine" });
  tone(330, 0.25, 0.7, { type: "sine" });
}

// Two-note ascending bell: dawn breaking.
export function playDayChime() {
  tone(523, 0, 0.4, { type: "triangle" });
  tone(659, 0.15, 0.6, { type: "triangle" });
}

// Firm double beep: voting is open, decide now.
export function playVoteChime() {
  tone(698, 0, 0.18, { type: "square", gain: 0.1 });
  tone(698, 0.22, 0.22, { type: "square", gain: 0.1 });
}

// Resolving triad: the game has ended.
export function playGameOverChime() {
  tone(440, 0, 0.9, { type: "triangle", gain: 0.12 });
  tone(554, 0.1, 0.9, { type: "triangle", gain: 0.12 });
  tone(659, 0.2, 1.1, { type: "triangle", gain: 0.12 });
}

// Short high click, used once per second in the final countdown.
export function playTick() {
  tone(880, 0, 0.08, { type: "square", gain: 0.08 });
}

// Low descending tone: you have been eliminated. Personal -- only the
// player who died hears this one.
export function playEliminated() {
  tone(220, 0, 0.35, { type: "sawtooth", gain: 0.12 });
  tone(146, 0.25, 0.7, { type: "sawtooth", gain: 0.12 });
}

// Single soft low toll: someone else in the room has died. Deliberately
// shorter and quieter than playEliminated so the two are never confused --
// this is an ambient notice, not a personal event.
export function playDeathToll() {
  tone(165, 0, 0.5, { type: "sine", gain: 0.1 });
}

export function unlockAudio() {
  if (enabled) getCtx();
}
