import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Matches, Origin } from "./Matches";
import type { RatedPosting } from "./Matches";

function rated(id: string, title: string, band: string, nice_met = 0): RatedPosting {
  return {
    id,
    title,
    source: "Manual Source",
    posting_type: "employment",
    created_at: new Date().toISOString(),
    match: {
      band,
      nice_met,
      reasons: [`Reason for ${title}`],
      gaps: ["Kubernetes: no Evidence found"],
      profile_prompts: ["Add your seniority to your Profile"],
      requirements: [
        { requirement: "Python", kind: "must_have", quote: "5+ years of Python", result: "met", evidence: ["Shipped Python services"], gap: null },
        { requirement: "Kubernetes", kind: "must_have", quote: "Kubernetes in production", result: "missing", evidence: [], gap: null },
        { requirement: "English", kind: "hard_blocker", quote: null, result: "met", evidence: ["Your Profile: English"], gap: null, profile_field: "languages" },
        { requirement: "Work in Canada", kind: "hard_blocker", quote: "authorised to work in Canada", result: "unknown", evidence: [], gap: null, profile_field: "work_authorization" },
      ],
    },
  } as RatedPosting;
}

afterEach(cleanup);

describe("Origin", () => {
  it("credits the Source with its own text and link", () => {
    render(
      <Origin
        posting={{
          source: "Greenhouse",
          employer: "Northwind Labs",
          created_at: new Date().toISOString(),
          credit_url: "https://job-boards.greenhouse.io/northwindlabs",
          credit_text: "Greenhouse job board",
        }}
      />,
    );

    const link = screen.getByRole("link", { name: "Northwind Labs on Greenhouse job board" });
    expect(link.getAttribute("href")).toBe("https://job-boards.greenhouse.io/northwindlabs");
  });
});

