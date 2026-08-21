import { useEffect } from "react";
import { letterUnfold } from "../audio";

// Every piece of private information arrives as a letter (section 4.5):
// role, investigation result, the offer. Never a toast, a banner, a
// modal, or a feed line. This component owns none of that judgment
// itself: it renders whatever content it's given, on paper or on the
// Black Hand's inverted room-ground surface, and it never closes itself.
// Dismissal, if a use of it needs one, is the caller's own explicit
// control (a button inside the children), never an outside click.
export default function Letter({ faction = "table", className, style, soundDelayMs = 0, children }) {
  // One paper unfold, 380ms, on arrival (section 4.5). Every mount is a
  // new letter arriving, never a re-opening of the same one. soundDelayMs
  // exists for The Reading (section 6.11), where every letter mounts in
  // the same render but must still sound staggered, matching the visual
  // stagger driven separately by the animationDelay in style.
  useEffect(() => {
    if (soundDelayMs > 0) {
      const t = setTimeout(letterUnfold, soundDelayMs);
      return () => clearTimeout(t);
    }
    letterUnfold();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const classes = [
    "letter",
    faction === "hand" ? "letter-hand" : "letter-table",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes} style={style}>
      <div className="letter-page">{children}</div>
    </div>
  );
}
