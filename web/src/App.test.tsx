import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const posting = {
  id: "1",
  title: "Senior GenAI Engineer",
  source: "Manual Source",
  text: "Senior GenAI Engineer",
  status: "queued",
  created_at: "2026-11-02T00:00:00Z",
};

function respondWith(listed: unknown[][]) {
  const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
    init?.method === "POST"
      ? new Response("{}", { status: 201 })
      : new Response(JSON.stringify(listed.shift() ?? [])),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("pasting a Job Posting", () => {
  it("shows the required notice directly above the field", async () => {
    respondWith([[]]);
    render(<App />);
    const notice = screen.getByText(/own career page/);
    const field = screen.getByLabelText("Paste a Job Posting");

    expect(notice.textContent).toBe(
      "Paste only from an employer's own career page, not sites like LinkedIn, Indeed or Upwork. The text goes to an LLM provider.",
    );
    expect(notice.compareDocumentPosition(field)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(notice.nextElementSibling).toBe(field);
    await screen.findByText("No Job Postings yet.");
  });

  it("sends the text and lists the new posting with its Source", async () => {
    const fetchMock = respondWith([[], [posting]]);
    render(<App />);
    await screen.findByText("No Job Postings yet.");

    fireEvent.change(screen.getByLabelText("Paste a Job Posting"), {
      target: { value: "Senior GenAI Engineer" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add posting" }));

    expect(await screen.findByText("Senior GenAI Engineer")).toBeTruthy();
    expect(screen.getByText("Manual Source")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/job-postings",
      expect.objectContaining({ body: JSON.stringify({ text: "Senior GenAI Engineer" }) }),
    );
  });

  it("updates the title by itself once the worker has processed the posting", async () => {
    const processed = { ...posting, title: "GenAI Developer at Northwind Labs", status: "received" };
    const fetchMock = respondWith([[], [posting], [processed]]);
    render(<App />);
    await screen.findByText("No Job Postings yet.");

    fireEvent.change(screen.getByLabelText("Paste a Job Posting"), {
      target: { value: "Senior GenAI Engineer" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add posting" }));

    expect(await screen.findByText("Working on the title…")).toBeTruthy();
    expect(
      await screen.findByText("GenAI Developer at Northwind Labs", {}, { timeout: 4000 }),
    ).toBeTruthy();
    expect(screen.queryByText("Working on the title…")).toBeNull();

    const callsWhenDone = fetchMock.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 2500));
    expect(fetchMock.mock.calls.length).toBe(callsWhenDone);
  }, 10000);

  it("clears the text and doesn't invite a retry when only the refresh fails", async () => {
    let lists = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        if (init?.method === "POST") return new Response("{}", { status: 201 });
        lists += 1;
        return lists === 1 ? new Response("[]") : new Response("{}", { status: 500 });
      }),
    );
    render(<App />);
    await screen.findByText("No Job Postings yet.");
    const field = screen.getByLabelText<HTMLTextAreaElement>("Paste a Job Posting");

    fireEvent.change(field, { target: { value: "Saved once" } });
    fireEvent.click(screen.getByRole("button", { name: "Add posting" }));

    expect((await screen.findByRole("alert")).textContent).toContain("was saved");
    expect(field.value).toBe("");
  });

  it("shows an error and keeps the text when saving fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) =>
        init?.method === "POST"
          ? new Response("{}", { status: 500 })
          : new Response("[]"),
      ),
    );
    render(<App />);
    await screen.findByText("No Job Postings yet.");
    const field = screen.getByLabelText<HTMLTextAreaElement>("Paste a Job Posting");

    fireEvent.change(field, { target: { value: "Keep me" } });
    fireEvent.click(screen.getByRole("button", { name: "Add posting" }));

    expect((await screen.findByRole("alert")).textContent).toContain("couldn't save");
    expect(field.value).toBe("Keep me");
  });
});
