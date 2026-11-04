import { useState } from "react";
import type { CSSProperties } from "react";

export type Band = "High" | "Medium" | "Low";
export type RatingState = "rated" | "rating" | "waiting";

export type Requirement = {
  requirement: string;
  kind: "hard_blocker" | "must_have" | "nice_to_have";
  quote: string | null;
  result: "met" | "partial" | "missing" | "unknown";
  evidence: string[];
  gap: string | null;
  profile_field?: string | null;
};

export type Match = {
  band: Band;
  nice_met: number;
  reasons: string[];
  gaps: string[];
  profile_prompts: string[];
  requirements: Requirement[];
};

export type PostingOrigin = {
  source: string;
  employer?: string | null;
  created_at: string;
  // The original publish date from the Source; pasted postings have none.
  posted_on?: string | null;
  date_provided?: boolean;
  credit_url?: string | null;
  credit_text?: string | null;
};

export type RatedPosting = PostingOrigin & {
  id: string;
  title: string;
  posting_type: "employment" | "freelance" | null;
  match: Match;
  // The Application started by clicking Apply, if there is one.
  application_id?: string | null;
};

const BANDS: Band[] = ["High", "Medium", "Low"];
const KINDS = { hard_blocker: "Hard Blocker", must_have: "Must-have", nice_to_have: "Nice-to-have" };
const RESULTS = { met: "Met", partial: "Partial", missing: "Missing", unknown: "Unknown" };
const BAND_COLOURS: Record<Band, CSSProperties> = {
  High: { background: "#dff5e3", color: "#14622a" },
  Medium: { background: "#fff3c4", color: "#6b4e00" },
  Low: { background: "#fdecea", color: "#8a1c12" },
};
const card: CSSProperties = { border: "1px solid #ccc", borderRadius: 8, padding: 12, marginBottom: 8 };
const badge: CSSProperties = { fontSize: 12, fontWeight: 700, padding: "1px 8px", borderRadius: 10, marginRight: 4, background: "#e4e7eb" };
const DAY_MS = 86_400_000;

export function age(posting: PostingOrigin): string {
  if (posting.date_provided === false) return "Date not provided";
  const verb = posting.posted_on ? "Posted" : "Added";
  const days = Math.floor((Date.now() - new Date(posting.posted_on ?? posting.created_at).getTime()) / DAY_MS);
  return days < 1 ? `${verb} today` : `${verb} ${days} ${days === 1 ? "day" : "days"} ago`;
}

export function Origin({ posting }: { posting: PostingOrigin }) {
  const where = posting.credit_text ?? posting.source;
  const name = posting.employer ? `${posting.employer} on ${where}` : where;
  return posting.credit_url ? (
    <a href={posting.credit_url} target="_blank" rel="noreferrer noopener">
      {name}
    </a>
  ) : (
    <span>{name}</span>
  );
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

type DetailProps = {
  posting: RatedPosting;
  onAddToProfile: (draft: string) => void;
  onApply: (posting: RatedPosting) => void;
};

function Detail({ posting, onAddToProfile, onApply }: DetailProps) {
  const { match } = posting;
  return (
    <div style={{ ...card, position: "sticky", top: 8 }}>
      <h2 style={{ marginTop: 0 }}>{posting.title}</h2>
      <Badges posting={posting} />
      <div style={{ fontSize: 13 }}>
        <Origin posting={posting} /> · {age(posting)}
      </div>
      <p>
        <button
          style={{ background: "#1f5fbf", borderColor: "#1f5fbf", color: "#fff" }}
          onClick={() => onApply(posting)}
        >
          {posting.application_id ? "Open Application Pack" : "Apply"}
        </button>{" "}
        <span style={{ fontSize: 13 }}>Apply writes your Application Pack. Nothing is submitted.</span>
      </p>
      <ul>
        {match.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
      {match.gaps.length > 0 && <p style={{ fontSize: 13 }}>Gaps: {match.gaps.join("; ")}</p>}
      {match.profile_prompts.map((ask) => (
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
                ) : r.profile_field ? (
                  <>
                    <div style={{ fontSize: 13 }}>Not in your Profile</div>
                    <button onClick={() => onAddToProfile("")}>Update your Profile</button>
                  </>
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
  onApply,
}: {
  postings: RatedPosting[];
  // Opens the Profile, with an Evidence item started from `draft` when it isn't empty.
  onAddToProfile: (draft: string) => void;
  // Starts the posting's Application, or opens the one already started.
  onApply: (posting: RatedPosting) => void;
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
        <span style={{ fontSize: 13 }}>{age(posting)}</span>
      </div>
      <button aria-label={`View ${posting.title}`} onClick={() => setSelectedId(posting.id)}>
        View
      </button>
    </div>
  );
  const inBand = (band: Band) => sorted.filter((p) => p.match.band === band);

  return (
    <section>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(260px, 2fr) 3fr", gap: 12, alignItems: "start" }}>
        <div>
          {(["High", "Medium"] as const).map((band) => (
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
        <Detail posting={selected} onAddToProfile={onAddToProfile} onApply={onApply} />
      </div>
      <p style={{ fontSize: 13 }}>
        Interview Likelihood is an estimate of how well your Evidence covers the posting. It doesn't predict the
        employer's decision.
      </p>
    </section>
  );
}
