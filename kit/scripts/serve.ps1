# serve.ps1 - (re)start the Rojo server for this project.
# Double-click or run from PowerShell. Keep the window open while working in Studio.
# If Studio says "Couldn't connect to the Rojo server", it means this isn't running.
$env:PATH = "$HOME\.rokit\bin;$env:PATH"
Set-Location $PSScriptRoot\..
rojo serve default.project.json --port 34872
