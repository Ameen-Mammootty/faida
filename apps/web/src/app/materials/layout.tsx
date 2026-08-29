import type { Metadata } from "next";
import AppShell from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Faida - Raw materials",
  description: "One shelf per ingredient: the packs you buy, joined into the things you cook with.",
};

export default function MaterialsLayout({ children }: { children: React.ReactNode }) {
  return <AppShell current="materials">{children}</AppShell>;
}
