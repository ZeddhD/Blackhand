import Mark from "../components/Mark";

// The Crossing (section 6.7). Three seconds, unskippable, no control on
// screen at all: this component takes no callback props, so there is
// nothing here that could ever become a button, a link, or an input.
// A door, not a loading screen.
export default function Crossing({ seatCount }) {
  const seats = Array.from({ length: seatCount });

  return (
    <div className="crossing">
      <div className="crossing-mark">
        <Mark lockup="mark" size={72} />
      </div>
      <div className="crossing-ring" aria-hidden="true">
        {seats.map((_, i) => {
          const angle = (360 / seats.length) * i - 90;
          const radians = (angle * Math.PI) / 180;
          const left = 50 + 38 * Math.cos(radians);
          const top = 50 + 38 * Math.sin(radians);
          return (
            <span
              key={i}
              className="crossing-seat"
              style={{ left: `${left}%`, top: `${top}%`, animationDelay: `${i * 220}ms` }}
            />
          );
        })}
      </div>
    </div>
  );
}
