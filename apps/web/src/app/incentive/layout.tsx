import type { Metadata } from "next";
import AppShell from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Faida - Incentive",
  description:
    "The staff incentive: how a month's pool is split, what each branch has to beat, and what the month has earned so far.",
};

export default function IncentiveLayout({ children }: { children: React.ReactNode }) {
  return <AppShell current="incentive">{children}</AppShell>;
}
