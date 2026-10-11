# SmartSort Browser Lab: application-local Python, no pip/admin required.
[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'SmartSortBrowserLab'),
    [ValidateRange(1024,65535)][int]$Port = 8001,
    [switch]$Offline,
    [switch]$NoBrowser,
    [switch]$NoShortcut,
    [switch]$Stop
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$repoBase = 'https://raw.githubusercontent.com/buide03/smartsort-colab-lab/main'
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$statePath = Join-Path $InstallRoot 'server.json'
$cacheManifest = Join-Path $InstallRoot 'release.json'
$url = "http://127.0.0.1:$Port/"

function Write-Step([string]$Message) { Write-Host $Message -ForegroundColor Cyan }
function Read-Status {
    try { return Invoke-RestMethod -Uri ($url+'smartsort-status') -TimeoutSec 2 -UseBasicParsing }
    catch { return $null }
}
function Stop-OwnedServer {
    if (!(Test-Path -LiteralPath $statePath)) { return }
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$state.pid)" -ErrorAction SilentlyContinue
    if ($process -and $process.ExecutablePath -eq $state.python -and $process.CommandLine.Contains($state.server)) {
        Stop-Process -Id ([int]$state.pid) -ErrorAction Stop
        Write-Host 'Da dung SmartSort. Du lieu trong trinh duyet van duoc giu.'
    }
}
function Download-Checked([string]$Address,[string]$Destination,[string]$Hash) {
    if (Test-Path -LiteralPath $Destination) {
        if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -eq $Hash) { return }
    }
    if ($Offline) { throw 'Thieu file cai dat offline. Chay lan dau khi co Internet.' }
    Invoke-WebRequest -Uri $Address -OutFile $Destination -UseBasicParsing -TimeoutSec 180
    if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -ne $Hash) {
        throw 'File tai ve khong dung ma kiem tra. Chua chay file nay. Hay thu lai.'
    }
}
function Expand-Checked([string]$Archive,[string]$Destination) {
    # Every ZIP entry must remain in this exact destination before extraction.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $target = [IO.Path]::GetFullPath($Destination).TrimEnd('\')+'\'
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        foreach ($entry in $zip.Entries) {
            $resolved = [IO.Path]::GetFullPath((Join-Path $target $entry.FullName))
            if (!$resolved.StartsWith($target,[StringComparison]::OrdinalIgnoreCase)) { throw 'ZIP co duong dan khong an toan.' }
        }
    } finally { $zip.Dispose() }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Expand-Archive -LiteralPath $Archive -DestinationPath $Destination -Force
}

