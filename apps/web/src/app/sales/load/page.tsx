import SalesLoader from "@/components/SalesLoader";

/**
 * M8 WP-83. Nested under `/sales`, so it inherits that route's AppShell with
 * "Sales" current - the loader is a consultant tool reached from the sales
 * screen's own link, never a nav item of its own (design review §4.1).
 */
export const metadata = { title: "Faida - Load sales" };

export default function SalesLoadPage() {
  return <SalesLoader />;
}
