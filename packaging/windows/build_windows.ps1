[CmdletBinding()]
param(
    [string]$Version = "",
    [string]$PythonExe = "python",
    [string]$CacheDir = "",
    [switch]$UseLocalFfmpeg,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$DistDir = Join-Path $RepoRoot "dist"
$BuildWorkDir = Join-Path $RepoRoot "build\pyinstaller-win"
$RuntimeDir = Join-Path $RepoRoot "build\win_runtime"
$SpecFile = Join-Path $RepoRoot "packaging\windows\IJustWantToCut.spec"
$IssFile = Join-Path $RepoRoot "packaging\windows\IJustWantToCut.iss"
$IconFile = Join-Path $RepoRoot "packaging\assets\ijustwanttocut.ico"
$FetchScript = Join-Path $RepoRoot "packaging\windows\fetch_deps.ps1"

if ([string]::IsNullOrWhiteSpace($Version)) {
    Push-Location $RepoRoot
    try {
        $Version = (& $PythonExe -c "import version; print(version.APP_VERSION)").Trim()
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to resolve APP_VERSION from version.py"
        }
    } finally {
        Pop-Location
    }
}

$Version = $Version.Trim() -replace "^v", ""
if ([string]::IsNullOrWhiteSpace($Version)) {
    throw "Resolved version string is empty."
}

# Build numeric 4-part version (X.Y.Z.W, each 0..65535) for Windows VersionInfo
if ($Version -match "^(\d+)\.(\d+)\.(\d+)(?:[^\d]+(\d+))?") {
    $vMajor = [Math]::Min([int]$Matches[1], 65535)
    $vMinor = [Math]::Min([int]$Matches[2], 65535)
    $vPatch = [Math]::Min([int]$Matches[3], 65535)
    $vBuild = if ($Matches[4]) { [Math]::Min([int]$Matches[4], 65535) } else { 0 }
    $NumericVersion = "${vMajor}.${vMinor}.${vPatch}.${vBuild}"
} else {
    $NumericVersion = "0.1.0.0"
}

Write-Host "==> Building IJustWantToCut for Windows (Version=$Version, Numeric=$NumericVersion)"

# 1. Fetch/stage FFmpeg + VLC + Licenses
$fetchParams = @{
    OutDir = $RuntimeDir
}
if (-not [string]::IsNullOrWhiteSpace($CacheDir)) {
    $fetchParams["CacheDir"] = $CacheDir
}
if ($UseLocalFfmpeg) {
    $fetchParams["UseLocalFfmpeg"] = $true
}
& $FetchScript @fetchParams

# 2. Run PyInstaller onedir build
$BundleDir = Join-Path $DistDir "IJustWantToCut"
if (Test-Path -LiteralPath $BuildWorkDir) {
    Remove-Item -LiteralPath $BuildWorkDir -Recurse -Force
}
if (Test-Path -LiteralPath $BundleDir) {
    Remove-Item -LiteralPath $BundleDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

Write-Host "==> Running PyInstaller..."
& $PythonExe -m PyInstaller --noconfirm --clean `
    --workpath $BuildWorkDir `
    --distpath $DistDir `
    $SpecFile
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

# 3. Copy FFmpeg, VLC, and Licenses into onedir bundle
Write-Host "==> Assembling bundled runtimes into $BundleDir..."
foreach ($folder in @("bin", "vlc", "LICENSES")) {
    $src = Join-Path $RuntimeDir $folder
    $dst = Join-Path $BundleDir $folder
    if (Test-Path -LiteralPath $dst) {
        Remove-Item -LiteralPath $dst -Recurse -Force
    }
    Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force
}

# 4. Sanity checks on staged bundle
$requiredPaths = @(
    (Join-Path $BundleDir "IJustWantToCut.exe"),
    (Join-Path $BundleDir "bin\ffmpeg.exe"),
    (Join-Path $BundleDir "bin\ffprobe.exe"),
    (Join-Path $BundleDir "vlc\libvlc.dll"),
    (Join-Path $BundleDir "vlc\libvlccore.dll"),
    (Join-Path $BundleDir "vlc\plugins"),
    (Join-Path $BundleDir "LICENSES\README-LICENSES.txt")
)
foreach ($req in $requiredPaths) {
    if (-not (Test-Path -LiteralPath $req)) {
        throw "Required bundle path is missing: $req"
    }
}

$qwindows = Get-ChildItem -Path (Join-Path $BundleDir "_internal") -Recurse -File -Filter "qwindows.dll" | Select-Object -First 1
if (-not $qwindows) {
    throw "Qt Windows platform plugin (qwindows.dll) not found in bundle!"
}
Write-Host "==> Found Qt platform plugin: $($qwindows.FullName)"

$vlcPluginDlls = Get-ChildItem -Path (Join-Path $BundleDir "vlc\plugins") -Recurse -File -Filter "*.dll"
if ($vlcPluginDlls.Count -lt 10) {
    throw "Expected VLC plugin DLLs in vlc\plugins, found only $($vlcPluginDlls.Count)"
}
Write-Host "==> Found $($vlcPluginDlls.Count) VLC plugin DLLs."

function Write-Sha256File {
    param([string]$FilePath)
    $hash = (Get-FileHash -LiteralPath $FilePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $fileName = [System.IO.Path]::GetFileName($FilePath)
    $shaPath = "${FilePath}.sha256"
    [System.IO.File]::WriteAllText(
        $shaPath,
        "${hash}  ${fileName}`n",
        (New-Object System.Text.UTF8Encoding($false))
    )
}

