import { useEffect, useRef, useState } from "react";
import Avatar from "../components/Avatar";

const SKIP_VOTE = "skip";

// Nearly inaudible at 45 seconds, impossible to ignore at 8 (section 6.8).
// Absolute thresholds, the same way Timer.jsx's lamp cutoff is absolute
// rather than a percentage of whatever the host configured.
function pulseDurationMs(secondsLeft) {
  if (secondsLeft == null) return 3000;
  const clamped = Math.max(8, Math.min(45, secondsLeft));
  const t = (45 - clamped) / (45 - 8);
  return 3000 - t * 2500;
}

// The Table (section 6.8). A ring, inverted ground, one affordance: point
// at a seat. No chat, no back, no tabs, no side panel exist here, this
// component is rendered as the entire screen, nothing else mounted
// alongside it.
export default function Table({ state, seatOrder, playerId, timer, vote }) {
  const [revealedVoterIds, setRevealedVoterIds] = useState([]);
  const queueRef = useRef([]);
  const knownRef = useRef(new Set());
  const pendingTimeoutRef = useRef(null);

  useEffect(() => {
    const currentVoters = Object.keys(state.votes || {});
    const fresh = currentVoters.filter((id) => !knownRef.current.has(id));
    fresh.forEach((id) => knownRef.current.add(id));
    if (fresh.length === 0) return;
    queueRef.current.push(...fresh);
    if (pendingTimeoutRef.current) return;
    const step = () => {
      const next = queueRef.current.shift();
      if (next) setRevealedVoterIds((prev) => [...prev, next]);
      if (queueRef.current.length > 0) {
        pendingTimeoutRef.current = setTimeout(step, 220);
      } else {
        pendingTimeoutRef.current = null;
      }
    };
    step();
    return () => {
      clearTimeout(pendingTimeoutRef.current);
      pendingTimeoutRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.votes]);

  const order = seatOrder && seatOrder.length ? seatOrder : state.players.map((p) => p.id);
  const byId = Object.fromEntries(state.players.map((p) => [p.id, p]));
  const votedFor = (targetId) =>
    revealedVoterIds.filter((voterId) => state.votes[voterId] === targetId).length;

  const secondsLeft = timer?.phase === "voting" ? timer.secondsLeft : null;
  const pulseMs = pulseDurationMs(secondsLeft);

  const myVote = state.votes[playerId];

  return (
    <div className="table-screen">
      <div className="table-ring-wrap">
        <span className="table-pulse" style={{ "--pulse-duration": `${pulseMs}ms` }} aria-hidden="true" />
        <div className="table-ring">
          {order.map((id, i) => {
            const player = byId[id];
            if (!player) return null;
            const angle = (360 / order.length) * i - 90;
            const radians = (angle * Math.PI) / 180;
            const left = 50 + 42 * Math.cos(radians);
            const top = 50 + 42 * Math.sin(radians);
            const style = { left: `${left}%`, top: `${top}%` };

            if (!player.alive) {
              return (
                <span key={id} className="table-seat table-seat-empty" style={style} aria-hidden="true" />
              );
            }

            const count = votedFor(player.id);
            const isMe = player.id === playerId;
            const isMyVote = myVote === player.id;

            return (
              <button
                key={id}
                type="button"
                className={["table-seat", isMyVote ? "table-seat-selected" : ""].filter(Boolean).join(" ")}
                style={style}
                disabled={isMe}
                onClick={() => vote(player.id)}
              >
                <Avatar name={player.name} />
                <span className="table-seat-name">{player.name}</span>
                {count > 0 && (
                  <span key={count} className="table-seat-tally motion-stamped">
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <button
        type="button"
        className={["stand-aside", myVote === SKIP_VOTE ? "stand-aside-selected" : ""].filter(Boolean).join(" ")}
        onClick={() => vote(SKIP_VOTE)}
      >
        STAND ASIDE
      </button>
    </div>
  );
}
