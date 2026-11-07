import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { dollars } from "./labels";

type EvalRunSummary = {
  id: number;
  started_at: string;
  finished_at: string | null;
  cost_usd: string | null;
  passed: number;
  failed: number;
  did_not_run: number;
  hard_failures: number;
  // Results of cases whose labels the owner hasn't checked yet.
  unchecked: number;
};
type EvalCaseResult = {
  case_id: string;
  area: string;
  status: "passed" | "failed" | "did_not_run";
  hard_failure: boolean;
  labels_checked: boolean;
  reason: string;
  // Where to look first to fix a failure.
  fix_area: string | null;
};
type EvalRun = EvalRunSummary & { deepeval_version: string; results: EvalCaseResult[] };

const STATUS = { passed: "Passed", failed: "Failed", did_not_run: "Did not run" };
const cell: CSSProperties = { borderBottom: "1px solid #ddd", padding: "4px 8px", textAlign: "left", verticalAlign: "top" };

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

// A red banner while evals are failing; it blocks nothing.
export function EvalBanner() {
  const [failing, setFailing] = useState(false);
  useEffect(() => {
    getJson<{ failing: boolean }>("/api/evals/status")
      .then((status) => setFailing(status.failing === true))
      .catch(() => {});
  }, []);
  if (!failing) return null;
  return (
    <p role="alert" style={{ background: "#fdecea", color: "#8a1c12", border: "1px solid #f0b8b2", padding: "8px 12px" }}>
      Evals are failing. New Application Packs need extra care until a run passes. See Eval Runs for what failed.
    </p>
  );
}

export function EvalRuns() {
  const [runs, setRuns] = useState<EvalRunSummary[] | null>(null);
  const [run, setRun] = useState<EvalRun | null>(null);
  const [error, setError] = useState("");

  function open(id: number) {
    getJson<EvalRun>(`/api/eval-runs/${id}`)
      .then(setRun)
      .catch(() => setError("We couldn't load this Eval Run. Try again."));
  }

  useEffect(() => {
    getJson<EvalRunSummary[]>("/api/eval-runs")
      .then((loaded) => {
        setRuns(loaded);
        if (loaded.length) open(loaded[0].id);
      })
      .catch(() => setError("We couldn't load the Eval Runs. Try refreshing the page."));
  }, []);

  if (error) return <p role="alert">{error}</p>;
  if (!runs) return <p>Loading Eval Runs…</p>;
  if (!runs.length) return <p>No Eval Runs yet. The worker runs every Eval Case once a day.</p>;
  return (
    <section>
      <h2>Eval Runs</h2>
      <p style={{ fontSize: 13 }}>
        Every Eval Case runs once a day on invented data. Results of cases whose labels you haven't checked aren't
        trusted yet, and don't turn on the warning.
      </p>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {runs.map((summary) => (
          <li key={summary.id}>
            <button aria-pressed={run?.id === summary.id} onClick={() => open(summary.id)}>
              Run {summary.id} · {new Date(summary.started_at).toLocaleString()}
            </button>{" "}
            {summary.passed} passed, {summary.failed} failed, {summary.did_not_run} did not run
            {summary.hard_failures > 0 && <strong style={{ color: "#8a1c12" }}> · {summary.hard_failures} Hard Failures</strong>}
            {summary.cost_usd && <> · {dollars(summary.cost_usd)}</>}
          </li>
        ))}
      </ul>
      {run && (
        <>
          <h3>
            Run {run.id}, DeepEval {run.deepeval_version}
          </h3>
          {run.results.length === 0 ? (
            <p>No case results.</p>
          ) : (
            <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
              <thead>
                <tr>
                  {["Case", "Area", "Result", "Labels", "Reason", "Look first at"].map((heading) => (
                    <th key={heading} style={cell}>
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {run.results.map((result) => (
                  <tr key={result.case_id}>
                    <td style={cell}>{result.case_id}</td>
                    <td style={cell}>{result.area}</td>
                    <td style={cell}>{result.hard_failure ? "Hard Failure" : STATUS[result.status]}</td>
                    <td style={cell}>{result.labels_checked ? "Checked" : "Labels not checked"}</td>
                    <td style={cell}>{result.reason}</td>
                    <td style={cell}>{result.fix_area ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}
