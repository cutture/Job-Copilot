import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Application } from "./Application";
import type { ApplicationData } from "./Application";

const python = { text: "Python Developer, Example Co, Jan 2021 to present", origin: "resume" as const };

function application(
  status: "generating" | "waiting" | "ready",
  changes: Partial<ApplicationData> = {},
): ApplicationData {
  const ready = status === "ready";
  return {
    id: "a",
    title: "Applied AI Engineer",
    employer: "Northwind Labs",
    source: "Greenhouse",
    apply_url: "https://job-boards.greenhouse.io/northwindlabs/jobs/1",
    reviewed: false,
    submitted_at: null,
    outcome: null,
    cost_usd: "0.0061",
    name: "Sam Rivera",
    contact: "sam@example.com",
    accent_colour: "teal",
    has_photo: false,
    ...changes,
    pack: {
      version: 1,
      status,
      warning: status === "waiting" ? "Our AI model isn't responding, so this Application Pack is waiting." : null,
      model: ready ? "anthropic/claude-haiku-5-5" : null,
      resume: ready
        ? {
            sections: [
              { kind: "skills", heading: "Skills", claims: [{ text: "Python", evidence: [python] }], groups: [], roles: [] },
              {
                kind: "experience",
                heading: "Experience",
                claims: [],
                groups: [],
                roles: [{ heading: { text: python.text, evidence: [python] }, lines: [] }],
              },
            ],
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
      extra_care: false,
      coverage: ready
        ? {
            score: 75,
            counted: [
              { requirement: "Python", kind: "must_have", result: "met", in_resume: true },
              { requirement: "Retrieval", kind: "must_have", result: "partial", in_resume: true },
              { requirement: "SQL", kind: "must_have", result: "met", in_resume: false },
              { requirement: "Terraform", kind: "nice_to_have", result: "missing", in_resume: null },
            ],
          }
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

describe("Application", () => {
  it("shows both verified documents, the Evidence and the Removed Claims", async () => {
    serve({ "GET /api/applications/a": () => application("ready") });

    render(<Application id="a" onBack={() => {}} />);

    const resume = await screen.findByLabelText("Resume");
    expect([...resume.querySelectorAll("h4")].map((h) => h.textContent)).toEqual(["Skills", "Experience"]);
    expect(screen.getByLabelText("Cover letter").textContent).toContain("Dear Northwind Labs hiring team,");
    // As the files download: name and contact line on top, the letter signed with the name.
    expect(resume.textContent!.startsWith("Sam Riverasam@example.com")).toBe(true);
    expect(screen.getByLabelText("Cover letter").textContent!.endsWith("Sam Rivera")).toBe(true);
    expect(screen.getAllByText("Resume: Python Developer, Example Co, Jan 2021 to present")).toHaveLength(2);
    expect(screen.getByText("Led a team of six engineers").tagName).toBe("S");
    expect(screen.getByText(/goes beyond what your Evidence says/)).toBeTruthy();
  });

  it("shows the keyword coverage score and which Requirements it counts", async () => {
    serve({ "GET /api/applications/a": () => application("ready") });

    render(<Application id="a" onBack={() => {}} />);

    const coverage = await screen.findByRole("region", { name: "Keyword coverage" });
    expect(coverage.textContent).toContain("Keyword coverage: 75%");
    expect([...coverage.querySelectorAll("li")].map((li) => li.textContent)).toEqual([
      "Python: Met, in your resume",
      "Retrieval: Partial, in your resume",
      "SQL: Met, not in this resume",
      "Terraform (nice-to-have): Missing",
    ]);
  });

  it("asks for extra care on a Pack made while evals are failing, without blocking it", async () => {
    const ready = application("ready");
    serve({ "GET /api/applications/a": () => ({ ...ready, pack: { ...ready.pack!, extra_care: true } }) });
    render(<Application id="a" onBack={() => {}} />);

    expect((await screen.findByRole("note")).textContent).toContain("Extra care: evals are failing");
    expect(screen.getByLabelText("Resume")).toBeTruthy();
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

  it("keeps downloads and Submitted locked until the review is ticked", async () => {
    const calls = serve({
      "GET /api/applications/a": () => application("ready"),
      "PUT /api/applications/a/review": () => application("ready", { reviewed: true }),
    });
    render(<Application id="a" onBack={() => {}} />);

    expect((await screen.findByRole("button", { name: "Resume DOCX" })).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "I submitted it on their site" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/cost \$0\.0061 so far/)).toBeTruthy();

    fireEvent.click(screen.getByLabelText(/I've reviewed this Application Pack/));

    await vi.waitFor(() =>
      expect(screen.getByRole("button", { name: "Resume DOCX" }).hasAttribute("disabled")).toBe(false),
    );
    expect(screen.getByRole("button", { name: "Cover letter DOCX" }).hasAttribute("disabled")).toBe(false);
    expect(screen.getByRole("link", { name: "Open employer's application page" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "I submitted it on their site" }).hasAttribute("disabled")).toBe(false);
    expect(calls).toContain("PUT /api/applications/a/review");
  });

  it("reports an Outcome with one click once Submitted", async () => {
    const submitted = { reviewed: true, submitted_at: "2026-11-04T10:00:00Z" };
    const calls = serve({
      "GET /api/applications/a": () => application("ready", submitted),
      "PUT /api/applications/a/outcome": () => application("ready", { ...submitted, outcome: "interview" }),
    });
    render(<Application id="a" onBack={() => {}} />);

    fireEvent.click(await screen.findByRole("button", { name: "Interview" }));

    expect((await screen.findByRole("button", { name: "Interview", pressed: true })).textContent).toBe("Interview");
    expect(screen.getByRole("button", { name: /✓ Submitted/ }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByLabelText(/I've reviewed this Application Pack/).hasAttribute("disabled")).toBe(true);
    expect(calls).toContain("PUT /api/applications/a/outcome");
  });

  it("offers a new Pack once the Pack is deleted, and deletes the Application", async () => {
    const calls = serve({
      "GET /api/applications/a": () => application("ready"),
      "DELETE /api/applications/a/pack": () => ({ ...application("ready"), pack: null }),
      "POST /api/applications/a/pack": () => application("generating"),
      "DELETE /api/applications/a": () => ({}),
    });
    const onBack = vi.fn();
    render(<Application id="a" onBack={onBack} />);

    fireEvent.click(await screen.findByRole("button", { name: "Delete this Pack" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    fireEvent.click(await screen.findByRole("button", { name: "Write a new Application Pack" }));
    expect(await screen.findByText("Writing and checking your Application Pack…")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Delete this Application" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await vi.waitFor(() => expect(onBack).toHaveBeenCalled());
    expect(calls).toEqual(expect.arrayContaining(["DELETE /api/applications/a/pack", "DELETE /api/applications/a"]));
  });

  it("marks Evidence deleted after a Pack was Submitted", async () => {
    const sent = application("ready", { reviewed: true, submitted_at: "2026-11-04T10:00:00Z" });
    sent.pack!.resume!.sections[0].claims[0].evidence = [{ ...python, deleted: true }];
    serve({ "GET /api/applications/a": () => sent });

    render(<Application id="a" onBack={() => {}} />);

    expect(await screen.findByText("(Evidence deleted)")).toBeTruthy();
    // A Submitted Application keeps the Pack that was sent.
    expect(screen.queryByRole("button", { name: "Delete this Pack" })).toBeNull();
  });

  it("offers Back to job listings at the top and the bottom of the page", async () => {
    serve({ "GET /api/applications/a": () => application("ready") });
    const onBack = vi.fn();
    render(<Application id="a" onBack={onBack} />);

    await screen.findByLabelText("Resume");
    const buttons = screen.getAllByRole("button", { name: "← Back to job listings" });
    expect(buttons).toHaveLength(2);
    fireEvent.click(buttons[1]);
    expect(onBack).toHaveBeenCalled();
  });

  it("shows the photo round beside the name on the styled resume only", async () => {
    serve({ "GET /api/applications/a": () => application("ready", { has_photo: true }) });
    render(<Application id="a" onBack={() => {}} />);

    const photo = within(await screen.findByLabelText("Resume")).getByRole("img", { name: "Your photo" });
    expect(photo.getAttribute("src")).toBe("/api/profile/photo");
    expect(photo.style.borderRadius).toBe("50%");
    expect(within(screen.getByLabelText("Cover letter")).queryByRole("img")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Plain pair" }));

    expect(within(screen.getByLabelText("Resume")).queryByRole("img")).toBeNull();
  });

  it("previews the styled pair by default and switches to the plain pair, downloading the one shown", async () => {
    vi.stubGlobal("URL", { ...URL, createObjectURL: () => "blob:file", revokeObjectURL: () => {} });
    const saved = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const file = () =>
      new Response("docx", {
        headers: { "content-disposition": "attachment; filename*=UTF-8''Sam-Rivera-Resume-plain.docx" },
      });
    const calls = serve({
      "GET /api/applications/a": () => application("ready", { reviewed: true }),
      "GET /api/applications/a/resume.docx?pair=plain": file,
    });
    render(<Application id="a" onBack={() => {}} />);

    // Styled: the surname in the accent colour, and the role's dates set apart at the right.
    const resume = await screen.findByLabelText("Resume");
    expect(screen.getAllByText("Rivera")[0].style.color).toBe("rgb(15, 94, 94)");
    expect(screen.getByText("Jan 2021 to present")).toBeTruthy();
    expect(screen.getByText("Python Developer, Example Co")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Plain pair" }));

    expect(screen.queryByText("Jan 2021 to present")).toBeNull();
    expect(resume.textContent).toContain(python.text);
    fireEvent.click(screen.getByRole("button", { name: "Resume DOCX (plain)" }));
    await vi.waitFor(() => expect(saved).toHaveBeenCalled());
    expect(calls).toContain("GET /api/applications/a/resume.docx?pair=plain");
    saved.mockRestore();
  });

  it("explains a file the ATS check refused instead of downloading it", async () => {
    serve({
      "GET /api/applications/a": () => application("ready", { reviewed: true }),
      "GET /api/applications/a/resume.docx?pair=styled": () =>
        new Response(JSON.stringify({ detail: "This file didn't pass the ATS check, so it can't be downloaded: x" }), {
          status: 409,
        }),
    });
    render(<Application id="a" onBack={() => {}} />);

    fireEvent.click(await screen.findByRole("button", { name: "Resume DOCX" }));

    expect((await screen.findByRole("alert")).textContent).toContain("didn't pass the ATS check");
  });

  it("asks for a name when the Profile has none", async () => {
    serve({ "GET /api/applications/a": () => application("ready", { name: null, contact: null }) });

    render(<Application id="a" onBack={() => {}} />);

    expect(await screen.findByText(/Add your name to your Profile/)).toBeTruthy();
  });
});
