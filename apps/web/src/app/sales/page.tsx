import Link from "next/link";

/**
 * M8: the branch table - purchases ÷ net sales (cash basis) per branch,
 * ranked, every row labelled - arrives with WP-84 and builds from the
 * founder's wireframe pick. Until it lands this is the landing spot for the
 * loader's "See the branches" link, and says so rather than pretending.
 */
export const metadata = { title: "Faida - Sales" };

export default function SalesPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">Sales</h1>
        <p className="mt-1 max-w-2xl text-sm text-stone">
          Every branch&apos;s takings set against what it paid its suppliers. The ranked branch
          table is being built; sales can already be loaded from the till&apos;s export, and every
          day loaded here will be on it.
        </p>
      </header>
      <section className="rounded-md border border-ink/10 bg-paper p-5">
        <p className="text-sm text-ink">No branch table yet.</p>
        <p className="mt-1 max-w-2xl text-sm text-stone">
          Upload the till&apos;s export and every branch&apos;s purchases will be set against what it
          took, once the table arrives.
        </p>
        <Link
          href="/sales/load"
          className="mt-4 inline-flex min-h-11 items-center rounded-sm bg-palm px-4 py-2 text-sm font-medium text-cream hover:bg-palm-deep"
        >
          Load sales from a CSV
        </Link>
      </section>
    </div>
  );
}
