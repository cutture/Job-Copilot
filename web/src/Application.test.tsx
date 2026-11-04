import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Application } from "./Application";
import type { ApplicationData } from "./Application";

const python = { text: "Python Developer, Example Co, Jan 2021 to present", origin: "resume" as const };

function application(status: "generating" | "waiting" | "ready"): ApplicationData {
  const ready = status === "ready";
  return {
    id: "a",
    title: "Applied AI Engineer",
    employer: "Northwind Labs",
    source: "Greenhouse",
    pack: {
      version: 1,
      status,
      warning: status === "waiting" ? "Our AI model isn't responding, so this Application Pack is waiting." : null,
      model: ready ? "anthropic/claude-haiku-5-5" : null,
      resume: ready
        ? {
            skills: [{ text: "Python", evidence: [python] }],
            experience: [{ heading: { text: python.text, evidence: [python] }, bullets: [] }],
            education: [],
          }
        : null,
      cover_letter: ready
        ? { paragraphs: [[{ text: "Dear Northwind Labs hiring team,", evidence: [] }]] }
        : null,
      removed_claims: ready
        ? [
            {
              text: "Led a team of six engineers",
              kind: "stretched",
              reason: "It goes beyond what your Evidence says: “Member of a team”",
              next_step: "If it's true, add Evidence for it to your Profile, then generate the Pack again.",
            },
          ]
        : null,
    },
  };
}

function serve(routes: Record<string, () => unknown>) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      calls.push(key);
      const body = routes[key];
      return body ? new Response(JSON.stringify(body())) : new Response("{}", { status: 404 });
    }),
  );
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Application", () => {
  it("shows both verified documents, the Evidence and the Removed Claims", async () => {
    serve({ "GET /api/applications/a": () => application("ready") });

    render(<Application id="a" onBack={() => {}} />);

    const resume = await screen.findByLabelText("Resume");
    expect([...resume.querySelectorAll("h4")].map((h) => h.textContent)).toEqual(["Skills", "Experience"]);
    expect(screen.getByLabelText("Cover letter").textContent).toContain("Dear Northwind Labs hiring team,");
    expect(screen.getAllByText("Resume: Python Developer, Example Co, Jan 2021 to present")).toHaveLength(2);
    expect(screen.getByText("Led a team of six engineers").tagName).toBe("S");
    expect(screen.getByText(/goes beyond what your Evidence says/)).toBeTruthy();
  });

  it("shows no documents until the Pack is verified", async () => {
    serve({ "GET /api/applications/a": () => application("generating") });

    render(<Application id="a" onBack={() => {}} />);

    expect(await screen.findByText("Writing and checking your Application Pack…")).toBeTruthy();
    expect(screen.queryByLabelText("Resume")).toBeNull();
  });

  it("warns when the Pack is waiting and retries it", async () => {
    const calls = serve({
      "GET /api/applications/a": () => application("waiting"),
      "POST /api/applications/a/retry": () => application("generating"),
    });
    render(<Application id="a" onBack={() => {}} />);

    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Writing and checking your Application Pack…")).toBeTruthy();
    expect(calls).toContain("POST /api/applications/a/retry");
  });
});
