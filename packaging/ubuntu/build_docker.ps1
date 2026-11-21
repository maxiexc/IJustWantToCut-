[CmdletBinding()]
param(
    [string]$Version = "",
    [switch]$Verify
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$DistDir = Join-Path $RepoRoot "dist"
$Dockerfile = Join-Path $RepoRoot "packaging\ubuntu\Dockerfile"
$VerifyScript = Join-Path $RepoRoot "packaging\ubuntu\verify_deb.sh"

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

$env:DOCKER_BUILDKIT = "1"

$buildArgs = @(
    "build",
    "--target", "export",
    "--output", "type=local,dest=$DistDir",
    "-f", $Dockerfile
)

if (-not [string]::IsNullOrWhiteSpace($Version)) {
    $buildArgs += @("--build-arg", "APP_VERSION=$Version")
}

$buildArgs += $RepoRoot

Write-Host "==> Building Ubuntu .deb via Docker (Ubuntu 22.04 builder)..."
& docker @buildArgs
if ($LASTEXITCODE -ne 0) {
    throw "Docker build failed with exit code $LASTEXITCODE"
}

Write-Host "==> Build output in ${DistDir}:"
Get-ChildItem -Path $DistDir -Filter "ijustwanttocut_*.deb*" | Format-Table Name, Length, LastWriteTime

if ($Verify) {
    foreach ($ubuntuVer in @("22.04", "24.04", "26.04")) {
        Write-Host "==> Verifying .deb inside ubuntu:${ubuntuVer}..."
        & docker run --rm `
            -v "${DistDir}:/pkg:ro" `
            -v "${VerifyScript}:/verify.sh:ro" `
            "ubuntu:${ubuntuVer}" `
            bash /verify.sh
        if ($LASTEXITCODE -ne 0) {
            throw "Verification failed on ubuntu:${ubuntuVer} with exit code $LASTEXITCODE"
        }
    }
}
