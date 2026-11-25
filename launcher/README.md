# AlgoArchive native launcher

AlgoArchive.exe is a small GUI-subsystem launcher for the packaged
start.bat. It resolves the script relative to its own directory, forwards
command-line arguments, and embeds ACM-ICPC-Windows.ico. It is statically
linked against the MinGW C and C++ runtimes, so the packaged launcher does not
require compiler DLLs on the user's computer.

Build with MinGW-w64. If -Version is omitted, the script reads APP_VERSION
from app.py; passing a different version is rejected.

    .\launcher\build-launcher.ps1

The build verifies the PE version resources, confirms the embedded icon matches
ACM-ICPC-Windows.ico, rejects dynamic MinGW runtime imports, and runs a small
Windows argument-forwarding smoke test against a temporary start.bat.
