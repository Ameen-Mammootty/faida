import Link from "next/link";
import { isMockMode } from "@/lib/api";

const NAV = [
  { href: "/invoices", label: "Invoices" },
  { href: "/materials", label: "Raw materials" },
];

/**
 * The chrome every working screen shares: brand header, nav, content column,
 * quiet footer. The marketing landing page at the root owns its own.
 */
export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col antialiased">
      <header className="border-b border-ink/10">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link href="/invoices" className="flex items-center gap-2.5 rounded-sm" aria-label="Faida">
            <img src="/brand/faida-mark.svg" alt="" className="h-5 w-auto" />
            <span className="font-display text-xl font-semibold tracking-[-0.02em] text-ink">
              faida
            </span>
          </Link>
          <div className="flex items-center gap-4">
            {isMockMode() ? (
              <span className="rounded-sm bg-mist px-2 py-0.5 text-xs font-medium text-stone">
                Sample data
              </span>
            ) : null}
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="text-sm font-medium text-palm hover:text-palm-deep"
              >
                {item.label}
              </Link>
            ))}
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
