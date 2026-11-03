import { useState } from "react";
import type { CSSProperties } from "react";

export type Requirement = {
  requirement: string;
  kind: "hard_blocker" | "must_have" | "nice_to_have";
  quote: string | null;
  result: "met" | "partial" | "missing" | "unknown";
  evidence: string[];
  gap: string | null;
};

export type Match = {
  band: string;
  nice_met: number;
  reasons: string[];
  gaps: string[];
  requests: string[];
  requirements: Requirement[];
};

export type RatedPosting = {
  id: string;
  title: string;
  source: string;
  posting_type: "employment" | "freelance" | null;
  created_at: string;
  match: Match;
};

const BANDS = ["High", "Medium", "Low"];
const KINDS = { hard_blocker: "Hard Blocker", must_have: "Must-have", nice_to_have: "Nice-to-have" };
const RESULTS = { met: "Met", partial: "Partial", missing: "Missing", unknown: "Unknown" };
const BAND_COLOURS: Record<string, CSSProperties> = {
  High: { background: "#dff5e3", color: "#14622a" },
  Medium: { background: "#fff3c4", color: "#6b4e00" },
  Low: { background: "#fdecea", color: "#8a1c12" },
};
const card: CSSProperties = { border: "1px solid #ccc", borderRadius: 8, padding: 12, marginBottom: 8 };
const badge: CSSProperties = { fontSize: 12, fontWeight: 700, padding: "1px 8px", borderRadius: 10, marginRight: 4, background: "#e4e7eb" };
const DAY_MS = 86_400_000;

function age(createdAt: string): string {
  const days = Math.floor((Date.now() - new Date(createdAt).getTime()) / DAY_MS);
  return days < 1 ? "Added today" : `Added ${days} ${days === 1 ? "day" : "days"} ago`;
}

function Badges({ posting }: { posting: RatedPosting }) {
  return (
    <>
      <span style={{ ...badge, ...BAND_COLOURS[posting.match.band] }}>{posting.match.band}</span>
      {posting.posting_type && (
        <span style={badge}>{posting.posting_type === "freelance" ? "Freelance" : "Employment"}</span>
      )}
    </>
  );
}

function Detail({ posting, onAddToProfile }: { posting: RatedPosting; onAddToProfile: (requirement: string) => void }) {
  const { match } = posting;
  return (
    <div style={{ ...card, position: "sticky", top: 8 }}>
      <h2 style={{ marginTop: 0 }}>{posting.title}</h2>
      <Badges posting={posting} />
      <div style={{ fontSize: 13 }}>
        {posting.source} · {age(posting.created_at)}
      </div>
      <ul>
        {match.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
      {match.gaps.length > 0 && <p style={{ fontSize: 13 }}>Gaps: {match.gaps.join("; ")}</p>}
      {match.requests.map((ask) => (
        <p key={ask} style={{ fontSize: 13, background: "#fff8e1", padding: "4px 8px" }}>
          {ask}
        </p>
      ))}
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left" }}>Requirement</th>
            <th style={{ textAlign: "left" }}>Result</th>
            <th style={{ textAlign: "left" }}>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {match.requirements.map((r) => (
            <tr key={`${r.kind}-${r.requirement}`} style={{ borderTop: "1px solid #e4e7eb", verticalAlign: "top" }}>
              <td>
                <b>{r.requirement}</b>
                <div style={{ fontSize: 13 }}>{KINDS[r.kind]}</div>
                <div style={{ fontSize: 13, borderLeft: "3px solid #9aa5b1", paddingLeft: 6 }}>
                  {r.quote ? `“${r.quote}”` : "Taken as required: the posting names no language"}
                </div>
              </td>
              <td>
                {RESULTS[r.result]}
                {r.gap && <div style={{ fontSize: 13 }}>{r.gap}</div>}
              </td>
              <td>
                {r.evidence.length > 0 ? (
                  r.evidence.map((item) => <div key={item}>{item}</div>)
                ) : (
                  <>
                    <div style={{ fontSize: 13 }}>No Evidence found</div>
                    <button onClick={() => onAddToProfile(r.requirement)}>Add to Profile</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Matches({
  postings,
  onAddToProfile,
}: {
  postings: RatedPosting[];
  onAddToProfile: (requirement: string) => void;
}) {
  const [showLow, setShowLow] = useState(false);
  const sorted = [...postings].sort(
    (a, b) => BANDS.indexOf(a.match.band) - BANDS.indexOf(b.match.band) || b.match.nice_met - a.match.nice_met,
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = sorted.find((p) => p.id === selectedId) ?? sorted.find((p) => p.match.band !== "Low") ?? sorted[0];
  if (!selected) return null;

  const row = (posting: RatedPosting) => (
    <div key={posting.id} style={{ ...card, outline: posting.id === selected.id ? "2px solid #1f5fbf" : undefined }}>
      <b>{posting.title}</b>
      <div>
        <Badges posting={posting} />
        <span style={{ fontSize: 13 }}>{age(posting.created_at)}</span>
      </div>
      <button aria-label={`View ${posting.title}`} onClick={() => setSelectedId(posting.id)}>
        View
      </button>
    </div>
  );
  const inBand = (band: string) => sorted.filter((p) => p.match.band === band);

  return (
    <section>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(260px, 2fr) 3fr", gap: 12, alignItems: "start" }}>
        <div>
          {["High", "Medium"].map((band) => (
            <div key={band}>
              <h3>
                {band} ({inBand(band).length})
              </h3>
              {inBand(band).map(row)}
            </div>
          ))}
          {inBand("Low").length > 0 && (
            <>
              <button aria-expanded={showLow} onClick={() => setShowLow(!showLow)}>
                {showLow ? "Hide" : "Show"} Low ({inBand("Low").length})
              </button>
              {showLow && inBand("Low").map(row)}
            </>
          )}
        </div>
        <Detail posting={selected} onAddToProfile={onAddToProfile} />
      </div>
      <p style={{ fontSize: 13 }}>
        Interview Likelihood is an estimate of how well your Evidence covers the posting. It doesn't predict the
        employer's decision.
      </p>
    </section>
  );
}
