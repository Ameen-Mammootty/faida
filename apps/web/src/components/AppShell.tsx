import Link from "next/link";
import { isMockMode } from "@/lib/api";

/**
 * The app shell for the console screens: brand header, content column, quiet
 * footer. The marketing landing page at the root owns its own chrome.
 *
 * Extracted when M5 added a second screen (WP-52). `current` is passed in
 * rather than read from the router so the layouts stay server components.
 */
export default function AppShell({
  current,
  children,
}: {
  current: "invoices" | "materials" | "menu";
  children: React.ReactNode;
}) {
  const linkClasses = (name: "invoices" | "materials" | "menu") =>
    current === name
      ? "text-sm font-semibold text-palm"
      : "text-sm font-medium text-stone hover:text-palm";

  return (
    <div className="flex min-h-screen flex-col antialiased">
      <header className="border-b border-ink/10">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link
            href="/invoices"
            className="flex items-center gap-2.5 rounded-sm"
            aria-label="Faida invoices"
          >
            <img src="/brand/faida-mark.svg" alt="" className="h-5 w-auto" />
            <span className="font-display text-xl font-semibold tracking-[-0.02em] text-ink">
              faida
            </span>
          </Link>
          <div className="flex items-center gap-3 sm:gap-4">
            {isMockMode() ? (
              // nowrap: at 390 px it wrapped to two lines and crowded the
              // wordmark. The chip is one short phrase or it is nothing.
              <span className="rounded-sm bg-mist px-2 py-0.5 text-xs font-medium whitespace-nowrap text-stone">
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
