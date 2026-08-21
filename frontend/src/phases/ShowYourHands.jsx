import Avatar from "../components/Avatar";

// Show Your Hands (section 6.10). "Not a phase change. It happens
// inside the ring, which is why it feels like the table calling itself
// to order rather than a new screen appearing." Reuses the exact same
// ring container and seat layout as The Table, but seats are a passive
// roster here, not a target: the only affordance is the question
// itself. The result ("N HOLD, M CALL IT") is a public event once
// resolved, shown the normal way once this screen hands off, not
// re-announced here.
export default function ShowYourHands({ state, seatOrder, timer, submitVote }) {
  const order = seatOrder && seatOrder.length ? seatOrder : state.players.map((p) => p.id);
  const byId = Object.fromEntries(state.players.map((p) => [p.id, p]));

  const myVote = state.show_hands_your_vote;
  const secondsLeft = timer?.phase === "show_hands" ? timer.secondsLeft : null;

  return (
    <div className="table-screen">
      <div className="table-ring-wrap">
        <div className="table-ring" aria-hidden="true">
          {order.map((id, i) => {
            const player = byId[id];
            if (!player) return null;
            const angle = (360 / order.length) * i - 90;
            const radians = (angle * Math.PI) / 180;
            const left = 50 + 42 * Math.cos(radians);
            const top = 50 + 42 * Math.sin(radians);
            const style = { left: `${left}%`, top: `${top}%` };

            if (!player.alive) {
              return <span key={id} className="table-seat table-seat-empty" style={style} />;
            }
            return (
              <span key={id} className="table-seat" style={style}>
                <Avatar name={player.name} />
                <span className="table-seat-name">{player.name}</span>
              </span>
            );
          })}
        </div>
      </div>

      <div className="show-hands-question">
        <p className="t-said">Do you believe the Black Hand is gone?</p>
        {secondsLeft != null && <p className="show-hands-timer t-record">{secondsLeft}</p>}
        <div className="show-hands-controls">
          <button
            type="button"
            className="show-hands-choice"
            disabled={myVote != null}
            data-selected={myVote === "hold"}
            onClick={() => submitVote("hold")}
          >
            Hold
          </button>
          <button
            type="button"
            className="show-hands-choice"
            disabled={myVote != null}
            data-selected={myVote === "call_it"}
            onClick={() => submitVote("call_it")}
          >
            Call It
          </button>
        </div>
        {myVote != null && (
          <p className="muted show-hands-waiting">
            {state.show_hands_done} / {state.show_hands_total} have answered.
          </p>
        )}
      </div>
    </div>
  );
}
