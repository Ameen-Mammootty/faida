"use client";

import { useEffect, useId, useRef, useSyncExternalStore } from "react";

/**
 * The circled "i" beside a figure, a name or a heading, and the panel of
 * sentences behind it (the founder's redesign, 2026-09-07: "for any
 * additional information, you can put an icon that we can show. Users can get
 * it once they click on it or hover over it").
 *
 * Every line it prints is a sentence the API sent or a join
 * `lib/dashboardScreen.ts` already made. This component composes nothing and
 * knows nothing about the dashboard: it is given lines and shows them.
 *
 * One tip is open at a time across the whole screen, so the module - not any
 * one tip - holds which, and opening one closes the last without either
 * knowing the other exists.
 *
 * The panel is `position: fixed` because the cards and tables it opens from
 * are `overflow-hidden`, and it is measured against its own icon on open, on
 * scroll and on resize: below the icon by default, flipped above when the
 * room below it is short, pulled back from either edge, and never wider than
 * the viewport. No library, no shadow (the brand guide forbids them).
 */

let openTip: string | null = null;
const listeners = new Set<() => void>();

function show(id: string | null): void {
  if (openTip === id) return;
  openTip = id;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

const read = () => openTip;
const readOnServer = () => null;

/** The one glyph this redesign adds: a 16 px circled "i". */
function InfoIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className="h-4 w-4">
      <circle cx="8" cy="8" r="6.25" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="8" cy="5.1" r="0.9" fill="currentColor" />
      <path
        d="M8 7.5v3.7"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** The gap between the icon and the panel, the margin the panel keeps from
 * every edge of the viewport, and the widest it is ever drawn. */
const GAP = 6;
const EDGE = 8;
const MAX_WIDTH = 320;

export default function InfoTip({
  lines,
  label = "More about this",
}: {
  /** One sentence a line, in the words their author wrote them in. */
  lines: string[];
  label?: string;
}) {
  const id = useId();
  const current = useSyncExternalStore(subscribe, read, readOnServer);
  const shown = current === id && lines.length > 0;
  const wrap = useRef<HTMLSpanElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLSpanElement>(null);
  // Set by a click or a key, cleared when the tip closes: leaving with the
  // mouse never shuts a tip the reader opened on purpose.
  const pinned = useRef(false);

  // DOM only - the placement is written straight onto the node through a ref,
  // so opening a tip never re-renders the screen behind it.
  useEffect(() => {
    if (!shown) {
      pinned.current = false;
      return;
    }
    const place = () => {
      const box = panel.current;
      const icon = trigger.current;
      if (box === null || icon === null) return;
      const room = document.documentElement.clientWidth;
      box.style.maxWidth = `${Math.min(MAX_WIDTH, room - EDGE * 2)}px`;
      const at = icon.getBoundingClientRect();
      const size = box.getBoundingClientRect();
      const left = Math.min(
        Math.max(at.left + at.width / 2 - size.width / 2, EDGE),
        Math.max(room - size.width - EDGE, EDGE),
      );
      let top = at.bottom + GAP;
      if (top + size.height > window.innerHeight - EDGE) {
        const above = at.top - size.height - GAP;
        top =
          above >= EDGE
            ? above
            : Math.max(EDGE, window.innerHeight - size.height - EDGE);
      }
      box.style.left = `${left}px`;
      box.style.top = `${top}px`;
      box.style.visibility = "visible";
    };
    place();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") show(null);
    };
    const onDown = (event: Event) => {
      const target = event.target;
      if (target instanceof Node && wrap.current?.contains(target)) return;
      show(null);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [shown]);

  // Nothing to say, nothing to click: a tile with no note carries no icon.
  if (lines.length === 0) return null;

  return (
    <span ref={wrap} className="inline-flex align-middle">
      <button
        ref={trigger}
        type="button"
        aria-label={label}
        aria-expanded={shown}
        aria-describedby={shown ? id : undefined}
        onClick={() => {
          if (shown && pinned.current) {
            show(null);
            return;
          }
          pinned.current = true;
          show(id);
        }}
        onMouseEnter={() => show(id)}
        onMouseLeave={() => {
          if (openTip === id && !pinned.current) show(null);
        }}
        onFocus={() => show(id)}
        onBlur={() => {
          if (openTip === id) show(null);
        }}
        // 16 px of layout, a 28 px hit box: the pseudo-element carries the
        // target so a line of text is not pushed apart by the icon.
        className="relative inline-flex h-4 w-4 items-center justify-center rounded-full text-stone before:absolute before:-inset-1.5 before:content-[''] hover:text-palm focus-visible:text-palm"
      >
        <InfoIcon />
      </button>
      {shown ? (
        <span
          id={id}
          ref={panel}
          role="tooltip"
          style={{ position: "fixed", left: 0, top: 0, visibility: "hidden" }}
          className="z-50 block space-y-1 rounded-md border border-ink/15 bg-paper px-3 py-2 text-left text-[12.5px] leading-snug font-normal text-stone"
        >
          {lines.map((line, index) => (
            <span key={`${index}-${line}`} className="block">
              {line}
            </span>
          ))}
        </span>
      ) : null}
    </span>
  );
}
