"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const POLL_DELAY_MS = 2000;

// Mirrors the named scenarios in simulator/scenarios.py, in plain customer
// language. This dropdown is demo infrastructure only -- there is no real
// payment gateway behind it, so a real product would never ask a customer
// to pick their own decline reason. Labeled honestly in the UI as a demo
// control, not a real step in a checkout flow.
const DEMO_SCENARIOS: { value: string; label: string }[] = [
  { value: "insufficient_funds_standard_customer", label: "Insufficient funds" },
  {
    value: "insufficient_funds_with_backup_card",
    label: "Insufficient funds (I have a backup card on file)",
  },
  {
    value: "insufficient_funds_high_value_customer",
    label: "Insufficient funds (a large purchase)",
  },
  { value: "expired_card_no_backup", label: "My card expired" },
  {
    value: "expired_card_with_backup",
    label: "My card expired (I have a backup card on file)",
  },
  {
    value: "fraud_hold_stolen_card",
    label: "I think my card was stolen or used without my permission",
  },
  { value: "fraudulent_charge_flagged", label: "I don't recognize this charge" },
  { value: "processing_error_transient", label: "I got a processing error" },
  { value: "try_again_later_transient", label: "I got a “try again later” message" },
];

type PaymentFailedResponse = {
  case_id: string;
  workflow_id: string;
  status: string;
  attempt_count: number;
};

// Matches api/main.py's ResolutionResponse -- computed server-side on
// purpose, so this page never has to guess at a raw CaseStatus or decide
// for itself what's safe to show a customer (that used to live here;
// moving it server-side is what let it name the actual action taken for
// a resolved case without also risking a leak of *why* an escalated one
// escalated).
type Resolution = {
  customer_status: "in_progress" | "being_reviewed" | "resolved" | "escalated";
  message: string;
};

function isTerminal(status: Resolution["customer_status"]): boolean {
  return status === "resolved" || status === "escalated";
}

function readCaseIdFromUrl(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("case");
}

export default function Page() {
  const [caseId, setCaseId] = useState<string | null>(readCaseIdFromUrl);
  const [resolution, setResolution] = useState<Resolution | null>(null);
  const [complaintText, setComplaintText] = useState("");
  const [scenario, setScenario] = useState(DEMO_SCENARIOS[0].value);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // One in-flight status request at a time: the next poll is scheduled
  // only after the previous one finishes (success or failure), never on
  // a fixed interval -- so a slow request can't cause requests to pile up.
  const pollOnce = useCallback(async (id: string) => {
    try {
      const res = await fetch(`${API_URL}/cases/${id}/resolution`);
      if (!res.ok) throw new Error(`status ${res.status}`);
      const data: Resolution = await res.json();
      setResolution(data);
      setError(null);
      if (!isTerminal(data.customer_status)) {
        pollTimeoutRef.current = setTimeout(() => pollOnce(id), POLL_DELAY_MS);
      }
    } catch {
      setError("Couldn't reach the server. We'll keep trying.");
      pollTimeoutRef.current = setTimeout(() => pollOnce(id), POLL_DELAY_MS);
    }
  }, []);

  useEffect(() => {
    if (caseId) {
      pollOnce(caseId);
    }
    return () => {
      if (pollTimeoutRef.current !== null) {
        clearTimeout(pollTimeoutRef.current);
        pollTimeoutRef.current = null;
      }
    };
  }, [caseId, pollOnce]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!complaintText.trim() || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/events/payment-failed`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          idempotency_key: crypto.randomUUID(),
          payload: { complaint_text: complaintText, scenario },
        }),
      });
      if (!res.ok) throw new Error(`status ${res.status}`);
      const data: PaymentFailedResponse = await res.json();
      // Demo convenience only: this URL has no authorization check, so a
      // real deployment must not treat "?case=<id>" as access control --
      // see CLAUDE.md's Sprint 6a note.
      window.history.replaceState(null, "", `/?case=${data.case_id}`);
      setCaseId(data.case_id);
    } catch {
      setError("Something went wrong submitting your report. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleStartOver = () => {
    window.history.replaceState(null, "", "/");
    setCaseId(null);
    setResolution(null);
    setComplaintText("");
    setError(null);
  };

  return (
    <main>
      <h1>Report a Payment Issue</h1>

      {!caseId && (
        <form onSubmit={handleSubmit}>
          <label htmlFor="complaint">What happened?</label>
          <textarea
            id="complaint"
            required
            rows={4}
            value={complaintText}
            onChange={(e) => setComplaintText(e.target.value)}
            placeholder="e.g. My payment was declined at checkout and I'm not sure why."
          />

          <label htmlFor="scenario">Demo scenario (simulated — no real payment gateway)</label>
          <select
            id="scenario"
            value={scenario}
            onChange={(e) => setScenario(e.target.value)}
          >
            {DEMO_SCENARIOS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>

          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Submitting..." : "Submit"}
          </button>
        </form>
      )}

      {caseId && (
        <div className="status-box">
          {!resolution && <p>Loading your case status...</p>}
          {resolution && (
            <>
              <p>{resolution.message}</p>
              {!isTerminal(resolution.customer_status) && (
                <p aria-live="polite">Checking for updates...</p>
              )}
              {isTerminal(resolution.customer_status) && (
                <button onClick={handleStartOver}>Report another issue</button>
              )}
            </>
          )}
        </div>
      )}

      {error && <p role="alert">{error}</p>}
    </main>
  );
}
