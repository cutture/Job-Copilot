import { useState } from "react";
import type { CSSProperties } from "react";

export type DeletionReport = { deleted: Record<string, number>; not_deleted: string[]; notes: string[] };

const card: CSSProperties = { border: "1px solid #f0b8b2", borderRadius: 8, padding: 16, marginBottom: 12 };

export function DeleteEverything({ onDeleted }: { onDeleted: (report: DeletionReport) => void }) {
  const [typed, setTyped] = useState("");
  const [includeEvalRuns, setIncludeEvalRuns] = useState(false);
  const [error, setError] = useState("");

  async function deleteEverything() {
    setError("");
    const response = await fetch("/api/delete-everything", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm: typed, include_eval_runs: includeEvalRuns }),
    }).catch(() => null);
    if (!response?.ok) {
      setError("We couldn't delete everything. Nothing was deleted, so try again.");
      return;
    }
    onDeleted(await response.json());
  }

  return (
    <div style={card}>
      <h2>Delete everything</h2>
      <p>
        This permanently deletes your Profile, Evidence, Watchlist, Job Postings, Matches, Applications, Application
        Packs, searches and spending ledger. There's no hidden copy.
      </p>
      <p style={{ fontSize: 13 }}>
        Some things are out of Job Copilot's reach: files you downloaded, what AI model providers already received, and
        your API keys. The report afterwards says what happens to each. Export comes later, so download any files you
        want to keep first.
      </p>
      <p>
        <label>
          <input
            type="checkbox"
            checked={includeEvalRuns}
            onChange={(event) => setIncludeEvalRuns(event.target.checked)}
          />{" "}
          Also delete Eval Runs. They hold only invented test data, so they stay unless you tick this.
        </label>
      </p>
      <label htmlFor="confirm-delete">Type DELETE to confirm</label>{" "}
      <input id="confirm-delete" value={typed} onChange={(event) => setTyped(event.target.value)} />{" "}
      <button disabled={typed !== "DELETE"} onClick={deleteEverything}>
        Delete everything
      </button>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}

export function DeletionReportView({ report }: { report: DeletionReport }) {
  return (
    <section>
      <h2>Everything is deleted</h2>
      <ul>
        {Object.entries(report.deleted).map(([what, count]) => (
          <li key={what}>
            {what}: {count} deleted
          </li>
        ))}
      </ul>
      {report.notes.map((note) => (
        <p key={note}>{note}</p>
      ))}
      <h3>What Job Copilot couldn't delete</h3>
      <ul>
        {report.not_deleted.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
