[CmdletBinding()]
param(
    [string]$DistDir = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if ([string]::IsNullOrWhiteSpace($DistDir)) {
    $DistDir = Join-Path $RepoRoot "dist"
}
$DistDir = (Resolve-Path $DistDir).Path

function Assert-Sha256 {
    param([string]$FilePath)
    $shaFile = "${FilePath}.sha256"
    if (-not (Test-Path -LiteralPath $shaFile)) {
        throw "Missing checksum file: $shaFile"
    }
    $expected = ((Get-Content -LiteralPath $shaFile -Raw).Trim() -split "\s+")[0].ToLowerInvariant()
    $actual = (Get-FileHash -LiteralPath $FilePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($expected -ne $actual) {
        throw "SHA256 mismatch for ${FilePath}: expected $expected, got $actual"
    }
    Write-Host "==> SHA256 OK: $([System.IO.Path]::GetFileName($FilePath))"
}

function Invoke-GuiProcess {
    param(
        [string]$ExePath,
        [string[]]$Arguments,
        [int]$TimeoutSeconds = 60
    )

    $tmpBase = Join-Path ([System.IO.Path]::GetTempPath()) ("ijwtc_proc_" + [System.Guid]::NewGuid().ToString("N"))
    $stdoutFile = "${tmpBase}.out.txt"
    $stderrFile = "${tmpBase}.err.txt"

    try {
        $proc = Start-Process `
            -FilePath $ExePath `
            -ArgumentList $Arguments `
            -RedirectStandardOutput $stdoutFile `
            -RedirectStandardError $stderrFile `
            -NoNewWindow `
            -PassThru

        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            try { $proc.Kill() } catch {}
            $outPartial = if (Test-Path $stdoutFile) { Get-Content -LiteralPath $stdoutFile -Raw } else { "" }
            $errPartial = if (Test-Path $stderrFile) { Get-Content -LiteralPath $stderrFile -Raw } else { "" }
            throw "Process timed out after ${TimeoutSeconds}s: $ExePath $($Arguments -join ' ')`nSTDOUT:`n$outPartial`nSTDERR:`n$errPartial"
        }

        $proc.WaitForExit()
        $stdout = if (Test-Path $stdoutFile) { Get-Content -LiteralPath $stdoutFile -Raw } else { "" }
        $stderr = if (Test-Path $stderrFile) { Get-Content -LiteralPath $stderrFile -Raw } else { "" }
        return @{
            ExitCode = $proc.ExitCode
            StdOut   = if ($null -eq $stdout) { "" } else { $stdout }
            StdErr   = if ($null -eq $stderr) { "" } else { $stderr }
        }
    } finally {
        Remove-Item -LiteralPath $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue
    }
}

function Assert-AppBundleWorks {
    param(
        [string]$AppDir,
        [string]$Label
    )

    $exePath = Join-Path $AppDir "IJustWantToCut.exe"
    $ffmpegPath = Join-Path $AppDir "bin\ffmpeg.exe"
    $ffprobePath = Join-Path $AppDir "bin\ffprobe.exe"
    $libVlcPath = Join-Path $AppDir "vlc\libvlc.dll"

    foreach ($p in @($exePath, $ffmpegPath, $ffprobePath, $libVlcPath)) {
        if (-not (Test-Path -LiteralPath $p)) {
            throw "[$Label] Missing expected file: $p"
        }
    }

    Write-Host "==> [$Label] Checking --version..."
    $verRes = Invoke-GuiProcess -ExePath $exePath -Arguments @("--version")
    Write-Host $verRes.StdOut.Trim()
    if ($verRes.ExitCode -ne 0 -or $verRes.StdOut.Trim() -notmatch "^IJustWantToCut\s+") {
        throw "[$Label] --version failed (exit=$($verRes.ExitCode)): stdout='$($verRes.StdOut)' stderr='$($verRes.StdErr)'"
    }

    Write-Host "==> [$Label] Checking bundled FFmpeg libx265 encoder..."
    $encOut = (& $ffmpegPath -hide_banner -encoders 2>&1) | Out-String
    if ($LASTEXITCODE -ne 0 -or $encOut -notmatch "libx265") {
        throw "[$Label] Bundled ffmpeg.exe does not report libx265 encoder!"
    }

    Write-Host "==> [$Label] Running --smoke-test..."
    $smokeRes = Invoke-GuiProcess -ExePath $exePath -Arguments @("--smoke-test")
    Write-Host $smokeRes.StdOut.Trim()
    if (-not [string]::IsNullOrWhiteSpace($smokeRes.StdErr)) {
        Write-Host "STDERR: $($smokeRes.StdErr.Trim())"
    }
    if ($smokeRes.ExitCode -ne 0 -or $smokeRes.StdOut -notmatch "\[SMOKE-TEST\] OK") {
        throw "[$Label] --smoke-test failed (exit=$($smokeRes.ExitCode))"
    }

    # Verify all resolved tools come from inside $AppDir (self-contained, not host tools)
    $normAppDir = [System.IO.Path]::GetFullPath($AppDir).TrimEnd("\").ToLowerInvariant()
    foreach ($key in @("ffmpeg", "ffprobe", "vlc_lib", "vlc_plugins")) {
        if ($smokeRes.StdOut -match "(?m)^\[SMOKE-TEST\] ${key}=(.+)$") {
            $resolved = $Matches[1].Trim()
            $normResolved = [System.IO.Path]::GetFullPath($resolved).ToLowerInvariant()
            if (-not $normResolved.StartsWith($normAppDir)) {
                throw "[$Label] Expected $key inside $AppDir, but resolved to: $resolved"
            }
        } else {
            throw "[$Label] Missing [SMOKE-TEST] ${key}=... line in output"
        }
    }

    Write-Host "==> [$Label] PASSED!"
}

$portableZip = Get-ChildItem -Path $DistDir -File -Filter "IJustWantToCut-*-win64-portable.zip" | Select-Object -First 1
if (-not $portableZip) {
    throw "Portable zip not found in $DistDir"
}
Assert-Sha256 -FilePath $portableZip.FullName

$setupExe = Get-ChildItem -Path $DistDir -File -Filter "IJustWantToCut-*-win64-setup.exe" | Select-Object -First 1
if (-not $setupExe) {
    throw "Inno Setup installer not found in $DistDir"
}
Assert-Sha256 -FilePath $setupExe.FullName

$TestBase = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [System.IO.Path]::GetTempPath() }
$PortableExtractDir = Join-Path $TestBase "IJustWantToCut Portable Test"
$InstallTestDir = Join-Path $TestBase "IJustWantToCut Install Test"

# 1. Verify Portable Zip (in a path containing spaces)
try {
    if (Test-Path -LiteralPath $PortableExtractDir) {
        Remove-Item -LiteralPath $PortableExtractDir -Recurse -Force
    }
    Write-Host "==> Extracting portable zip to: $PortableExtractDir"
    Expand-Archive -LiteralPath $portableZip.FullName -DestinationPath $PortableExtractDir -Force

    $portableAppDir = Join-Path $PortableExtractDir "IJustWantToCut"
    Assert-AppBundleWorks -AppDir $portableAppDir -Label "Portable Zip"
} finally {
    if (Test-Path -LiteralPath $PortableExtractDir) {
        Remove-Item -LiteralPath $PortableExtractDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# 2. Verify Inno Setup Installer (silent install -> smoke test -> silent uninstall)
try {
    if (Test-Path -LiteralPath $InstallTestDir) {
        Remove-Item -LiteralPath $InstallTestDir -Recurse -Force
    }

    Write-Host "==> Installing $($setupExe.Name) silently to: $InstallTestDir"
    $installArgs = @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CURRENTUSER",
        "/DIR=`"$InstallTestDir`""
    )
    $installProc = Start-Process -FilePath $setupExe.FullName -ArgumentList $installArgs -Wait -PassThru
    if ($installProc.ExitCode -ne 0) {
        throw "Silent install failed with exit code $($installProc.ExitCode)"
    }

    Assert-AppBundleWorks -AppDir $InstallTestDir -Label "Inno Setup Installed"

    $uninstaller = Join-Path $InstallTestDir "unins000.exe"
    if (-not (Test-Path -LiteralPath $uninstaller)) {
        throw "Uninstaller not found at $uninstaller"
    }

    Write-Host "==> Testing silent uninstall..."
    $uninstProc = Start-Process -FilePath $uninstaller -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Wait -PassThru
    if ($uninstProc.ExitCode -ne 0) {
        throw "Silent uninstall failed with exit code $($uninstProc.ExitCode)"
    }

    # Inno Setup uninstaller spawns a helper in %TEMP% to finish deleting itself
    $installedExe = Join-Path $InstallTestDir "IJustWantToCut.exe"
    for ($i = 0; $i -lt 30; $i++) {
        if (-not (Test-Path -LiteralPath $installedExe)) {
            break
        }
        Start-Sleep -Milliseconds 500
    }
    if (Test-Path -LiteralPath $installedExe) {
        throw "Uninstaller did not remove $installedExe"
    }
    Write-Host "==> Silent uninstall verified!"
} finally {
    if (Test-Path -LiteralPath $InstallTestDir) {
        Remove-Item -LiteralPath $InstallTestDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "==> ALL WINDOWS VERIFICATION CHECKS PASSED!"