$mutex = New-Object Threading.Mutex($false,"Local\SmartSortBrowser-$env:USERNAME-$Port")
$owned = $false
try {
    $owned = $mutex.WaitOne(0)
    if (!$owned) { throw 'SmartSort dang khoi dong trong cua so khac. Cho mot chut roi thu lai.' }
    if ($Stop) { Stop-OwnedServer; return }
    if (![Environment]::Is64BitOperatingSystem) { throw 'Launcher nay can Windows 10/11 64-bit.' }
    New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    Write-Step '[1/4] Kiem tra bo cai SmartSort...'
    $manifest = $null
    if (!$Offline) {
        try { $manifest = Invoke-RestMethod -Uri ($repoBase+'/student/release.json') -UseBasicParsing -TimeoutSec 30 }
        catch { if (!(Test-Path -LiteralPath $cacheManifest)) { throw 'Chua tai duoc SmartSort. Kiem tra Internet/GitHub roi chay lai.' } }
    }
    if (!$manifest) { $manifest = Get-Content -LiteralPath $cacheManifest -Raw | ConvertFrom-Json }
    if ($manifest.version -notmatch '^[a-f0-9]{16}$' -or $manifest.bundle -notmatch '^student/SmartSort_Browser_[a-f0-9]{16}\.zip$' -or $manifest.sha256 -notmatch '^[a-f0-9]{64}$') {
        throw 'Thong tin bo cai khong hop le.'
    }
    $architecture = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') { 'arm64' } else { 'amd64' }
    $runtime = Join-Path $InstallRoot ('python-3.13.16-'+$architecture)
    $python = Join-Path $runtime 'python.exe'
    $pythonHash = if ($architecture -eq 'arm64') { '790d097697a2020477549a6764d89d22194c88d6e42caebcb2db63791e004c94' } else { '97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297' }
    $downloads = Join-Path $InstallRoot 'downloads'
    New-Item -ItemType Directory -Path $downloads -Force | Out-Null
    Write-Step '[2/4] Chuan bi Python rieng cho lab (khong can cai thu vien)...'
    if (!(Test-Path -LiteralPath $python)) {
        $pythonZip = Join-Path $downloads ('python-3.13.16-'+$architecture+'.zip')
        Download-Checked "https://www.python.org/ftp/python/3.13.16/python-3.13.16-embed-$architecture.zip" $pythonZip $pythonHash
        Expand-Checked $pythonZip $runtime
    }
    & $python -c 'import http.server, json'
    if ($LASTEXITCODE -ne 0) { throw 'Python chua chay duoc. Kiem tra Windows va quyen chay phan mem cua nha truong.' }
    Write-Step '[3/4] Tai giao dien va mo hinh chay tren trinh duyet...'
    $bundleZip = Join-Path $downloads ([IO.Path]::GetFileName($manifest.bundle))
    $application = Join-Path (Join-Path $InstallRoot 'versions') $manifest.version
    Download-Checked ($repoBase+'/'+$manifest.bundle) $bundleZip $manifest.sha256
    Expand-Checked $bundleZip $application
    $server = Join-Path $application 'run_browser_lab.py'
    if (!(Test-Path -LiteralPath $server)) { throw 'Bo cai thieu file chay.' }
    $manifest | ConvertTo-Json | Set-Content -LiteralPath $cacheManifest -Encoding UTF8
    Write-Step '[4/4] Khoi dong phong thuc hanh...'
    $status = Read-Status
    if ($status -and $status.application -eq 'smartsort-browser-lab' -and $status.version -ne $manifest.version) {
        Stop-OwnedServer
        Start-Sleep -Milliseconds 500
        $status = Read-Status
    }
    if (!$status) {
        $stdout = Join-Path $InstallRoot 'server-output.log'
        $stderr = Join-Path $InstallRoot 'server-error.log'
        $process = Start-Process -FilePath $python -ArgumentList @('-u',('"'+$server+'"'),'--port',"$Port") -WorkingDirectory $application -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        @{ pid=$process.Id; python=$python; server=$server; port=$Port } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
        for ($attempt=0; $attempt -lt 40; $attempt++) {
            Start-Sleep -Milliseconds 250
            $status = Read-Status
            if ($status) { break }
            if ($process.HasExited) { throw "Server chua chay duoc. Xem file: $stderr. Cong $Port co the dang bi ung dung khac su dung." }
        }
    }
    if (!$status -or $status.application -ne 'smartsort-browser-lab' -or $status.version -ne $manifest.version) {
        throw "Cong $Port dang co ung dung/ban lab khac. Dong ban do roi chay lai; giu nguyen cong de giu phien hoc."
    }
    if (!$NoShortcut) {
        $desktop = [Environment]::GetFolderPath('DesktopDirectory')
        if ($desktop) {
            $shell = New-Object -ComObject WScript.Shell
            foreach ($item in @(@{name='SmartSort Lab';extra=''},@{name='Dung SmartSort Lab';extra=' -Stop'})) {
                $shortcut = $shell.CreateShortcut((Join-Path $desktop ($item.name+'.lnk')))
                $shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
                $shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $application 'start-student.ps1')+'" -InstallRoot "'+$InstallRoot+'" -Port '+$Port+$item.extra
                $shortcut.WorkingDirectory = $InstallRoot
                $shortcut.Description = 'SmartSort - Train Colab, validation/test trong trinh duyet'
                $shortcut.Save()
            }
        }
    }
    Write-Host "SAN SANG: $url" -ForegroundColor Green
    Write-Host 'Lan sau bam SmartSort Lab tren Desktop. Nho Sao luu phien truoc khi doi may.'
    if (!$NoBrowser) { Start-Process $url }
} catch {
    Write-Host ('KHONG KHOI DONG DUOC: '+$_.Exception.Message) -ForegroundColor Red
    throw
} finally {
    if ($owned) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
