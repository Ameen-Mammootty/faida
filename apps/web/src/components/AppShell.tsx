import Link from "next/link";
import { isMockMode } from "@/lib/api";
import SessionMenu from "./SessionMenu";

/**
 * The app shell for the console screens. The marketing landing page at the
 * root owns its own chrome.
 *
 * Two chromes, one at a time (M9 WP-97, decision D4 of 2026-09-05):
 *
 * - From 1280 px (Tailwind's `xl`) a 232 px Date Palm sidebar: the lockup, the
 *   five words in three groups, and at its foot who is signed in, the mock
 *   chip and the brand line. 1280 and not 1024 because the content column is
 *   then still about 1000 px, wider than the 976 px every fixed grid on the
 *   app has already been measured at, so no table is ever squeezed.
 * - Under 1280 px the top bar exactly as it was measured at 390 px in WP-93:
 *   the mark as the dashboard link with its small "Dashboard" label from
 *   640 px, the four words, and the quiet second row on a phone.
 *
 * `AppShell` stays a server component and cannot pick a chrome by viewport, so
 * both are in the DOM and Tailwind's `hidden` - which is `display:none`, never
 * `sr-only` or opacity - takes the other out of the accessibility tree and the
 * focus order too. Each chrome wraps its links in `<nav aria-label="Faida">`,
 * so exactly one navigation landmark is heard at any width.
 *
 * `current` is passed in rather than read from the router so the layouts stay
 * server components. The one client island is `SessionMenu` (M7 WP-71), and
 * there is exactly one of it in the DOM: the shell used to mount it twice,
 * once per header row, each running its own session read. It now sits in one
 * slot that CSS moves - the phone's second row, the header row from 640 px,
 * and the sidebar foot from 1280 px - so a page load reads the session once.
 */
type Screen = "dashboard" | "invoices" | "materials" | "menu" | "sales";

