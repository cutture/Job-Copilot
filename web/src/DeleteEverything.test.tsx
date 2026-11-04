import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DeleteEverything, DeletionReportView } from "./DeleteEverything";

const report = {
  deleted: { "Job Postings": 4, Applications: 1 },
  not_deleted: ["Files you downloaded stay on your computer. Delete them yourself."],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("DeleteEverything", () => {
  it("deletes only once DELETE is typed, then reports what was and wasn't deleted", async () => {
    const sent: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        sent.push(String(init?.body));
        return new Response(JSON.stringify(report));
      }),
    );
    const onDeleted = vi.fn();
    render(<DeleteEverything onDeleted={onDeleted} />);
    const button = screen.getByRole("button", { name: "Delete everything" });

    fireEvent.change(screen.getByLabelText("Type DELETE to confirm"), { target: { value: "delete" } });
    expect(button.hasAttribute("disabled")).toBe(true);
    fireEvent.change(screen.getByLabelText("Type DELETE to confirm"), { target: { value: "DELETE" } });
    fireEvent.click(button);

    await vi.waitFor(() => expect(onDeleted).toHaveBeenCalledWith(report));
    expect(sent).toEqual([JSON.stringify({ confirm: "DELETE" })]);
  });

  it("lists the report", () => {
    render(<DeletionReportView report={report} />);

    expect(screen.getByText("Job Postings: 4 deleted")).toBeTruthy();
    expect(screen.getByText(/downloaded stay on your computer/)).toBeTruthy();
  });
});
