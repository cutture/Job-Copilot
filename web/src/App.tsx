import { useEffect, useState } from "react";
import type { FormEvent } from "react";

type JobPosting = {
  id: string;
  title: string;
  source: string;
  status: string;
  created_at: string;
};

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

  useEffect(() => {
    fetchPostings()
      .then(setPostings)
      .catch(() => setError("We couldn't load your Job Postings. Try refreshing the page."));
  }, []);

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
      setPostings(await fetchPostings());
      setText("");
    } catch {
      setError("We couldn't save this posting. Your text is still here, so try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main style={{ maxWidth: 760, margin: "0 auto", padding: 20, fontFamily: "system-ui, sans-serif" }}>
      <h1>Job listings</h1>
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
      <ul>
        {postings?.map((posting) => (
          <li key={posting.id}>
            <strong>{posting.title}</strong> <span>{posting.source}</span>
          </li>
        ))}
      </ul>
    </main>
  );
}
