# Changelog

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
