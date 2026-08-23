"use client";

import { FormEvent, useState } from "react";

import styles from "./landing.module.css";

type FormState = "idle" | "submitting" | "success" | "error";

export function WaitlistForm() {
  const [state, setState] = useState<FormState>("idle");
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState("submitting");
    setMessage("");

    const data = new FormData(event.currentTarget);
    try {
      const response = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: data.get("email"),
          website: data.get("website"),
        }),
      });

      if (!response.ok) {
        setState("error");
        setMessage(
          response.status === 422
            ? "Enter a valid email address."
            : "We could not save your place. Try again.",
        );
        return;
      }

      event.currentTarget.reset();
      setState("success");
      setMessage("You are on the list. We will be in touch when the private pilot opens.");
    } catch {
      setState("error");
      setMessage("We could not reach Faida. Check your connection and try again.");
    }
  }

  return (
    <div className={styles.formWrap} id="waitlist-form">
      {state === "success" ? (
        <div className={styles.successMessage} role="status" aria-live="polite">
          <span aria-hidden="true">✓</span>
          <div>
            <strong>You are on the list.</strong>
            <p>{message}</p>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} className={styles.waitlistForm}>
          <label htmlFor="waitlist-email" className={styles.srOnly}>
            Work email
          </label>
          <input
            id="waitlist-email"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="email"
            maxLength={254}
            placeholder="you@company.com"
            required
            aria-describedby={state === "error" ? "waitlist-message" : undefined}
          />
          <div className={styles.honeypot} aria-hidden="true">
            <label htmlFor="company-website">Company website</label>
            <input
              id="company-website"
              name="website"
              type="text"
              autoComplete="off"
              tabIndex={-1}
            />
          </div>
          <button type="submit" disabled={state === "submitting"}>
            <span>{state === "submitting" ? "Joining..." : "Join the waitlist"}</span>
            <svg aria-hidden="true" viewBox="0 0 20 20">
              <path
                d="M4 10h11M11 5l5 5-5 5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
              />
            </svg>
          </button>
        </form>
      )}
      <p
        id="waitlist-message"
        className={state === "error" ? styles.formError : styles.formHint}
        role={state === "error" ? "alert" : undefined}
      >
        {state === "error"
          ? message
          : "For owners and operators. No spam, no generic product newsletter."}
      </p>
    </div>
  );
}
