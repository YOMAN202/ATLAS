// Mirrors backend/app/core/security.py exactly — the frontend's role
// selector and the API's X-Atlas-Role check must agree on these values.
// Simulated actors are role-played through the UI, not backed by a real
// identity provider (ATLAS-SRS.md §16) — this is a declared role, not a
// login.

export const EXECUTIVE = "executive" as const;
export const OPERATIONS_ANALYST = "operations_analyst" as const;
export const SUPPLY_PLANNER = "supply_planner" as const;
export const ADMINISTRATOR = "administrator" as const;

export type AtlasRole =
  | typeof EXECUTIVE
  | typeof OPERATIONS_ANALYST
  | typeof SUPPLY_PLANNER
  | typeof ADMINISTRATOR;

export const ALL_ROLES: { value: AtlasRole; label: string }[] = [
  { value: EXECUTIVE, label: "Executive" },
  { value: OPERATIONS_ANALYST, label: "Operations Analyst" },
  { value: SUPPLY_PLANNER, label: "Supply Planner" },
  { value: ADMINISTRATOR, label: "Administrator" },
];
