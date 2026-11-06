import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { ConfirmDelete } from "./ConfirmDelete";
import { ACCENTS, OUTCOMES, dollars, splitDates } from "./labels";
import type { AccentColour, Outcome } from "./labels";

type EvidenceRef = {
  text: string;
  origin: "resume" | "self_reported" | "profile";
  // Deleted after this Pack was Submitted; the Pack stays as it was sent.
  deleted?: boolean;
};
type Claim = { text: string; evidence: EvidenceRef[] };
type RemovedClaim = {
  text: string;
  kind: "stretched" | "invented" | "unchecked" | "with_heading" | "evidence_deleted";
  reason: string;
  next_step: string;
};
type Role = { heading: Claim; lines: Claim[] };
// Experience holds roles; every other kind holds Claims.
type SectionKind =
  | "summary"
  | "skills"
  | "experience"
  | "education"
  | "qualifications"
  | "affiliations"
  | "certifications"
  | "custom";
type Group = { heading: Claim; claims: Claim[] };
type Section = { kind: SectionKind; heading: string; claims: Claim[]; groups: Group[]; roles: Role[] };
type Pack = {
  version: number;
  status: "generating" | "waiting" | "ready";
  warning: string | null;
  model: string | null;
  resume: { sections: Section[] } | null;
  cover_letter: { paragraphs: Claim[][] } | null;
  removed_claims: RemovedClaim[] | null;
};
export type ApplicationData = {
  id: string;
  title: string;
  employer: string | null;
  source: string;
  apply_url: string | null;
  reviewed: boolean;
  submitted_at: string | null;
  outcome: Outcome | null;
  cost_usd: string;
  // From the Profile; both files start with them and the letter is signed with the name.
  name: string | null;
  contact: string | null;
  accent_colour: AccentColour;
  // None once the person deletes it.
  pack: Pack | null;
};
type Signature = Pick<ApplicationData, "name" | "contact">;
export type Pair = "styled" | "plain";
type Props<T> = { signature: Signature; pair: Pair; accent: AccentColour } & T;

// The styled pair's page uses the files' sans-serif font; the plain pair keeps the page's own.
function pageFor(pair: Pair): CSSProperties {
  return pair === "styled" ? { ...page, fontFamily: "Calibri, sans-serif" } : page;
}

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
const KINDS = {
  stretched: "Stretched",
  invented: "No Evidence",
  unchecked: "Not checked",
  evidence_deleted: "Evidence deleted",
  with_heading: "Removed with its job heading",
};

async function getApplication(id: string): Promise<ApplicationData> {
  const response = await fetch(`/api/applications/${id}`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

// The top of both files, as they download: the styled pair's name is two-tone, its surname and
// a thin rule in the accent colour.
function Header({ signature: { name, contact }, pair, accent }: Props<object>) {
  const colour = ACCENTS[accent].text;
  if (pair === "plain") {
    return (
      <>
        {name && <b style={{ display: "block" }}>{name}</b>}
        {contact && <div>{contact}</div>}
      </>
    );
  }
  const split = name ? name.lastIndexOf(" ") : -1;
  return (
    <div style={{ textAlign: "center" }}>
      {name && (
        <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "Calibri, sans-serif" }}>
          {split > 0 && <span style={{ color: "#333333" }}>{name.slice(0, split + 1)}</span>}
          <span style={{ color: colour }}>{name.slice(split + 1)}</span>
        </div>
      )}
      {contact && <div style={{ borderBottom: `1px solid ${colour}`, paddingBottom: 2 }}>{contact}</div>}
    </div>
  );
}

function Heading({ text, pair, accent }: { text: string; pair: Pair; accent: AccentColour }) {
  if (pair === "plain") return <h4 style={sectionHeading}>{text}</h4>;
  const { text: colour, band } = ACCENTS[accent];
  return (
    <h4
      style={{
        ...sectionHeading,
        color: colour,
        background: band,
        borderBottom: `1px solid ${colour}`,
        textAlign: "center",
        textTransform: "uppercase",
      }}
    >
      {text}
    </h4>
  );
}

// Skills as the files set them: two columns of bullets when styled, one line when plain.
function Skills({ skills, styled }: { skills: Claim[]; styled: boolean }) {
  return styled ? (
    <ul style={{ columns: 2, margin: "4px 0", paddingLeft: 20 }}>
      {skills.map((skill) => (
        <li key={skill.text}>{skill.text}</li>
      ))}
    </ul>
  ) : (
    <div>{skills.map((skill) => skill.text).join(", ")}</div>
  );
}

