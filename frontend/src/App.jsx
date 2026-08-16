import { useEffect, useRef, useState } from "react";
import { useGameSocket } from "./useGameSocket";
import MafiaChat from "./components/MafiaChat";
import RoleConfig from "./components/RoleConfig";
import Timer from "./components/Timer";
import PlayerRow from "./components/PlayerRow";
import { ROLE_INFO, roleLabel } from "./roles";
import {
  isSoundEnabled,
  playDayChime,
  playDeathToll,
  playEliminated,
  playGameOverChime,
  playNightChime,
  playTick,
  playVoteChime,
  setSoundEnabled,
  unlockAudio,
} from "./sound";

// Must match engine.game.SKIP_VOTE exactly -- not a real player id.
const SKIP_VOTE = "skip";

function codeFromUrl() {
  const path = window.location.pathname.replace(/\//g, "");
  return path.length === 4 ? path.toUpperCase() : "";
}

const PHASE_CHIME = {
  night: playNightChime,
  day_discussion: playDayChime,
  voting: playVoteChime,
  game_over: playGameOverChime,
};

const PHASE_ANNOUNCEMENT = {
  night: "Night has fallen. Stay silent.",
  day_discussion: "Day discussion has begun.",
  voting: "Voting is open.",
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
  } = useGameSocket();

  const [name, setName] = useState("");
  const [joinCode, setJoinCode] = useState(codeFromUrl());
  const [selectedTarget, setSelectedTarget] = useState(null);
  const [soundOn, setSoundOn] = useState(true);
  const [announcement, setAnnouncement] = useState("");

  const prevPhase = useRef(null);
  const prevDead = useRef(false);
  const lastTick = useRef(null);
  const prevAlive = useRef({});
  const mainRef = useRef(null);

  useEffect(() => {
    setSelectedTarget(null);
  }, [state?.phase, state?.night_number]);

  useEffect(() => {
    document.body.dataset.phase = state?.phase || "title";
  }, [state?.phase]);

  const isDead = !!state && state.phase !== "lobby" && state.phase !== "game_over" && !state.your_alive;

  useEffect(() => {
    document.body.dataset.dead = isDead ? "true" : "false";
  }, [isDead]);

  useEffect(() => {
    if (!state) return;
    if (state.phase !== prevPhase.current) {
      prevPhase.current = state.phase;
      const chime = PHASE_CHIME[state.phase];
      if (chime) chime();
      setAnnouncement(PHASE_ANNOUNCEMENT[state.phase] || `Phase changed: ${state.phase}`);
      // Move focus to the new phase's content so screen reader users land
      // somewhere meaningful instead of staying wherever focus was before.
      mainRef.current?.focus();
    }
  }, [state?.phase]);

  useEffect(() => {
    if (isDead && !prevDead.current) playEliminated();
    prevDead.current = isDead;
  }, [isDead]);

  useEffect(() => {
    if (!state) return;
    const prev = prevAlive.current;
    const newlyDead = state.players.filter((p) => prev[p.id] === true && !p.alive && p.id !== playerId);
    if (newlyDead.length > 0) playDeathToll();
    const next = {};
    state.players.forEach((p) => {
      next[p.id] = p.alive;
    });
    prevAlive.current = next;
  }, [state?.players, playerId]);

  useEffect(() => {
    if (!timer || timer.secondsLeft == null) return;
    if (timer.secondsLeft <= 10 && timer.secondsLeft !== lastTick.current) {
      lastTick.current = timer.secondsLeft;
      playTick();
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
        <h1 className="title">MAFIA</h1>
        <p className="credit">made by ZeddhD</p>
        <p className="muted">{connected ? "Ready." : "Connecting..."}</p>
        <div className="card">
          <div className="card-tab tab-brass">Join</div>
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

  return (
    <div className="screen">
      <header className="topbar">
        <span className="room-code">Room {roomCode}</span>
        <div className="topbar-right">
          {timer && timer.phase === state.phase && timer.secondsLeft != null && (
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
        <div className="card">
          <div className="card-tab tab-brass">Your Role</div>
          <p className="role-badge">
            You are: <strong>{roleLabel(state.your_role)}</strong>
          </p>
          <p className="role-secret">Do not reveal your role until the game ends.</p>
          {state.allies?.length > 0 && (
            <p className="muted">Fellow Mafia: {state.allies.join(", ")}</p>
          )}
          {state.known_mafia?.length > 0 && (
            <p className="muted">You secretly know the Mafia: {state.known_mafia.join(", ")}</p>
          )}
        </div>
      )}

      {isDead && <DeadPanel state={state} />}

      {!isDead && state.phase === "night" && (
        <NightPanel
          state={state}
          others={others}
          selectedTarget={selectedTarget}
          setSelectedTarget={setSelectedTarget}
          nightAction={nightAction}
        />
      )}

      {!isDead && state.your_role === "mafia" && state.phase === "night" && (
        <MafiaChat messages={mafiaChat} onSend={sendMafiaChat} />
      )}

      {!isDead && state.phase === "day_discussion" && (
        <div className="card">
          <div className="card-tab tab-brass">Day</div>
          <h2>Day Discussion</h2>
          <p className="muted">Talk it out over voice. Voting starts when the timer ends.</p>
          <ul className="player-list">
            {state.players.map((p) => (
              <li key={p.id}>
                <PlayerRow name={p.name} dead={!p.alive} offline={state.connected?.[p.id] === false} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {!isDead && state.phase === "voting" && (
        <div className="card">
          <div className="card-tab tab-blood">Vote</div>
          <h2>Vote to Remove a Player</h2>
          <p className="muted">
            Voting ends when the timer runs out, or as soon as everyone has voted.
          </p>
          {state.votes_total != null && (
            <p className="night-progress">
              {state.votes_done} / {state.votes_total} players have voted
            </p>
          )}
          <ul className="player-list">
            {alivePlayers.map((p) => (
              <li key={p.id}>
                <PlayerRow
                  name={p.name}
                  danger
                  selected={state.votes[playerId] === p.id}
                  tag={state.votes[playerId] === p.id ? "YOUR VOTE" : null}
                  offline={state.connected?.[p.id] === false}
                  onClick={() => vote(p.id)}
                />
              </li>
            ))}
          </ul>
          <button
            className={state.votes[playerId] === SKIP_VOTE ? "selected" : "ghost"}
            onClick={() => vote(SKIP_VOTE)}
          >
            Skip My Vote
          </button>
        </div>
      )}

      {state.phase === "game_over" && (
        <GameOverPanel state={state} onReturnToLobby={returnToLobby} onLeave={leaveRoom} />
      )}
      </div>

      <EventLog events={state.events} privateLog={state.private_log} />
    </div>
  );
}

function RoleExplainer() {
  return (
    <div className="card role-explainer">
      <div className="card-tab tab-steel">How to Play</div>
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
  const [roleCounts, setRoleCounts] = useState({ mafia: 1, detective: 1, doctor: 1, godfather: 0 });
  const [discussion, setDiscussion] = useState(60);
  const [voting, setVoting] = useState(60);

  return (
    <div className="card">
      <div className="card-tab tab-brass">Lobby</div>
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

function NightPanel({ state, others, selectedTarget, setSelectedTarget, nightAction }) {
  const role = state.your_role;
  const actionByRole = { mafia: "kill", doctor: "protect", detective: "investigate" };
  const actionType = actionByRole[role];

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
  const selectedId = role === "mafia" ? state.mafia_kill_target_id : selectedTarget;

  return (
    <div className="card">
      <div className="card-tab tab-blood">Night</div>
      <div className="silent-banner compact">
        <p className="silent-banner-text">STAY SILENT</p>
      </div>
      <h2>{ACTION_TITLE[actionType]}</h2>
      {role === "mafia" && (
        <p className="muted">
          {state.mafia_kill_target_name
            ? `Team target: ${state.mafia_kill_target_name}. Any Mafia member can change it.`
            : "No target chosen yet."}
        </p>
      )}
      {progress}
      <ul className="player-list">
        {targets.map((p) => (
          <li key={p.id}>
            <PlayerRow
              name={p.name}
              danger={actionType === "kill"}
              selected={selectedId === p.id}
              offline={state.connected?.[p.id] === false}
              onClick={() => {
                setSelectedTarget(p.id);
                nightAction(actionType, p.id);
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
      <div className="card-tab tab-blood">Eliminated</div>
      <span className="eliminated-stamp">ELIMINATED</span>
      <p className="dead-panel-sub">You cannot talk or use voice chat for the rest of the game.</p>
      <p className="muted">You can now see everything that happens, round by round.</p>
      <RoundLog log={state.round_log} />
    </div>
  );
}

function RoundLog({ log }) {
  if (!log?.length) return null;
  return (
    <div className="round-log">
      <h3>Case Log</h3>
      {log.map((round, i) => (
        <div key={i} className="round-log-entry">
          <p className="round-log-title">{round.title}</p>
          {round.lines.map((line, j) => (
            <p key={j} className="round-log-line">
              {line}
            </p>
          ))}
        </div>
      ))}
    </div>
  );
}

function GameOverPanel({ state, onReturnToLobby, onLeave }) {
  const mafiaWon = state.winner === "mafia";
  return (
    <div className="card center">
      <div className={`card-tab ${mafiaWon ? "tab-blood" : "tab-brass"}`}>Case Closed</div>
      <h1 className="title">{mafiaWon ? "Mafia Win" : "Civilians Win"}</h1>
      {mafiaWon ? (
        <>
          <p className="muted">The winning Mafia:</p>
          <p className="winner-names">{state.mafia_reveal?.join(", ")}</p>
        </>
      ) : (
        <>
          <p className="muted">The Mafia were caught. They were:</p>
          <p className="winner-names">{state.mafia_reveal?.join(", ") || "no one"}</p>
        </>
      )}
      <RoundLog log={state.round_log} />
      <div className="game-over-actions">
        <button
          className="primary"
          onClick={() => {
            if (window.confirm("Return everyone in this room to the lobby for a rematch?")) {
              onReturnToLobby();
            }
          }}
        >
          Return to Lobby
        </button>
        <button
          className="ghost"
          onClick={() => {
            if (window.confirm("Leave this game and return to the title screen?")) {
              onLeave();
            }
          }}
        >
          Leave Game
        </button>
      </div>
    </div>
  );
}

function EventLog({ events, privateLog }) {
  if (!events?.length && !privateLog?.length) return null;
  return (
    <div className="card log">
      <div className="card-tab tab-steel">Log</div>
      {privateLog?.map((msg, i) => (
        <p key={`p${i}`} className="private-log">
          {msg}
        </p>
      ))}
      {events?.map((msg, i) => (
        <p key={`e${i}`}>{msg}</p>
      ))}
    </div>
  );
}
