import { createContext, useContext, useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { ConfirmDelete } from "./ConfirmDelete";
import { ACCENTS, KINDS as REQUIREMENT_KINDS, OUTCOMES, PHOTO_STYLE, RESULTS, dollars, splitDates } from "./labels";
import type { AccentColour, Kind, Outcome, Result } from "./labels";

type EvidenceRef = {
  text: string;
  origin: "resume" | "self_reported" | "profile";
  // Deleted after this Pack was Submitted; the Pack stays as it was sent.
  deleted?: boolean;
  // The Evidence item's ID; null for a Profile fact.
  id?: number | null;
};
// kept: kept with Keep Anyway, so it has no Evidence; labelled here, never in the files.
type Claim = { text: string; evidence: EvidenceRef[]; kept?: boolean };
// One of the Application's Requirements and the Evidence its Result rests on.
type Requirement = {
  requirement: string;
  kind: Kind;
  result: Result;
  evidence_ids: number[];
  // The Profile field that decides it, such as a Hard Blocker; no Claim answers those.
  profile_field?: string | null;
};
type RemovedClaim = {
  text: string;
  kind: "stretched" | "invented" | "unchecked" | "with_heading" | "evidence_deleted";
  reason: string;
  next_step: string;
  // Its draft ID, which its actions use; null on Packs written before drafts were saved.
  id: string | null;
  // Kept with Keep Anyway, so it's in the documents too.
  kept: boolean;
  // Why Keep Anyway isn't offered, or null when it is.
  cant_keep: string | null;
  // Whether Check again could bring it back once Evidence is added.
  can_check: boolean;
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
type CountedRequirement = {
  requirement: string;
  kind: Exclude<Kind, "hard_blocker">;
  result: Result;
  // Whether the resume cites Evidence the Result rests on; null for Missing or Unknown.
  in_resume: boolean | null;
};
type Pack = {
  version: number;
  status: "generating" | "waiting" | "ready";
  warning: string | null;
  model: string | null;
  resume: { sections: Section[] } | null;
  cover_letter: { paragraphs: Claim[][] } | null;
  removed_claims: RemovedClaim[] | null;
  // For information only: nothing that writes or renders the Pack uses it.
  coverage: { score: number; counted: CountedRequirement[] } | null;
  requirements: Requirement[] | null;
  // Made while evals are failing; it blocks nothing.
  extra_care: boolean;
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
  // A photo goes on the styled resume, served by the Profile.
  has_photo: boolean;
  // None once the person deletes it.
  pack: Pack | null;
};
type Signature = Pick<ApplicationData, "name" | "contact" | "has_photo">;
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
// How the panel labels each Evidence item, and where it came from.
const ORIGINS = {
  resume: { badge: "Direct Evidence", from: "Your resume" },
  self_reported: { badge: "Self-reported", from: "A Profile entry you wrote" },
  profile: { badge: "Your Profile", from: "Your Profile's details" },
};

// The Claim open in the Evidence panel, and how a Claim in the documents opens it.
const ClaimPicker = createContext<{ selected: Claim | null; select: (claim: Claim) => void } | null>(null);

// A Claim with Evidence, underlined on screen only; label is a heading without its dates.
function ClaimText({ claim, label = claim.text }: { claim: Claim; label?: string }) {
  const picker = useContext(ClaimPicker);
  if (claim.kept) return <Kept text={label} />;
  if (!picker || claim.evidence.length === 0) return <>{label}</>;
  return (
    <ClaimLink selected={picker.selected === claim} onClick={() => picker.select(claim)}>
      {label}
    </ClaimLink>
  );
}

// A span rather than a button, so a Claim that wraps stays inline text, its bullet beside it.
// selected is left out where a Claim only opens, rather than shows which one is open.
function ClaimLink({ selected, onClick, children }: { selected?: boolean; onClick: () => void; children: string }) {
  return (
    <span
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={onClick}
      onKeyDown={(event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        onClick();
      }}
      style={{
        borderBottom: "1px dotted #1f5fbf",
        background: selected ? "#e3edff" : undefined,
        cursor: "pointer",
      }}
    >
      {children}
    </span>
  );
}

const keptBadge: CSSProperties = {
  fontFamily: "system-ui, sans-serif",
  fontSize: 11,
  background: "#fdecea",
  color: "#8a1c12",
  borderRadius: 4,
  padding: "0 4px",
  marginLeft: 4,
  whiteSpace: "nowrap",
};

// A kept Claim, labelled on screen only.
function Kept({ text }: { text: string }) {
  return (
    <>
      {text}
      <span style={keptBadge}>Kept by you</span>
    </>
  );
}

// Claims run together, as a summary, a skills line or a letter paragraph is written.
function Joined({ claims, separator }: { claims: Claim[]; separator: string }) {
  return (
    <>
      {claims.map((claim, position) => (
        <span key={position}>
          {position > 0 && separator}
          <ClaimText claim={claim} />
        </span>
      ))}
    </>
  );
}
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
function Header({ signature: { name, contact }, pair, accent, photo = false }: Props<{ photo?: boolean }>) {
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
      {(name || photo) && (
        <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "Calibri, sans-serif" }}>
          {photo && <img src="/api/profile/photo" alt="Your photo" style={{ ...PHOTO_STYLE, marginRight: 8 }} />}
          {name && split > 0 && <span style={{ color: "#333333" }}>{name.slice(0, split + 1)}</span>}
          {name && <span style={{ color: colour }}>{name.slice(split + 1)}</span>}
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
        <li key={skill.text}>
          <ClaimText claim={skill} />
        </li>
      ))}
    </ul>
  ) : (
    <div>
      <Joined claims={skills} separator=", " />
    </div>
  );
}

