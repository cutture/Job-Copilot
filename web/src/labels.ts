// Shown on both the Application page and the Applications list.
export type Outcome = "interview" | "offer" | "rejected" | "no_response";

export const OUTCOMES: Record<Outcome, string> = {
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  no_response: "No response",
};

export function dollars(cost: string): string {
  return `$${Number(cost).toFixed(4)}`;
}
