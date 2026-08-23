import type { Metadata } from "next";
import { Inter, Manrope } from "next/font/google";

import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope", display: "swap" });

export const metadata: Metadata = {
  title: "Faida | Every branch. Clearer margins.",
  description:
    "Forward supplier invoices on WhatsApp and see where prices and margins are moving across every branch.",
  applicationName: "Faida",
  keywords: [
    "cafeteria profit",
    "restaurant supplier prices",
    "invoice tracking",
    "GCC restaurants",
  ],
  openGraph: {
    title: "Faida | Every branch. Clearer margins.",
    description:
      "Supplier invoice and margin visibility for GCC cafeterias, starting in WhatsApp.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${manrope.variable}`}>{children}</body>
    </html>
  );
}
