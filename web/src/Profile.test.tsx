import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Profile } from "./Profile";

const baseProfile = {
  resume_filename: "resume.pdf",
  resume_text: "Sam Rivera\nPython Developer, Example Co",
  extraction_status: "done",
  name: null,
  contact: null,
  work_authorization: null,
  lives_in: null,
  education: null,
  search_window_days: 15,
  accent_colour: "navy",
  custom_sections: ["Volunteering", "Open Source"],
  languages: ["English"],
  seniority: null,
  roles: [],
  work_type: "employment_and_freelance",
  min_pay: [],
  location_arrangements: ["remote"],
  location_places: [],
  evidence: [
    { id: 1, text: "Python Developer at Example Co", origin: "resume", confirmed: false, created_at: "" },
    { id: 2, text: "Ran Kubernetes services", origin: "self_reported", confirmed: true, created_at: "" },
  ],
};

type Call = { url: string; method: string; body: unknown };

function serve(profile: object = baseProfile, overrides: Record<string, Response> = {}) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: init?.body });
      const override = overrides[`${method} ${url}`];
      if (override) return override.clone();
      if (method === "DELETE") return new Response(null, { status: 204 });
      return new Response(JSON.stringify(profile));
    }),
  );
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Profile setup", () => {
  it("shows the resume beside what was understood, marking self-reported Evidence", async () => {
    serve();
    render(<Profile />);

    expect(await screen.findByText(/Python Developer, Example Co/)).toBeTruthy();
    const proposed = screen.getByText("Python Developer at Example Co").closest("li")!;
    expect(within(proposed).getByRole("button", { name: "Confirm" })).toBeTruthy();
    const self = screen.getByText("Ran Kubernetes services").closest("li")!;
    expect(within(self).getByText("Self-reported")).toBeTruthy();
  });

  it("confirms an Evidence item", async () => {
    const calls = serve();
    render(<Profile />);
    const item = (await screen.findByText("Python Developer at Example Co")).closest("li")!;

    fireEvent.click(within(item).getByRole("button", { name: "Confirm" }));

    await vi.waitFor(() =>
      expect(calls).toContainEqual({
        url: "/api/evidence/1",
        method: "PATCH",
        body: JSON.stringify({ confirmed: true }),
      }),
    );
  });

  it("corrects an Evidence item", async () => {
    const calls = serve();
    render(<Profile />);
    const item = (await screen.findByText("Python Developer at Example Co")).closest("li")!;

    fireEvent.click(within(item).getByRole("button", { name: "Edit" }));
    fireEvent.change(within(item).getByRole("textbox"), {
      target: { value: "Python Developer at Example Co, 2021 to present" },
    });
    fireEvent.click(within(item).getByRole("button", { name: "Save and confirm" }));

    await vi.waitFor(() =>
      expect(calls).toContainEqual({
        url: "/api/evidence/1",
        method: "PATCH",
        body: JSON.stringify({ text: "Python Developer at Example Co, 2021 to present" }),
      }),
    );
  });

  it("deletes an Evidence item only after one confirmation", async () => {
    const calls = serve();
    render(<Profile />);
    const item = (await screen.findByText("Ran Kubernetes services")).closest("li")!;

    fireEvent.click(within(item).getByRole("button", { name: "Delete" }));
    expect(calls.some((call) => call.method === "DELETE")).toBe(false);
    fireEvent.click(within(item).getByRole("button", { name: "Yes, delete" }));

    await vi.waitFor(() =>
      expect(calls.some((call) => call.method === "DELETE" && call.url === "/api/evidence/2")).toBe(true),
    );
  });

  it("adds self-reported Evidence", async () => {
    const calls = serve();
    render(<Profile />);
    await screen.findByText("Ran Kubernetes services");

    fireEvent.change(screen.getByLabelText("Add something your resume misses"), {
      target: { value: "Mentored two interns" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add as self-reported" }));

    await vi.waitFor(() =>
      expect(calls).toContainEqual({
        url: "/api/evidence",
        method: "POST",
        body: JSON.stringify({ text: "Mentored two interns" }),
      }),
    );
  });

  it("saves where the person lives separately from their Location Preference", async () => {
    const calls = serve();
    render(<Profile />);
    expect(((await screen.findByLabelText("Languages")) as HTMLInputElement).value).toBe("English");

    fireEvent.change(screen.getByLabelText("Where you live"), { target: { value: "Austin, US" } });
    fireEvent.change(screen.getByLabelText("Education"), { target: { value: "BSc Computer Science" } });
    fireEvent.change(screen.getByLabelText("Search Window, in days"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText(/Accent colour/), { target: { value: "teal" } });
    fireEvent.change(screen.getByLabelText("Countries or cities you'd work in"), {
      target: { value: "US, San Francisco" },
    });
    fireEvent.click(screen.getByLabelText("Hybrid"));
    fireEvent.click(screen.getByRole("button", { name: "Add a currency" }));
    fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "usd" } });
    fireEvent.change(screen.getByLabelText("Yearly, for employment"), { target: { value: "120000" } });
    fireEvent.change(screen.getByLabelText("Hourly, for freelance"), { target: { value: "70" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));

    await vi.waitFor(() => expect(calls.some((call) => call.method === "PUT")).toBe(true));
    const saved = JSON.parse(String(calls.find((call) => call.method === "PUT")!.body));
    expect(saved.lives_in).toBe("Austin, US");
    expect(saved.education).toBe("BSc Computer Science");
    expect(saved.search_window_days).toBe(10);
    expect(saved.accent_colour).toBe("teal");
    expect(saved.location_places).toEqual(["US", "San Francisco"]);
    expect(saved.location_arrangements).toEqual(["remote", "hybrid"]);
    expect(saved.languages).toEqual(["English"]);
    expect(saved.min_pay).toEqual([{ currency: "USD", yearly: 120000, hourly: 70 }]);
  });

  it("adds, renames and removes custom resume sections", async () => {
    const calls = serve();
    render(<Profile />);

    fireEvent.change(await screen.findByLabelText("Resume section 1"), { target: { value: "Community Work" } });
    fireEvent.click(screen.getByRole("button", { name: "Remove Open Source" }));
    fireEvent.click(screen.getByRole("button", { name: "Add a resume section" }));
    fireEvent.change(screen.getByLabelText("Resume section 2"), { target: { value: "Talks" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));

    await vi.waitFor(() => expect(calls.some((call) => call.method === "PUT")).toBe(true));
    const saved = JSON.parse(String(calls.find((call) => call.method === "PUT")!.body));
    expect(saved.custom_sections).toEqual(["Community Work", "Talks"]);
  });

  it("asks for the currency of a minimum saved without one", async () => {
    serve({ ...baseProfile, min_pay: [{ currency: null, yearly: 120000, hourly: null }] });
    render(<Profile />);

    expect(await screen.findByText("Choose the currency for this amount. Until then Filter doesn't use it.")).toBeTruthy();
    expect((screen.getByLabelText("Yearly, for employment") as HTMLInputElement).value).toBe("120000");
  });

  it("explains why an upload was refused", async () => {
    serve(baseProfile, {
      "POST /api/profile/resume": new Response(
        JSON.stringify({ detail: "We found no text in this file. Scanned resumes aren't supported yet." }),
        { status: 422 },
      ),
    });
    render(<Profile />);
    await screen.findByText("Ran Kubernetes services");

    fireEvent.change(screen.getByLabelText("Upload your resume (PDF or DOCX)"), {
      target: { files: [new File(["x"], "scan.pdf")] },
    });

    expect((await screen.findByRole("alert")).textContent).toContain("Scanned resumes");
  });

  it("says where the resume text goes", async () => {
    serve();
    render(<Profile />);

    expect(await screen.findByText(/sent to Anthropic/)).toBeTruthy();
    expect(screen.queryByText(/stays on your server/)).toBeNull();
  });

  it("reports a failed delete instead of failing silently", async () => {
    serve(baseProfile, { "DELETE /api/evidence/2": new Response(null, { status: 500 }) });
    render(<Profile />);
    const item = (await screen.findByText("Ran Kubernetes services")).closest("li")!;

    fireEvent.click(within(item).getByRole("button", { name: "Delete" }));
    fireEvent.click(within(item).getByRole("button", { name: "Yes, delete" }));

    expect((await screen.findByRole("alert")).textContent).toContain("couldn't");
  });

  it("offers to read the resume again after a failure", async () => {
    const calls = serve({ ...baseProfile, extraction_status: "failed", evidence: [] });
    render(<Profile />);

    fireEvent.click(await screen.findByRole("button", { name: "Try reading it again" }));

    await vi.waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.url === "/api/profile/resume/read-again")).toBe(true),
    );
  });

  it("links to Anthropic's data policy", async () => {
    serve();
    render(<Profile />);

    const link = await screen.findByRole("link", { name: "Anthropic's data policy" });
    expect(link.getAttribute("href")).toBe("https://privacy.claude.com/");
  });

  it("confirms all unconfirmed items after one more click", async () => {
    const calls = serve();
    render(<Profile />);

    fireEvent.click(await screen.findByRole("button", { name: "Confirm all (1)" }));
    expect(calls.some((c) => c.url === "/api/evidence/confirm-all")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "I've read them. Confirm all 1" }));

    await vi.waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.url === "/api/evidence/confirm-all")).toBe(true),
    );
  });

  it("says when Evidence couldn't be read from the resume", async () => {
    serve({ ...baseProfile, extraction_status: "failed", evidence: [] });
    render(<Profile />);

    expect(await screen.findByText(/couldn't read Evidence from your resume/)).toBeTruthy();
  });
});
