"use client";

import { useEffect, useState } from "react";

import { ApiError } from "./api-client";

type QueryState<T> =
  | { status: "loading"; data: null; error: null }
  | { status: "error"; data: null; error: ApiError | Error }
  | { status: "ready"; data: T; error: null };

/** Minimal fetch-on-mount-and-on-deps-change hook — no caching/retry
 * beyond what the browser and the API's own ETL-run-keyed cache already
 * provide (backend/app/api/cache.py). Scoped deliberately small: this
 * is a batch-analytics dashboard, not a real-time app that needs
 * react-query's full feature set. */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[]): QueryState<T> {
  const [state, setState] = useState<QueryState<T>>({ status: "loading", data: null, error: null });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading", data: null, error: null });
    fetcher()
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data, error: null });
      })
      .catch((error) => {
        if (!cancelled) setState({ status: "error", data: null, error });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
