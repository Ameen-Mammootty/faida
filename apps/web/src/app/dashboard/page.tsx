import { Suspense } from "react";
import Dashboard from "@/components/Dashboard";

/**
 * M9 WP-93: the owner dashboard - Variant A, "Branch first" (design review
 * 2026-09-05): the freshness line, the two answer sentences, the branch
 * league with contribution beside the ratio, the signals ranked by money,
 * the items five and five, and the coverage strip as a link to the queue.
 * Where a sign-in lands (P10).
 */
export const metadata = { title: "Faida - Dashboard" };

export default function DashboardPage() {
  return (
    // The component reads `?branch=` from the URL, which Next asks to be
    // wrapped for the static render.
    <Suspense fallback={null}>
      <Dashboard />
    </Suspense>
  );
}
