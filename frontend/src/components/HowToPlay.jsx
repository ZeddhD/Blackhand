import { useState } from "react";
import Letter from "./Letter";

// How to Play, replacing the old flat role glossary. Each beat is named
// after the real in-fiction phase it maps to (The Dark, First Light, The
// Room, The Table), so this doubles as a preview of what the player will
// actually see later, not just an abstract rules summary. Role behavior
// lives only inside "The Dark" now, in context, rather than its own
// separate list -- a deliberate choice, not an oversight.
const BEATS = [
  {
    title: "Before We Begin",
    teaser: "Some of you aren't who you say you are.",
    lines: [
      "You're one of several people at this table. Some of you are exactly who you say you are. One or more of you are not. They know exactly who else isn't, too. Nobody else does.",
    ],
  },
  {
    title: "The Dark",
    teaser: "Secret jobs happen here.",
    lines: [
      "Each night, the table goes quiet. If you have a job, this is when you do it. Quietly. Alone, or with your team.",
      "The Black Hand agrees, together, on one person to kill. Once per game, they can try something else instead: secretly recruit someone to join them.",
      "The Inspector checks one person. Guilty, or innocent.",
      "The Watchman protects one person from tonight's attack. Even themselves, but only once the whole game.",
      "Everyone else just waits. No talking. No hints.",
    ],
  },
  {
    title: "First Light",
    teaser: "You'll never be sure what really happened.",
    lines: [
      "Morning comes, and something gets announced. Listen close though: a kill that got blocked, a night where nobody was even targeted, and a secret recruitment that just worked all sound exactly the same. \"Nobody was killed last night.\" That's not a bug. That's the whole point. You're never allowed to be sure which one just happened.",
    ],
  },
  {
    title: "The Room",
    teaser: "Talk. Accuse. Everything's on the record.",
    lines: [
      "Now you talk. Accuse, defend, lie, listen. No mechanics here, just people. Every vote anyone has ever cast, this round or three rounds back, is written down forever and visible to everyone. Nothing gets boiled down into a verdict for you. You make the case yourself.",
    ],
  },
  {
    title: "The Table",
    teaser: "Point fingers. Most votes loses.",
    lines: [
      "When talk runs out, you point. Most votes loses. They're revealed as Black Hand or not, right there. A tie saves everyone, for now.",
    ],
  },
  {
    title: "How It Ends",
    teaser: "It's not about surviving. It's about numbers.",
    lines: [
      "Here's the part that trips people up. The Black Hand doesn't need to win a fight to the last player. They win the moment they equal or outnumber whoever's left at the table. The Table only wins by catching every single one of them first. Watch the numbers, not just the bodies.",
    ],
  },
];

function BeatLetter({ beat }) {
  const [open, setOpen] = useState(false);
  return (
    <Letter faction="table" className="setting-letter how-to-play-letter">
      <button type="button" className="setting-letter-toggle" onClick={() => setOpen((o) => !o)}>
        <div className="setting-letter-head">
          <h3>{beat.title}</h3>
          <span className="setting-letter-indicator t-whisper" aria-hidden="true">
            {open ? "CLOSE" : "OPEN"}
          </span>
        </div>
        {!open && <span className="t-record setting-summary">{beat.teaser}</span>}
      </button>
      {open && (
        <div className="setting-letter-body motion-unfolded">
          {beat.lines.map((line, i) => (
            <p key={i} className="how-to-play-line">
              {line}
            </p>
          ))}
        </div>
      )}
    </Letter>
  );
}

export default function HowToPlay() {
  return (
    <div className="how-to-play">
      <h2>How to Play</h2>
      {BEATS.map((beat) => (
        <BeatLetter key={beat.title} beat={beat} />
      ))}
    </div>
  );
}
