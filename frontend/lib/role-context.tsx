"use client";

import { createContext, useContext, useEffect, useState } from "react";

import { ADMINISTRATOR, type AtlasRole } from "./roles";

const STORAGE_KEY = "atlas-role";

interface RoleContextValue {
  role: AtlasRole;
  setRole: (role: AtlasRole) => void;
}

const RoleContext = createContext<RoleContextValue | null>(null);

export function RoleProvider({ children }: { children: React.ReactNode }) {
  const [role, setRoleState] = useState<AtlasRole>(ADMINISTRATOR);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY) as AtlasRole | null;
    if (stored) setRoleState(stored);
  }, []);

  function setRole(next: AtlasRole) {
    setRoleState(next);
    window.localStorage.setItem(STORAGE_KEY, next);
  }

  return <RoleContext.Provider value={{ role, setRole }}>{children}</RoleContext.Provider>;
}

export function useRole(): RoleContextValue {
  const ctx = useContext(RoleContext);
  if (!ctx) throw new Error("useRole must be used within a RoleProvider");
  return ctx;
}
