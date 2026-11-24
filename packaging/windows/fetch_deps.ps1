[CmdletBinding()]
param(
    [string]$CacheDir = "",
    [string]$OutDir = "",
    [string]$VlcVersion = "3.0.21",
    [switch]$UseLocalFfmpeg
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if ([string]::IsNullOrWhiteSpace($CacheDir)) {
    $CacheDir = Join-Path $RepoRoot "build\deps"
}
if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutDir = Join-Path $RepoRoot "build\win_runtime"
}

New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null

function Test-ZipFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -lt 1024) {
        return $false
    }
    $fs = [System.IO.File]::OpenRead($Path)
    try {
        $b0 = $fs.ReadByte()
        $b1 = $fs.ReadByte()
        return ($b0 -eq 0x50 -and $b1 -eq 0x4B)
    } finally {
        $fs.Dispose()
    }
}

function Invoke-DownloadFile {
    param(
        [string[]]$Urls,
        [string]$Destination
    )

    if (Test-ZipFile -Path $Destination) {
        Write-Host "==> Using cached archive: $Destination"
        return
    }

    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Force
    }

    $tmpPath = "$Destination.download"
    $curlCmd = Get-Command curl.exe -ErrorAction SilentlyContinue

    foreach ($url in $Urls) {
        Write-Host "==> Downloading $url ..."
        if (Test-Path -LiteralPath $tmpPath) {
            Remove-Item -LiteralPath $tmpPath -Force
        }

        $ok = $false
        if ($curlCmd) {
            & $curlCmd.Source -fSL --retry 3 --retry-delay 5 --connect-timeout 30 -o $tmpPath $url
            if ($LASTEXITCODE -eq 0 -and (Test-ZipFile -Path $tmpPath)) {
                $ok = $true
            }
        } else {
            try {
                Invoke-WebRequest -Uri $url -OutFile $tmpPath -UseBasicParsing
                if (Test-ZipFile -Path $tmpPath) {
                    $ok = $true
                }
            } catch {
                Write-Warning "Download failed from ${url}: $_"
            }
        }

        if ($ok) {
            Move-Item -LiteralPath $tmpPath -Destination $Destination -Force
            return
        }
        Write-Warning "Failed to download valid archive from $url"
    }

    throw "Unable to download archive to $Destination from any configured URL."
}

function Expand-ArchiveFast {
    param(
        [string]$ArchivePath,
        [string]$DestinationPath
    )

    if (Test-Path -LiteralPath $DestinationPath) {
        Remove-Item -LiteralPath $DestinationPath -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $DestinationPath | Out-Null

    $sevenZip = Get-Command 7z.exe -ErrorAction SilentlyContinue
    if (-not $sevenZip) {
        $default7z = Join-Path $env:ProgramFiles "7-Zip\7z.exe"
        if (Test-Path -LiteralPath $default7z) {
            $sevenZip = Get-Item -LiteralPath $default7z
        }
    }

    if ($sevenZip) {
        $exe = if ($sevenZip.PSObject.Properties["Source"]) { $sevenZip.Source } else { $sevenZip.FullName }
        & $exe x -y "-o$DestinationPath" $ArchivePath | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "7z extraction failed for $ArchivePath (exit code $LASTEXITCODE)"
        }
    } else {
        Expand-Archive -LiteralPath $ArchivePath -DestinationPath $DestinationPath -Force
    }
}

# Clean output directory
if (Test-Path -LiteralPath $OutDir) {
    Remove-Item -LiteralPath $OutDir -Recurse -Force
}

$BinOut = Join-Path $OutDir "bin"
$VlcOut = Join-Path $OutDir "vlc"
$LicOut = Join-Path $OutDir "LICENSES"
New-Item -ItemType Directory -Force -Path $BinOut, $VlcOut, $LicOut | Out-Null

