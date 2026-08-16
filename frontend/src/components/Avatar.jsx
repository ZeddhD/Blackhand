// Fixed swatches drawn from the same three-color system as the rest of the
// UI (brass / steel / blood family) plus their dim variants. No hue outside
// this set is ever used, so avatars read as part of the same system rather
// than a random rainbow bolted on.
const PALETTE = ["#c9a227", "#6c8a9a", "#8a6f1f", "#3d525c", "#9a5a3d", "#5a6b4a"];

function colorFor(seed) {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return PALETTE[hash % PALETTE.length];
}

function initialsFor(name) {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export default function Avatar({ name }) {
  return (
    <span className="avatar" style={{ background: colorFor(name) }}>
      {initialsFor(name)}
    </span>
  );
}
