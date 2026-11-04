import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

type EvidenceRef = { text: string; origin: "resume" | "self_reported" | "profile" };
type Claim = { text: string; evidence: EvidenceRef[] };
type RemovedClaim = { text: string; kind: "stretched" | "invented" | "unchecked"; reason: string; next_step: string };
type Pack = {
  version: number;
  status: "generating" | "waiting" | "ready";
  warning: string | null;
  model: string | null;
  resume: { skills: Claim[]; experience: { heading: Claim; bullets: Claim[] }[]; education: Claim[] } | null;
  cover_letter: { paragraphs: Claim[][] } | null;
  removed_claims: RemovedClaim[] | null;
};
export type ApplicationData = { id: string; title: string; employer: string | null; source: string; pack: Pack };

const REFRESH_MS = 2000;
const card: CSSProperties = { border: "1px solid #ccc", borderRadius: 8, padding: 12, marginBottom: 10 };
const page: CSSProperties = {
  background: "#fff",
  boxShadow: "0 1px 5px rgba(0,0,0,.25)",
  padding: "34px 40px",
  fontFamily: "Georgia, serif",
  minHeight: 400,
};
const sectionHeading: CSSProperties = { margin: "12px 0 2px", borderBottom: "1px solid #52606d", fontSize: 14 };
const ORIGINS = { resume: "Resume", self_reported: "Profile entry (self-reported)", profile: "Your Profile" };
const KINDS = { stretched: "Stretched", invented: "No Evidence", unchecked: "Not checked" };

async function getApplication(id: string): Promise<ApplicationData> {
  const response = await fetch(`/api/applications/${id}`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function Resume({ resume }: { resume: NonNullable<Pack["resume"]> }) {
  return (
    <div style={page} aria-label="Resume">
      {resume.skills.length > 0 && (
        <>
          <h4 style={sectionHeading}>Skills</h4>
          {resume.skills.map((skill) => skill.text).join(", ")}
        </>
      )}
      {resume.experience.length > 0 && <h4 style={sectionHeading}>Experience</h4>}
      {resume.experience.map((job) => (
        <div key={job.heading.text}>
          <b>{job.heading.text}</b>
          <ul style={{ margin: "4px 0", paddingLeft: 20 }}>
            {job.bullets.map((bullet) => (
              <li key={bullet.text}>{bullet.text}</li>
            ))}
          </ul>
        </div>
      ))}
      {resume.education.length > 0 && (
        <>
          <h4 style={sectionHeading}>Education</h4>
          {resume.education.map((item) => (
            <div key={item.text}>{item.text}</div>
          ))}
        </>
      )}
    </div>
  );
}

function CoverLetter({ letter }: { letter: NonNullable<Pack["cover_letter"]> }) {
  return (
    <div style={page} aria-label="Cover letter">
      {letter.paragraphs.map((paragraph) => (
        <p key={paragraph.map((sentence) => sentence.text).join(" ")}>
          {paragraph.map((sentence) => sentence.text).join(" ")}
        </p>
      ))}
    </div>
  );
}

function allClaims(pack: Pack): Claim[] {
  const resume = pack.resume!;
  return [
    ...resume.skills,
    ...resume.experience.flatMap((job) => [job.heading, ...job.bullets]),
    ...resume.education,
    ...pack.cover_letter!.paragraphs.flat(),
  ].filter((claim) => claim.evidence.length > 0);
}

export function Application({ id, onBack }: { id: string; onBack: () => void }) {
  const [application, setApplication] = useState<ApplicationData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getApplication(id)
      .then(setApplication)
      .catch(() => setError("We couldn't load this Application. Try refreshing the page."));
  }, [id]);

  const generating = application?.pack.status === "generating";
  useEffect(() => {
    if (!generating) return;
    // A failed refresh just tries again on the next tick.
    const timer = setInterval(() => {
      getApplication(id)
        .then(setApplication)
        .catch(() => {});
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [id, generating]);

  async function retry() {
    setError("");
    const response = await fetch(`/api/applications/${id}/retry`, { method: "POST" }).catch(() => null);
    if (!response?.ok) {
      setError("We couldn't retry. Try again in a moment.");
      return;
    }
    setApplication(await response.json());
  }

  const pack = application?.pack;
  return (
    <section>
      <p>
        <button onClick={onBack}>← Back to job listings</button>{" "}
        <span style={{ fontSize: 13 }}>Your draft stays saved.</span>
      </p>
      {application && (
        <h2>
          Final documents: {application.title}
          {application.employer && `, ${application.employer}`}
        </h2>
      )}
      {error && <p role="alert">{error}</p>}
      {pack?.status === "generating" && <p>Writing and checking your Application Pack…</p>}
      {pack?.status === "waiting" && (
        <div role="alert" style={{ ...card, background: "#fdecea" }}>
          <p style={{ marginTop: 0 }}>{pack.warning}</p>
          <button onClick={retry}>Retry</button>
        </div>
      )}
      {pack?.status === "ready" && (
        <>
          <p style={{ ...card, background: "#e3edff" }}>
            Preview of both final documents. Every Claim was checked against your Evidence.
            {pack.model && ` Written by ${pack.model}.`}
          </p>
          {pack.removed_claims!.length > 0 && (
            <div style={card}>
              <h3 style={{ marginTop: 0 }}>Claims without Evidence</h3>
              {pack.removed_claims!.map((removed) => (
                <div key={removed.text} style={{ borderTop: "1px solid #e4e7eb", padding: "6px 0" }}>
                  <s>{removed.text}</s> <span style={{ fontSize: 12 }}>({KINDS[removed.kind]})</span>
                  <div style={{ fontSize: 13 }}>{removed.reason}</div>
                  <div style={{ fontSize: 13 }}>{removed.next_step}</div>
                </div>
              ))}
            </div>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, alignItems: "start" }}>
            <Resume resume={pack.resume!} />
            <CoverLetter letter={pack.cover_letter!} />
          </div>
          <div style={{ ...card, marginTop: 12 }}>
            <h3 style={{ marginTop: 0 }}>Evidence</h3>
            <ul>
              {allClaims(pack).map((claim) => (
                <li key={claim.text}>
                  <b>{claim.text}</b>
                  {claim.evidence.map((item) => (
                    <div key={item.text} style={{ fontSize: 13 }}>
                      {ORIGINS[item.origin]}: {item.text}
                    </div>
                  ))}
                </li>
              ))}
            </ul>
          </div>
          <p style={{ fontSize: 13 }}>Job Copilot never submits for you.</p>
        </>
      )}
    </section>
  );
}
