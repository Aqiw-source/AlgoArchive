# Online Demo Implementation Plan

> Execute sequentially in the current authorized workspace. Do not delegate.

**Goal:** Ship a GitHub Pages demo, refreshed README previews, Windows 2.2.6, and a data-preserving installed upgrade.

**Architecture:** Reuse web assets. A demo-only in-memory API adapter supplies verified public metadata; a dedicated Node build produces static Pages artifacts. Local Python APIs remain unchanged by the adapter.

- [x] Add failing Node tests for fixture classification/scale, store contracts, mutation isolation, locks, unsupported system operations, and static artifact privacy.
- [x] Implement demo fixture, in-memory store, browser adapter, static builder, and Pages workflow; rerun Node tests.
- [x] Replace screenshot seeding with the shared fixture, capture independent desktop/mobile previews, verify interactions and all local resources at a project subpath.
- [x] Synchronize 2.2.6 versions, native launcher and release documentation; run backend/browser/package/native checks.
- [ ] Commit and push; enable Pages, verify exact-commit CI and deployed demo; then tag and verify all four public release assets.
- [ ] Upgrade installed program from verified public ZIP. Compare complete state/config hashes and native service version.
