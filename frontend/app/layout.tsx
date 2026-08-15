import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { RoleProvider } from "@/lib/role-context";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "ATLAS — Enterprise Supply Chain Intelligence",
  description:
    "A monitor-predict-decide supply chain intelligence platform: real-time dashboards, six decision-intelligence modules, and a verification-first analytics copilot.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} dark`}>
      <body className="min-h-screen bg-page font-sans text-ink-primary antialiased">
        <RoleProvider>{children}</RoleProvider>
      </body>
    </html>
  );
}
