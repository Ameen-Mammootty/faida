"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { listInvoices, uploadDocument } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { branchOptions, type FilterOption } from "@/lib/options";
import { AlertIcon } from "./icons";

/**
 * WP-34's upload path: pick or drop an invoice photo, POST /api/documents,
 * then poll the invoice list until the extracted invoice appears (list rows
 * carry document_id) and open its review screen.
 *
 * C6 has no document-status endpoint, so the page cannot ask "did extraction
 * fail?" - the poll budget is the honest detector for both "failed" and
 * "slow" (a real failure takes the queue's three retries anyway). When the
 * budget runs out, the page says exactly what is known - the file is saved,
 * the invoice may still appear - and hands over to manual entry. Never a
 * dead end (plan.md §5 layer 6).
 */

const ACCEPTED_MIMES = ["image/jpeg", "image/png", "application/pdf"];
const ACCEPT_ATTR = ACCEPTED_MIMES.join(",");
const MAX_BYTES = 10 * 1024 * 1024; // mirrors the API's UPLOAD_MAX_BYTES
const POLL_MS = 3000;
const POLL_BUDGET_MS = 60_000;

type Phase = "idle" | "uploading" | "waiting" | "timeout";

function fileLabel(file: File): string {
  const kb = file.size / 1024;
  const size = kb >= 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(kb))} KB`;
  return `${file.name} · ${size}`;
}

export default function UploadInvoice() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [branchId, setBranchId] = useState("");
  const [branches, setBranches] = useState<FilterOption[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  // Branch choices come from the invoice list (C6 has no branches endpoint);
  // with no invoices yet the select simply stays hidden - branch is optional.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const invoices = await listInvoices();
        if (!cancelled) setBranches(branchOptions(invoices));
      } catch {
        // No options; the upload still works without a branch.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Revoke the preview URL when it is replaced or the page unmounts.
  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  // The poll: every few seconds, look for an invoice carrying our
  // document_id; found -> its review screen. Budget spent -> honest state.
  useEffect(() => {
    if (phase !== "waiting" || documentId === null) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const deadline = Date.now() + POLL_BUDGET_MS;

    async function poll() {
      try {
        const invoices = await listInvoices();
        if (cancelled) return;
        const match = invoices.find((invoice) => invoice.document_id === documentId);
        if (match) {
          router.replace(`/invoices/${match.id}`);
          return;
        }
      } catch {
        // A failed poll is not a failed upload; keep trying until the budget.
      }
      if (cancelled) return;
      if (Date.now() >= deadline) {
        setPhase("timeout");
        return;
      }
      timer = setTimeout(poll, POLL_MS);
    }

    timer = setTimeout(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [phase, documentId, router]);

  function choose(next: File) {
    const mime = (next.type || "").toLowerCase();
    if (!ACCEPTED_MIMES.includes(mime)) {
      setError("That file type won't work. Send a JPEG or PNG photo, or a PDF.");
      return;
    }
    if (next.size > MAX_BYTES) {
      setError("That file is over the 10 MB limit. Try a smaller photo.");
      return;
    }
    if (next.size === 0) {
      setError("That file is empty. Pick the invoice photo again.");
      return;
    }
    setError(null);
    setFile(next);
    setPreview(mime.startsWith("image/") ? URL.createObjectURL(next) : null);
  }

  async function submit() {
    if (!file) return;
    setPhase("uploading");
    setError(null);
    try {
      const result = await uploadDocument(file, branchId || undefined);
      setDocumentId(result.document_id);
      setPhase("waiting");
    } catch (err) {
      setPhase("idle");
      setError(err instanceof ApiError ? err.message : "Couldn't upload the file. Try again.");
    }
  }

  function reset() {
    setPhase("idle");
    setDocumentId(null);
    setFile(null);
    setPreview(null);
    setError(null);
  }

  const manualHref = branchId
    ? `/invoices/manual?branch_id=${encodeURIComponent(branchId)}`
    : "/invoices/manual";

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <nav>
        <Link href="/invoices" className="text-sm font-medium text-palm hover:text-palm-deep">
          &larr; All invoices
        </Link>
      </nav>

      <header>
        <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
          Upload an invoice
        </h1>
        <p className="mt-1 text-sm text-stone">
          The photo goes through the same reading and checking as one forwarded on WhatsApp.
          Prefer typing?{" "}
          <Link href={manualHref} className="font-medium text-palm hover:text-palm-deep">
            Enter it manually
          </Link>
          .
        </p>
      </header>

      {phase === "waiting" ? (
        <div
          aria-busy="true"
          className="rounded-md border border-ink/10 bg-paper p-8 text-center"
        >
          <p role="status" className="text-sm font-medium text-ink">
            Reading the invoice
          </p>
          <p className="mt-1 text-sm text-stone">
            {file ? `${fileLabel(file)} is uploaded. ` : null}
            This usually takes under 20 seconds; you&apos;ll land on the review screen the moment
            it&apos;s ready.
          </p>
        </div>
      ) : phase === "timeout" ? (
        <div className="rounded-md border border-caution/20 bg-gold-soft p-6">
          <p className="flex items-center gap-2 text-sm font-medium text-caution">
            <AlertIcon />
            This one is taking too long.
          </p>
          <p className="mt-2 text-sm text-ink">
            The photo is saved, so nothing is lost - the invoice may still appear in the list in
            a few minutes, or reading it may have failed. You don&apos;t have to wait: type it in
            and it counts right away.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Link
              href={manualHref}
              className="rounded-sm bg-palm px-3.5 py-2 text-sm font-semibold text-white hover:bg-palm-deep"
            >
              Enter it manually
            </Link>
            <Link
              href="/invoices"
              className="rounded-sm border border-palm/30 px-3.5 py-2 text-sm font-medium text-palm hover:border-palm hover:bg-mist"
            >
              Check the list
            </Link>
            <button
              type="button"
              onClick={reset}
              className="px-2 py-2 text-sm font-medium text-stone hover:text-ink"
            >
              Try another photo
            </button>
          </div>
        </div>
      ) : (
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              const dropped = event.dataTransfer.files[0];
              if (dropped) choose(dropped);
            }}
            className={`rounded-md border-2 border-dashed bg-paper p-8 text-center transition-colors ${
              dragging ? "border-palm bg-mist" : "border-ink/20"
            }`}
          >
            {file ? (
              <>
                {preview ? (
                  <img
                    src={preview}
                    alt="Preview of the chosen invoice photo"
                    className="mx-auto mb-3 max-h-48 rounded-sm border border-ink/10"
                  />
                ) : null}
                <p className="text-sm font-medium text-ink">{fileLabel(file)}</p>
                <button
                  type="button"
                  onClick={() => inputRef.current?.click()}
                  className="mt-1 text-sm font-medium text-palm hover:text-palm-deep"
                >
                  Choose a different file
                </button>
              </>
            ) : (
              <>
                <p className="text-sm text-ink">Drop the invoice photo here</p>
                <p className="mt-1 text-sm text-stone">
                  JPEG, PNG, or PDF, up to 10 MB - or{" "}
                  <button
                    type="button"
                    onClick={() => inputRef.current?.click()}
                    className="font-medium text-palm hover:text-palm-deep"
                  >
                    browse for it
                  </button>
                </p>
              </>
            )}
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT_ATTR}
              className="sr-only"
              aria-label="Invoice photo"
              onChange={(event) => {
                const picked = event.target.files?.[0];
                if (picked) choose(picked);
                event.target.value = ""; // re-picking the same file must re-fire
              }}
            />
          </div>

          {branches.length > 0 ? (
            <label className="flex items-center gap-2 text-sm font-medium text-stone">
              Branch
              <select
                value={branchId}
                onChange={(event) => setBranchId(event.target.value)}
                className="rounded-sm border border-ink/20 bg-paper px-2 py-1.5 text-sm text-ink hover:border-palm/50"
              >
                <option value="">Not set</option>
                {branches.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          {error ? <p className="text-sm font-medium text-plum">{error}</p> : null}

          <button
            type="submit"
            disabled={!file || phase === "uploading"}
            className="rounded-sm bg-palm px-4 py-2 text-sm font-semibold text-white hover:bg-palm-deep disabled:opacity-60"
          >
            {phase === "uploading" ? "Uploading" : "Upload and read"}
          </button>
        </form>
      )}
    </div>
  );
}
