const PHASE_LABEL = {
  night: "NIGHT",
  day_discussion: "DISCUSSION",
  voting: "VOTING",
  show_hands: "SHOW YOUR HANDS",
  offer: "THE OFFER",
};

const RADIUS = 18;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

// Lamp is rationed to three things in this system: time running out is one
// of them (section 4.2). Everywhere else the ring is a neutral ink-quiet
// line on the room, same as any other piece of chrome.
function colorFor(seconds) {
  return seconds <= 10 ? "var(--lamp)" : "var(--ink-quiet)";
}

export default function Timer({ seconds, total, phase }) {
  const fraction = total ? Math.max(0, Math.min(1, seconds / total)) : 0;
  const offset = CIRCUMFERENCE * (1 - fraction);
  const color = colorFor(seconds);

  const label = PHASE_LABEL[phase] || phase;

  return (
    <div className="ring-timer" role="img" aria-label={`${label}, ${seconds} seconds remaining`}>
      <span className="ring-timer-label" aria-hidden="true">
        {label}
      </span>
      <svg width="42" height="42" viewBox="0 0 42 42" aria-hidden="true">
        <circle cx="21" cy="21" r={RADIUS} fill="none" stroke="var(--ink-faint)" strokeWidth="2" />
        <g transform="rotate(-90 21 21)">
          <circle
            cx="21"
            cy="21"
            r={RADIUS}
            fill="none"
            stroke={color}
            strokeWidth="2"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={offset}
            style={{ transition: "stroke-dashoffset 1s linear" }}
          />
        </g>
        <text x="21" y="25" textAnchor="middle" fontSize="11" className="ring-timer-value" fill={color}>
          {seconds}
        </text>
      </svg>
    </div>
  );
}
