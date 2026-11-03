import { useEffect, useState } from "react";
import type { FormEvent } from "react";

type WatchlistEntry = { id: string; name: string; source: string; failure: string | null };
type SearchStatus = { runs_left: number; daily_limit: number; searching: boolean };

const REFRESH_MS = 2000;

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function detail(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    return typeof body.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

export function Search({ onProgress }: { onProgress: () => void }) {
  const [status, setStatus] = useState<SearchStatus | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [adding, setAdding] = useState(false);
  const [url, setUrl] = useState("");
  const [message, setMessage] = useState("");

  async function refresh() {
    const [nextStatus, entries] = await Promise.all([
      getJson<SearchStatus>("/api/search"),
      getJson<WatchlistEntry[]>("/api/watchlist"),
    ]);
    setStatus(nextStatus);
    setWatchlist(entries);
    return nextStatus;
  }

  useEffect(() => {
    refresh().catch(() => setMessage("We couldn't load your Watchlist. Try refreshing the page."));
  }, []);

  const searching = status?.searching ?? false;
  useEffect(() => {
    if (!searching) return;
    // New postings appear while the search runs; a failed refresh tries again on the next tick.
    const timer = setInterval(() => {
      refresh()
        .then(onProgress)
        .catch(() => {});
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [searching, onProgress]);

  async function searchNow() {
    setMessage("");
    const response = await fetch("/api/search", { method: "POST" }).catch(() => null);
    if (!response?.ok) {
      setMessage(response ? await detail(response, "We couldn't start a search.") : "We couldn't start a search.");
      return;
    }
    setStatus(await response.json());
  }

  async function addEmployer(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    const response = await fetch("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    }).catch(() => null);
    if (!response?.ok) {
      setMessage(response ? await detail(response, "We couldn't add this employer.") : "We couldn't add this employer.");
      return;
    }
    setUrl("");
    await refresh().catch(() => {});
  }

  async function removeEmployer(entry: WatchlistEntry) {
    const response = await fetch(`/api/watchlist/${entry.id}`, { method: "DELETE" }).catch(() => null);
    if (!response?.ok) {
      setMessage(`We couldn't remove ${entry.name}. Try again.`);
      return;
    }
    await refresh().catch(() => {});
  }

  const failures = watchlist.filter((entry) => entry.failure);
  return (
    <section style={{ border: "1px solid #ccc", borderRadius: 8, padding: 12, marginBottom: 12 }}>
      <button onClick={searchNow} disabled={searching || status?.runs_left === 0}>
        {searching ? "Searching…" : "Search now"}
      </button>{" "}
      {status && (
        <span style={{ fontSize: 13 }}>
          {status.runs_left} of {status.daily_limit} runs left today
        </span>
      )}{" "}
      <button aria-expanded={adding} onClick={() => setAdding(!adding)}>
        Add a job source
      </button>
      {adding && (
        <form onSubmit={addEmployer} style={{ marginTop: 8 }}>
          <label htmlFor="careers-url">Add employer by careers page URL</label>{" "}
          <input id="careers-url" size={40} value={url} onChange={(event) => setUrl(event.target.value)} required />{" "}
          <button type="submit" disabled={!url.trim()}>
            Add to Watchlist
          </button>
        </form>
      )}
      {message && <p role="alert">{message}</p>}
      {failures.map((entry) => (
        <p key={entry.id} style={{ background: "#fff8e1", padding: "4px 8px" }}>
          {entry.failure}
        </p>
      ))}
      {watchlist.length > 0 && (
        <div style={{ fontSize: 13, marginTop: 8 }}>
          Watchlist:{" "}
          {watchlist.map((entry) => (
            <span key={entry.id} style={{ marginRight: 8 }}>
              {entry.name} ({entry.source}){" "}
              <button aria-label={`Remove ${entry.name}`} onClick={() => removeEmployer(entry)}>
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </section>
  );
}
