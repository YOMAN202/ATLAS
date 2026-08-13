import type { Metadata } from "next";

import { Nav } from "@/components/nav";
import { RoleProvider } from "@/lib/role-context";

import "./globals.css";

export const metadata: Metadata = {
  title: "ATLAS",
  description: "Enterprise Supply Chain Intelligence Platform",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
        <RoleProvider>
          <Nav />
          <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
        </RoleProvider>
      </body>
    </html>
  );
}
