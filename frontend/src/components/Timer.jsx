const PHASE_LABEL = {
  night: "NIGHT",
  day_discussion: "DISCUSSION",
  voting: "VOTING",
};

const RADIUS = 18;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

// Color carries the urgency: steel with time to spare, brass in the final
// third, blood in the final ten seconds -- the same threshold that
// triggers the tick sound in App.jsx.
function colorFor(seconds, total) {
  if (seconds <= 10) return "var(--blood-bright)";
  if (total && seconds <= total / 3) return "var(--brass)";
  return "var(--steel)";
}

export default function Timer({ seconds, total, phase }) {
  const fraction = total ? Math.max(0, Math.min(1, seconds / total)) : 0;
  const offset = CIRCUMFERENCE * (1 - fraction);
  const color = colorFor(seconds, total);

  const label = PHASE_LABEL[phase] || phase;

  return (
    <div className="ring-timer" role="img" aria-label={`${label}, ${seconds} seconds remaining`}>
      <span className="ring-timer-label" aria-hidden="true">
        {label}
      </span>
      <svg width="42" height="42" viewBox="0 0 42 42" aria-hidden="true">
        <circle cx="21" cy="21" r={RADIUS} fill="none" stroke="var(--paper-edge)" strokeWidth="4" />
        <g transform="rotate(-90 21 21)">
          <circle
            cx="21"
            cy="21"
            r={RADIUS}
            fill="none"
            stroke={color}
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={offset}
            style={{ transition: "stroke-dashoffset 1s linear, stroke 0.3s ease" }}
          />
        </g>
        <text x="21" y="25" textAnchor="middle" fontSize="11" className="ring-timer-value" fill={color}>
          {seconds}
        </text>
      </svg>
    </div>
  );
}
