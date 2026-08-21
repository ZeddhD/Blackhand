import Letter from "../components/Letter";
import Timer from "../components/Timer";

// The Room (section 6.6). Discussion. A vertical feed of every player's
// letter, carrying whatever marks they have accumulated so far, and
// nothing else: no vote, no target, no app input at all. Voice does the
// work here. "The loosest phase in the game, deliberately."
export default function Room({ players, connected, ledger, timer, seatOrder }) {
  const order = seatOrder && seatOrder.length ? seatOrder : players.map((p) => p.id);
  return (
    <div className="room-feed">
      {timer && timer.phase === "day_discussion" && timer.secondsLeft != null && (
        <div className="room-feed-timer">
          <Timer seconds={timer.secondsLeft} total={timer.totalSeconds} phase={timer.phase} />
        </div>
      )}
      <ul className="room-feed-list">
        {players.map((p) => (
          <li key={p.id}>
            <Letter faction="table">
              <span className="t-name">{p.name}</span>
              {connected?.[p.id] === false && <span className="player-row-offline"> OFFLINE</span>}
              <PlayerMarks player={p} ledger={ledger} seatOrder={order} />
            </Letter>
          </li>
        ))}
      </ul>
    </div>
  );
}

// The 8-point compass, matching the same clockwise-from-top ring geometry
// The Table/Crossing use: index 0 sits at the top (-90deg), angle grows
// clockwise as seat index increases (frontend/src/phases/Table.jsx).
const COMPASS = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"];

function seatAngleDeg(seatOrder, playerId) {
  const idx = seatOrder.indexOf(playerId);
  if (idx === -1 || seatOrder.length === 0) return null;
  return (360 / seatOrder.length) * idx - 90;
}

function arrowForAngle(angleDeg) {
  const normalized = ((angleDeg % 360) + 360) % 360;
  const idx = Math.round((normalized + 90) / 45) % 8;
  return COMPASS[idx];
}

// Accretion marks (section 6.12). Never cleaned, never summarized into a
// score: every vote a player has ever cast is its own mark here, grouped
// only by which real compass direction (toward the target's actual seat
// on the ring) it pointed, never collapsed into a single opaque count.
function PlayerMarks({ player, ledger, seatOrder }) {
  const votes = ledger?.votes ?? [];
  const cast = votes.filter((v) => v.voter_id === player.id);
  const standAsides = cast.filter((v) => v.target_id === null).length;
  const castTargets = cast.filter((v) => v.target_id !== null);
  const votesReceived = votes.filter((v) => v.target_id === player.id).length;
  const losingSide = ledger?.losing_side_counts?.[player.id] ?? 0;

  const directionCounts = new Map();
  for (const v of castTargets) {
    const angle = seatAngleDeg(seatOrder, v.target_id);
    const arrow = angle == null ? "→" : arrowForAngle(angle);
    directionCounts.set(arrow, (directionCounts.get(arrow) || 0) + 1);
  }

  const hasAnyMark = castTargets.length || votesReceived || standAsides || losingSide || !player.alive;
  if (!hasAnyMark) return null;

  return (
    <div className="marks">
      {[...directionCounts.entries()].map(([arrow, count]) => (
        <span key={arrow} className="mark" title="Vote cast, toward the target's seat">
          {arrow}
          {count}
        </span>
      ))}
      {votesReceived > 0 && (
        <span className="mark" title="Votes received">
          {"←"}
          {votesReceived}
        </span>
      )}
      {standAsides > 0 && (
        <span className="mark" title="Stood aside">
          {"∅"}
          {standAsides}
        </span>
      )}
      {losingSide > 0 && (
        <span className="mark" title="Losing side of a lynch">
          {"×"}
          {losingSide}
        </span>
      )}
      {!player.alive && (
        <span className="mark mark-dead" title="Eliminated">
          {"●"}
        </span>
      )}
    </div>
  );
}
