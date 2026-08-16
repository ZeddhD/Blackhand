const PHASE_LABEL = {
  night: "Night",
  day_discussion: "Discussion",
  voting: "Voting",
};

export default function Timer({ seconds, phase }) {
  const mm = Math.floor(seconds / 60);
  const ss = String(seconds % 60).padStart(2, "0");
  return (
    <span className="timer">
      {PHASE_LABEL[phase] || phase}: {mm}:{ss}
    </span>
  );
}
