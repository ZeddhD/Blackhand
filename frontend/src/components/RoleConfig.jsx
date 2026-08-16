const CONFIGURABLE_ROLES = ["mafia", "detective", "doctor", "godfather"];

export default function RoleConfig({ roleCounts, setRoleCounts, playerCount }) {
  const assigned = Object.values(roleCounts).reduce((a, b) => a + b, 0);
  const villagers = Math.max(0, playerCount - assigned);

  return (
    <div className="role-config">
      <h3>Roles</h3>
      {CONFIGURABLE_ROLES.map((role) => (
        <div className="row" key={role}>
          <label>{role}</label>
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
      <p className="muted">{villagers} villager{villagers === 1 ? "" : "s"} fill the rest ({playerCount} players)</p>
    </div>
  );
}
