import { useCallback, useEffect, useRef, useState } from "react";

function wsUrl() {
  if (import.meta.env.DEV) return "ws://localhost:8000/ws";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

export function useGameSocket() {
  const [connected, setConnected] = useState(false);
  const [state, setState] = useState(null);
  const [mafiaChat, setMafiaChat] = useState([]);
  const [timer, setTimer] = useState(null);
  const [error, setError] = useState(null);
  const [roomCode, setRoomCode] = useState(null);
  const [playerId, setPlayerId] = useState(null);
  const wsRef = useRef(null);

  const send = useCallback((payload) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }, []);

  useEffect(() => {
    const ws = new WebSocket(wsUrl());
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      const savedRoom = localStorage.getItem("mafia_room_code");
      const savedPlayer = localStorage.getItem("mafia_player_id");
      if (savedRoom && savedPlayer) {
        ws.send(JSON.stringify({ type: "join", room_code: savedRoom, player_id: savedPlayer }));
      }
    };

    ws.onclose = () => setConnected(false);

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      switch (msg.type) {
        case "room_created":
        case "joined":
          setRoomCode(msg.room_code);
          setPlayerId(msg.player_id);
          localStorage.setItem("mafia_room_code", msg.room_code);
          localStorage.setItem("mafia_player_id", msg.player_id);
          window.history.replaceState(null, "", `/${msg.room_code}`);
          setError(null);
          break;
        case "state":
          setState(msg.state);
          if (msg.state.phase === "lobby") setMafiaChat([]);
          break;
        case "left":
          localStorage.removeItem("mafia_room_code");
          localStorage.removeItem("mafia_player_id");
          window.history.replaceState(null, "", "/");
          setState(null);
          setRoomCode(null);
          setPlayerId(null);
          setTimer(null);
          setMafiaChat([]);
          break;
        case "mafia_chat":
          setMafiaChat(msg.messages);
          break;
        case "timer":
          setTimer({ phase: msg.phase, secondsLeft: msg.seconds_left, totalSeconds: msg.total_seconds });
          break;
        case "error":
          setError(msg.message);
          break;
        default:
          break;
      }
    };

    return () => ws.close();
  }, []);

  const createRoom = useCallback((name) => send({ type: "create_room", name }), [send]);
  const joinRoom = useCallback((code, name) => send({ type: "join", room_code: code, name }), [send]);
  const startGame = useCallback(
    (roleCounts, timers, showHands) =>
      send({
        type: "start_game",
        role_counts: roleCounts,
        timers,
        show_hands_enabled: showHands?.enabled,
        show_hands_threshold: showHands?.threshold,
      }),
    [send]
  );
  const leaveRoom = useCallback(() => send({ type: "leave_room" }), [send]);
  const returnToLobby = useCallback(() => send({ type: "return_to_lobby" }), [send]);
  const nightAction = useCallback(
    (actionType, targetId) => send({ type: "night_action", action_type: actionType, target_id: targetId }),
    [send]
  );
  const vote = useCallback((targetId) => send({ type: "vote", target_id: targetId }), [send]);
  const sendMafiaChat = useCallback((text) => send({ type: "mafia_chat", text }), [send]);
  const respondToOffer = useCallback((accepted) => send({ type: "offer_response", accepted }), [send]);
  const submitShowHandsVote = useCallback((choice) => send({ type: "show_hands_vote", choice }), [send]);

  return {
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
    submitShowHandsVote,
  };
}
