import MenuLoader from "@/components/MenuLoader";

/**
 * M6 WP-64. Nested under `/menu`, so it inherits that route's AppShell with
 * "Menu" current - the loader is a consultant tool reached from consultant
 * contexts, never a fourth item in the owner's nav.
 */
export const metadata = { title: "Faida - Load a menu" };

export default function MenuLoadPage() {
  return <MenuLoader />;
}