$TmpRoot = Join-Path $RepoRoot "build\tmp_win_deps"
if (Test-Path -LiteralPath $TmpRoot) {
    Remove-Item -LiteralPath $TmpRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $TmpRoot | Out-Null

try {
    # 1. Fetch and extract VLC 64-bit runtime
    $vlcZip = Join-Path $CacheDir "vlc-${VlcVersion}-win64.zip"
    $vlcUrls = @(
        "https://download.videolan.org/pub/videolan/vlc/${VlcVersion}/win64/vlc-${VlcVersion}-win64.zip",
        "https://get.videolan.org/vlc/${VlcVersion}/win64/vlc-${VlcVersion}-win64.zip"
    )
    Invoke-DownloadFile -Urls $vlcUrls -Destination $vlcZip

    $vlcExtractDir = Join-Path $TmpRoot "vlc"
    Write-Host "==> Extracting VLC ${VlcVersion}..."
    Expand-ArchiveFast -ArchivePath $vlcZip -DestinationPath $vlcExtractDir

    $libVlcFile = Get-ChildItem -Path $vlcExtractDir -Recurse -File -Filter "libvlc.dll" | Select-Object -First 1
    if (-not $libVlcFile) {
        throw "Could not find libvlc.dll inside $vlcZip"
    }
    $vlcSourceDir = $libVlcFile.Directory.FullName
    $libVlcCoreFile = Join-Path $vlcSourceDir "libvlccore.dll"
    $vlcPluginsSource = Join-Path $vlcSourceDir "plugins"

    if (-not (Test-Path -LiteralPath $libVlcCoreFile)) {
        throw "Could not find libvlccore.dll beside libvlc.dll in $vlcSourceDir"
    }
    if (-not (Test-Path -LiteralPath $vlcPluginsSource)) {
        throw "Could not find plugins directory in $vlcSourceDir"
    }

    Copy-Item -LiteralPath $libVlcFile.FullName -Destination (Join-Path $VlcOut "libvlc.dll") -Force
    Copy-Item -LiteralPath $libVlcCoreFile -Destination (Join-Path $VlcOut "libvlccore.dll") -Force
    Copy-Item -LiteralPath $vlcPluginsSource -Destination (Join-Path $VlcOut "plugins") -Recurse -Force

    # Prune non-playback VLC plugin subdirectories to reduce package size safely
    $prunedPluginDirs = @(
        "gui",
        "lua",
        "skins2",
        "visualization",
        "services_discovery",
        "stream_out",
        "mux",
        "access_output",
        "control",
        "notify"
    )
    foreach ($sub in $prunedPluginDirs) {
        $target = Join-Path (Join-Path $VlcOut "plugins") $sub
        if (Test-Path -LiteralPath $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
        }
    }

    foreach ($licName in @("COPYING.txt", "COPYING.LIB.txt")) {
        $srcLic = Join-Path $vlcSourceDir $licName
        if (Test-Path -LiteralPath $srcLic) {
            Copy-Item -LiteralPath $srcLic -Destination (Join-Path $LicOut "VLC-$licName") -Force
        }
    }

    # 2. Fetch and extract FFmpeg (ffmpeg.exe + ffprobe.exe only)
    $localFfmpeg = Join-Path $RepoRoot "ffmpeg.exe"
    $localFfprobe = Join-Path $RepoRoot "ffprobe.exe"
    if ($UseLocalFfmpeg -and (Test-Path -LiteralPath $localFfmpeg) -and (Test-Path -LiteralPath $localFfprobe)) {
        Write-Host "==> Using local ffmpeg.exe and ffprobe.exe from repository root..."
        Copy-Item -LiteralPath $localFfmpeg -Destination (Join-Path $BinOut "ffmpeg.exe") -Force
        Copy-Item -LiteralPath $localFfprobe -Destination (Join-Path $BinOut "ffprobe.exe") -Force
    } else {
        $ffmpegZip = Join-Path $CacheDir "ffmpeg-win64-essentials.zip"
        $ffmpegUrls = @(
            "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        )
        Invoke-DownloadFile -Urls $ffmpegUrls -Destination $ffmpegZip

        $ffmpegExtractDir = Join-Path $TmpRoot "ffmpeg"
        Write-Host "==> Extracting FFmpeg..."
        Expand-ArchiveFast -ArchivePath $ffmpegZip -DestinationPath $ffmpegExtractDir

        $ffmpegExe = Get-ChildItem -Path $ffmpegExtractDir -Recurse -File -Filter "ffmpeg.exe" | Select-Object -First 1
        $ffprobeExe = Get-ChildItem -Path $ffmpegExtractDir -Recurse -File -Filter "ffprobe.exe" | Select-Object -First 1
        if (-not $ffmpegExe -or -not $ffprobeExe) {
            throw "Could not find ffmpeg.exe and ffprobe.exe inside $ffmpegZip"
        }

        Copy-Item -LiteralPath $ffmpegExe.FullName -Destination (Join-Path $BinOut "ffmpeg.exe") -Force
        Copy-Item -LiteralPath $ffprobeExe.FullName -Destination (Join-Path $BinOut "ffprobe.exe") -Force

        $ffmpegLic = Get-ChildItem -Path $ffmpegExtractDir -Recurse -File |
            Where-Object { $_.Name -match "^LICENSE(\.txt)?$" } |
            Select-Object -First 1
        if ($ffmpegLic) {
            Copy-Item -LiteralPath $ffmpegLic.FullName -Destination (Join-Path $LicOut "FFMPEG-LICENSE.txt") -Force
        }
    }

    # 3. Write third-party license summary
    $licenseSummary = @"
IJustWantToCut - Third-Party Software and License Notices
=========================================================

1. IJustWantToCut
   License: MIT License
   Source:  https://github.com/maxiexc/IJustWantToCut-

2. PySide6 / shiboken6 (Qt for Python 6.5.3)
   License: GNU Lesser General Public License v3.0 (LGPL-3.0)
   Source:  https://code.qt.io/cgit/pyside/pyside-setup.git/
   Note:    Dynamically linked in onedir distribution.

3. VLC / libVLC ($VlcVersion, win64)
   License: GNU Lesser General Public License v2.1+ (LGPL-2.1+) / GPL-2.0+
   Source:  https://download.videolan.org/pub/videolan/vlc/$VlcVersion/
   Note:    See VLC-COPYING.txt and VLC-COPYING.LIB.txt in this directory.

4. FFmpeg / FFprobe (with libx265)
   License: GNU General Public License v2.0+ / v3.0 (GPL)
   Source:  https://ffmpeg.org/download.html
   Builds:  https://www.gyan.dev/ffmpeg/builds/
            https://github.com/BtbN/FFmpeg-Builds
   Note:    Invoked as standalone external executables (bin/ffmpeg.exe, bin/ffprobe.exe).
            See FFMPEG-LICENSE.txt in this directory when bundled.
"@
    [System.IO.File]::WriteAllText(
        (Join-Path $LicOut "README-LICENSES.txt"),
        $licenseSummary.Replace("`r`n", "`n"),
        (New-Object System.Text.UTF8Encoding($false))
    )

    Write-Host "==> Windows runtime dependencies staged successfully at: $OutDir"
} finally {
    if (Test-Path -LiteralPath $TmpRoot) {
        Remove-Item -LiteralPath $TmpRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
