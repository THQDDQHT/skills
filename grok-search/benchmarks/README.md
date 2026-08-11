# Public benchmark

This directory contains the public, reproducible part of the grok-search evaluation.

Included:

- `lib/benchmark-15q-v2.mjs`: frozen 15-question set, expected fields, official URLs, and deterministic patterns.
- `run-responses-15q.mjs`: provider-neutral Responses runner using the normal grok-search configuration.
- `score-responses-15q.mjs`: deterministic correctness and official-source scoring.
- `public/2026-07-11-summary.json`: sanitized aggregate sample from the original study.

Excluded from Git:

- raw provider responses and internal IDs;
- complete fetched page bodies;
- private proxy and relay configuration;
- per-request channel pricing and failure logs;
- historical Chat protocol probes.

Run a small subset first to control cost:

```bash
npm run benchmark -- --only node,rust,python
npm run benchmark:score
```

Runs write raw responses to `benchmarks/results/`, which is intentionally ignored by Git. The historical experiment archive and internal reports remain under the separate local-only `.private/` directory.

## Grader amendments

The question set, truth snapshots, and official URLs stay frozen. Scoring regexes may gain
synonym translations when a semantically correct answer is rejected on vocabulary alone:

- 2026-08-10: the `rust` criterion for "symbol mangling v0" also accepts 修饰 (the
  `rust-vs-deno` criterion already did); a correct answer phrased as 符号修饰 had scored as a miss.
