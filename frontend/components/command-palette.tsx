"use client";

import { Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

interface Link {
  href: string;
  label: string;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  links: Link[];
  onNavigate: (href: string) => void;
}

export function CommandPalette({ open, onClose, links, onNavigate }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const results = useMemo(() => {
    if (!query.trim()) return links;
    const q = query.toLowerCase();
    return links.filter((l) => l.label.toLowerCase().includes(q));
  }, [links, query]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIndex(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  if (!open) return null;

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && results[activeIndex]) {
      onNavigate(results[activeIndex].href);
      onClose();
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-[15vh] animate-fade-in"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-lg border border-hairline-strong bg-surface shadow-overlay animate-rise-in"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <div className="flex items-center gap-2 border-b border-hairline px-4 py-3">
          <Search className="h-4 w-4 text-ink-muted" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Jump to a dashboard…"
            className="w-full bg-transparent text-sm text-ink-primary placeholder:text-ink-muted focus:outline-none"
          />
          <kbd className="rounded border border-hairline px-1.5 py-0.5 font-mono text-2xs text-ink-muted">
            esc
          </kbd>
        </div>
        <div className="max-h-80 overflow-y-auto p-2">
          {results.length === 0 && (
            <p className="px-3 py-6 text-center text-sm text-ink-muted">No matches.</p>
          )}
          {results.map((link, i) => (
            <button
              key={link.href}
              onMouseEnter={() => setActiveIndex(i)}
              onClick={() => {
                onNavigate(link.href);
                onClose();
              }}
              className={`flex w-full items-center rounded-md px-3 py-2 text-left text-sm ${
                i === activeIndex ? "bg-accent-subtle text-accent" : "text-ink-secondary"
              }`}
            >
              {link.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
