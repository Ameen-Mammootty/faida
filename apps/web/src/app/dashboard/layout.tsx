import type { Metadata } from "next";
import AppShell from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Faida - Dashboard",
  description:
    "Which branch and which dish to look at first: what each kept after ingredients and packaging, over the days you have loaded.",
};

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return <AppShell current="dashboard">{children}</AppShell>;
}
