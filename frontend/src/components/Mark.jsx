// The hand mark (section 5). A single open hand, drawn rather than traced:
// deliberately asymmetric finger lengths and a thumb set at its own angle,
// one continuous SVG path, no groups, no strokes. Renders in --room or
// --paper only (never --lamp), via currentColor so the caller's CSS color
// decides which. Minimum render size is 24px (section 5.5); below that the
// asymmetry disappears and it reads as a generic hand icon.
const HAND_PATH =
  "M53.60,12.66 C52.80,9.53 51.54,10.24 50.55,9.77 C49.57,9.30 48.55,9.54 47.69,9.84 " +
  "C46.84,10.15 46.04,8.86 45.43,11.59 C44.81,14.32 44.67,25.49 44.01,26.23 " +
  "C43.34,26.97 42.49,18.00 41.44,16.05 C40.38,14.10 38.87,14.43 37.67,14.54 " +
  "C36.47,14.65 34.96,11.68 34.24,16.70 C33.52,21.73 36.23,40.48 33.37,44.69 " +
  "C30.50,48.89 20.23,42.11 17.05,41.92 C13.88,41.72 15.00,42.76 14.33,43.50 " +
  "C13.66,44.25 12.99,45.19 13.06,46.39 C13.13,47.59 11.47,47.77 14.74,50.71 " +
  "C18.01,53.65 29.85,61.09 32.67,64.05 C35.50,67.00 31.59,65.84 31.70,68.44 " +
  "C31.80,71.03 31.70,77.74 33.29,79.60 C34.89,81.46 40.07,78.27 41.27,79.60 " +
  "C42.46,80.93 36.75,86.25 40.47,87.58 C44.19,88.91 60.01,88.91 63.60,87.58 " +
  "C67.19,86.25 61.07,80.93 62.00,79.60 C62.93,78.27 67.59,81.20 69.18,79.60 " +
  "C70.78,78.01 71.31,73.75 71.57,70.03 C71.84,66.31 71.70,60.98 70.78,57.27 " +
  "C69.85,53.56 65.67,48.83 66.03,47.78 C66.39,46.73 70.45,54.22 72.92,50.96 " +
  "C75.38,47.69 79.68,32.51 80.80,28.19 C81.92,23.88 80.18,25.75 79.65,25.07 " +
  "C79.11,24.39 78.30,24.20 77.59,24.12 C76.88,24.03 77.31,21.96 75.37,24.56 " +
  "C73.43,27.16 67.71,41.16 65.95,39.71 C64.20,38.26 65.58,20.18 64.84,15.87 " +
  "C64.09,11.57 62.63,13.96 61.47,13.89 C60.31,13.82 58.89,13.01 57.88,15.45 " +
  "C56.87,17.89 56.11,28.99 55.39,28.52 C54.68,28.06 54.41,15.78 53.60,12.66 Z";

export function HandGlyph({ size = 48, className }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 100 100"
      aria-hidden="true"
      focusable="false"
    >
      <path d={HAND_PATH} fill="currentColor" />
    </svg>
  );
}

export default function Mark({ lockup = "mark", size = 48, className }) {
  if (lockup === "stacked") {
    return (
      <div className={["mark-lockup", "mark-lockup-stacked", className].filter(Boolean).join(" ")}>
        <HandGlyph size={size} />
        <span className="wordmark">BLACKHAND</span>
      </div>
    );
  }

  if (lockup === "horizontal") {
    return (
      <div className={["mark-lockup", "mark-lockup-horizontal", className].filter(Boolean).join(" ")}>
        <HandGlyph size={size} />
        <span className="wordmark">BLACKHAND</span>
      </div>
    );
  }

  return <HandGlyph size={size} className={className} />;
}
