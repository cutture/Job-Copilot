import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Matches, Origin } from "./Matches";
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
};

function PostingRow({ posting }: { posting: JobPosting }) {
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
  const [view, setView] = useState<"postings" | "profile">("postings");
  const [showFiltered, setShowFiltered] = useState(false);
  const [evidenceDraft, setEvidenceDraft] = useState("");

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

  return (
    <main style={{ maxWidth: 1100, margin: "0 auto", padding: 20, fontFamily: "system-ui, sans-serif" }}>
      <h1>Job Copilot</h1>
      <nav aria-label="Pages" style={{ marginBottom: 16 }}>
        <button aria-pressed={view === "postings"} onClick={() => setView("postings")}>
          Job Postings
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
      {view === "profile" ? <Profile key={evidenceDraft} draft={evidenceDraft} /> : <>
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
      />
      {waiting > 0 && (
        <p>
          {waiting} {waiting === 1 ? "posting" : "postings"} waiting to be rated
        </p>
      )}
      <ul>
        {shown.map((posting) => (
          <PostingRow key={posting.id} posting={posting} />
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
                <PostingRow key={posting.id} posting={posting} />
              ))}
            </ul>
          )}
        </>
      )}
      </>}
    </main>
  );
}
