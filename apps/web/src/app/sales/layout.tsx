import type { Metadata } from "next";
import AppShell from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Faida - Sales",
  description:
    "What each branch took, set against what it paid its suppliers - purchases ÷ net sales, on a cash basis.",
};

export default function SalesLayout({ children }: { children: React.ReactNode }) {
  return <AppShell current="sales">{children}</AppShell>;
}
