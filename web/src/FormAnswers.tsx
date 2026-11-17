import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

type Sentence = { text: string };
type Removed = { text: string; kind: string; reason: string };
type Answer = {
  id: number;
  question: string;
  kind: "contact" | "write" | "attach" | "yourself" | "demographic";
  origin: "greenhouse" | "common" | "pasted";
  required: boolean;
  options: string[];
  // A contact field's value from the Profile.
  value: string | null;
  // Null until written; empty when nothing in the Evidence answers it.
  sentences: Sentence[] | null;
  removed: Removed[];
};
type Form = { note: string; answers: Answer[] };

const card: CSSProperties = { border: "1px solid #ccc", borderRadius: 8, padding: 12, marginTop: 12 };
const row: CSSProperties = { borderTop: "1px solid #e4e7eb", padding: "6px 0" };
const muted: CSSProperties = { fontSize: 13, color: "#52606d" };
const NOTES: Record<Exclude<Answer["kind"], "contact" | "write">, string> = {
  attach: "Attach your resume yourself: the form takes the file.",
  yourself: "Answer this yourself.",
  demographic: "Left for you: demographic questions are always yours to answer, or to skip.",
};

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() =>
        navigator.clipboard
          .writeText(text)
          .then(() => setCopied(true))
          .catch(() => setCopied(false))
      }
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

// Form answers for one Application: copied by the person, never filled in or submitted here.
export function FormAnswers({ applicationId }: { applicationId: string }) {
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pasted, setPasted] = useState("");

  useEffect(() => {
    fetch(`/api/applications/${applicationId}/form-answers`)
      .then((response) => (response.ok ? response.json() : Promise.reject(response)))
      .then(setForm)
      .catch(() => setError("We couldn't load the form questions. Try refreshing the page."));
  }, [applicationId]);

  async function send(path: string, method: string, failure: string, body?: unknown): Promise<boolean> {
    setBusy(true);
    setError("");
    const response = await fetch(`/api/applications/${applicationId}/form-answers${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }).catch(() => null);
    setBusy(false);
    if (!response?.ok) {
      const detail = await response?.json().then((b) => b.detail).catch(() => null);
      setError(typeof detail === "string" ? detail : failure);
      return false;
    }
    setForm(await response.json());
    return true;
  }

  // A failed first load says so quietly; the rest of the Application page still works.
  if (error && !form) return <p style={muted}>{error}</p>;
  if (!form) return null;
  const unwritten = form.answers.some((a) => a.kind === "write" && a.sentences === null);
  return (
    <section aria-label="Form answers" style={card}>
      <h3 style={{ marginTop: 0 }}>Form answers</h3>
      <p style={muted}>
        {form.note} Answers are written only from your Evidence and checked like your documents. Check each answer
        before you paste it. Job Copilot never fills in or submits a form.
      </p>
      {unwritten && (
        <button
          disabled={busy}
          onClick={() => send("/prepare", "POST", "We couldn't write the answers. Try again later.")}
        >
          {busy ? "Writing answers…" : "Prepare answers"}
        </button>
      )}
      {error && <p role="alert">{error}</p>}
      {form.answers.map((answer) => (
        <div key={answer.id} style={row}>
          <b>{answer.question}</b>
          {answer.required && <span style={muted}> (required)</span>}
          {answer.kind === "contact" &&
            (answer.value ? (
              <div>
                {answer.value} <CopyButton text={answer.value} />
              </div>
            ) : (
              <div style={muted}>Add it to your Profile's contact line, or type it yourself.</div>
            ))}
          {answer.kind === "write" &&
            answer.sentences !== null &&
            (answer.sentences.length ? (
              <div>
                {answer.sentences.map((s) => s.text).join(" ")}{" "}
                <CopyButton text={answer.sentences.map((s) => s.text).join(" ")} />
              </div>
            ) : (
              <div style={muted}>Nothing in your Evidence answers this. Write it yourself.</div>
            ))}
          {answer.kind === "write" && answer.sentences !== null && (
            <button
              disabled={busy}
              onClick={() => send(`/${answer.id}/write`, "POST", "We couldn't write this answer. Try again later.")}
            >
              Write again
            </button>
          )}
          {answer.kind !== "contact" && answer.kind !== "write" && <div style={muted}>{NOTES[answer.kind]}</div>}
          {answer.options.length > 0 && answer.kind !== "demographic" && (
            <div style={muted}>Options: {answer.options.join(", ")}</div>
          )}
          {answer.removed.map((removed) => (
            <div key={removed.text} style={muted}>
              <s>{removed.text}</s> Taken out: {removed.reason}
            </div>
          ))}
          {answer.origin === "pasted" && (
            <button
              disabled={busy}
              onClick={() => send(`/${answer.id}`, "DELETE", "We couldn't remove this question. Try again.")}
            >
              Remove
            </button>
          )}
        </div>
      ))}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void send("/questions", "POST", "We couldn't answer this question. Try again later.", {
            question: pasted.trim(),
          }).then((added) => added && setPasted(""));
        }}
        style={{ marginTop: 8 }}
      >
        <label htmlFor="pasted-question" style={{ display: "block", fontWeight: 600 }}>
          Paste a question from the form
        </label>
        <textarea
          id="pasted-question"
          rows={2}
          maxLength={500}
          style={{ width: "100%", boxSizing: "border-box" }}
          value={pasted}
          onChange={(event) => setPasted(event.target.value)}
        />
        <button type="submit" disabled={busy || !pasted.trim()}>
          Answer it
        </button>
      </form>
    </section>
  );
}