describe("Matches", () => {
  const all = [
    rated("a", "Plain High", "High", 0),
    rated("b", "Best High", "High", 2),
    rated("c", "Some Medium", "Medium"),
    rated("d", "Hidden Low", "Low"),
  ];

  it("applies to the selected Match, or opens its Application once started", () => {
    const onApply = vi.fn();
    const started = { ...rated("e", "Started High", "High", 3), application_id: "app-1" };
    render(<Matches postings={[...all, started]} onAddToProfile={() => {}} onApply={onApply} onDelete={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: "Open Application Pack" }));
    fireEvent.click(screen.getByRole("button", { name: "View Plain High" }));
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(onApply.mock.calls.map(([posting]) => posting.id)).toEqual(["e", "a"]);
  });

  it("deletes a Match's Job Posting after one confirmation that names its Application", () => {
    const onDelete = vi.fn();
    const started = { ...rated("e", "Started High", "High", 3), application_id: "app-1" };
    render(<Matches postings={[...all, started]} onAddToProfile={() => {}} onApply={() => {}} onDelete={onDelete} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(screen.getByText(/Its Application and Application Pack go too/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));

    expect(onDelete.mock.calls.map(([posting]) => posting.id)).toEqual(["e"]);
  });

  it("says when Evidence a rating relied on was deleted", () => {
    const changed = rated("a", "Changed High", "High", 9);
    changed.match.profile_changed = true;
    render(<Matches postings={[changed]} onAddToProfile={() => {}} onApply={() => {}} onDelete={() => {}} />);

    expect(screen.getByText(/Profile changed/)).toBeTruthy();
  });

  it("groups by Band, sorts by nice-to-haves met and collapses Low but counts it", () => {
    render(<Matches postings={all} onAddToProfile={() => {}} onApply={() => {}} onDelete={() => {}} />);

    expect(screen.getByRole("heading", { name: "High (2)" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Medium (1)" })).toBeTruthy();
    const titles = screen.getAllByRole("button", { name: /^View / }).map((b) => b.getAttribute("aria-label"));
    expect(titles).toEqual(["View Best High", "View Plain High", "View Some Medium"]);
    expect(screen.queryByRole("button", { name: "View Hidden Low" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Show Low (1)" }));

    expect(screen.getByRole("button", { name: "View Hidden Low" })).toBeTruthy();
  });

  it("shows every Requirement with its quote and Evidence, and labels the rating an estimate", () => {
    render(<Matches postings={all} onAddToProfile={() => {}} onApply={() => {}} onDelete={() => {}} />);

    expect(screen.getByRole("heading", { name: "Best High" })).toBeTruthy();
    expect(screen.getByText("Reason for Best High")).toBeTruthy();
    expect(screen.getByText("“5+ years of Python”")).toBeTruthy();
    expect(screen.getByText("Shipped Python services")).toBeTruthy();
    expect(screen.getByText("Add your seniority to your Profile")).toBeTruthy();
    expect(screen.getByText(/doesn't predict the employer's decision/)).toBeTruthy();
  });

  it("offers one-click Add to Profile on a gap", () => {
    const add = vi.fn();
    render(<Matches postings={all} onAddToProfile={add} onApply={() => {}} onDelete={() => {}} />);

    expect(screen.getByText("No Evidence found")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Add to Profile" }));

    expect(add).toHaveBeenCalledWith("Kubernetes");
  });

  it("sends an empty Profile field to the Profile rather than asking for Evidence", () => {
    const add = vi.fn();
    render(<Matches postings={all} onAddToProfile={add} onApply={() => {}} onDelete={() => {}} />);

    expect(screen.getByText("Your Profile: English")).toBeTruthy();
    expect(screen.getAllByText("No Evidence found")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Update your Profile" }));

    expect(add).toHaveBeenCalledWith("");
  });

  it("switches the detail to the Match picked", () => {
    render(<Matches postings={all} onAddToProfile={() => {}} onApply={() => {}} onDelete={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: "View Some Medium" }));

    expect(screen.getByRole("heading", { name: "Some Medium" })).toBeTruthy();
  });
});

describe("Rescore", () => {
  function serve(estimate: unknown) {
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push(`${url} ${init?.body ?? ""}`);
        return url === "/api/rescore/estimate"
          ? new Response(JSON.stringify(estimate))
          : new Response(null, { status: 202 });
      }),
    );
    return calls;
  }
  const noop = () => {};

  afterEach(() => vi.unstubAllGlobals());

  it("shows the estimate first, and Rescores one Match only once it's confirmed", async () => {
    const calls = serve({ count: 1, full_ratings: 0, cost_usd: "0.0012", model: "Claude Haiku 5.5", free: false });
    const rescored = vi.fn();
    render(
      <Matches
        postings={[rated("1", "Applied AI Engineer", "High")]}
        onAddToProfile={noop}
        onApply={noop}
        onDelete={noop}
        onRescored={rescored}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Rescore" }));
    expect(await screen.findByText(/Rescore 1 Match for about \$0\.0012 with Claude Haiku 5\.5\?/)).toBeTruthy();
    expect(calls).toEqual(['/api/rescore/estimate {"job_posting_ids":["1"]}']);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Rescore" }));
    await screen.findByText(/Rescore 1 Match for about/);
    fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Rescore" }));

    await vi.waitFor(() => expect(rescored).toHaveBeenCalled());
    expect(calls.at(-1)).toBe('/api/rescore {"job_posting_ids":["1"]}');
  });

  it("selects every Match not applied to, and says what a free or full Rescore means", async () => {
    const calls = serve({ count: 2, full_ratings: 1, cost_usd: "0", model: "Groq GPT-OSS 120B", free: true });
    const applied = { ...rated("3", "Data Engineer", "Medium"), application_id: "a" };
    render(
      <Matches
        postings={[rated("1", "Applied AI Engineer", "High"), rated("2", "ML Engineer", "High"), applied]}
        onAddToProfile={noop}
        onApply={noop}
        onDelete={noop}
      />,
    );

    // An applied Match keeps its rating, so it can't be ticked.
    expect(screen.queryByLabelText("Select Data Engineer")).toBeNull();
    fireEvent.click(screen.getByLabelText("Select all you haven't applied to"));
    fireEvent.click(screen.getByRole("button", { name: "Rescore selected (2)" }));

    expect(await screen.findByText(/Rescore 2 Matches free with Groq GPT-OSS 120B\?/)).toBeTruthy();
    expect(screen.getByText(/rated in full this once/)).toBeTruthy();
    expect(calls[0]).toBe('/api/rescore/estimate {"job_posting_ids":["1","2"]}');
  });

  it("shows a Rescore under way and what a Rescore changed", () => {
    const changed = rated("1", "Applied AI Engineer", "High");
    changed.match.previous_band = "Medium";
    const running = { ...rated("2", "ML Engineer", "High"), rescoring: true };
    const applied = { ...rated("3", "Data Engineer", "High"), application_id: "a" };
    render(<Matches postings={[changed, running, applied]} onAddToProfile={noop} onApply={noop} onDelete={noop} />);

    expect(screen.getByText("Rescored: was Medium.")).toBeTruthy();
    expect(screen.getByText(/Rescoring…/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "View Data Engineer" }));
    expect(screen.queryByRole("button", { name: "Rescore" })).toBeNull();
  });
});
