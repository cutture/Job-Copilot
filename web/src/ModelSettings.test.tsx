import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ModelSettings } from "./ModelSettings";

const free = {
  mode: "free",
  note: "No Anthropic key is set, so free models that don't train on your data are in use.",
  groq_zdr_confirmed: false,
  personal_work_waits: true,
};

function serve(body: object) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, method: init?.method ?? "GET", body: init?.body });
      return new Response(JSON.stringify(init?.method === "PUT" ? { ...body, groq_zdr_confirmed: true, personal_work_waits: false } : body));
    }),
  );
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ModelSettings", () => {
  it("says why free models are in use and that personal work waits until a free model is set up", async () => {
    serve(free);
    render(<ModelSettings />);

    expect(await screen.findByText(/No Anthropic key is set/)).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("wait");
  });

  it("confirms Groq's Zero Data Retention with a checkbox that starts unticked", async () => {
    const calls = serve(free);
    render(<ModelSettings />);

    const box = (await screen.findByRole("checkbox", { name: /Zero Data Retention/ })) as HTMLInputElement;
    expect(box.checked).toBe(false);
    fireEvent.click(box);

    expect(await screen.findByRole("checkbox", { checked: true })).toBeTruthy();
    expect(calls.at(-1)).toEqual({ url: "/api/model-settings/groq-zdr", method: "PUT", body: JSON.stringify({ confirmed: true }) });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says paid models are in use when there is a key with credit", async () => {
    serve({ ...free, mode: "paid", note: null, personal_work_waits: false });
    render(<ModelSettings />);

    expect(await screen.findByText(/Claude Haiku is in use/)).toBeTruthy();
  });

  it("links each provider's data policy", async () => {
    serve(free);
    render(<ModelSettings />);

    for (const name of [/Anthropic's data policy/, /Groq's data controls/, /Cloudflare's data policy/]) {
      expect((await screen.findByRole("link", { name })).getAttribute("href")).toMatch(/^https:\/\//);
    }
  });
});
