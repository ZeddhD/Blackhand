import Avatar from "./Avatar";

// Shared row for every place a player is listed and clickable (lobby roster,
// night targeting, voting). One component means the visual language for
// "this represents a person" never drifts between screens.
//
// There is no "dangerous action" color variant. A kill target and a
// protect target render identically -- the weight of a choice comes from
// its context and copy, never from a color (section 4.2: no red anywhere).
export default function PlayerRow({ name, onClick, selected, tag, disabled, offline, dead }) {
  const classes = ["player-row", selected ? "selected" : "primary"].filter(Boolean).join(" ");

  const content = (
    <>
      <Avatar name={name} />
      <span className="player-row-name">
        {name}
        {dead && <span className="player-row-dead"> (out)</span>}
      </span>
      {offline && <span className="player-row-offline">OFFLINE</span>}
      {tag && <span className="player-row-tag">{tag}</span>}
    </>
  );

  if (!onClick) {
    return <div className="player-row lobby-player">{content}</div>;
  }

  return (
    <button type="button" className={classes} onClick={onClick} disabled={disabled}>
      {content}
    </button>
  );
}
