// Every piece of private information arrives as a letter (section 4.5):
// role, investigation result, the offer. Never a toast, a banner, a
// modal, or a feed line. This component owns none of that judgment
// itself: it renders whatever content it's given, on paper or on the
// Black Hand's inverted room-ground surface, and it never closes itself.
// Dismissal, if a use of it needs one, is the caller's own explicit
// control (a button inside the children), never an outside click.
export default function Letter({ faction = "table", className, children }) {
  const classes = [
    "letter",
    faction === "hand" ? "letter-hand" : "letter-table",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes}>
      <div className="letter-page">{children}</div>
    </div>
  );
}
