import { describe, expect, it } from "vitest";
import { deletionNotice } from "./labels";

describe("deletionNotice", () => {
  const today = new Date("2026-11-15T12:00:00Z");

  it("counts down only in the last week before an automatic deletion", () => {
    expect(deletionNotice("2026-11-30", "This Pack", today)).toBeNull();
    expect(deletionNotice("2026-11-22", "This Pack", today)).toBe("This Pack will be deleted in 7 days");
    expect(deletionNotice("2026-11-16", "This Pack", today)).toBe("This Pack will be deleted in 1 day");
    expect(deletionNotice("2026-11-15", "This Pack", today)).toBe("This Pack will be deleted today");
  });

  it("says nothing when nothing is due to be deleted", () => {
    expect(deletionNotice(null, "This Pack", today)).toBeNull();
    expect(deletionNotice(undefined, "This Pack", today)).toBeNull();
  });
});
