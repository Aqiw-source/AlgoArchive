# AlgoArchive native launcher

`AlgoArchive.exe` is a small GUI-subsystem launcher for the packaged
`start.bat`. It resolves the script relative to its own directory, forwards
command-line arguments, and embeds `ACM-ICPC-Windows.ico`. It is statically
linked against the MinGW C and C++ runtimes, so the packaged launcher does not
require compiler DLLs on the user's computer.

Build with MinGW-w64:

```powershell
.\launcher\build-launcher.ps1 -Version 2.2.5
```
