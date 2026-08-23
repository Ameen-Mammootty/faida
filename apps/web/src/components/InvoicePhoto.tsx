"use client";

import { useState } from "react";

/**
 * The stored original, zoomable without a library: click toggles a CSS
 * transform zoom, and while zoomed the transform origin follows the cursor
 * so the reader can inspect any cell of the invoice.
 *
 * The src is a short-lived signed URL (~600 s): when a long-open image stops
 * loading, onExpired asks the parent for a freshly signed detail. The error
 * state resets the moment a new src arrives.
 */
export default function InvoicePhoto({
  src,
  alt,
  onExpired,
}: {
  src: string | null;
  alt: string;
  onExpired?: () => void;
}) {
  const [zoomed, setZoomed] = useState(false);
  const [origin, setOrigin] = useState("50% 50%");
  // The failed URL, not a boolean: a freshly signed src clears the state by
  // simply being a different string - no reset effect needed.
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const failed = src !== null && failedSrc === src;

  if (!src) {
    return (
      <div className="rounded-md border border-ink/10 bg-paper p-8 text-center text-sm text-stone">
        No photo for this invoice. It was entered manually.
      </div>
    );
  }

  if (failed) {
    return (
      <div className="rounded-md border border-ink/10 bg-paper p-8 text-center text-sm text-stone">
        Couldn&apos;t load the invoice photo. Reload the page to try again.
      </div>
    );
  }

  return (
    <figure className="overflow-hidden rounded-md border border-ink/10 bg-paper">
      <button
        type="button"
        aria-pressed={zoomed}
        aria-label={zoomed ? "Reset zoom" : "Zoom into the invoice photo"}
        onClick={() => setZoomed((z) => !z)}
        onMouseMove={(event) => {
          if (!zoomed) return;
          const rect = event.currentTarget.getBoundingClientRect();
          const x = ((event.clientX - rect.left) / rect.width) * 100;
          const y = ((event.clientY - rect.top) / rect.height) * 100;
          setOrigin(`${x}% ${y}%`);
        }}
        onMouseLeave={() => setOrigin("50% 50%")}
        className={`block w-full overflow-hidden ${zoomed ? "cursor-zoom-out" : "cursor-zoom-in"}`}
      >
        <img
          src={src}
          alt={alt}
          onError={() => {
            setFailedSrc(src);
            onExpired?.();
          }}
          className="block w-full transition-transform duration-200 ease-out"
          style={{ transform: zoomed ? "scale(2.2)" : "scale(1)", transformOrigin: origin }}
        />
      </button>
      <figcaption className="flex items-center justify-between border-t border-ink/10 px-3 py-2 text-xs text-stone">
        <span>Original photo</span>
        <span>{zoomed ? "Click to reset" : "Click to zoom"}</span>
      </figcaption>
    </figure>
  );
}
