import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Applications } from "./Applications";

const row = {
  employer: null,
  source: "Manual Source",
  submitted_at: null,
  outcome: null,
  cost_usd: "0.0061",
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Applications", () => {
  it("shows each Application's Job Posting, Source, status, Outcome, Submitted time and cost", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify([
            {
              ...row,
              id: "a",
              title: "Applied AI Engineer",
              status: "ready",
              deletes_on: new Date(Date.now() + 2 * 86_400_000).toISOString().slice(0, 10),
            },
            {
              ...row,
              id: "b",
              title: "ML Engineer",
              employer: "Northwind Labs",
              source: "Greenhouse",
              status: "submitted",
              submitted_at: "2026-11-04T10:00:00Z",
              outcome: "no_response",
              own_resume: true,
            },
          ]),
        ),
      ),
    );
    const onOpen = vi.fn();
    render(<Applications onOpen={onOpen} />);

    const opened = await screen.findByRole("button", { name: "ML Engineer, Northwind Labs" });
    const rows = screen.getAllByRole("row").map((r) => r.textContent);
    expect(rows[1]).toContain("Ready for review");
    expect(rows[1]).toContain("Not yet");
    expect(rows[1]).toContain("Its Pack will be deleted in 2 days unless you open it");
    expect(rows[2]).toContain("Greenhouse");
    expect(rows[2]).toContain("Submitted, no Pack");
    expect(rows[2]).toContain("No response");
    expect(rows[2]).toContain("$0.0061");

    fireEvent.click(opened);
    expect(onOpen).toHaveBeenCalledWith("b");
  });

  it("says when there are no Applications", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("[]")));

    render(<Applications onOpen={() => {}} />);

    expect(await screen.findByText(/No Applications yet/)).toBeTruthy();
  });
});
