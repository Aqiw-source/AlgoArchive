# Changelog

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
