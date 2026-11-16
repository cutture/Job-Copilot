import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EvalBanner, EvalRuns } from "./EvalRuns";

const runs = [
  {
    id: 2,
    started_at: "2026-11-08T06:00:00Z",
    finished_at: "2026-11-08T06:04:00Z",
    cost_usd: "0.0312",
    passed: 22,
    failed: 1,
    did_not_run: 1,
    hard_failures: 1,
    unchecked: 16,
  },
  {
    id: 1,
    started_at: "2026-11-07T06:00:00Z",
    finished_at: "2026-11-07T06:04:00Z",
    cost_usd: "0.0300",
    passed: 24,
    failed: 0,
    did_not_run: 0,
    hard_failures: 0,
    unchecked: 16,
  },
];
const run2 = {
  ...runs[0],
  deepeval_version: "4.3.3",
  results: [
    {
      case_id: "pack-trap-degree",
      area: "pack",
      status: "failed",
      hard_failure: true,
      labels_checked: true,
      reason: "An Invented Claim reached the final Pack: “PhD”",
      fix_area: "Application Pack: the writer prompts, then Verification, in applications.py",
    },
    {
      case_id: "scoring-thin-posting",
      area: "scoring",
      status: "passed",
      hard_failure: false,
      labels_checked: false,
      reason: "Matches its labels",
      fix_area: null,
    },
  ],
  tracked_scores: [
    { name: "Exact Band", value: 75, target: "80% or more", met: false },
    { name: "Wrong removals", value: 0, target: "10% or less", met: true },
    { name: "Stretched Claims", value: 4, target: "Report only", met: null },
    { name: "Requirement Results", value: null, target: "85% or more", met: null },
  ],
};

function serve(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url in routes ? new Response(JSON.stringify(routes[url])) : new Response("{}", { status: 404 }),
    ),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("EvalRuns", () => {
  it("lists runs and shows the latest run's failures with their reason and area to fix", async () => {
    serve({ "/api/eval-runs": runs, "/api/eval-runs/2": run2, "/api/eval-runs/1": { ...runs[1], deepeval_version: "4.3.3", results: [], tracked_scores: [] } });
    render(<EvalRuns />);

    const failure = (await screen.findByText("pack-trap-degree")).closest("tr")!;
    expect(within(failure).getByText("Hard Failure")).toBeTruthy();
    expect(within(failure).getByText(/PhD/)).toBeTruthy();
    expect(within(failure).getByText(/the writer prompts, then Verification/)).toBeTruthy();
    const unchecked = screen.getByText("scoring-thin-posting").closest("tr")!;
    expect(within(unchecked).getByText("Labels not checked")).toBeTruthy();

    const missed = screen.getByText("Exact Band").closest("tr")!;
    expect(within(missed).getByText("75%")).toBeTruthy();
    expect(within(missed).getByText("Missed")).toBeTruthy();
    expect(within(screen.getByText("Wrong removals").closest("tr")!).getByText("Met")).toBeTruthy();
    expect(within(screen.getByText("Stretched Claims").closest("tr")!).getByText("Report only")).toBeTruthy();
    expect(within(screen.getByText("Requirement Results").closest("tr")!).getByText(/No checked cases/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /^Run 1 / }));
    expect(await screen.findByText(/No case results: the run stopped/)).toBeTruthy();
  });

  it("shows a run as running until its last case finishes", async () => {
    const running = { ...runs[0], id: 3, finished_at: null, cost_usd: null, passed: 0, failed: 0, did_not_run: 0, hard_failures: 0 };
    serve({ "/api/eval-runs": [running], "/api/eval-runs/3": { ...running, deepeval_version: "4.3.3", results: [], tracked_scores: [] } });
    render(<EvalRuns />);

    const row = (await screen.findByRole("button", { name: /^Run 3 / })).closest("li")!;
    expect(within(row).getByText(/Running/)).toBeTruthy();
    expect(await screen.findByText(/Running: no case has finished yet/)).toBeTruthy();
  });

  it("labels a Challenger run and shows the model each step used", async () => {
    const challenger = { ...runs[0], id: 4, challenger_label: "Rating Matches", challenger_name: "Groq gpt-oss-120b (free)" };
    const result = { ...run2.results[1], models: { "Rating Matches": "Groq gpt-oss-120b (free)", "Writing Application Packs": "Claude Haiku 5.5" } };
    serve({
      "/api/eval-runs": [challenger],
      "/api/eval-runs/4": { ...challenger, deepeval_version: "4.3.3", results: [result], tracked_scores: [] },
    });
    render(<EvalRuns />);

    const row = (await screen.findByRole("button", { name: /^Run 4 / })).closest("li")!;
    expect(within(row).getByText(/Challenger: Groq gpt-oss-120b \(free\) for Rating Matches/)).toBeTruthy();
    const cells = (await screen.findByText("scoring-thin-posting")).closest("tr")!;
    expect(within(cells).getByText(/Rating Matches: Groq gpt-oss-120b \(free\)/)).toBeTruthy();
  });

  it("shows Kept Claims per Application as a usage figure with no pass or fail", async () => {
    serve({
      "/api/eval-runs": runs,
      "/api/eval-runs/2": run2,
      "/api/kept-claims": { kept: 3, applications: 4 },
    });
    render(<EvalRuns />);

    const figure = await screen.findByText(/Kept Claims: 0\.8 per Application/);
    expect(figure.parentElement!.textContent).toContain("3 kept across 4 Applications");
    expect(figure.parentElement!.textContent).toContain("it has no pass or fail");
  });

  it("says when there are no runs yet", async () => {
    serve({ "/api/eval-runs": [] });
    render(<EvalRuns />);

    expect(await screen.findByText(/No Eval Runs yet/)).toBeTruthy();
  });
});

describe("EvalBanner", () => {
  it("shows a red banner only while evals are failing", async () => {
    serve({ "/api/evals/status": { failing: true, failing_since: "2026-11-08T06:04:00Z" } });
    render(<EvalBanner />);
    expect((await screen.findByRole("alert")).textContent).toContain("Evals are failing");

    cleanup();
    serve({ "/api/evals/status": { failing: false, failing_since: null } });
    render(<EvalBanner />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
