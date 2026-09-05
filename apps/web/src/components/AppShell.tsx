import Link from "next/link";
import { isMockMode } from "@/lib/api";
import SessionMenu from "./SessionMenu";

/**
 * The app shell for the console screens: brand header, content column, quiet
 * footer. The marketing landing page at the root owns its own chrome.
 *
 * Extracted when M5 added a second screen (WP-52). `current` is passed in
 * rather than read from the router so the layouts stay server components.
 * The one client island is `SessionMenu` (M7 WP-71): who is signed in, and
 * the sign-out control.
 *
 * The brand lockup is the dashboard's nav entry (M9 WP-93, the design review
 * of 2026-09-05): a fifth word does not fit the top row at 390 px by this
 * shell's own measurement below, so the mark itself is the link, with a small
 * "Dashboard" label beside the wordmark from 640 px up and the word in the
 * quiet second row on a phone. The nav keeps its four words.
 */
type Screen = "dashboard" | "invoices" | "materials" | "menu" | "sales";

export default function AppShell({
  current,
  children,
}: {
  current: Screen;
  children: React.ReactNode;
}) {
  const linkClasses = (name: Screen) =>
    current === name
      ? "text-sm font-semibold text-palm"
      : "text-sm font-medium text-stone hover:text-palm";

  return (
    <div className="flex min-h-screen flex-col antialiased">
      <header className="border-b border-ink/10">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link
            href="/dashboard"
            className="flex items-center gap-2.5 rounded-sm"
            aria-label="Faida dashboard"
            aria-current={current === "dashboard" ? "page" : undefined}
          >
            <img src="/brand/faida-mark.svg" alt="" className="h-5 w-auto" />
            <span className="font-display text-xl font-semibold tracking-[-0.02em] text-ink">
              faida
            </span>
            <span
              className={`hidden text-xs font-medium sm:inline ${
                current === "dashboard" ? "text-palm" : "text-stone"
              }`}
            >
              Dashboard
            </span>
          </Link>
          <div className="flex items-center gap-3 sm:gap-4">
            {isMockMode() ? (
              // nowrap: at 390 px it wrapped to two lines and crowded the
              // wordmark. The chip is one short phrase or it is nothing - and
              // below sm it lives on the second row: with four nav items
              // (Sales joined in M8) the top row had 8 px less than it needed.
              <span className="hidden rounded-sm bg-mist px-2 py-0.5 text-xs font-medium whitespace-nowrap text-stone sm:inline-block">
                Sample data
              </span>
            ) : null}
            <Link
              href="/invoices"
              aria-current={current === "invoices" ? "page" : undefined}
              className={linkClasses("invoices")}
            >
              Invoices
            </Link>
            <Link
              href="/materials"
              aria-current={current === "materials" ? "page" : undefined}
              className={linkClasses("materials")}
            >
              Materials
            </Link>
            <Link
              href="/menu"
              aria-current={current === "menu" ? "page" : undefined}
              className={linkClasses("menu")}
            >
              Menu
            </Link>
            <Link
              href="/sales"
              aria-current={current === "sales" ? "page" : undefined}
              className={linkClasses("sales")}
            >
              Sales
            </Link>
            <div className="hidden items-center gap-4 sm:flex">
              <span aria-hidden="true" className="h-4 w-px bg-ink/10" />
              <SessionMenu />
            </div>
          </div>
        </div>
        {/* Below sm the header row is full with the nav alone (measured at
            390 px: Sign out beside Menu pushed the row 64 px past the edge),
            so who is signed in and the way out get a quiet row of their own. */}
        <div className="border-t border-ink/5 sm:hidden">
          <div className="mx-auto flex h-9 w-full max-w-6xl items-center justify-between px-4">
            <div className="flex items-center gap-3">
              <Link
                href="/dashboard"
                aria-current={current === "dashboard" ? "page" : undefined}
                className={`text-xs ${
                  current === "dashboard"
                    ? "font-semibold text-palm"
                    : "font-medium text-stone hover:text-palm"
                }`}
              >
                Dashboard
              </Link>
              {isMockMode() ? (
                <span className="rounded-sm bg-mist px-2 py-0.5 text-xs font-medium whitespace-nowrap text-stone">
                  Sample data
                </span>
              ) : null}
            </div>
            <SessionMenu showEmail />
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">{children}</main>
      <footer className="mx-auto w-full max-w-6xl px-4 pt-4 pb-10 sm:px-6">
        <p className="text-xs text-stone">Profit, in plain sight.</p>
      </footer>
    </div>
  );
}
