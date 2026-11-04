import { useEffect, useState } from "react";
import { OUTCOMES, dollars } from "./labels";
import type { Outcome } from "./labels";

type ApplicationRow = {
  id: string;
  title: string;
  employer: string | null;
  source: string;
  status: "generating" | "waiting" | "ready" | "reviewed" | "submitted";
  submitted_at: string | null;
  outcome: Outcome | null;
  cost_usd: string;
};

const STATUSES = {
  generating: "Writing the Pack",
  waiting: "Pack waiting",
  ready: "Ready for review",
  reviewed: "Reviewed",
  submitted: "Submitted",
};
const cell = { textAlign: "left" as const, padding: "4px 8px", borderTop: "1px solid #e4e7eb" };

export function Applications({ onOpen }: { onOpen: (id: string) => void }) {
  const [rows, setRows] = useState<ApplicationRow[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/applications")
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then(setRows)
      .catch(() => setError("We couldn't load your Applications. Try refreshing the page."));
  }, []);

  if (error) return <p role="alert">{error}</p>;
  if (rows?.length === 0) return <p>No Applications yet. Click Apply on a Match to start one.</p>;
  return (
    <table style={{ borderCollapse: "collapse", width: "100%" }}>
      <thead>
        <tr>
          {["Job Posting", "Source", "Status", "Outcome", "Submitted", "Cost"].map((heading) => (
            <th key={heading} style={cell}>
              {heading}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows?.map((row) => (
          <tr key={row.id}>
            <td style={cell}>
              <button onClick={() => onOpen(row.id)}>
                {row.title}
                {row.employer && `, ${row.employer}`}
              </button>
            </td>
            <td style={cell}>{row.source}</td>
            <td style={cell}>{STATUSES[row.status]}</td>
            <td style={cell}>{row.outcome ? OUTCOMES[row.outcome] : "None yet"}</td>
            <td style={cell}>{row.submitted_at ? new Date(row.submitted_at).toLocaleString() : "Not yet"}</td>
            <td style={cell}>{dollars(row.cost_usd)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
