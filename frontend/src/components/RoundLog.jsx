// The full detailed record (round-by-round kills, saves, investigations,
// offers, lynches), visible to dead players during play and to everyone
// at The Reading (section 6.11). Shared by DeadPanel and Reading so the
// two don't drift into two slightly different renderings of the same data.
export default function RoundLog({ log }) {
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
