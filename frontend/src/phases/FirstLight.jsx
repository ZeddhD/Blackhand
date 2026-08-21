import { HandGlyph } from "../components/Mark";

// First Light (section 6.5). Dawn. 10 seconds, no input available to
// anyone. The exact public event text is reused verbatim rather than a
// second hardcoded copy of "Nobody was killed last night.", so this can
// never drift from the one string the engine actually guarantees is
// byte-identical across a blocked kill and a successful recruitment
// (NO_VISIBLE_DEATH_MESSAGE). A death gets the true hand-shaped handprint
// from section 4.6, the same one built for the DeadPanel.
export default function FirstLight({ events }) {
  const last = events?.[events.length - 1] || "";
  const died = / was killed during the night\.$/.test(last);

  return (
    <div className="first-light-screen">
      {died && (
        <span className="eliminated-stamp motion-stamped" aria-hidden="true">
          <HandGlyph size={56} className="handprint-glyph" />
          <span className="eliminated-stamp-label">ELIMINATED</span>
        </span>
      )}
      <p className="t-said center">{last}</p>
    </div>
  );
}
