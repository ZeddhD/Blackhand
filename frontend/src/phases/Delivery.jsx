import Letter from "../components/Letter";
import { roleLabel } from "../roles";

// The Delivery (section 6.2). Role reveal, once per game, right as it
// starts. "The room drops to a single lamp. Every other letter goes
// dark. Yours unfolds." 4 seconds, no dismiss control, closes itself --
// App.jsx owns the 4 second timer and stops rendering this on its own,
// this component has no close button because none exists in the spec.
export default function Delivery({ state, isHandFaction }) {
  return (
    <div className="delivery-screen">
      <Letter faction={isHandFaction ? "hand" : "table"}>
        <h2>Your Role</h2>
        <p className="role-badge">
          You are: <strong>{roleLabel(state.your_role)}</strong>
        </p>
        <p className="role-secret">Do not reveal your role until the game ends.</p>
        {state.allies?.length > 0 && <p className="muted">Fellow Hand: {state.allies.join(", ")}</p>}
      </Letter>
    </div>
  );
}
