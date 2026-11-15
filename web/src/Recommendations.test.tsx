import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Recommendations, StepModels } from "./Recommendations";

const groq = "groq/openai/gpt-oss-120b";
const recommendation = {
  step: "rating",
  model: groq,
  model_name: "Groq gpt-oss-120b (free)",
  current_name: "Claude Haiku 5.5",
  runs: [7, 5, 3],
  evidence: [{ score: "Exact Band", challenger: 100, current: 75 }],
  monthly_cost_usd: "0",
};
const steps = [
  { step: "rating", label: "Rating Matches", model_name: "Groq gpt-oss-120b (free)", approved: true },
  { step: "pack", label: "Writing Application Packs", model_name: "Claude Haiku 5.5", approved: false },
];

type Call = { url: string; method: string; body: unknown };

function serve(routes: Record<string, unknown>): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: init?.body });
      const key = `${method} ${url}`;
      return key in routes ? new Response(JSON.stringify(routes[key])) : new Response("{}", { status: 404 });
    }),
  );
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Recommendations", () => {
  it("shows a qualifying Challenger with its evidence and approves it", async () => {
    const calls = serve({
      "GET /api/recommendations": [recommendation],
      "POST /api/recommendations/approve": steps,
    });
    render(<Recommendations />);

    expect(await screen.findByText(/Groq gpt-oss-120b \(free\) did better than Claude Haiku 5.5 at Rating Matches/)).toBeTruthy();
    expect(screen.getByText(/Exact Band: 100% against 75%/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    expect(await screen.findByText(/Approved\. An Eval Run on the new model has started/)).toBeTruthy();
    expect(calls.at(-1)).toEqual({
      url: "/api/recommendations/approve",
      method: "POST",
      body: JSON.stringify({ step: "rating", model: groq }),
    });
  });

  it("dismisses a recommendation", async () => {
    serve({ "GET /api/recommendations": [recommendation], "POST /api/recommendations/dismiss": [] });
    render(<Recommendations />);

    fireEvent.click(await screen.findByRole("button", { name: "Dismiss" }));

    await screen.findByText(/Dismissed/);
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });

  it("shows nothing when no Challenger qualifies", async () => {
    serve({ "GET /api/recommendations": [] });
    const { container } = render(<Recommendations />);

    await Promise.resolve();
    expect(container.textContent).toBe("");
  });
});

describe("StepModels", () => {
  it("shows each step's model and switches an approved one back", async () => {
    const calls = serve({
      "GET /api/step-models": steps,
      "DELETE /api/step-models/rating": [{ ...steps[0], model_name: "Claude Haiku 5.5", approved: false }, steps[1]],
    });
    render(<StepModels />);

    expect(await screen.findByText(/Rating Matches: Groq gpt-oss-120b \(free\), which you approved/)).toBeTruthy();
    expect(screen.getByText(/Writing Application Packs: Claude Haiku 5.5/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Switch Rating Matches back" }));

    expect(await screen.findByText(/Rating Matches: Claude Haiku 5.5/)).toBeTruthy();
    expect(calls.at(-1)?.method).toBe("DELETE");
  });
});
