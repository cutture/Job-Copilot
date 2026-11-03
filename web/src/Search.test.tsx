import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Search } from "./Search";

type Call = { url: string; method: string; body: string };

function serve(routes: Record<string, () => Response>) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: String(init?.body ?? "") });
      return routes[`${method} ${url}`]?.() ?? new Response("{}", { status: 404 });
    }),
  );
  return calls;
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const status = (runs_left: number, searching = false) => json({ runs_left, daily_limit: 5, searching });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Search", () => {
  it("shows runs left and each failing Source", async () => {
    serve({
      "GET /api/search": () => status(3),
      "GET /api/watchlist": () =>
        json([
          { id: "a", name: "Northwind Labs", source: "Greenhouse", failure: "Northwind Labs's Greenhouse board didn't respond." },
          { id: "b", name: "Contoso", source: "Greenhouse", failure: null },
        ]),
    });

    render(<Search onProgress={() => {}} />);

    expect(await screen.findByText("3 of 5 runs left today")).toBeTruthy();
    expect(screen.getByText("Northwind Labs's Greenhouse board didn't respond.")).toBeTruthy();
    expect(screen.getByText(/Contoso \(Greenhouse\)/)).toBeTruthy();
  });

  it("adds an employer from a careers URL and explains an unsupported one", async () => {
    let added = false;
    const calls = serve({
      "GET /api/search": () => status(5),
      "GET /api/watchlist": () =>
        json(added ? [{ id: "a", name: "Northwind Labs", source: "Greenhouse", failure: null }] : []),
      "POST /api/watchlist": () => {
        if (calls.at(-1)!.body.includes("lever")) {
          return json({ detail: "This careers page isn't supported yet. Supported job boards: Greenhouse." }, 422);
        }
        added = true;
        return json({ id: "a", name: "Northwind Labs", source: "Greenhouse", failure: null }, 201);
      },
    });
    render(<Search onProgress={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add a job source" }));

    fireEvent.change(screen.getByLabelText("Add employer by careers page URL"), {
      target: { value: "https://jobs.lever.co/northwindlabs" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add to Watchlist" }));
    expect((await screen.findByRole("alert")).textContent).toContain("isn't supported yet");

    fireEvent.change(screen.getByLabelText("Add employer by careers page URL"), {
      target: { value: "https://job-boards.greenhouse.io/northwindlabs" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add to Watchlist" }));
    expect(await screen.findByText(/Northwind Labs \(Greenhouse\)/)).toBeTruthy();
  });

  it("starts a search and shows the runs left", async () => {
    let runsLeft = 1;
    serve({
      "GET /api/search": () => status(runsLeft),
      "GET /api/watchlist": () => json([]),
      "POST /api/search": () => {
        if (runsLeft === 0) {
          return json({ detail: "Today's 5 searches are used. Search is available again tomorrow." }, 429);
        }
        runsLeft = 0;
        return status(0, true);
      },
    });
    render(<Search onProgress={() => {}} />);

    fireEvent.click(await screen.findByRole("button", { name: "Search now" }));

    expect(await screen.findByRole("button", { name: "Searching…" })).toBeTruthy();
    expect(screen.getByText("0 of 5 runs left today")).toBeTruthy();
  });
});
