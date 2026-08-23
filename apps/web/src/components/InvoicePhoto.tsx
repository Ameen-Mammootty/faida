"use client";

import { useState } from "react";

/**
 * The stored original, zoomable without a library: click toggles a CSS
 * transform zoom, and while zoomed the transform origin follows the cursor
 * so the reader can inspect any cell of the invoice.
 */
export default function InvoicePhoto({ src, alt }: { src: string | null; alt: string }) {
  const [zoomed, setZoomed] = useState(false);
  const [origin, setOrigin] = useState("50% 50%");

  if (!src) {
    return (
      <div className="rounded-md border border-ink/10 bg-paper p-8 text-center text-sm text-stone">
        No photo for this invoice. It was entered manually.
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
