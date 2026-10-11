# Run under Windows PowerShell 5.1; use an isolated installation, not student data.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $repo 'start-student.ps1'
$installation = Join-Path $PSScriptRoot ('runtime/student launcher '+[Guid]::NewGuid().ToString('N'))
$labPort = 18021
try {
    & $launcher -InstallRoot $installation -Port $labPort -NoBrowser -NoShortcut
    $state = Get-Content -LiteralPath (Join-Path $installation 'server.json') -Raw | ConvertFrom-Json
    $status = Invoke-RestMethod "http://127.0.0.1:$labPort/smartsort-status" -UseBasicParsing
    if ($status.application -ne 'smartsort-browser-lab') { throw 'Wrong application.' }
    $index = Invoke-WebRequest "http://127.0.0.1:$labPort/" -UseBasicParsing
    if (!$index.Content.Contains('BROWSER LAB')) { throw 'Missing student UI.' }
    $module = Invoke-WebRequest "http://127.0.0.1:$labPort/vendor/ort-wasm-simd-threaded.mjs" -UseBasicParsing
    if ($module.Headers['Content-Type'] -ne 'application/javascript') { throw 'Wrong module MIME type.' }
    & $launcher -InstallRoot $installation -Port $labPort -Offline -NoBrowser -NoShortcut
    $again = Get-Content -LiteralPath (Join-Path $installation 'server.json') -Raw | ConvertFrom-Json
    if ($again.pid -ne $state.pid) { throw 'Repeated launch created another server.' }
    $listeners = Get-NetTCPConnection -LocalPort $labPort -State Listen
    if ($listeners.LocalAddress -ne '127.0.0.1') { throw 'Server exposed beyond localhost.' }
    & $launcher -InstallRoot $installation -Port $labPort -Stop
    Start-Sleep -Milliseconds 500
    if (Get-Process -Id $state.pid -ErrorAction SilentlyContinue) { throw 'Owned server was not stopped.' }
    & $launcher -InstallRoot $installation -Port $labPort -Offline -NoBrowser -NoShortcut
    Write-Host 'PASS: clean portable install, static UI, WASM MIME, offline repeat/restart and safe stop.'
} finally {
    & $launcher -InstallRoot $installation -Port $labPort -Stop
}
