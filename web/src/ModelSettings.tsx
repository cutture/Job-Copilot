import { useEffect, useState } from "react";

type Settings = {
  mode: "paid" | "free";
  // Why free models are in use, when they are.
  note: string | null;
  groq_zdr_confirmed: boolean;
  personal_work_waits: boolean;
};

export function ModelSettings() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/model-settings")
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then(setSettings)
      .catch(() => setError("We couldn't load your model settings. Try refreshing the page."));
  }, []);

  async function confirmZdr(confirmed: boolean) {
    const response = await fetch("/api/model-settings/groq-zdr", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmed }),
    });
    if (response.ok) setSettings(await response.json());
    else setError("We couldn't save that. Try again.");
  }

  if (error && !settings) return <p role="alert">{error}</p>;
  if (!settings) return null;
  return (
    <section>
      <h3>AI models</h3>
      <p>{settings.note ?? "Claude Haiku is in use for your Profile, ratings and Application Packs."}</p>
      {settings.personal_work_waits && (
        <p role="alert">
          Ratings and Application Packs wait until a free model may receive your data. Tick the box below, or add
          Cloudflare keys to your .env file.
        </p>
      )}
      <label>
        <input
          type="checkbox"
          checked={settings.groq_zdr_confirmed}
          onChange={(event) => confirmZdr(event.target.checked)}
        />{" "}
        I've turned on Zero Data Retention in Groq, so Groq may receive my data when free models are in use
      </label>{" "}
      <p>
        Your data goes only to models that don't train on it:{" "}
        <a href="https://www.anthropic.com/legal/commercial-terms" target="_blank" rel="noreferrer">
          Anthropic's data policy
        </a>
        ,{" "}
        <a href="https://console.groq.com/docs/your-data" target="_blank" rel="noreferrer">
          Groq's data controls
        </a>{" "}
        and{" "}
        <a href="https://developers.cloudflare.com/workers-ai/platform/privacy/" target="_blank" rel="noreferrer">
          Cloudflare's data policy
        </a>
        .
      </p>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
