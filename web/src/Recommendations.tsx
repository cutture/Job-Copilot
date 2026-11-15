import { useEffect, useState } from "react";

type ScoreComparison = { score: string; challenger: number; current: number };
type ModelRecommendation = {
  step: string;
  label: string;
  model: string;
  model_name: string;
  current_name: string;
  runs: number[];
  compared: ScoreComparison[];
  // Last month's total spending, with this step repriced at the Challenger's rates.
  projected_monthly_usd: string;
};
type StepModel = { step: string; label: string; model_name: string; approved: boolean };

async function send(url: string, method: string, body?: object): Promise<Response> {
  return fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body && JSON.stringify(body),
  });
}

// A Challenger that did better than the current model; nothing changes until it's approved.
export function Recommendations() {
  const [found, setFound] = useState<ModelRecommendation[]>([]);
  const [done, setDone] = useState("");

  useEffect(() => {
    fetch("/api/model-recommendations")
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then(setFound)
      .catch(() => setDone("We couldn't check for model recommendations. Try refreshing the page."));
  }, []);

  async function decide(recommendation: ModelRecommendation, approve: boolean) {
    const response = await send(`/api/model-recommendations/${approve ? "approve" : "dismiss"}`, "POST", {
      step: recommendation.step,
      model: recommendation.model,
    });
    if (!response.ok) {
      setDone("We couldn't save that. Refresh the page and try again.");
      return;
    }
    setFound(found.filter((r) => r !== recommendation));
    setDone(
      approve
        ? "Approved. An Eval Run on the new model has started; you can switch back on the Settings page."
        : "Dismissed. It shows again only if a newer Challenger run still does better.",
    );
  }

  if (!found.length && !done) return null;
  return (
    <section aria-label="Model recommendations">
      {found.map((recommendation) => (
        <div key={`${recommendation.step} ${recommendation.model}`} style={{ border: "1px solid #b7d3f2", padding: "8px 12px", marginBottom: 8 }}>
          <p style={{ margin: 0 }}>
            {recommendation.model_name} did better than {recommendation.current_name} at {recommendation.label} in
            its last {recommendation.runs.length} Challenger runs, with no Hard Failures. With it, last month's
            spending would have come to ${Number(recommendation.projected_monthly_usd).toFixed(2)} in all.
          </p>
          <ul style={{ margin: "4px 0" }}>
            {recommendation.compared.map((e) => (
              <li key={e.score}>
                {e.score}: {Math.round(e.challenger)}% against {Math.round(e.current)}%
              </li>
            ))}
          </ul>
          <button onClick={() => decide(recommendation, true)}>Approve</button>{" "}
          <button onClick={() => decide(recommendation, false)}>Dismiss</button>
        </div>
      ))}
      {done && <p role="status">{done}</p>}
    </section>
  );
}

// Each step's model, for the Settings page, with a way back to the default.
export function StepModels() {
  const [steps, setSteps] = useState<StepModel[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/step-models")
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then(setSteps)
      .catch(() => setError("We couldn't load each step's model. Try refreshing the page."));
  }, []);

  async function switchBack(step: StepModel) {
    const response = await send(`/api/step-models/${step.step}`, "DELETE");
    if (response.ok) setSteps(await response.json());
    else setError("We couldn't switch that back. Try again.");
  }

  if (error) return <p role="alert">{error}</p>;
  if (!steps) return null;
  return (
    <ul>
      {steps.map((step) => (
        <li key={step.step}>
          {step.label}: {step.model_name}
          {step.approved && (
            <>
              , which you approved{" "}
              <button onClick={() => switchBack(step)}>Switch {step.label} back</button>
            </>
          )}
        </li>
      ))}
    </ul>
  );
}
