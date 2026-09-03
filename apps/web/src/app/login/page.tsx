import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import LoginForm from "@/components/LoginForm";

export const metadata: Metadata = {
  title: "Faida - Sign in",
  description: "Sign in to the Faida console.",
};

/**
 * M7 WP-71: the one door into the console. Email and password only
 * (decision D17); accounts are created by the founder in the Supabase
 * dashboard and sign-ups are off (D8), so there is no sign-up page and no
 * invite flow to link to. A signed-in visitor never sees this page: the
 * request interceptor sends them on to the console first.
 *
 * The form reads `?next=` from the URL, which needs `useSearchParams` and
 * therefore a Suspense boundary around the client component.
 */
export default function LoginPage() {
  return (
    <div className="flex min-h-screen flex-col antialiased">
      <header className="border-b border-ink/10">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center px-4 sm:px-6">
          <Link href="/" className="flex items-center gap-2.5 rounded-sm" aria-label="Faida home">
            <img src="/brand/faida-mark.svg" alt="" className="h-5 w-auto" />
            <span className="font-display text-xl font-semibold tracking-[-0.02em] text-ink">
              faida
            </span>
          </Link>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-4 py-10 sm:px-6 sm:py-16">
        <section className="mx-auto w-full max-w-sm">
          <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
            Sign in
          </h1>
          <p className="mt-1 text-sm text-stone">
            Your invoices, materials and menu, in one place.
          </p>
          <div className="mt-6 rounded-md border border-ink/10 bg-paper p-4 sm:p-5">
            <Suspense
              fallback={
                <p aria-busy="true" className="text-sm text-stone">
                  Loading
                </p>
              }
            >
              <LoginForm />
            </Suspense>
          </div>
          <p className="mt-4 text-xs text-stone">
            Accounts are set up by Faida. If you need one, or forgot your password, message the
            team.
          </p>
        </section>
      </main>
      <footer className="mx-auto w-full max-w-6xl px-4 pt-4 pb-10 sm:px-6">
        <p className="text-xs text-stone">Profit, in plain sight.</p>
      </footer>
    </div>
  );
}
