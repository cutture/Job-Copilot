import { useEffect, useState } from "react";
import type { ChangeEvent, CSSProperties } from "react";

type Evidence = {
  id: number;
  text: string;
  origin: "resume" | "self_reported";
  confirmed: boolean;
};

type ProfileData = {
  resume_filename: string | null;
  resume_text: string | null;
  extraction_status: "queued" | "done" | "failed" | null;
  work_authorization: string | null;
  lives_in: string | null;
  languages: string[];
  seniority: string | null;
  roles: string[];
  work_type: string;
  min_pay: { currency: string | null; yearly: number | null; hourly: number | null }[];
  location_arrangements: string[];
  location_places: string[];
  evidence: Evidence[];
};

type Form = {
  work_authorization: string;
  lives_in: string;
  languages: string;
  seniority: string;
  roles: string;
  work_type: string;
  min_pay: PayRow[];
  location_arrangements: string[];
  location_places: string;
};

type PayRow = { currency: string; yearly: string; hourly: string };

const REFRESH_MS = 2000;
const CURRENCIES = ["USD", "EUR", "GBP", "INR", "AUD", "CAD", "SGD", "MYR", "THB", "IDR", "PHP", "VND", "AED", "CHF", "JPY"];
const ARRANGEMENTS = [
  ["remote", "Remote"],
  ["hybrid", "Hybrid"],
  ["on_site", "On-site"],
] as const;
const card: CSSProperties = { border: "1px solid #ccc", borderRadius: 8, padding: 16, marginBottom: 12 };
const field: CSSProperties = { display: "block", width: "100%", boxSizing: "border-box", marginBottom: 8 };

function toForm(profile: ProfileData): Form {
  return {
    work_authorization: profile.work_authorization ?? "",
    lives_in: profile.lives_in ?? "",
    languages: profile.languages.join(", "),
    seniority: profile.seniority ?? "",
    roles: profile.roles.join(", "),
    work_type: profile.work_type,
    min_pay: profile.min_pay.map((pay) => ({
      currency: pay.currency ?? "",
      yearly: pay.yearly?.toString() ?? "",
      hourly: pay.hourly?.toString() ?? "",
    })),
    location_arrangements: profile.location_arrangements,
    location_places: profile.location_places.join(", "),
  };
}

const list = (value: string) =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

