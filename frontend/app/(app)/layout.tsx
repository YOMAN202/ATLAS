import { Nav } from "@/components/nav";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Nav />
      <main className="ml-64 min-h-screen">
        <div className="mx-auto max-w-grid px-6 py-8 md:px-8">{children}</div>
      </main>
    </>
  );
}
