import type { Metadata, Viewport } from "next";
import { Outfit } from "next/font/google";

import "./globals.css";

const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit" });

export const metadata: Metadata = {
  title: "Carewise — find your next healthcare step",
  description:
    "Describe what's going on in your own words and get a clear, safety-first suggestion for where to seek care. Not a diagnosis.",
};

export const viewport: Viewport = {
  themeColor: "#f5f6f8",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={outfit.variable}>
      <body className="min-h-dvh font-sans">{children}</body>
    </html>
  );
}
