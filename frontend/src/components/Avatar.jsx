// No per-player color. Blackhand's palette is closed to four colors and
// their documented mixes (section 4.2) -- a per-player hue would be a
// fifth, sixth, and seventh color the moment a second player joins.
// Identity here is the name itself, not a swatch; every avatar is styled
// identically, an ink-bordered mark on the room, initials in the record
// face.
function initialsFor(name) {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export default function Avatar({ name }) {
  return <span className="avatar">{initialsFor(name)}</span>;
}