function Resume({ resume, signature, pair, accent }: Props<{ resume: NonNullable<Pack["resume"]> }>) {
  const styled = pair === "styled";
  return (
    <div style={pageFor(pair)} aria-label="Resume">
      <Header signature={signature} pair={pair} accent={accent} />
      {resume.sections.map((section, position) => (
        <div key={`${section.kind}-${position}`}>
          <Heading text={section.heading} pair={pair} accent={accent} />
          {section.kind === "summary" ? (
            <div>{section.claims.map((sentence) => sentence.text).join(" ")}</div>
          ) : section.kind === "skills" ? (
            <>
              {section.claims.length > 0 && <Skills skills={section.claims} styled={styled} />}
              {section.groups.map((group) =>
                styled ? (
                  <div key={group.heading.text}>
                    <b>{group.heading.text}</b>
                    <Skills skills={group.claims} styled />
                  </div>
                ) : (
                  <div key={group.heading.text}>
                    <b>{group.heading.text}: </b>
                    {group.claims.map((skill) => skill.text).join(", ")}
                  </div>
                ),
              )}
            </>
          ) : (
            section.claims.map((claim) => <div key={claim.text}>{claim.text}</div>)
          )}
          {section.roles.map((role) => {
            const [title, dates] = styled ? splitDates(role.heading.text) : [role.heading.text, null];
            return (
              <div key={role.heading.text}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <b>{title}</b>
                  {dates && <span>{dates}</span>}
                </div>
                <ul style={{ margin: "4px 0", paddingLeft: 20 }}>
                  {role.lines.map((line) => (
                    <li key={line.text}>{line.text}</li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function CoverLetter({ letter, signature, pair, accent }: Props<{ letter: NonNullable<Pack["cover_letter"]> }>) {
  return (
    <div
      style={pageFor(pair)}
      aria-label="Cover letter"
    >
      <Header signature={signature} pair={pair} accent={accent} />
      {letter.paragraphs.map((paragraph) => (
        <p key={paragraph.map((sentence) => sentence.text).join(" ")}>
          {paragraph.map((sentence) => sentence.text).join(" ")}
        </p>
      ))}
      {signature.name && <p>{signature.name}</p>}
    </div>
  );
}

function allClaims(pack: Pack): Claim[] {
  return [
    ...pack.resume!.sections.flatMap((section) => [
      ...section.claims,
      ...section.groups.flatMap((group) => [group.heading, ...group.claims]),
      ...section.roles.flatMap((role) => [role.heading, ...role.lines]),
    ]),
    ...pack.cover_letter!.paragraphs.flat(),
  ].filter((claim) => claim.evidence.length > 0);
}

type FinishProps = {
  application: ApplicationData;
  pair: Pair;
  onReview: (reviewed: boolean) => void;
  onSubmitted: () => void;
  onOutcome: (outcome: Outcome) => void;
  onDownload: (path: string) => void;
  // Why the last download was refused, shown beside the buttons.
  downloadError: string;
};

function Finish({ application, pair, onReview, onSubmitted, onOutcome, onDownload, downloadError }: FinishProps) {
  const { reviewed, submitted_at } = application;
  const download = (path: string, label: string) => (
    <button disabled={!reviewed} onClick={() => onDownload(`${path}?pair=${pair}`)}>
      {label}
    </button>
  );
  const suffix = pair === "styled" ? "" : " (plain)";
  return (
    <div style={{ ...card, marginTop: 12 }}>
      {!application.name && (
        <p style={{ fontSize: 13, background: "#fff8e1", padding: "4px 8px" }}>
          Add your name to your Profile so it appears in your files and their names.
        </p>
      )}
      <label>
        <input
          type="checkbox"
          checked={reviewed}
          disabled={!!submitted_at}
          onChange={(event) => onReview(event.target.checked)}
        />{" "}
        I've reviewed
        this Application Pack
      </label>
      <div style={{ margin: "6px 0" }}>
        {download("resume.docx", `Resume DOCX${suffix}`)}{" "}
        {download("cover-letter.docx", `Cover letter DOCX${suffix}`)}
      </div>
      {downloadError && <p role="alert">{downloadError}</p>}
      <div>
        {application.apply_url &&
          (reviewed ? (
            <a href={application.apply_url} target="_blank" rel="noreferrer noopener" style={{ marginRight: 8 }}>
              Open employer's application page
            </a>
          ) : (
            <button disabled>Open employer's application page</button>
          ))}
        <button disabled={!reviewed || !!submitted_at} onClick={onSubmitted}>
          {submitted_at ? `✓ Submitted ${new Date(submitted_at).toLocaleString()}` : "I submitted it on their site"}
        </button>
      </div>
      {submitted_at && (
        <div role="group" aria-label="Outcome" style={{ marginTop: 6 }}>
          Outcome:{" "}
          {(Object.keys(OUTCOMES) as Outcome[]).map((outcome) => (
            <button key={outcome} aria-pressed={application.outcome === outcome} onClick={() => onOutcome(outcome)}>
              {OUTCOMES[outcome]}
            </button>
          ))}
        </div>
      )}
      <p style={{ fontSize: 13, marginBottom: 0 }}>
        Job Copilot never submits for you. This Application has cost {dollars(application.cost_usd)} so far.
      </p>
    </div>
  );
}

export function Application({ id, onBack }: { id: string; onBack: () => void }) {
  const [application, setApplication] = useState<ApplicationData | null>(null);
  const [error, setError] = useState("");
  const [downloadError, setDownloadError] = useState("");
  const [pair, setPair] = useState<Pair>("styled");

  useEffect(() => {
    getApplication(id)
      .then(setApplication)
      .catch(() => setError("We couldn't load this Application. Try refreshing the page."));
  }, [id]);

  const generating = application?.pack?.status === "generating";
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

  async function update(path: string, method: string, failure: string, body?: unknown) {
    setError("");
    const response = await fetch(`/api/applications/${id}/${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }).catch(() => null);
    if (!response?.ok) {
      setError(failure);
      return;
    }
    setApplication(await response.json());
  }

  const retry = () => update("retry", "POST", "We couldn't retry. Try again in a moment.");
  const review = (reviewed: boolean) =>
    update("review", "PUT", "We couldn't save your review. Try again.", { reviewed });
  const submitted = () => update("submitted", "POST", "We couldn't mark it as Submitted. Try again.");
  const report = (outcome: Outcome) =>
    update("outcome", "PUT", "We couldn't save the Outcome. Try again.", { outcome });
  const deletePack = () => update("pack", "DELETE", "We couldn't delete the Pack. Try again.");
  const writePack = () => update("pack", "POST", "We couldn't start a new Pack. Try again.");

  // Fetched first, so a file the ATS check refuses shows why instead of saving an error page.
  async function downloadFile(path: string) {
    setDownloadError("");
    const response = await fetch(`/api/applications/${id}/${path}`).catch(() => null);
    if (!response?.ok) {
      const detail = await response?.json().then((body) => body.detail).catch(() => null);
      setDownloadError(typeof detail === "string" ? detail : "We couldn't download the file. Try again.");
      return;
    }
    const name = /filename\*=UTF-8''([^;]+)/.exec(response.headers.get("content-disposition") ?? "");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(await response.blob());
    link.download = name ? decodeURIComponent(name[1]) : path.split("?")[0];
    link.click();
    URL.revokeObjectURL(link.href);
  }

  async function deleteApplication() {
    const response = await fetch(`/api/applications/${id}`, { method: "DELETE" }).catch(() => null);
    if (!response?.ok) {
      setError("We couldn't delete this Application. Try again.");
      return;
    }
    onBack();
  }

  const pack = application?.pack;
  const back = (
    <p>
      <button onClick={onBack}>← Back to job listings</button>{" "}
      <span style={{ fontSize: 13 }}>Your draft stays saved.</span>
    </p>
  );
  return (
    <section>
      {back}
      {application && (
        <h2>
          Final documents: {application.title}
          {application.employer && `, ${application.employer}`}
        </h2>
      )}
      {error && <p role="alert">{error}</p>}
      {application && !pack && (
        <div style={card}>
          <p style={{ marginTop: 0 }}>This Application has no Application Pack.</p>
          <button onClick={writePack}>Write a new Application Pack</button>
        </div>
      )}
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
          <div role="group" aria-label="Which pair" style={{ marginBottom: 8 }}>
            Preview and download:{" "}
            <button aria-pressed={pair === "styled"} onClick={() => setPair("styled")}>
              Styled pair
            </button>{" "}
            <button aria-pressed={pair === "plain"} onClick={() => setPair("plain")}>
              Plain pair
            </button>{" "}
            <span style={{ fontSize: 13 }}>Both read cleanly in an ATS. Use the plain pair for strict portals.</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, alignItems: "start" }}>
            <Resume resume={pack.resume!} signature={application!} pair={pair} accent={application!.accent_colour} />
            <CoverLetter
              letter={pack.cover_letter!}
              signature={application!}
              pair={pair}
              accent={application!.accent_colour}
            />
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
                      {item.deleted && <strong> (Evidence deleted)</strong>}
                    </div>
                  ))}
                </li>
              ))}
            </ul>
          </div>
          {application && (
            <Finish
              application={application}
              pair={pair}
              onReview={review}
              onSubmitted={submitted}
              onOutcome={report}
              onDownload={downloadFile}
              downloadError={downloadError}
            />
          )}
        </>
      )}
      {application && (
        <p>
          {pack && pack.status !== "generating" && !application.submitted_at && (
            <ConfirmDelete
              label="Delete this Pack"
              question="Delete this Application Pack? The Application stays."
              onConfirm={deletePack}
            />
          )}{" "}
          <ConfirmDelete
            label="Delete this Application"
            question="Delete this Application and its Pack? The Job Posting stays."
            onConfirm={deleteApplication}
          />
        </p>
      )}
      {/* A long Pack page ends where it started, so there's no scrolling back up. */}
      {back}
    </section>
  );
}
