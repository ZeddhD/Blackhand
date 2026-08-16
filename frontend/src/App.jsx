import { useEffect, useState } from "react";
import { useGameSocket } from "./useGameSocket";
import MafiaChat from "./components/MafiaChat";
import RoleConfig from "./components/RoleConfig";
import Timer from "./components/Timer";

function codeFromUrl() {
  const path = window.location.pathname.replace(/\//g, "");
  return path.length === 4 ? path.toUpperCase() : "";
}

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
    nightAction,
    vote,
    sendMafiaChat,
    forceAdvance,
  } = useGameSocket();

  const [name, setName] = useState("");
  const [joinCode, setJoinCode] = useState(codeFromUrl());
  const [selectedTarget, setSelectedTarget] = useState(null);

  useEffect(() => {
    setSelectedTarget(null);
  }, [state?.phase, state?.night_number]);

  useEffect(() => {
    document.body.dataset.phase = state?.phase || "title";
  }, [state?.phase]);

  if (!state) {
    return (
      <div className="screen center">
        <h1 className="title">MAFIA</h1>
        <p className="muted">{connected ? "Ready." : "Connecting..."}</p>
        <div className="card">
          <input
            placeholder="Your name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button
            disabled={!connected || !name.trim()}
            onClick={() => createRoom(name.trim())}
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
              disabled={!connected || !name.trim() || joinCode.length !== 4}
              onClick={() => joinRoom(joinCode, name.trim())}
            >
              Join
            </button>
          </div>
        </div>
        {error && <p className="error">{error}</p>}
      </div>
    );
  }

  const isHost = state.is_host === true;
  const alivePlayers = state.players.filter((p) => p.alive);
  const others = state.players.filter((p) => p.id !== playerId);

  return (
    <div className="screen">
      <header className="topbar">
        <span className="room-code">Room {roomCode}</span>
        {timer && timer.phase === state.phase && timer.secondsLeft != null && (
          <Timer seconds={timer.secondsLeft} phase={timer.phase} />
        )}
      </header>

      {error && <p className="error">{error}</p>}

      {state.phase === "lobby" && (
        <Lobby
          state={state}
          isHost={isHost}
          onStart={startGame}
          onLeave={leaveRoom}
        />
      )}

      {state.phase !== "lobby" && state.phase !== "game_over" && (
        <div className="card">
          <p className="role-badge">
            You are: <strong>{state.your_role?.toUpperCase()}</strong>{" "}
            {!state.your_alive && <span className="dead">(dead)</span>}
          </p>
          {state.allies?.length > 0 && (
            <p className="muted">Fellow Mafia: {state.allies.join(", ")}</p>
          )}
          {state.known_mafia?.length > 0 && (
            <p className="muted">You secretly know the Mafia: {state.known_mafia.join(", ")}</p>
          )}
        </div>
      )}

      {state.phase === "night" && state.your_alive && (
        <NightPanel
          state={state}
          others={others}
          selectedTarget={selectedTarget}
          setSelectedTarget={setSelectedTarget}
          nightAction={nightAction}
        />
      )}

      {state.your_role === "mafia" && state.phase === "night" && (
        <MafiaChat messages={mafiaChat} onSend={sendMafiaChat} />
      )}

      {state.phase === "day_discussion" && (
        <div className="card center">
          <h2>Day Discussion</h2>
          <p className="muted">Talk it out over voice. Voting starts when the timer ends.</p>
        </div>
      )}

      {state.phase === "voting" && state.your_alive && (
        <div className="card">
          <h2>Vote to Lynch</h2>
          <ul className="player-list">
            {alivePlayers.map((p) => (
              <li key={p.id}>
                <button
                  className={state.votes[playerId] === p.id ? "selected" : ""}
                  onClick={() => vote(p.id)}
                >
                  {p.name} {state.votes[playerId] === p.id ? "(your vote)" : ""}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {state.phase === "game_over" && (
        <div className="card center">
          <h1 className="title">{state.winner === "town" ? "Town Wins" : "Mafia Wins"}</h1>
          <ul className="player-list">
            {state.players.map((p) => (
              <li key={p.id}>{p.name} {!p.alive && <span className="dead">(dead)</span>}</li>
            ))}
          </ul>
        </div>
      )}

      <EventLog events={state.events} privateLog={state.private_log} />

      {isHost && state.phase !== "lobby" && state.phase !== "game_over" && (
        <button className="ghost" onClick={forceAdvance}>
          Skip timer (host)
        </button>
      )}
    </div>
  );
}

function Lobby({ state, isHost, onStart, onLeave }) {
  const [roleCounts, setRoleCounts] = useState({ mafia: 1, detective: 1, doctor: 1, godfather: 0 });
  const [discussion, setDiscussion] = useState(60);
  const [voting, setVoting] = useState(60);

  return (
    <div className="card">
      <h2>Lobby</h2>
      <p className="muted">Share the code above. Players join at /{"<CODE>"} on their phones.</p>
      <ul className="player-list">
        {state.players.map((p) => (
          <li key={p.id} className="lobby-player">
            {p.name}
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
            <p className="muted">Night has no timer -- it ends once every active role has acted.</p>
          </div>
          <button
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

  return (
    <div className="card">
      <div className="silent-banner compact">
        <p className="silent-banner-text">STAY SILENT</p>
      </div>
      <h2>Night — {actionType}</h2>
      {progress}
      <ul className="player-list">
        {targets.map((p) => (
          <li key={p.id}>
            <button
              className={selectedTarget === p.id ? "selected" : ""}
              onClick={() => {
                setSelectedTarget(p.id);
                nightAction(actionType, p.id);
              }}
            >
              {p.name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EventLog({ events, privateLog }) {
  if (!events?.length && !privateLog?.length) return null;
  return (
    <div className="card log">
      {privateLog?.map((msg, i) => (
        <p key={`p${i}`} className="private-log">{msg}</p>
      ))}
      {events?.map((msg, i) => (
        <p key={`e${i}`}>{msg}</p>
      ))}
    </div>
  );
}
