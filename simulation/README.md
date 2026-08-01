# simulation/

Day-advancing simulation engine that generates a realistic 5-year operational history by calling the OLTP Domain Services layer — never writing to the database directly (ADR-007).

Populated in **Phase 3** (`simulation/engine.py`, `simulation/generators/`, `simulation/config/`), after the Domain Services layer (Phase 2) it depends on. See `docs/ATLAS-Roadmap.md`.

**Current status:** Phase 3 is in progress. The engine, generators,
configuration, validation runner, and test suite are implemented. The
remaining workflow is the Roadmap-defined 90-day validation run, review
of its realism/performance evidence, and only then a gated full 5-year
generation.

## Deterministic Replay Verification

The weighted product sampler uses replacement plus collision redraw to
avoid NumPy's expensive weighted `replace=False` path. Deterministic
replay is verified by
`tests/test_demand.py::test_weighted_indices_without_replacement_is_deterministic_given_same_seed`:
two fresh NumPy generators seeded with `99` each produce the same 50
successive selections. The optimization may consume a different RNG draw
sequence than the former NumPy implementation, so replay is guaranteed
within the optimized implementation, not byte-for-byte against historical
pre-optimization runs.

`benchmark_demand_sampling.py` compares the optimized sampler with the
former path at the validation-scale SKU count and reports ABC demand-share
differences as a statistical-equivalence check.
