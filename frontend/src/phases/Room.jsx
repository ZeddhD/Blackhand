import Letter from "../components/Letter";
import Timer from "../components/Timer";

// The Room (section 6.6). Discussion. A vertical feed of every player's
// letter, carrying whatever marks they have accumulated so far, and
// nothing else: no vote, no target, no app input at all. Voice does the
// work here. "The loosest phase in the game, deliberately."
export default function Room({ players, connected, ledger, timer, discussionSeconds }) {
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
              <PlayerMarks player={p} ledger={ledger} discussionSeconds={discussionSeconds} />
            </Letter>
          </li>
        ))}
      </ul>
    </div>
  );
}

// Accretion marks (section 6.12). Never cleaned, never summarized into a
// score: raw counts and a bar, exactly what the Ledger already tracks.
// True directional marks toward a target's seat position need seat
// angles, which don't exist until The Crossing assigns them (Phase 10),
// so these render as plain counts for now, not compass directions.
function PlayerMarks({ player, ledger, discussionSeconds }) {
  const votes = ledger?.votes ?? [];
  const cast = votes.filter((v) => v.voter_id === player.id);
  const standAsides = cast.filter((v) => v.target_id === null).length;
  const votesCast = cast.length - standAsides;
  const votesReceived = votes.filter((v) => v.target_id === player.id).length;
  const losingSide = ledger?.losing_side_counts?.[player.id] ?? 0;
  const speaking = ledger?.speaking_seconds?.[player.id] ?? 0;
  const speakingPct = Math.min(100, (speaking / (discussionSeconds || 60)) * 100);

  const hasAnyMark = votesCast || votesReceived || standAsides || losingSide || speaking || !player.alive;
  if (!hasAnyMark) return null;

  return (
    <div className="marks">
      {votesCast > 0 && (
        <span className="mark" title="Votes cast">
          {"→"}
          {votesCast}
        </span>
      )}
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
      {speaking > 0 && (
        <span className="mark-bar" title="Speaking time">
          <span className="mark-bar-fill" style={{ width: `${speakingPct}%` }} />
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
