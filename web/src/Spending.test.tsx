import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Spending, SpendingBanner } from "./Spending";

const shown = {
  spent_usd: "8.40",
  evals_usd: "1.20",
  cap_usd: "10.00",
  eval_cap_usd: "3.00",
  level: "warning",
  warning: "You've used 80% of this month's $10.00 cap: $8.40 so far.",
  months: [
    { month: "2026-11-01T00:00:00Z", spent_usd: "8.40", evals_usd: "1.20" },
    { month: "2026-10-01T00:00:00Z", spent_usd: "4.10", evals_usd: "0.90" },
  ],
};

type Call = { url: string; method: string; body: unknown };

function serve(body: object = shown) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, method: init?.method ?? "GET", body: init?.body });
      return new Response(JSON.stringify(body));
    }),
  );
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Spending", () => {
  it("shows this month's paid use against the cap, evals included, and each month", async () => {
    serve();
    render(<Spending />);

    expect(await screen.findByText(/\$8\.40 of your \$10\.00 monthly cap/)).toBeTruthy();
    expect(screen.getByText(/\$1\.20 of it from Eval Runs\. They stop at their own \$3\.00/)).toBeTruthy();
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell").map((cell) => cell.textContent))).toEqual([
      ["November 2026", "$8.40", "$1.20"],
      ["October 2026", "$4.10", "$0.90"],
    ]);
  });

  it("changes the cap", async () => {
    const calls = serve();
    render(<Spending />);

    fireEvent.change(await screen.findByLabelText("Monthly cap, in US dollars"), { target: { value: "20" } });
    fireEvent.click(screen.getByRole("button", { name: "Save cap" }));

    await vi.waitFor(() => expect(calls.some((call) => call.method === "PUT")).toBe(true));
    const put = calls.find((call) => call.method === "PUT")!;
    expect(put.url).toBe("/api/spending/cap");
    expect(JSON.parse(String(put.body))).toEqual({ monthly_cap_usd: 20 });
  });
});

describe("SpendingBanner", () => {
  it("warns at 80% and at the cap, and says nothing below", async () => {
    serve();
    render(<SpendingBanner />);
    expect((await screen.findByRole("status")).textContent).toContain("80% of this month's $10.00 cap");

    cleanup();
    serve({ ...shown, level: "reached", warning: "You've reached this month's $10.00 cap." });
    render(<SpendingBanner />);
    expect((await screen.findByRole("alert")).textContent).toContain("reached this month's $10.00 cap");

    cleanup();
    serve({ ...shown, level: "ok", warning: null });
    render(<SpendingBanner />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