function Resume({ resume, signature, pair, accent }: Props<{ resume: NonNullable<Pack["resume"]> }>) {
  const styled = pair === "styled";
  return (
    <div style={pageFor(pair)} aria-label="Resume">
      <Header signature={signature} pair={pair} accent={accent} photo={signature.has_photo} />
      {resume.sections.map((section, position) => (
        <div key={`${section.kind}-${position}`}>
          <Heading text={section.heading} pair={pair} accent={accent} />
          {section.kind === "summary" ? (
            <div>
              <Joined claims={section.claims} separator=" " />
            </div>
          ) : section.kind === "skills" ? (
            <>
              {section.claims.length > 0 && <Skills skills={section.claims} styled={styled} />}
              {section.groups.map((group) => (
                <div key={group.heading.text}>
                  <b>
                    <ClaimText claim={group.heading} />
                    {!styled && ": "}
                  </b>
                  {styled ? <Skills skills={group.claims} styled /> : <Joined claims={group.claims} separator=", " />}
                </div>
              ))}
            </>
          ) : (
            section.claims.map((claim) => (
              <div key={claim.text}>
                <ClaimText claim={claim} />
              </div>
            ))
          )}
          {section.roles.map((role) => {
            const [title, dates] = styled ? splitDates(role.heading.text) : [role.heading.text, null];
            return (
              <div key={role.heading.text}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <b>
                    <ClaimText claim={role.heading} label={title} />
                  </b>
                  {dates && <span>{dates}</span>}
                </div>
                <ul style={{ margin: "4px 0", paddingLeft: 20 }}>
                  {role.lines.map((line) => (
                    <li key={line.text}>
                      <ClaimText claim={line} />
                    </li>
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
          <Joined claims={paragraph} separator=" " />
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

function answers(requirement: Requirement, item: EvidenceRef): boolean {
  return item.id != null && requirement.evidence_ids.includes(item.id);
}

const tab = (selected: boolean): CSSProperties => ({
  background: selected ? "#1f2933" : undefined,
  color: selected ? "#fff" : undefined,
});

const TABS = { evidence: "Evidence", coverage: "Requirement coverage" } as const;
type View = keyof typeof TABS;

// Beside the documents: the Evidence behind the Claim picked in them, or how the Pack answers
// each of the posting's Requirements.
function EvidencePanel({ pack, onAddToProfile }: { pack: Pack; onAddToProfile?: (draft: string) => void }) {
  const [view, setView] = useState<View>("evidence");
  const { selected, select } = useContext(ClaimPicker)!;
  const requirements = pack.requirements ?? [];
  const claims = allClaims(pack);
  // Packs written before Evidence IDs were kept can't link a Claim to a Requirement.
  const linked = claims.some((claim) => claim.evidence.some((item) => item.id != null));
  const inResume = new Map((pack.coverage?.counted ?? []).map((r) => [r.requirement, r.in_resume]));
  return (
    <section style={{ ...card, position: "sticky", top: 8 }} aria-label="Evidence panel">
      <div role="tablist" style={{ display: "flex", gap: 6, marginBottom: 10 }}>
        {(Object.keys(TABS) as View[]).map((key) => (
          <button
            key={key}
            id={`tab-${key}`}
            role="tab"
            aria-selected={view === key}
            aria-controls={`panel-${key}`}
            tabIndex={view === key ? 0 : -1}
            style={tab(view === key)}
            onClick={() => setView(key)}
          >
            {TABS[key]}
          </button>
        ))}
      </div>
      {view === "evidence" ? (
        <div role="tabpanel" id="panel-evidence" aria-labelledby="tab-evidence">
          <p style={{ fontSize: 13, marginTop: 0 }}>Click any underlined Claim in the documents.</p>
          {selected && (
            <>
              <b>{selected.text}</b>
              {selected.evidence.map((item, position) => {
                const answered = requirements.filter((r) => answers(r, item));
                return (
                  <div key={position} style={{ fontSize: 13, borderTop: "1px solid #e4e7eb", marginTop: 6, paddingTop: 6 }}>
                    <span style={{ fontWeight: 600 }}>{ORIGINS[item.origin].badge}</span>
                    {item.deleted && <strong> (Evidence deleted)</strong>}
                    <div>From: {ORIGINS[item.origin].from}</div>
                    <div>Quote: “{item.text}”</div>
                    <div>
                      Answers:{" "}
                      {answered.length
                        ? answered.map((r) => `${r.requirement} (${RESULTS[r.result]})`).join("; ")
                        : item.id == null
                          ? "not linked to a Requirement"
                          : "no single Requirement"}
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>
      ) : (
        <div role="tabpanel" id="panel-coverage" aria-labelledby="tab-coverage" style={{ fontSize: 13 }}>
          {pack.coverage && (
            <p style={{ marginTop: 0 }}>
              <b>Keyword coverage: {pack.coverage.score}%</b> of the posting's Requirements, from your Requirement
              Results. It's for your information only: the Pack never adds a keyword your Evidence doesn't support.
            </p>
          )}
          {!linked && (
            <p role="note">
              This Pack was written before Claims were linked to Requirements. Write a new Pack to see where each one
              is used.
            </p>
          )}
          {requirements.map((r, position) => {
            const using = claims.filter((claim) => claim.evidence.some((item) => answers(r, item)));
            const counted = inResume.get(r.requirement);
            return (
              <div key={position} style={{ borderTop: "1px solid #e4e7eb", padding: "6px 0" }}>
                <b>{r.requirement}</b> <span>{REQUIREMENT_KINDS[r.kind]}</span>, {RESULTS[r.result]}
                {counted != null && (counted ? ", in your resume" : ", not in this resume")}
                <div>
                  {r.profile_field ? (
                    "Decided by your Profile."
                  ) : !linked ? null : using.length > 0 ? (
                    <>
                      Used in:
                      <ul style={{ margin: "2px 0", paddingLeft: 18 }}>
                        {using.map((claim, at) => (
                          <li key={at}>
                            <ClaimLink
                              onClick={() => {
                                select(claim);
                                setView("evidence");
                              }}
                            >
                              {claim.text}
                            </ClaimLink>
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : r.result === "missing" || r.result === "unknown" ? (
                    <>
                      Not in this Pack: no Evidence answers it yet.{" "}
                      {onAddToProfile && <button onClick={() => onAddToProfile(r.requirement)}>Add to Profile</button>}
                    </>
                  ) : (
                    "Not used in this Pack."
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

type RemovedClaimsProps = {
  removed: RemovedClaim[];
  submitted: boolean;
  onKeep: (claimId: string) => Promise<void>;
  onUnkeep: (claimId: string) => Promise<void>;
  onCheck: (claimId: string) => Promise<void>;
  onAddToProfile?: (draft: string) => void;
};

// Claims Verification took out, and what the person can do about each: add Evidence and check
// again, or keep it anyway after a warning, one Claim at a time.
function RemovedClaims({ removed, submitted, onKeep, onUnkeep, onCheck, onAddToProfile }: RemovedClaimsProps) {
  // Draft IDs, so a list that changes meanwhile never confirms or checks a different Claim.
  const [confirming, setConfirming] = useState<string | null>(null);
  const [checking, setChecking] = useState<string | null>(null);
  return (
    <div style={card}>
      <h3 style={{ marginTop: 0 }}>Claims without Evidence</h3>
      {removed.map((claim, index) => (
        <div key={claim.id ?? index} style={{ borderTop: "1px solid #e4e7eb", padding: "6px 0" }}>
          {claim.kept ? (
            <Kept text={claim.text} />
          ) : (
            <>
              <s>{claim.text}</s> <span style={{ fontSize: 12 }}>({KINDS[claim.kind]})</span>
            </>
          )}
          <div style={{ fontSize: 13 }}>{claim.reason}</div>
          {!claim.kept && <div style={{ fontSize: 13 }}>{claim.next_step}</div>}
          {!submitted && (
            <div style={{ marginTop: 4 }}>
              {claim.kept ? (
                <button onClick={() => onUnkeep(claim.id!)}>Stop keeping</button>
              ) : confirming !== null && confirming === claim.id ? (
                <div role="alertdialog" aria-label="Keep this Claim?" style={{ background: "#fdecea", padding: "4px 8px" }}>
                  <b>Keep this?</b> We found no Evidence for it in your resume or Profile. Keep it only if it's true:
                  it goes in your files without any Evidence behind it.
                  <div>
                    <button
                      onClick={() => {
                        setConfirming(null);
                        void onKeep(claim.id!);
                      }}
                    >
                      Keep it, it's true
                    </button>{" "}
                    <button onClick={() => setConfirming(null)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <>
                  {onAddToProfile && <button onClick={() => onAddToProfile(claim.text)}>Add Evidence</button>}{" "}
                  {claim.can_check && (
                    <button
                      disabled={checking !== null}
                      onClick={() => {
                        setChecking(claim.id);
                        onCheck(claim.id!).finally(() => setChecking(null));
                      }}
                    >
                      {checking !== null && checking === claim.id ? "Checking…" : "Check again"}
                    </button>
                  )}{" "}
                  {claim.cant_keep === null ? (
                    <button onClick={() => setConfirming(claim.id)}>Keep anyway</button>
                  ) : (
                    <span style={{ fontSize: 13 }}>{claim.cant_keep}</span>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
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
        <OutcomeButtons outcome={application.outcome} onOutcome={onOutcome} />
      )}
      <p style={{ fontSize: 13, marginBottom: 0 }}>
        Job Copilot never submits for you. This Application has cost {dollars(application.cost_usd)} so far.
      </p>
    </div>
  );
}

function OutcomeButtons({ outcome, onOutcome }: { outcome: Outcome | null; onOutcome: (outcome: Outcome) => void }) {
  return (
    <div role="group" aria-label="Outcome" style={{ marginTop: 6 }}>
      Outcome:{" "}
      {(Object.keys(OUTCOMES) as Outcome[]).map((choice) => (
        <button key={choice} aria-pressed={outcome === choice} onClick={() => onOutcome(choice)}>
          {OUTCOMES[choice]}
        </button>
      ))}
    </div>
  );
}

// Applying with the person's own resume when there's no ready Application Pack.
function OwnResume({ applyUrl, onSubmitted }: { applyUrl: string | null; onSubmitted: () => void }) {
  return (
    <>
      {applyUrl && (
        <a href={applyUrl} target="_blank" rel="noreferrer noopener" style={{ marginRight: 8 }}>
          Open employer's application page
        </a>
      )}
      <button onClick={onSubmitted}>I submitted it on their site</button>
    </>
  );
}

export function Application({
  id,
  onBack,
  onOpenSettings,
  onAddToProfile,
}: {
  id: string;
  onBack: () => void;
  onOpenSettings?: () => void;
  onAddToProfile?: (draft: string) => void;
}) {
  const [application, setApplication] = useState<ApplicationData | null>(null);
  const [picked, setPicked] = useState<Claim | null>(null);
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
  // The first Claim with Evidence is open until the person picks another one still in the Pack.
  const claims = pack?.status === "ready" ? allClaims(pack) : [];
  const selected = picked && claims.includes(picked) ? picked : (claims[0] ?? null);
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
      {application && !pack && application.submitted_at && (
        <div style={card}>
          <p style={{ marginTop: 0 }}>
            Submitted with your own resume on {new Date(application.submitted_at).toLocaleString()}, with no
            Application Pack.
          </p>
          <OutcomeButtons outcome={application.outcome} onOutcome={report} />
        </div>
      )}
      {application && !pack && !application.submitted_at && (
        <div style={card}>
          <p style={{ marginTop: 0 }}>This Application has no Application Pack.</p>
          <button onClick={writePack}>Write a new Application Pack</button>{" "}
          <OwnResume applyUrl={application.apply_url} onSubmitted={submitted} />
        </div>
      )}
      {pack?.status === "generating" && <p>Writing and checking your Application Pack…</p>}
      {application && pack?.status === "waiting" && (
        <div role="alert" style={{ ...card, background: "#fdecea" }}>
          <p style={{ marginTop: 0 }}>{pack.warning}</p>
          <button onClick={retry}>Retry</button> <button onClick={onOpenSettings}>Check model settings</button>{" "}
          <OwnResume applyUrl={application.apply_url} onSubmitted={submitted} />
        </div>
      )}
      {pack?.status === "ready" && (
        <>
          <p style={{ ...card, background: "#e3edff" }}>
            Preview of both final documents. Every Claim was checked against your Evidence. Click an underlined
            Claim to see its Evidence. Underlining appears only here, never in your files.
            {pack.model && ` Written by ${pack.model}.`}
          </p>
          {pack.extra_care && (
            <p role="note" style={{ ...card, background: "#fdecea", color: "#8a1c12" }}>
              Extra care: evals are failing. Check this Application Pack closely before you send it.
            </p>
          )}
          {pack.removed_claims!.length > 0 && (
            <RemovedClaims
              removed={pack.removed_claims!}
              submitted={!!application?.submitted_at}
              onKeep={(claimId) => update(`removed/${claimId}/keep`, "POST", "We couldn't keep this Claim. Try again.")}
              onUnkeep={(claimId) =>
                update(`removed/${claimId}/keep`, "DELETE", "We couldn't stop keeping this Claim. Try again.")
              }
              onCheck={(claimId) =>
                update(
                  `removed/${claimId}/check`,
                  "POST",
                  "We couldn't check this Claim again. Your Pack is unchanged, so try again later.",
                )
              }
              onAddToProfile={onAddToProfile}
            />
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
          <ClaimPicker.Provider value={{ selected, select: setPicked }}>
            <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 14, alignItems: "start" }}>
              <EvidencePanel pack={pack} onAddToProfile={onAddToProfile} />
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, alignItems: "start" }}>
                <Resume resume={pack.resume!} signature={application!} pair={pair} accent={application!.accent_colour} />
                <CoverLetter
                  letter={pack.cover_letter!}
                  signature={application!}
                  pair={pair}
                  accent={application!.accent_colour}
                />
              </div>
            </div>
          </ClaimPicker.Provider>
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
