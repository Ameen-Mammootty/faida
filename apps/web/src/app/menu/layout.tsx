import type { Metadata } from "next";
import AppShell from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Faida - Menu",
  description: "What each menu item earns after its ingredients - what to push, and what to fix.",
};

export default function MenuLayout({ children }: { children: React.ReactNode }) {
  return <AppShell current="menu">{children}</AppShell>;
}
