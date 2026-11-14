// Pricing comparison table (Sheet 2A screen 01, "COMPARE CAPABILITIES").
// Plan column headers align with the three plan cards; markers use a
// dot/symbol plus an accessible text label (never color alone).
import {
  COMPARISON_ROWS,
  MARKER_LABELS,
  MARKER_SYMBOLS,
  PLAN_COLUMN_LABELS,
} from "@/lib/marketing";
import { cn } from "@/lib/utils";

function Marker({ marker }: { marker: "included" | "basic" | "excluded" }) {
  if (marker === "included") {
    return (
      <span className="inline-flex items-center gap-2">
        <span
          aria-hidden="true"
          className="inline-block size-2.5 rounded-full bg-success"
          style={{ width: 10, height: 10 }}
        />
        <span className="sr-only">{MARKER_LABELS[marker]}</span>
      </span>
    );
  }
  return (
    <span className={cn("text-sm", marker === "basic" ? "text-soft-gray" : "text-muted")}>
      {MARKER_SYMBOLS[marker]}
      <span className="sr-only">{MARKER_LABELS[marker]}</span>
    </span>
  );
}

export function ComparisonTable() {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] border-collapse text-left">
        <caption className="sr-only">Plan capability comparison</caption>
        <thead>
          <tr>
            <th scope="col" className="pb-3">
              <span className="sr-only">Capability</span>
            </th>
            {PLAN_COLUMN_LABELS.map((label) => (
              <th
                key={label}
                scope="col"
                className="pb-3 text-center text-xs font-semibold uppercase tracking-wider text-muted"
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {COMPARISON_ROWS.map((row) => (
            <tr key={row.capability} className="border-t border-line">
              <th scope="row" className="py-3.5 pr-4 text-sm font-medium text-off-white">
                {row.capability}
              </th>
              {row.markers.map((marker, index) => (
                <td key={PLAN_COLUMN_LABELS[index]} className="py-3.5 text-center text-off-white">
                  <Marker marker={marker} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
