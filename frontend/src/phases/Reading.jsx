import { useEffect, useState } from "react";
import Letter from "../components/Letter";
import Mark from "../components/Mark";
import RoundLog from "../components/RoundLog";
import { roleLabel } from "../roles";

const STAGGER_MS = 260;
const LETTER_UNFOLD_MS = 420;
const PAUSE_MS = 2000;

// The Reading (section 6.11). Everything rationed all game is spent
// here: every role, the full record, the offer's outcome if there was
// one, and last of all, alone, the one line that only exists when
// somebody refused. Belongs to THE ROOM's spatial grammar (section
// 4.9's own list: "lobby, dawn, discussion, results"), not THE TABLE,
// so this is a normal scrollable feed, not a full-screen takeover.
export default function Reading({ state, seatOrder, onReturnToLobby, onLeave }) {
  const order = seatOrder && seatOrder.length ? seatOrder : state.players.map((p) => p.id);
  const revealById = Object.fromEntries((state.role_reveal || []).map((r) => [r.id, r]));
  const offerOutcome = state.offer_outcome;
  const showsRefusal = !!offerOutcome && offerOutcome.accepted === false;
  const handWon = state.winner === "hand";

  const [stage, setStage] = useState("letters");

  useEffect(() => {
    const totalUnfoldMs = Math.max(0, (order.length - 1) * STAGGER_MS) + LETTER_UNFOLD_MS;
    const t = setTimeout(() => {
      setStage(showsRefusal ? "refusal" : "logo");
    }, totalUnfoldMs + PAUSE_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (stage !== "refusal") return;
    const t = setTimeout(() => setStage("logo"), 900);
    return () => clearTimeout(t);
  }, [stage]);

  return (
    <div className="reading">
      <h1 className="title center">{handWon ? "The Black Hand Wins" : "The Table Wins"}</h1>

      <ul className="reading-list">
        {order.map((id, i) => {
          const reveal = revealById[id];
          if (!reveal) return null;
          return (
            <li key={id}>
              <Letter
                faction="table"
                style={{ animationDelay: `${i * STAGGER_MS}ms` }}
                soundDelayMs={i * STAGGER_MS}
              >
                <span className="t-name">{reveal.name}</span>
                <p className="t-record reading-role">
                  {roleLabel(reveal.role)}
                  {reveal.marked ? " (recruited)" : ""}
                </p>
              </Letter>
            </li>
          );
        })}
      </ul>

      <RoundLog log={state.round_log} />

      {stage !== "letters" && showsRefusal && (
        <Letter faction="hand" className="reading-refusal">
          <p className="t-record">
            {offerOutcome.recipient_name} refused the hand on night {offerOutcome.night}.
          </p>
        </Letter>
      )}

      {stage === "logo" && (
        <>
          <Mark lockup="stacked" size={64} className="reading-mark" />
          <div className="game-over-actions">
            <button
              type="button"
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
              type="button"
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
        </>
      )}
    </div>
  );
}
