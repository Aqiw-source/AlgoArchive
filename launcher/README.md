# AlgoArchive native launcher

`AlgoArchive.exe` is a small GUI-subsystem launcher for the packaged
`start.bat`. It resolves the script relative to its own directory, forwards
command-line arguments, and embeds `ACM-ICPC-Windows.ico`.

Build with MinGW-w64:

```powershell
.\launcher\build-launcher.ps1 -Version 2.2.3
```
