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
    // globals.css sets scroll-behavior: smooth (the invoice-line anchors land
    // gently); Next asks for this attribute so it does not also smooth-scroll
    // route transitions, which reads as lag.
    // The font variables go on <html>, not <body>: globals.css resolves
    // --font-sans through var(--font-inter) inside @theme, which Tailwind
    // emits on :root. A custom property that references one declared further
    // down the tree is invalid at computed-value time, so --font-sans came out
    // empty and every screen fell back to the system stack - Manrope and Inter
    // were downloaded and never used (design review 2026-09-01).
    <html lang="en" data-scroll-behavior="smooth" className={`${inter.variable} ${manrope.variable}`}>
      <body>{children}</body>
    </html>
  );
}
