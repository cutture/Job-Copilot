import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

type SpendingData = {
  spent_usd: string;
  // Part of spent_usd, from Eval Runs.
  evals_usd: string;
  cap_usd: string;
  // Evals stop at their own cap first, inside yours.
  eval_cap_usd: string | null;
  level: "ok" | "warning" | "reached";
  warning: string | null;
  months: { month: string; spent_usd: string; evals_usd: string }[];
};

const money = (amount: string) => `$${Number(amount).toFixed(2)}`;
const cell: CSSProperties = { borderBottom: "1px solid #ddd", padding: "4px 8px", textAlign: "left" };

async function getSpending(): Promise<SpendingData> {
  const response = await fetch("/api/spending");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

// A warning at 80% of the monthly cap, and an alert once it's reached.
export function SpendingBanner() {
  const [spending, setSpending] = useState<SpendingData | null>(null);
  useEffect(() => {
    getSpending()
      .then(setSpending)
      .catch(() => {});
  }, []);
  if (!spending?.warning) return null;
  const reached = spending.level === "reached";
  return (
    <p
      role={reached ? "alert" : "status"}
      style={{
        background: reached ? "#fdecea" : "#fff8e1",
        color: reached ? "#8a1c12" : "#6b4e00",
        border: `1px solid ${reached ? "#f0b8b2" : "#f3d98b"}`,
        padding: "8px 12px",
      }}
    >
      {spending.warning}
    </p>
  );
}

export function Spending() {
  const [spending, setSpending] = useState<SpendingData | null>(null);
  const [cap, setCap] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getSpending()
      .then((loaded) => {
        setSpending(loaded);
        setCap(Number(loaded.cap_usd).toString());
      })
      .catch(() => setError("We couldn't load your spending. Try refreshing the page."));
  }, []);

  async function saveCap() {
    setError("");
    const response = await fetch("/api/spending/cap", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ monthly_cap_usd: Number(cap) }),
    }).catch(() => null);
    if (!response?.ok) {
      setError("Set a cap between $0.01 and $1,000, then save it again.");
      return;
    }
    setSpending(await response.json());
  }

  if (error && !spending) return <p role="alert">{error}</p>;
  if (!spending) return <p>Loading your spending…</p>;
  return (
    <section>
      <h2>Spending</h2>
      <p>
        This month: {money(spending.spent_usd)} of your {money(spending.cap_usd)} monthly cap, across every paid AI
        call whichever provider it went to.
      </p>
      {spending.eval_cap_usd && (
        <p style={{ fontSize: 13 }}>
          {money(spending.evals_usd)} of it from Eval Runs, which stop at {money(spending.eval_cap_usd)} so the rest of
          your cap stays free for your own work.
        </p>
      )}
      <label htmlFor="cap">Monthly cap, in US dollars</label>{" "}
      <input id="cap" type="number" min="0.01" max="1000" step="0.01" value={cap} onChange={(e) => setCap(e.target.value)} />{" "}
      <button onClick={saveCap}>Save cap</button>
      {error && <p role="alert">{error}</p>}
      <table style={{ borderCollapse: "collapse", marginTop: 12, fontSize: 13 }}>
        <thead>
          <tr>
            {["Month", "Spent", "Of which Eval Runs"].map((heading) => (
              <th key={heading} style={cell}>
                {heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {spending.months.map((month) => (
            <tr key={month.month}>
              <td style={cell}>
                {new Date(month.month).toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" })}
              </td>
              <td style={cell}>{money(month.spent_usd)}</td>
              <td style={cell}>{money(month.evals_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ fontSize: 13 }}>Each month starts again from $0 on the 1st, in UTC.</p>
    </section>
  );
}
