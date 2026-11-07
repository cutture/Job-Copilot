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
    serve({ "/api/eval-runs": runs, "/api/eval-runs/2": run2, "/api/eval-runs/1": { ...runs[1], deepeval_version: "4.3.3", results: [] } });
    render(<EvalRuns />);

    const failure = (await screen.findByText("pack-trap-degree")).closest("tr")!;
    expect(within(failure).getByText("Hard Failure")).toBeTruthy();
    expect(within(failure).getByText(/PhD/)).toBeTruthy();
    expect(within(failure).getByText(/the writer prompts, then Verification/)).toBeTruthy();
    const unchecked = screen.getByText("scoring-thin-posting").closest("tr")!;
    expect(within(unchecked).getByText("Labels not checked")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /^Run 1 / }));
    expect(await screen.findByText("No case results.")).toBeTruthy();
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
