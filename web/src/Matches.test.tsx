import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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

  it("groups by Band, sorts by nice-to-haves met and collapses Low but counts it", () => {
    render(<Matches postings={all} onAddToProfile={() => {}} />);

    expect(screen.getByRole("heading", { name: "High (2)" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Medium (1)" })).toBeTruthy();
    const titles = screen.getAllByRole("button", { name: /^View / }).map((b) => b.getAttribute("aria-label"));
    expect(titles).toEqual(["View Best High", "View Plain High", "View Some Medium"]);
    expect(screen.queryByRole("button", { name: "View Hidden Low" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Show Low (1)" }));

    expect(screen.getByRole("button", { name: "View Hidden Low" })).toBeTruthy();
  });

  it("shows every Requirement with its quote and Evidence, and labels the rating an estimate", () => {
    render(<Matches postings={all} onAddToProfile={() => {}} />);

    expect(screen.getByRole("heading", { name: "Best High" })).toBeTruthy();
    expect(screen.getByText("Reason for Best High")).toBeTruthy();
    expect(screen.getByText("“5+ years of Python”")).toBeTruthy();
    expect(screen.getByText("Shipped Python services")).toBeTruthy();
    expect(screen.getByText("Add your seniority to your Profile")).toBeTruthy();
    expect(screen.getByText(/doesn't predict the employer's decision/)).toBeTruthy();
  });

  it("offers one-click Add to Profile on a gap", () => {
    const add = vi.fn();
    render(<Matches postings={all} onAddToProfile={add} />);

    expect(screen.getByText("No Evidence found")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Add to Profile" }));

    expect(add).toHaveBeenCalledWith("Kubernetes");
  });

  it("sends an empty Profile field to the Profile rather than asking for Evidence", () => {
    const add = vi.fn();
    render(<Matches postings={all} onAddToProfile={add} />);

    expect(screen.getByText("Your Profile: English")).toBeTruthy();
    expect(screen.getAllByText("No Evidence found")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Update your Profile" }));

    expect(add).toHaveBeenCalledWith("");
  });

  it("switches the detail to the Match picked", () => {
    render(<Matches postings={all} onAddToProfile={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: "View Some Medium" }));

    expect(screen.getByRole("heading", { name: "Some Medium" })).toBeTruthy();
  });
});
