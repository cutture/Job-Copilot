import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Application } from "./Application";
import { Applications } from "./Applications";
import { ConfirmDelete } from "./ConfirmDelete";
import { Matches, Origin, deleteQuestion } from "./Matches";
import type { Match, PostingOrigin, RatedPosting, RatingState } from "./Matches";
import { Profile } from "./Profile";
import { Search } from "./Search";

type JobPosting = PostingOrigin & {
  id: string;
  title: string;
  status: string;
  posting_type: "employment" | "freelance" | null;
  filter_reason: string | null;
  salary_note: string | null;
  rating_state?: RatingState | null;
  match?: Match | null;
  application_id?: string | null;
};

function PostingRow({ posting, onDelete }: { posting: JobPosting; onDelete: (posting: JobPosting) => void }) {
  return (
    <li>
      <strong>{posting.title}</strong> <Origin posting={posting} />
      {posting.posting_type && (
        <>
          {" · "}
          <span>{posting.posting_type === "freelance" ? "Freelance" : "Employment"}</span>
        </>
      )}
      {posting.salary_note && (
        <>
          {" · "}
          <em>{posting.salary_note}</em>
        </>
      )}
      {posting.status === "queued" && <em> Working on the title…</em>}
      {posting.status === "model_unavailable" && <em> Our AI model couldn't read this posting.</em>}
      {posting.status === "not_rated" && <em> Our AI model couldn't rate this posting.</em>}
      {posting.rating_state === "rating" && <em> Rating…</em>}
      {posting.filter_reason && <div style={{ fontSize: 13 }}>{posting.filter_reason}</div>}
      <div>
        <ConfirmDelete question={deleteQuestion(posting)} onConfirm={() => onDelete(posting)} />
      </div>
    </li>
  );
}

const REFRESH_MS = 2000;

async function fetchPostings(): Promise<JobPosting[]> {
  const response = await fetch("/api/job-postings");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export function App() {
  const [postings, setPostings] = useState<JobPosting[] | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [view, setView] = useState<"postings" | "applications" | "profile">("postings");
  const [showFiltered, setShowFiltered] = useState(false);
  const [evidenceDraft, setEvidenceDraft] = useState("");
  const [applicationId, setApplicationId] = useState<string | null>(null);

  useEffect(() => {
    fetchPostings()
      .then(setPostings)
      .catch(() => setError("We couldn't load your Job Postings. Try refreshing the page."));
  }, []);

  // A search adds postings as it runs; a failed refresh just waits for the next one.
  const refreshPostings = useCallback(() => {
    fetchPostings()
      .then(setPostings)
      .catch(() => {});
  }, []);

  const processing =
    postings?.some((posting) => posting.status === "queued" || posting.rating_state === "rating") ?? false;
  const rated = postings?.filter((posting): posting is RatedPosting & JobPosting => !!posting.match) ?? [];
  const waiting = postings?.filter((posting) => posting.rating_state === "waiting").length ?? 0;
  const shown =
    postings?.filter(
      (posting) => posting.status !== "filtered" && !posting.match && posting.rating_state !== "waiting",
    ) ?? [];
  const filtered = postings?.filter((posting) => posting.status === "filtered") ?? [];

  useEffect(() => {
    if (!processing) return;
    // A failed refresh just tries again on the next tick.
    const timer = setInterval(() => {
      fetchPostings()
        .then(setPostings)
        .catch(() => {});
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [processing]);

  async function addPosting(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const response = await fetch("/api/job-postings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
    } catch {
      setError("We couldn't save this posting. Your text is still here, so try again.");
      setSaving(false);
      return;
    }
    setText("");
    try {
      setPostings(await fetchPostings());
    } catch {
      setError("Your posting was saved, but we couldn't refresh the list. Try refreshing the page.");
    } finally {
      setSaving(false);
    }
  }

  async function applyTo(posting: RatedPosting) {
    if (posting.application_id) {
      setApplicationId(posting.application_id);
      return;
    }
    setError("");
    const response = await fetch("/api/applications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_posting_id: posting.id }),
    }).catch(() => null);
    if (!response?.ok) {
      setError("We couldn't start this Application. Try again.");
      return;
    }
    setApplicationId((await response.json()).id);
  }

  async function deletePosting(posting: { id: string }) {
    setError("");
    const response = await fetch(`/api/job-postings/${posting.id}`, { method: "DELETE" }).catch(() => null);
    if (!response?.ok) {
      setError("We couldn't delete this Job Posting. Try again.");
      return;
    }
    refreshPostings();
  }

  function backToListings() {
    setApplicationId(null);
    setView("postings");
    refreshPostings();
  }

  if (applicationId) {
    return (
      <main style={{ maxWidth: 1320, margin: "0 auto", padding: 20, fontFamily: "system-ui, sans-serif" }}>
        <Application id={applicationId} onBack={backToListings} />
      </main>
    );
  }

  return (
    <main style={{ maxWidth: 1100, margin: "0 auto", padding: 20, fontFamily: "system-ui, sans-serif" }}>
      <h1>Job Copilot</h1>
      <nav aria-label="Pages" style={{ marginBottom: 16 }}>
        <button aria-pressed={view === "postings"} onClick={() => setView("postings")}>
          Job Postings
        </button>{" "}
        <button aria-pressed={view === "applications"} onClick={() => setView("applications")}>
          Applications
        </button>{" "}
        <button
          aria-pressed={view === "profile"}
          onClick={() => {
            setEvidenceDraft("");
            setView("profile");
          }}
        >
          Profile
        </button>
      </nav>
      {view === "applications" && <Applications onOpen={setApplicationId} />}
      {view === "profile" && <Profile key={evidenceDraft} draft={evidenceDraft} />}
      {view === "postings" && <>
      <Search onProgress={refreshPostings} />
      <form onSubmit={addPosting}>
        <label htmlFor="posting" style={{ display: "block", fontWeight: 600 }}>
          Paste a Job Posting
        </label>
        <p id="posting-notice" style={{ margin: "4px 0" }}>
          Paste only from an employer's own career page, not sites like LinkedIn, Indeed or Upwork.
          The text goes to an LLM provider.
        </p>
        <textarea
          id="posting"
          aria-describedby="posting-notice"
          rows={8}
          style={{ width: "100%", boxSizing: "border-box" }}
          value={text}
          onChange={(event) => setText(event.target.value)}
          required
        />
        <button type="submit" disabled={saving || !text.trim()}>
          Add posting
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      <h2>Your Job Postings</h2>
      {postings?.length === 0 && <p>No Job Postings yet.</p>}
      <Matches
        postings={rated}
        onAddToProfile={(draft) => {
          setEvidenceDraft(draft);
          setView("profile");
        }}
        onApply={applyTo}
        onDelete={deletePosting}
      />
      {waiting > 0 && (
        <p>
          {waiting} {waiting === 1 ? "posting" : "postings"} waiting to be rated
        </p>
      )}
      <ul>
        {shown.map((posting) => (
          <PostingRow key={posting.id} posting={posting} onDelete={deletePosting} />
        ))}
      </ul>
      {filtered.length > 0 && (
        <>
          <button aria-expanded={showFiltered} onClick={() => setShowFiltered(!showFiltered)}>
            {showFiltered ? "Hide" : "Show"} {filtered.length} Filtered{" "}
            {filtered.length === 1 ? "Posting" : "Postings"}
          </button>
          {showFiltered && (
            <ul>
              {filtered.map((posting) => (
                <PostingRow key={posting.id} posting={posting} onDelete={deletePosting} />
              ))}
            </ul>
          )}
        </>
      )}
      </>}
    </main>
  );
}
