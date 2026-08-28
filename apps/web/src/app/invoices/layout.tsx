import type { Metadata } from "next";
import AppShell from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Faida - Invoices",
  description: "Every number on screen traces to the invoice photo beside it.",
};

export default function InvoicesLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
