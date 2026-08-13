"""Role-based access for the dashboard API (SEC-5). Simulated actors are
role-played through the UI, not backed by a full identity provider
(ATLAS-SRS.md §16 assumption) — so "auth" here is a declared role on
each request, not a login/session/token system. A real deployment would
replace this dependency's internals with a real identity provider
without changing any route's `require_role(...)` call, since routes
depend on the *role*, not on how it was established.
"""

from fastapi import Header, HTTPException

EXECUTIVE = "executive"
OPERATIONS_ANALYST = "operations_analyst"
SUPPLY_PLANNER = "supply_planner"
ADMINISTRATOR = "administrator"

ALL_ROLES = {EXECUTIVE, OPERATIONS_ANALYST, SUPPLY_PLANNER, ADMINISTRATOR}


def require_role(*allowed: str):
    """FastAPI dependency factory: reads the caller's declared role from
    the X-Atlas-Role header and rejects the request if that role isn't
    in `allowed` for this endpoint. No default role — a missing header
    is a 401, not a silent fallback to some permissive role.
    """

    def dependency(x_atlas_role: str = Header(alias="X-Atlas-Role")) -> str:
        role = x_atlas_role.strip().lower()
        if role not in ALL_ROLES:
            raise HTTPException(
                status_code=401,
                detail=f"Unknown role '{x_atlas_role}'. Must be one of {sorted(ALL_ROLES)}.",
            )
        if role not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{role}' is not permitted to view this dashboard.",
            )
        return role

    return dependency
