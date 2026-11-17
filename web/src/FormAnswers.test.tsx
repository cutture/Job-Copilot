import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FormAnswers } from "./FormAnswers";

const base = { origin: "greenhouse", required: false, options: [], value: null, sentences: null, removed: [] };
const unwritten = {
  note: "These are the questions on this job's Greenhouse form.",
  answers: [
    { ...base, id: 1, question: "First Name", kind: "contact", required: true, value: "Sam" },
    { ...base, id: 2, question: "Resume/CV", kind: "attach" },
    { ...base, id: 3, question: "Why do you want to join Example Labs?", kind: "write" },
    { ...base, id: 4, question: "Are you legally authorized to work here?", kind: "yourself", options: ["Yes", "No"] },
    { ...base, id: 5, question: "Gender", kind: "demographic", options: ["Female", "Male"] },
  ],
};
const written = {
  ...unwritten,
  answers: unwritten.answers.map((a) =>
    a.id === 3
      ? {
          ...a,
          sentences: [{ text: "I have shipped retrieval systems to production." }],
          removed: [{ text: "I led a team of 20.", kind: "invented", reason: "Nothing in your resume or Profile mentions this." }],
        }
      : a,
  ),
};

function serve(routes: Record<string, () => Response | unknown>) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      calls.push(`${key} ${init?.body ?? ""}`.trim());
      const body = routes[key];
      if (body === undefined) return new Response("{}", { status: 404 });
      const value = body();
      return value instanceof Response ? value : new Response(JSON.stringify(value));
    }),
  );
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("FormAnswers", () => {
  it("shows each question with its way of being answered, and writes answers on request", async () => {
    const copied: string[] = [];
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async (text: string) => void copied.push(text) },
    });
    const calls = serve({
      "GET /api/applications/a/form-answers": () => unwritten,
      "POST /api/applications/a/form-answers/prepare": () => written,
    });
    render(<FormAnswers applicationId="a" />);

    expect(await screen.findByText(/questions on this job's Greenhouse form/)).toBeTruthy();
    expect(screen.getByText(/Attach your resume yourself/)).toBeTruthy();
    expect(screen.getByText("Options: Yes, No")).toBeTruthy();
    // Demographic questions are left blank, their options never offered.
    expect(screen.getByText(/demographic questions are always yours/)).toBeTruthy();
    expect(screen.queryByText("Options: Female, Male")).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: "Copy" })[0]);
    await vi.waitFor(() => expect(copied).toEqual(["Sam"]));

    fireEvent.click(screen.getByRole("button", { name: "Prepare answers" }));

    expect(await screen.findByText(/I have shipped retrieval systems to production\./)).toBeTruthy();
    expect(screen.getByText("I led a team of 20.").tagName).toBe("S");
    expect(calls).toContain("POST /api/applications/a/form-answers/prepare");
    expect(screen.queryByRole("button", { name: "Prepare answers" })).toBeNull();
  });

  it("answers a pasted question, says when nothing answers it, and explains a failure", async () => {
    const pasted = {
      ...unwritten,
      answers: [
        ...unwritten.answers,
        { ...base, id: 6, origin: "pasted", question: "Why Python?", kind: "write", sentences: [] },
      ],
    };
    const calls = serve({
      "GET /api/applications/a/form-answers": () => unwritten,
      "POST /api/applications/a/form-answers/questions": () => pasted,
      "POST /api/applications/a/form-answers/prepare": () =>
        new Response(JSON.stringify({ detail: "We couldn't write these answers: our AI models aren't responding right now." }), {
          status: 503,
        }),
    });
    render(<FormAnswers applicationId="a" />);

    fireEvent.change(await screen.findByLabelText("Paste a question from the form"), {
      target: { value: "Why Python?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Answer it" }));

    expect(await screen.findByText(/Nothing in your Evidence answers this/)).toBeTruthy();
    expect(calls).toContain('POST /api/applications/a/form-answers/questions {"question":"Why Python?"}');
    expect(screen.getByRole("button", { name: "Remove" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Prepare answers" }));
    expect((await screen.findByRole("alert")).textContent).toContain("aren't responding");
  });
});