/** The sidebar's five words, in the three groups confirmed by D5. */
const GROUPS: { caption: string; entries: { screen: Screen; href: string; label: string }[] }[] = [
  {
    caption: "Overview",
    entries: [{ screen: "dashboard", href: "/dashboard", label: "Dashboard" }],
  },
  {
    caption: "Operations",
    entries: [
      { screen: "invoices", href: "/invoices", label: "Invoices" },
      { screen: "sales", href: "/sales", label: "Sales" },
    ],
  },
  {
    caption: "Costing",
    entries: [
      { screen: "materials", href: "/materials", label: "Materials" },
      { screen: "menu", href: "/menu", label: "Menu" },
    ],
  },
];

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
  const mock = isMockMode();

  return (
    <div className="flex min-h-screen flex-col antialiased xl:pl-58">
      {/* The sidebar is fixed so the words stay put while a long table scrolls,
          which is also what lets the one session slot below sit at its foot. */}
      <aside className="fixed inset-y-0 left-0 z-10 hidden w-58 flex-col overflow-y-auto bg-palm py-6 xl:flex">
        <Link
          href="/dashboard"
          className="mx-5 flex items-center gap-4 rounded-sm focus-visible:outline-gold!"
          aria-label="Faida dashboard"
        >
          {/* The Margin Fold mark reversed for a Date Palm ground: the two dark
              tiles become Warm Cream, the centre fold stays Karak Gold. Both
              are the approved palette, and the lockup measures over the brand
              guide's 120 px floor for the horizontal form. */}
          <svg viewBox="0 0 112 104" aria-hidden="true" className="h-9 w-auto shrink-0">
            <path className="fill-cream" d="M8 61c0-8 4-14 11-18l27-16v30L20 72c-6 4-12 0-12-7z" />
            <path className="fill-gold" d="M37 47c0-8 4-14 11-18l26-15v30L48 59c-6 4-11 0-11-7z" />
            <path className="fill-cream" d="M66 32c0-8 4-14 11-18L104 0v70L78 85c-6 4-12 0-12-7z" />
          </svg>
          <span className="font-display text-3xl font-semibold tracking-[-0.02em] text-cream">
            faida
          </span>
        </Link>
        <nav aria-label="Faida" className="mt-9 flex flex-col gap-7">
          {GROUPS.map((group) => {
            const captionId = `sidebar-group-${group.caption.toLowerCase()}`;
            return (
              <div key={group.caption}>
                <p
                  id={captionId}
                  className="px-5 text-[0.6875rem] font-semibold tracking-[0.14em] text-cream/70 uppercase"
                >
                  {group.caption}
                </p>
                <ul aria-labelledby={captionId} className="mt-2 flex flex-col px-2">
                  {group.entries.map((entry) => {
                    const active = entry.screen === current;
                    return (
                      <li key={entry.href}>
                        <Link
                          href={entry.href}
                          aria-current={active ? "page" : undefined}
                          // The current word carries three cues, never colour
                          // alone: the word itself, bold weight, and the gold
                          // bar. The focus ring is gold too, because the palm
                          // ring the app uses elsewhere vanishes on palm.
                          className={`relative flex items-center rounded-sm px-3 py-2 focus-visible:outline-gold! ${
                            active
                              ? "text-sm font-semibold text-cream"
                              : "text-sm font-medium text-cream/70 hover:text-cream"
                          }`}
                        >
                          {active ? (
                            <span
                              aria-hidden="true"
                              className="absolute inset-y-0 left-0 w-[3px] rounded-sm bg-gold"
                            />
                          ) : null}
                          {entry.label}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </nav>
        {/* The foot. The 40 px band is the one session slot's, which is fixed
            over it; the two heights below and its `bottom-13` must agree. */}
        <div className="mt-auto px-5">
          {mock ? (
            <span className="inline-block rounded-sm bg-cream/10 px-2 py-0.5 text-xs font-medium whitespace-nowrap text-cream/80">
              Sample data
            </span>
          ) : null}
          <div aria-hidden="true" className="mt-4 h-10" />
          <p className="mt-3 h-4 text-xs leading-4 text-cream/70">Profit, in plain sight.</p>
        </div>
      </aside>

      <header className="relative border-b border-ink/10 xl:border-b-0">
        {/* The phone row's hairline, drawn across the full width as the shipped
            second row drew it, so the session slot can sit over the row. */}
        <span aria-hidden="true" className="absolute inset-x-0 top-14 h-px bg-ink/5 sm:hidden" />
        <div className="mx-auto flex w-full max-w-6xl items-start px-4 sm:px-6 xl:contents">
          {/* `flex-auto` and no wrapping from 640 px: the words then sit on
              their intrinsic width, so when the row is 2 px tight at 768 px the
              squeeze lands on the address beside Sign out, exactly where the
              shipped single row put it. Wrapping is the phone's second row. */}
          <nav
            aria-label="Faida"
            className="flex flex-auto flex-wrap items-center sm:flex-nowrap xl:hidden"
          >
            <Link
              href="/dashboard"
              className="mr-auto flex h-14 items-center gap-2.5 rounded-sm"
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
            <div className="flex h-14 items-center gap-3 sm:gap-4">
              {mock ? (
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
              <span aria-hidden="true" className="hidden h-4 w-px bg-ink/10 sm:block" />
            </div>
            {/* Below sm the header row is full with the nav alone (measured at
                390 px: Sign out beside Menu pushed the row 64 px past the edge),
                so who is signed in and the way out get a quiet row of their own.
                The 1 px is the hairline above it. */}
            <div className="mt-px flex h-9 w-full items-center gap-3 sm:hidden">
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
              {mock ? (
                <span className="rounded-sm bg-mist px-2 py-0.5 text-xs font-medium whitespace-nowrap text-stone">
                  Sample data
                </span>
              ) : null}
            </div>
          </nav>
          {/* The one session slot. On a phone it is lifted out of the flow so
              the four words keep the whole of the top row; from 640 px it is
              back in the row where it has always been; from 1280 px it is
              fixed into the sidebar's foot band. One node, one session read. */}
          <div className="absolute top-[57px] right-4 flex h-9 max-w-[55%] items-center sm:static sm:ml-4 sm:h-14 sm:max-w-none xl:fixed xl:top-auto xl:right-auto xl:bottom-13 xl:left-0 xl:z-20 xl:ml-0 xl:h-10 xl:w-58 xl:px-5">
            <SessionMenu />
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-5 sm:px-6 xl:pt-10">{children}</main>
      {/* The brand line moves into the sidebar foot where there is a sidebar. */}
      <footer className="mx-auto w-full max-w-6xl px-4 pt-4 pb-10 sm:px-6 xl:hidden">
        <p className="text-xs text-stone">Profit, in plain sight.</p>
      </footer>
    </div>
  );
}
