# Changelog

## 2.1.4 - 2026-10-29

- Reduced startup-window log noise by hiding successful static-file requests
  and repeated `/api/state` polling.
- Kept startup information, failed requests, warnings, exceptions, and concise
  records for successful create, update, and delete operations.

## 2.1.3 - 2026-10-29

- Fixed a Windows CI race where stopping a test run could be acknowledged
  before the compiler or student process was registered. A stopped runner no
  longer starts a new child process and now returns a cancelled result
  immediately.
- Added deterministic regression tests for stop-before-run and
  stop-before-process-launch behavior.

## 2.1.2 - 2026-10-29

- Added an actionable missing-compiler banner to the standalone code
  playground and per-problem test runner.
- The prompt links directly to compiler settings and explains that a complete
  MinGW-w64 toolchain is required, not just a copied `g++.exe`.
- Invalid explicitly configured compiler paths now report as unavailable
  instead of silently falling back to another compiler.

## 2.1.1 - 2026-10-29

- Added a standalone "Code Playground" workspace below All Problems in the
  sidebar for compiling and testing temporary C++ without creating a problem.
- Playground code, test cases, and time limit persist as a browser-local draft.
- Added a generic local compiler API shared with per-problem CPH testing.

## 2.1.0 - 2026-10-29

- Added a CPH-compatible C++ test-case panel with per-case and run-all
  execution, stop control, compile diagnostics, and CPH line-trim judging.
- Added `.prob` and JSON test-case import plus CPH-compatible `.prob` export.
- Test cases are stored in SQLite with the problem and survive backups,
  restarts, deletion, and schema upgrades.
- Defaulted C++ compilation to the current VS Code MinGW g++ 8.1.0 compiler
  with GNU++14, while allowing a custom compiler path and standard.
- Declared CPH author Divyanshu Agrawal, the upstream repository, reference
  commit, and GPL-3.0-or-later license in the app, third-party notices, and
  bundled license copy.

## 2.0.5 - 2026-10-28

- Added a built-in NowCoder workspace and NowCoder summary on the home page
  while preserving arbitrary platform input and unrestricted links.
- Added a NowCoder quick selection to the contest dialog.
- Recognized Luogu, NowCoder, and common NowCoder aliases across workspace
  filtering and counting.

## 2.0.4 - 2026-10-28

- Added a built-in Luogu workspace and Luogu summary on the home page while
  keeping arbitrary platform input and unrestricted competition links.
- Reworked the contest dialog into a compact two-column form with explicit
  Codeforces, AtCoder, and Luogu quick selections.
- Removed the browser-native platform suggestion overlay from the contest
  dialog so it no longer covers the footer actions.

## 2.0.3 - 2026-10-28

- Fixed startup failure when the installer wrote `config.json` using the
  Windows ANSI code page and the user profile contained non-ASCII characters.
- Read legacy UTF-8 BOM, UTF-16 BOM, Windows ANSI, and GB18030 configuration
  files while preferring a parsed `data_dir` that exists on disk.
- New installer configuration files are written as UTF-8 without a BOM.

## 2.0.2 - 2026-10-28

- Only show the installer data-directory page for a fresh current-user install,
  so the selected directory is never ignored by all-users or existing-config
  installations.
- Create the desktop shortcut automatically for installed and portable
  distributions.
- Clarify that users must download the Setup executable or Windows x64 ZIP,
  not GitHub's automatically generated source archive.

## 2.0.1 - 2026-10-28

- Added the project GitHub repository and author Aqiw labels to the top bar and
  About diagnostics.
- Updated release, download, documentation, and repository references to
  `Aqiw-source/AlgoArchive`.

## 2.0.0 - 2026-10-28

- Added per-user configuration with a saved custom data directory and explicit
  command-line override priority.
- Added safe data-directory classification, conflict detection, migration
  validation, and schema-version checks before database writes.
- Added browser selection, custom executable support, window mode fallback, and
  browser launch diagnostics.
- Added a tabbed settings interface for profile, browser, data management, and
  diagnostics.
- Added complete ZIP backup, import, restoration, rolling retention, and
  path-traversal protection.
- Added explicit graceful shutdown through the application interface.
- Added rotating local logs without request bodies or source-code contents.
- Added an Inno Setup installer with current-user/all-users privilege selection,
  custom program and data directory selection, and portable ZIP build scripts.
- Added Windows CI, release privacy checks, SHA-256 files, and release
  documentation.
