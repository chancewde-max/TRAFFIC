import { LEVEL_COLOR, LEVEL_ORDER } from "../congestionColors";

export default function CongestionLegend() {
  return (
    <div className="legend">
      {LEVEL_ORDER.map((level) => {
        const [r, g, b] = LEVEL_COLOR[level];
        return (
          <div className="legend-row" key={level}>
            <span className="legend-swatch" style={{ background: `rgb(${r},${g},${b})` }} />
            <span style={{ textTransform: "capitalize" }}>{level}</span>
          </div>
        );
      })}
    </div>
  );
}
