import { roleLabel } from "../roles";

const CONFIGURABLE_ROLES = ["hand", "inspector", "watchman"];

// Section 3.1's table, 6 to 12 players. "Hand count: auto, or manual
// override" (section 7.1) -- this is the auto half.
const AUTO_TABLE = {
  6: { hand: 1, inspector: 1, watchman: 1 },
  7: { hand: 2, inspector: 1, watchman: 1 },
  8: { hand: 2, inspector: 1, watchman: 1 },
  9: { hand: 2, inspector: 1, watchman: 1 },
  10: { hand: 3, inspector: 1, watchman: 1 },
  11: { hand: 3, inspector: 1, watchman: 1 },
  12: { hand: 3, inspector: 1, watchman: 1 },
};

function autoRoleCounts(playerCount) {
  const clamped = Math.max(6, Math.min(12, playerCount));
  return AUTO_TABLE[clamped];
}

export default function RoleConfig({ roleCounts, setRoleCounts, playerCount, readOnly }) {
  const assigned = Object.values(roleCounts).reduce((a, b) => a + b, 0);
  const civilians = Math.max(0, playerCount - assigned);

  if (readOnly) {
    return (
      <p className="t-record">
        {CONFIGURABLE_ROLES.map((role) => `${roleCounts[role] || 0} ${roleLabel(role)}`).join(", ")}
        {", "}
        {civilians} Civilian{civilians === 1 ? "" : "s"}
      </p>
    );
  }

  return (
    <div className="role-config">
      {CONFIGURABLE_ROLES.map((role) => (
        <div className="row" key={role}>
          <label>{roleLabel(role)}</label>
          <button
            onClick={() =>
              setRoleCounts((r) => ({ ...r, [role]: Math.max(0, (r[role] || 0) - 1) }))
            }
          >
            -
          </button>
          <span>{roleCounts[role] || 0}</span>
          <button onClick={() => setRoleCounts((r) => ({ ...r, [role]: (r[role] || 0) + 1 }))}>
            +
          </button>
        </div>
      ))}
      <p className="muted">
        {civilians} civilian{civilians === 1 ? "" : "s"} fill the rest ({playerCount} players)
      </p>
      <button type="button" className="ghost" onClick={() => setRoleCounts(autoRoleCounts(playerCount))}>
        Auto
      </button>
    </div>
  );
}
