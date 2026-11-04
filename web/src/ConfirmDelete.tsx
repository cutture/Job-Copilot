import { useState } from "react";

// A delete button that asks once before deleting for good.
export function ConfirmDelete({
  label = "Delete",
  question,
  onConfirm,
}: {
  label?: string;
  question: string;
  onConfirm: () => void | Promise<void>;
}) {
  const [asking, setAsking] = useState(false);
  if (!asking) return <button onClick={() => setAsking(true)}>{label}</button>;
  return (
    <span role="group" aria-label={question}>
      {question} This can't be undone.{" "}
      <button
        onClick={async () => {
          await onConfirm();
          setAsking(false);
        }}
      >
        Yes, delete
      </button>{" "}
      <button onClick={() => setAsking(false)}>Keep it</button>
    </span>
  );
}