# 5. Create Portable Zip archive
$PortableName = "IJustWantToCut-${Version}-win64-portable.zip"
$PortablePath = Join-Path $DistDir $PortableName
if (Test-Path -LiteralPath $PortablePath) {
    Remove-Item -LiteralPath $PortablePath -Force
}

Write-Host "==> Creating portable archive: $PortablePath"
$sevenZip = Get-Command 7z.exe -ErrorAction SilentlyContinue
if (-not $sevenZip) {
    $default7z = Join-Path $env:ProgramFiles "7-Zip\7z.exe"
    if (Test-Path -LiteralPath $default7z) {
        $sevenZip = Get-Item -LiteralPath $default7z
    }
}

if ($sevenZip) {
    $exe7z = if ($sevenZip.PSObject.Properties["Source"]) { $sevenZip.Source } else { $sevenZip.FullName }
    Push-Location $DistDir
    try {
        & $exe7z a -tzip -mx=9 $PortableName "IJustWantToCut" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "7z archive creation failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
} else {
    Compress-Archive -Path $BundleDir -DestinationPath $PortablePath -CompressionLevel Optimal
}

Write-Sha256File -FilePath $PortablePath

# 6. Compile Inno Setup single-file installer
if (-not $SkipInstaller) {
    $isccExe = $null
    $isccCmd = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($isccCmd) {
        $isccExe = $isccCmd.Source
    } else {
        foreach ($candidate in @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
        )) {
            if (Test-Path -LiteralPath $candidate) {
                $isccExe = $candidate
                break
            }
        }
    }

    if (-not $isccExe) {
        throw "Inno Setup compiler (ISCC.exe) not found. Install Inno Setup 6 or pass -SkipInstaller."
    }

    $SetupBaseName = "IJustWantToCut-${Version}-win64-setup"
    $SetupPath = Join-Path $DistDir "${SetupBaseName}.exe"
    if (Test-Path -LiteralPath $SetupPath) {
        Remove-Item -LiteralPath $SetupPath -Force
    }

    Write-Host "==> Compiling Inno Setup installer using $isccExe ..."
    & $isccExe `
        "/DAppVersion=$Version" `
        "/DAppNumericVersion=$NumericVersion" `
        "/DSourceDir=$BundleDir" `
        "/DOutputDir=$DistDir" `
        "/DOutputBaseFilename=$SetupBaseName" `
        "/DIconFile=$IconFile" `
        $IssFile
    if ($LASTEXITCODE -ne 0) {
        throw "ISCC.exe failed with exit code $LASTEXITCODE"
    }

    if (-not (Test-Path -LiteralPath $SetupPath)) {
        throw "Expected installer not found at $SetupPath"
    }

    Write-Sha256File -FilePath $SetupPath
}

Write-Host "==> Windows build artifacts in ${DistDir}:"
Get-ChildItem -Path $DistDir -File -Filter "IJustWantToCut-*" | Format-Table Name, Length, LastWriteTime
