import { useState } from "react";
import Letter from "../components/Letter";
import Mark from "../components/Mark";
import RoleConfig from "../components/RoleConfig";

const NUMBER_WORDS = [
  "Zero", "One", "Two", "Three", "Four", "Five", "Six",
  "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
];

function wordFor(n) {
  return NUMBER_WORDS[n] || String(n);
}

// Copy pattern, section 6.1: "Seven at the table. Three more before we
// begin." The document only gives the waiting case; the ready case below
// is this project's own plain, declarative continuation of that register.
function tableCopy(count) {
  const here = wordFor(count);
  if (count < 6) {
    return `${here} at the table. ${wordFor(6 - count)} more before we begin.`;
  }
  return `${here} at the table. Ready to begin.`;
}

// A configuration setting as its own letter, per section 7.4: "each
// setting is a small letter on the table that unfolds when tapped."
// Non-hosts get read-only paper (7.4): summary is all they ever see,
// children (the editable body) never renders for them at all.
function SettingLetter({ label, summary, isHost, children }) {
  const [open, setOpen] = useState(false);

  if (!isHost) {
    return (
      <Letter faction="table" className="setting-letter">
        <h3>{label}</h3>
        <div className="t-record setting-summary">{summary}</div>
      </Letter>
    );
  }

  return (
    <Letter faction="table" className="setting-letter">
      <button type="button" className="setting-letter-toggle" onClick={() => setOpen((o) => !o)}>
        <div className="setting-letter-head">
          <h3>{label}</h3>
          <span className="setting-letter-indicator t-whisper" aria-hidden="true">
            {open ? "CLOSE" : "OPEN"}
          </span>
        </div>
        {!open && <span className="t-record setting-summary">{summary}</span>}
      </button>
      {open && <div className="setting-letter-body motion-unfolded">{children}</div>}
    </Letter>
  );
}

function LobbyRoster({ players, connected }) {
  return (
    <div className="lobby-roster">
      {players.map((p) => (
        <div key={p.id} className="lobby-roster-letter">
          <span className="t-record">{p.name}</span>
          {connected?.[p.id] === false && <span className="player-row-offline"> OFFLINE</span>}
        </div>
      ))}
    </div>
  );
}

// The Waiting Room (section 6.1). Room ground, minimal paper, the
// stacked logo and the room code are the only large things on screen.
export default function WaitingRoom({ state, isHost, onStart, onLeave, roomCode }) {
  const [roleCounts, setRoleCounts] = useState({ hand: 1, inspector: 1, watchman: 1 });
  const [discussion, setDiscussion] = useState(60);
  const [showHandsEnabled, setShowHandsEnabled] = useState(true);
  const [showHandsThreshold, setShowHandsThreshold] = useState(6);

  const playerCount = state.players.length;
  const canStart = playerCount >= 6 && playerCount <= 12;

  return (
    <div className="waiting-room">
      <Mark lockup="stacked" size={80} />
      <p className="room-code-big t-event">{roomCode}</p>
      <p className="muted center">{tableCopy(playerCount)}</p>

      <LobbyRoster players={state.players} connected={state.connected} />

      <SettingLetter
        label="Hand Count"
        isHost={isHost}
        summary={<RoleConfig roleCounts={roleCounts} playerCount={playerCount} readOnly />}
      >
        <RoleConfig roleCounts={roleCounts} setRoleCounts={setRoleCounts} playerCount={playerCount} />
      </SettingLetter>

      <SettingLetter label="Discussion" isHost={isHost} summary={`${discussion}s`}>
        <div className="row">
          <label>Seconds</label>
          <div className="row-controls">
            <button type="button" onClick={() => setDiscussion((s) => Math.max(15, s - 15))}>
              -
            </button>
            <span>{discussion}</span>
            <button type="button" onClick={() => setDiscussion((s) => Math.min(600, s + 15))}>
              +
            </button>
          </div>
        </div>
        <p className="muted">15 to 600 seconds. The Table's own 45 seconds is fixed, not configurable.</p>
      </SettingLetter>

      <SettingLetter
        label="Show Your Hands"
        isHost={isHost}
        summary={showHandsEnabled ? `On, at ${showHandsThreshold} players or fewer` : "Off"}
      >
        <div className="row">
          <label>Enabled</label>
          <button
            type="button"
            className={showHandsEnabled ? "selected" : "ghost"}
            onClick={() => setShowHandsEnabled((v) => !v)}
          >
            {showHandsEnabled ? "On" : "Off"}
          </button>
        </div>
        {showHandsEnabled && (
          <div className="row">
            <label>Threshold</label>
            <div className="row-controls">
              <button
                type="button"
                onClick={() => setShowHandsThreshold((t) => Math.max(5, t - 1))}
              >
                -
              </button>
              <span>{showHandsThreshold}</span>
              <button
                type="button"
                onClick={() => setShowHandsThreshold((t) => Math.min(7, t + 1))}
              >
                +
              </button>
            </div>
          </div>
        )}
      </SettingLetter>

      {isHost ? (
        <button
          type="button"
          className="primary"
          disabled={!canStart}
          onClick={() =>
            onStart(roleCounts, { discussion }, { enabled: showHandsEnabled, threshold: showHandsThreshold })
          }
        >
          Start Game
        </button>
      ) : (
        <p className="muted center">Waiting for the host to start.</p>
      )}
      <button type="button" className="ghost" onClick={onLeave}>
        Leave Lobby
      </button>
    </div>
  );
}
