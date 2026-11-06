// Shown on both the Application page and the Applications list.
export type Outcome = "interview" | "offer" | "rejected" | "no_response";

export const OUTCOMES: Record<Outcome, string> = {
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  no_response: "No response",
};

export type AccentColour = "navy" | "teal" | "burgundy" | "gold";

// Each accent colour's text colour and the light band behind headings, as the files use them.
export const ACCENTS: Record<AccentColour, { text: string; band: string }> = {
  navy: { text: "#1F3A5F", band: "#EAF0F6" },
  teal: { text: "#0F5E5E", band: "#E5F1F1" },
  burgundy: { text: "#7A1F3D", band: "#F6EAEE" },
  gold: { text: "#7A5C10", band: "#F6F0E0" },
};

// A role heading's closing date range, which the styled resume sets at the right margin.
const DATES =
  /,?\s*((?:[A-Z][a-z]{2,8}\.?\s+)?(?:19|20)\d{2}\s*(?:-|–|—|to|until)\s*(?:(?:[A-Z][a-z]{2,8}\.?\s+)?(?:19|20)\d{2}|[Pp]resent|[Nn]ow|[Cc]urrent|[Tt]oday))\s*$/;

export function splitDates(heading: string): [string, string | null] {
  const match = DATES.exec(heading);
  if (!match || match.index === 0) return [heading, null];
  return [heading.slice(0, match.index).replace(/[ ,]+$/, ""), match[1]];
}

export function dollars(cost: string): string {
  return `$${Number(cost).toFixed(4)}`;
}
