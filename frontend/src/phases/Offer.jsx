import { useEffect, useState } from "react";
import Letter from "../components/Letter";
import { struckWire } from "../audio";

// The Offer (section 6.4). Once per game at most, almost nobody ever
// sees it. Full takeover, fully black room, one centered letter in the
// Black Hand's own colors, a struck wire that plays exactly once. This
// is rendered only for the one player the offer was actually made to;
// every other player's interface does not change in any way, which is
// enforced by App.jsx never mounting this component for anyone else.
export default function Offer({ timer, onRespond }) {
  const [responded, setResponded] = useState(false);

  useEffect(() => {
    struckWire();
  }, []);

  const secondsLeft = timer?.phase === "offer" ? timer.secondsLeft : null;

  const respond = (accepted) => {
    if (responded) return;
    setResponded(true);
    onRespond(accepted);
  };

  return (
    <div className="offer-screen">
      <Letter
        faction="hand"
        className={["offer-letter", responded ? "motion-taken" : ""].filter(Boolean).join(" ")}
      >
        {secondsLeft != null && <p className="offer-timer t-record">{secondsLeft}</p>}
        <p className="t-body">A hand was laid on you tonight.</p>
        <p className="t-body">
          You may take it, or you may refuse.
          <br />
          If you refuse, you will not see morning.
        </p>
        <p className="t-body">
          You will not learn whose hand it was
          <br />
          until after you have answered.
        </p>
        <div className="offer-controls">
          <button type="button" className="t-said offer-take" disabled={responded} onClick={() => respond(true)}>
            Take it
          </button>
          <button
            type="button"
            className="t-said offer-refuse"
            disabled={responded}
            onClick={() => respond(false)}
          >
            Refuse
          </button>
        </div>
      </Letter>
    </div>
  );
}