async function detail(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    return typeof body.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

async function loadProfile(): Promise<ProfileData> {
  const response = await fetch("/api/profile");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function EvidenceRow({
  item,
  onChanged,
  onError,
}: {
  item: Evidence;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.text);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  async function change(body: object) {
    const response = await fetch(`/api/evidence/${item.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch(() => null);
    if (!response?.ok) {
      onError("We couldn't save that change. Try again.");
      return;
    }
    setEditing(false);
    onChanged();
  }

  async function remove() {
    const response = await fetch(`/api/evidence/${item.id}`, { method: "DELETE" }).catch(() => null);
    if (!response?.ok) {
      onError("We couldn't delete that item. Try again.");
      setConfirmingDelete(false);
      return;
    }
    onChanged();
  }

  return (
    <li style={{ borderTop: "1px solid #eee", padding: "8px 0" }}>
      {editing ? (
        <>
          <textarea
            aria-label="Correct this item"
            style={field}
            rows={2}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <button onClick={() => change({ text: draft })} disabled={!draft.trim()}>
            Save and confirm
          </button>{" "}
          <button onClick={() => setEditing(false)}>Cancel</button>
        </>
      ) : (
        <>
          <span>{item.text}</span>{" "}
          {item.origin === "self_reported" ? (
            <strong>Self-reported</strong>
          ) : item.confirmed ? (
            <strong>Confirmed</strong>
          ) : (
            <em>Not confirmed</em>
          )}
          <div>
            {!item.confirmed && <button onClick={() => change({ confirmed: true })}>Confirm</button>}{" "}
            <button onClick={() => setEditing(true)}>Edit</button>{" "}
            {confirmingDelete ? (
              <>
                <button onClick={remove}>Yes, delete</button>{" "}
                <button onClick={() => setConfirmingDelete(false)}>Keep it</button>
              </>
            ) : (
              <button onClick={() => setConfirmingDelete(true)}>Delete</button>
            )}
          </div>
        </>
      )}
    </li>
  );
}

export function Profile({ draft = "" }: { draft?: string }) {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [newItem, setNewItem] = useState(draft);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [confirmingAll, setConfirmingAll] = useState(false);

  async function refresh(resetForm = false) {
    try {
      const loaded = await loadProfile();
      setProfile(loaded);
      if (resetForm) setForm(toForm(loaded));
    } catch {
      setError("We couldn't load your Profile. Try refreshing the page.");
    }
  }

  useEffect(() => {
    refresh(true);
  }, []);

  const extracting = profile?.extraction_status === "queued";
  useEffect(() => {
    if (!extracting) return;
    const timer = setInterval(() => refresh(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [extracting]);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    const body = new FormData();
    body.append("file", file);
    const response = await fetch("/api/profile/resume", { method: "POST", body });
    if (!response.ok) {
      setError(await detail(response, "We couldn't upload this file. Try again."));
      return;
    }
    refresh();
  }

  async function readAgain() {
    setError("");
    const response = await fetch("/api/profile/resume/read-again", { method: "POST" });
    if (!response.ok) setError(await detail(response, "We couldn't start reading it again."));
    refresh();
  }

  async function confirmAll() {
    setConfirmingAll(false);
    const response = await fetch("/api/evidence/confirm-all", { method: "POST" }).catch(() => null);
    if (!response?.ok) setError("We couldn't confirm the items. Try again.");
    refresh();
  }

  const unconfirmed = profile?.evidence.filter((item) => !item.confirmed).length ?? 0;

  async function addEvidence() {
    const response = await fetch("/api/evidence", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: newItem }),
    });
    if (response.ok) {
      setNewItem("");
      refresh();
    } else {
      setError(await detail(response, "We couldn't add this item. Try again."));
    }
  }

  async function save() {
    if (!form) return;
    setSaved(false);
    setError("");
    const response = await fetch("/api/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        work_authorization: form.work_authorization.trim() || null,
        lives_in: form.lives_in.trim() || null,
        languages: list(form.languages),
        seniority: form.seniority || null,
        roles: list(form.roles),
        work_type: form.work_type,
        min_pay: form.min_pay
          .filter((pay) => pay.currency.trim() || pay.yearly.trim() || pay.hourly.trim())
          .map((pay) => ({
            currency: pay.currency.trim().toUpperCase() || null,
            yearly: pay.yearly.trim() ? Number(pay.yearly) : null,
            hourly: pay.hourly.trim() ? Number(pay.hourly) : null,
          })),
        location_arrangements: form.location_arrangements,
        location_places: list(form.location_places),
      }),
    });
    if (response.ok) {
      setSaved(true);
      refresh(true);
    } else {
      setError(await detail(response, "We couldn't save your Profile. Check the values and try again."));
    }
  }

  const set = (key: keyof Form) => (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((current) => current && { ...current, [key]: event.target.value });

  function setPay(index: number, key: keyof PayRow, value: string) {
    setForm(
      (current) =>
        current && {
          ...current,
          min_pay: current.min_pay.map((pay, i) => (i === index ? { ...pay, [key]: value } : pay)),
        },
    );
  }

  function toggleArrangement(value: string) {
    setForm(
      (current) =>
        current && {
          ...current,
          location_arrangements: current.location_arrangements.includes(value)
            ? current.location_arrangements.filter((item) => item !== value)
            : [...current.location_arrangements, value],
        },
    );
  }

  return (
    <section>
      {error && <p role="alert">{error}</p>}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 16 }}>
        <div style={card}>
          <h2>Your resume</h2>
          <label htmlFor="resume" style={{ display: "block", fontWeight: 600 }}>
            Upload your resume (PDF or DOCX)
          </label>
          <input id="resume" type="file" accept=".pdf,.docx" onChange={upload} />
          <p style={{ fontSize: 13 }}>
            It's stored on your server. Its text is sent to Anthropic, the provider of the AI model that
            proposes your Evidence. See{" "}
            <a href="https://privacy.claude.com/" target="_blank" rel="noreferrer">
              Anthropic's data policy
            </a>
            .
          </p>
          {profile?.resume_text && (
            <>
              <p style={{ fontSize: 13 }}>{profile.resume_filename}</p>
              <pre style={{ whiteSpace: "pre-wrap", fontFamily: "Georgia, serif", maxHeight: 520, overflow: "auto" }}>
                {profile.resume_text}
              </pre>
            </>
          )}
        </div>

        <div>
          <div style={card}>
            <h2>What we understood</h2>
            {extracting && <p>Reading your resume…</p>}
            {profile?.extraction_status === "failed" && (
              <p>
                We couldn't read Evidence from your resume. Our AI model may be unavailable or out of
                credit. You can still add items below.{" "}
                <button onClick={readAgain}>Try reading it again</button>
              </p>
            )}
            <p style={{ fontSize: 13 }}>
              Only confirmed items are used to support what goes in your applications.
            </p>
            {unconfirmed > 0 &&
              (confirmingAll ? (
                <p>
                  Check every item first: confirmed items can be used in your applications.{" "}
                  <button onClick={confirmAll}>I've read them. Confirm all {unconfirmed}</button>{" "}
                  <button onClick={() => setConfirmingAll(false)}>Cancel</button>
                </p>
              ) : (
                <button onClick={() => setConfirmingAll(true)}>Confirm all ({unconfirmed})</button>
              ))}
            <ul style={{ listStyle: "none", padding: 0 }}>
              {profile?.evidence.map((item) => (
                <EvidenceRow
                  key={`${item.id}-${item.text}`}
                  item={item}
                  onChanged={() => refresh()}
                  onError={setError}
                />
              ))}
            </ul>
            <label htmlFor="new-evidence" style={{ display: "block", fontWeight: 600 }}>
              Add something your resume misses
            </label>
            <textarea
              id="new-evidence"
              style={field}
              rows={2}
              value={newItem}
              onChange={(event) => setNewItem(event.target.value)}
            />
            <button onClick={addEvidence} disabled={!newItem.trim()}>
              Add as self-reported
            </button>
          </div>

          {form && (
            <div style={card}>
              <h2>Facts about you</h2>
              <p style={{ fontSize: 13 }}>Empty fields count as Unknown, never as a Hard Blocker.</p>
              <label htmlFor="work-authorization">Work authorization</label>
              <input id="work-authorization" style={field} value={form.work_authorization} onChange={set("work_authorization")} />
              <label htmlFor="lives-in">Where you live</label>
              <input id="lives-in" style={field} value={form.lives_in} onChange={set("lives_in")} />
              <label htmlFor="languages">Languages</label>
              <input id="languages" style={field} value={form.languages} onChange={set("languages")} />
              <label htmlFor="seniority">Seniority</label>
              <select id="seniority" style={field} value={form.seniority} onChange={set("seniority")}>
                <option value="">Not set</option>
                <option>Junior</option>
                <option>Mid</option>
                <option>Senior</option>
                <option>Staff</option>
              </select>

              <h2>What you're looking for</h2>
              <label htmlFor="roles">Roles and keywords</label>
              <input id="roles" style={field} value={form.roles} onChange={set("roles")} />
              <label htmlFor="work-type">Work type</label>
              <select id="work-type" style={field} value={form.work_type} onChange={set("work_type")}>
                <option value="employment_and_freelance">Employment and freelance</option>
                <option value="employment">Employment only</option>
                <option value="freelance">Freelance only</option>
              </select>
              <fieldset style={{ border: 0, padding: 0, marginBottom: 8 }}>
                <legend>Minimum Pay (optional)</legend>
                <p style={{ fontSize: 13 }}>
                  One row for each currency. Employment is compared with the yearly amount and
                  freelance with the hourly one. Postings in other currencies pass.
                </p>
                <datalist id="currencies">
                  {CURRENCIES.map((code) => (
                    <option key={code} value={code} />
                  ))}
                </datalist>
                {form.min_pay.map((pay, index) => (
                  <div key={index} style={{ marginBottom: 8 }}>
                    <label>
                      Currency{" "}
                      <input
                        list="currencies"
                        maxLength={3}
                        size={4}
                        value={pay.currency}
                        onChange={(event) => setPay(index, "currency", event.target.value)}
                      />
                    </label>{" "}
                    <label>
                      Yearly, for employment{" "}
                      <input
                        inputMode="numeric"
                        size={10}
                        value={pay.yearly}
                        onChange={(event) => setPay(index, "yearly", event.target.value)}
                      />
                    </label>{" "}
                    <label>
                      Hourly, for freelance{" "}
                      <input
                        inputMode="decimal"
                        size={6}
                        value={pay.hourly}
                        onChange={(event) => setPay(index, "hourly", event.target.value)}
                      />
                    </label>{" "}
                    <button
                      type="button"
                      onClick={() =>
                        setForm((current) => current && { ...current, min_pay: current.min_pay.filter((_, i) => i !== index) })
                      }
                    >
                      Remove
                    </button>
                    {!pay.currency.trim() && (pay.yearly.trim() || pay.hourly.trim()) && (
                      <p role="alert" style={{ fontSize: 13 }}>
                        Choose the currency for this amount. Until then Filter doesn't use it.
                      </p>
                    )}
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() =>
                    setForm(
                      (current) =>
                        current && { ...current, min_pay: [...current.min_pay, { currency: "", yearly: "", hourly: "" }] },
                    )
                  }
                >
                  Add a currency
                </button>
              </fieldset>
              <fieldset style={{ border: 0, padding: 0, marginBottom: 8 }}>
                <legend>Location Preference</legend>
                {ARRANGEMENTS.map(([value, label]) => (
                  <label key={value} style={{ marginRight: 12 }}>
                    <input
                      type="checkbox"
                      checked={form.location_arrangements.includes(value)}
                      onChange={() => toggleArrangement(value)}
                    />{" "}
                    {label}
                  </label>
                ))}
              </fieldset>
              <label htmlFor="places">Countries or cities you'd work in</label>
              <input id="places" style={field} value={form.location_places} onChange={set("location_places")} />
              <p style={{ fontSize: 13 }}>Separate items with commas.</p>
              <button onClick={save}>Save Profile</button> {saved && <span>Saved.</span>}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
