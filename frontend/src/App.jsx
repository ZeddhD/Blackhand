import { useEffect, useRef, useState } from "react";
import { useGameSocket } from "./useGameSocket";
import Letter from "./components/Letter";
import MafiaChat from "./components/MafiaChat";
import Mark from "./components/Mark";
import RoleConfig from "./components/RoleConfig";
import Timer from "./components/Timer";
import PlayerRow from "./components/PlayerRow";
import Room from "./phases/Room";
import Crossing from "./phases/Crossing";
import Table from "./phases/Table";
import Offer from "./phases/Offer";
import Reading from "./phases/Reading";
import RoundLog from "./components/RoundLog";
import { ROLE_INFO, roleLabel } from "./roles";
import {
  clockTick,
  crossfadeBedTo,
  isSoundEnabled,
  penStroke,
  phaseChange,
  reconcileDeadCount,
  setSoundEnabled,
  startBed,
  startLobbyAmbient,
  stopBed,
  stopLobbyAmbient,
  theCrossing,
  unlockAudio,
} from "./audio";

function codeFromUrl() {
  const path = window.location.pathname.replace(/\//g, "");
  return path.length === 4 ? path.toUpperCase() : "";
}

const PHASE_ANNOUNCEMENT = {
  night: "Night has fallen. Stay silent.",
  day_discussion: "Day discussion has begun.",
  voting: "Voting is open.",
  show_hands: "Show Your Hands has begun.",
  offer: "The Offer is being made.",
  game_over: "The game has ended.",
};

export default function App() {
  const {
    connected,
    state,
    mafiaChat,
    timer,
    error,
    roomCode,
    playerId,
    createRoom,
    joinRoom,
    startGame,
    leaveRoom,
    returnToLobby,
    nightAction,
    vote,
    sendMafiaChat,
    respondToOffer,
  } = useGameSocket();

  const [name, setName] = useState("");
  const [joinCode, setJoinCode] = useState(codeFromUrl());
  const [selectedTarget, setSelectedTarget] = useState(null);
  const [soundOn, setSoundOn] = useState(true);
  const [announcement, setAnnouncement] = useState("");

  const prevPhase = useRef(null);
  const lastTick = useRef(null);
  const mainRef = useRef(null);
  const seatOrderRef = useRef(null);
  const prevPhaseForCrossing = useRef(null);
  const [showCrossing, setShowCrossing] = useState(false);

  useEffect(() => {
    setSelectedTarget(null);
  }, [state?.phase, state?.night_number]);

  useEffect(() => {
    document.body.dataset.phase = state?.phase || "title";
  }, [state?.phase]);

  // Seats never reorder (section 6.8): captured once from the first roster
  // seen after the game starts, then reused for the rest of the game
  // regardless of what order the server's own player list is in later.
  useEffect(() => {
    if (!state) return;
    if (state.phase === "lobby") {
      seatOrderRef.current = null;
      return;
    }
    if (!seatOrderRef.current) {
      seatOrderRef.current = state.players.map((p) => p.id);
    }
  }, [state?.phase, state?.players]);

  // The Crossing (section 6.7) is a fixed 3 second beat with no engine
  // phase of its own: the server moves straight from day_discussion to
  // voting, so this is a client-side hold in front of the Table, timed
  // independently of prevPhase below to avoid depending on effect order.
  useEffect(() => {
    if (!state) return;
    const was = prevPhaseForCrossing.current;
    prevPhaseForCrossing.current = state.phase;
    if (state.phase === "voting" && was === "day_discussion") {
      setShowCrossing(true);
      theCrossing();
      const t = setTimeout(() => setShowCrossing(false), 3000);
      return () => clearTimeout(t);
    }
  }, [state?.phase]);

  const isDead = !!state && state.phase !== "lobby" && state.phase !== "game_over" && !state.your_alive;

  useEffect(() => {
    document.body.dataset.dead = isDead ? "true" : "false";
  }, [isDead]);

  // Phase changes drive both the generic transition cue and the ambient
  // bed's crossfade (section 4.10). day_discussion -> voting is the one
  // exception: that transition gets the Crossing's own sound instead of
  // the generic one, played by the effect above. Leaving or entering the
  // lobby also starts or stops the two separate ambient systems: the
  // lobby's human murmur (section 6.1) never plays once the game starts,
  // and never returns after it does.
  useEffect(() => {
    if (!state) return;
    if (state.phase !== prevPhase.current) {
      const cameFrom = prevPhase.current;
      prevPhase.current = state.phase;

      if (state.phase === "lobby") {
        stopBed();
        startLobbyAmbient();
      } else {
        if (cameFrom === "lobby" || cameFrom === null) {
          stopLobbyAmbient();
          startBed();
        }
        if (!(state.phase === "voting" && cameFrom === "day_discussion")) {
          phaseChange();
        }
        crossfadeBedTo(state.phase);
      }

      setAnnouncement(PHASE_ANNOUNCEMENT[state.phase] || `Phase changed: ${state.phase}`);
      // Move focus to the new phase's content so screen reader users land
      // somewhere meaningful instead of staying wherever focus was before.
      mainRef.current?.focus();
    }
  }, [state?.phase]);

  // Death, section 4.10: driven by the server's own dead count, not by
  // locally diffing individual state updates, so a batch of simultaneous
  // deaths or a mid-game reconnect can't under- or double-count layers.
  useEffect(() => {
    if (!state) return;
    reconcileDeadCount(state.players.filter((p) => !p.alive).length);
  }, [state?.players]);

  useEffect(() => {
    if (!state) {
      stopBed();
      stopLobbyAmbient();
    }
  }, [state]);

  useEffect(() => {
    if (!timer || timer.secondsLeft == null) return;
    if (timer.secondsLeft <= 10 && timer.secondsLeft !== lastTick.current) {
      lastTick.current = timer.secondsLeft;
      clockTick();
    }
  }, [timer?.secondsLeft]);

  const toggleSound = () => {
    const next = !soundOn;
    setSoundOn(next);
    setSoundEnabled(next);
    if (next) unlockAudio();
  };

  if (!state) {
    return (
      <div className="screen center">
        <h1 className="title">BLACKHAND</h1>
        <p className="credit">made by ZeddhD</p>
        <p className="muted">{connected ? "Ready." : "Connecting..."}</p>
        <div className="card">
          <h2>Join</h2>
          <input
            placeholder="Your name"
            maxLength={24}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button
            className="primary"
            disabled={!connected || !name.trim()}
            onClick={() => {
              unlockAudio();
              createRoom(name.trim());
            }}
          >
            Host a new game
          </button>
          <div className="row">
            <input
              placeholder="ROOM CODE"
              maxLength={4}
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
            />
            <button
              className="primary"
              disabled={!connected || !name.trim() || joinCode.length !== 4}
              onClick={() => {
                unlockAudio();
                joinRoom(joinCode, name.trim());
              }}
            >
              Join
            </button>
          </div>
        </div>
        {error && <p className="error">{error}</p>}
        <RoleExplainer />
      </div>
    );
  }

  const alivePlayers = state.players.filter((p) => p.alive);
  const others = state.players.filter((p) => p.id !== playerId);
  const isHost = state.is_host === true;
  const isHandFaction = state.your_role === "hand" || state.marked;

  // The Table takes over the entire screen: no topbar, no event log, no
  // navigation reachable while it's up (section 6.8). The sr-only live
  // region is duplicated here rather than restructured into, since it's
  // an accessibility channel, not part of "the rest of the application."
  if (!isDead && state.phase === "voting") {
    return (
      <>
        <div className="sr-only" role="status" aria-live="polite">
          {announcement}
        </div>
        {showCrossing ? (
          <Crossing seatCount={(seatOrderRef.current || alivePlayers.map((p) => p.id)).length} />
        ) : (
          <Table state={state} seatOrder={seatOrderRef.current} playerId={playerId} timer={timer} vote={vote} />
        )}
      </>
    );
  }

  // The Offer (section 6.4) is rendered only for the one player it was
  // actually made to. Everyone else -- including the Hand who sent it --
  // keeps seeing whatever they were already looking at: state.phase is
  // "offer" for them too, but offer_pending is only ever true for the
  // recipient, so displayPhase below quietly treats it as still "night"
  // for anyone it wasn't sent to. "No other player's interface changes
  // in any way" is enforced by never mounting this component for them.
  if (state.offer_pending) {
    return (
      <>
        <div className="sr-only" role="status" aria-live="polite">
          {announcement}
        </div>
        <Offer timer={timer} onRespond={respondToOffer} />
      </>
    );
  }

  const displayPhase = state.phase === "offer" ? "night" : state.phase;

  return (
    <div className="screen">
      <header className="topbar">
        <span className="room-code">Room {roomCode}</span>
        <div className="topbar-right">
          {timer &&
            timer.phase === state.phase &&
            timer.secondsLeft != null &&
            state.phase !== "day_discussion" && (
              <Timer seconds={timer.secondsLeft} total={timer.totalSeconds} phase={timer.phase} />
            )}
          <button className="sound-toggle" onClick={toggleSound}>
            {soundOn ? "Sound On" : "Sound Off"}
          </button>
        </div>
      </header>

      <div className="sr-only" role="status" aria-live="polite">
        {announcement}
      </div>

      {error && <p className="error">{error}</p>}

      <div ref={mainRef} tabIndex={-1}>
      {state.phase === "lobby" && (
        <Lobby state={state} isHost={isHost} onStart={startGame} onLeave={leaveRoom} roomCode={roomCode} />
      )}

      {state.phase !== "lobby" && state.phase !== "game_over" && (
        <Letter faction={isHandFaction ? "hand" : "table"}>
          <h2>Your Role</h2>
          <p className="role-badge">
            You are: <strong>{roleLabel(state.your_role)}</strong>
          </p>
          <p className="role-secret">Do not reveal your role until the game ends.</p>
          {state.allies?.length > 0 && (
            <p className="muted">Fellow Hand: {state.allies.join(", ")}</p>
          )}
        </Letter>
      )}

      <InvestigationLetters log={state.private_log} />

      {isDead && <DeadPanel state={state} />}

      {!isDead && displayPhase === "night" && (
        <NightPanel
          state={state}
          others={others}
          isHandFaction={isHandFaction}
          selectedTarget={selectedTarget}
          setSelectedTarget={setSelectedTarget}
          nightAction={nightAction}
        />
      )}

      {!isDead && isHandFaction && displayPhase === "night" && (
        <MafiaChat messages={mafiaChat} onSend={sendMafiaChat} />
      )}

      {!isDead && state.phase === "day_discussion" && (
        <Room
          players={state.players}
          connected={state.connected}
          ledger={state.ledger}
          timer={timer}
          discussionSeconds={timer?.phase === "day_discussion" ? timer.totalSeconds : undefined}
        />
      )}

      {state.phase === "game_over" && (
        <Reading state={state} seatOrder={seatOrderRef.current} onReturnToLobby={returnToLobby} onLeave={leaveRoom} />
      )}
      </div>

      <EventLog events={state.events} />
    </div>
  );
}

function RoleExplainer() {
  return (
    <div className="card role-explainer">
      <h2>Roles</h2>
      {Object.values(ROLE_INFO).map((r) => (
        <div key={r.key} className="role-explainer-item">
          <p className="role-explainer-name">{r.label}</p>
          <p className="muted">{r.text}</p>
        </div>
      ))}
    </div>
  );
}

function Lobby({ state, isHost, onStart, onLeave, roomCode }) {
  const [roleCounts, setRoleCounts] = useState({ hand: 1, inspector: 1, watchman: 1 });
  const [discussion, setDiscussion] = useState(60);
  const [voting, setVoting] = useState(60);

  return (
    <div className="card">
      <Mark lockup="stacked" size={64} className="mark-on-paper" />
      <h2>Waiting Room</h2>
      <p className="muted">
        Share the code above. Players join at <span className="room-code">{roomCode}</span> on their devices.
      </p>
      <ul className="player-list">
        {state.players.map((p) => (
          <li key={p.id}>
            <PlayerRow name={p.name} offline={state.connected?.[p.id] === false} />
          </li>
        ))}
      </ul>
      {isHost ? (
        <>
          <RoleConfig roleCounts={roleCounts} setRoleCounts={setRoleCounts} playerCount={state.players.length} />
          <div className="role-config">
            <h3>Timers</h3>
            <div className="row">
              <label>Discussion (sec)</label>
              <input
                type="number"
                min={15}
                max={600}
                value={discussion}
                onChange={(e) => setDiscussion(e.target.value)}
              />
            </div>
            <div className="row">
              <label>Voting (sec)</label>
              <input type="number" min={15} max={600} value={voting} onChange={(e) => setVoting(e.target.value)} />
            </div>
            <p className="muted">Night has no timer. It ends once every active role has acted.</p>
          </div>
          <button
            className="primary"
            disabled={state.players.length < 4}
            onClick={() => onStart(roleCounts, { discussion, voting })}
          >
            Start Game
          </button>
        </>
      ) : (
        <p className="muted">Waiting for the host to start...</p>
      )}
      <button className="ghost" onClick={onLeave}>
        Leave Lobby
      </button>
    </div>
  );
}

const ACTION_TITLE = {
  kill: "Choose someone to kill",
  protect: "Choose someone to protect",
  investigate: "Choose someone to investigate",
};

function NightPanel({ state, others, isHandFaction, selectedTarget, setSelectedTarget, nightAction }) {
  // A Marked player's literal role never changes, only effective faction
  // does (engine/models.py's effective_faction), so this checks that, not
  // state.your_role directly -- a recruit who accepted the Offer must see
  // the Hand's kill target UI on every night after, not "STAY SILENT."
  // Hand's night action defaults to a kill target here; choosing the Offer
  // instead (section 2.3) has no UI yet, that's the sender's side of this
  // same beat and still has no control -- the Offer screen itself (this
  // phase) only builds the recipient's side.
  const actionType = isHandFaction
    ? "kill"
    : state.your_role === "watchman"
      ? "protect"
      : state.your_role === "inspector"
        ? "investigate"
        : null;

  const progress =
    state.night_actions_total != null ? (
      <p className="night-progress">
        {state.night_actions_done} / {state.night_actions_total} players have acted
      </p>
    ) : null;

  if (!actionType) {
    return (
      <div className="silent-banner">
        <p className="silent-banner-text">STAY SILENT</p>
        <p className="muted">The active roles are deciding. No talking until day.</p>
        {progress}
      </div>
    );
  }

  const targets = actionType === "protect" ? state.players.filter((p) => p.alive) : others.filter((p) => p.alive);
  const selectedId = isHandFaction ? state.hand_target_id : selectedTarget;

  return (
    <div className="card">
      <div className="silent-banner compact">
        <p className="silent-banner-text">STAY SILENT</p>
      </div>
      <h2>{ACTION_TITLE[actionType]}</h2>
      {isHandFaction && (
        <p className="muted">
          {state.hand_target_name
            ? `Team target: ${state.hand_target_name}. Any Hand member can change it.`
            : "No target chosen yet."}
        </p>
      )}
      {progress}
      <ul className="player-list">
        {targets.map((p) => (
          <li key={p.id}>
            <PlayerRow
              name={p.name}
              selected={selectedId === p.id}
              offline={state.connected?.[p.id] === false}
              onClick={() => {
                setSelectedTarget(p.id);
                nightAction(actionType, p.id);
                penStroke();
              }}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

function DeadPanel({ state }) {
  return (
    <div className="card dead-panel">
      <span className="eliminated-stamp">ELIMINATED</span>
      <p className="dead-panel-sub">You cannot talk or use voice chat for the rest of the game.</p>
      <p className="muted">You can now see everything that happens, round by round.</p>
      <RoundLog log={state.round_log} />
    </div>
  );
}

function InvestigationLetters({ log }) {
  if (!log?.length) return null;
  return (
    <>
      {log.map((msg, i) => (
        <Letter key={i} faction="table">
          <p className="private-log">{msg}</p>
        </Letter>
      ))}
    </>
  );
}

function EventLog({ events }) {
  if (!events?.length) return null;
  return (
    <div className="card log">
      {events.map((msg, i) => (
        <p key={i}>{msg}</p>
      ))}
    </div>
  );
}
