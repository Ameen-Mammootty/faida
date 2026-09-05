import SalesTable from "@/components/SalesTable";

/**
 * M8 WP-84: the branch table - purchases ÷ net sales (cash basis) per
 * branch, ranked, every row labelled - variant B, "Answer first".
 */
export const metadata = { title: "Faida - Sales" };

export default function SalesPage() {
  return <SalesTable />;
}
