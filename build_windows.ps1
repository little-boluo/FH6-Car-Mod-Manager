param([switch]$ManagerOnly)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
# Show Python output as it happens (and keep it in the transcript if the build is interrupted).
$env:PYTHONUNBUFFERED = '1'
if ($env:OS -ne 'Windows_NT') { throw 'Build this project on Windows 10/11 x64.' }
Start-Transcript -Path (Join-Path $PSScriptRoot 'build-windows.log') -Force
# Native programs' console output does not always reach the transcript; these lines always do.
function Step([string]$message) { Write-Host "==> $message" -ForegroundColor Cyan }
try {
    if (!$ManagerOnly) {
        Step 'Checking .NET SDK'
        if (!(Get-Command dotnet -ErrorAction SilentlyContinue)) {
            throw 'dotnet was not found. Install .NET 9 SDK x64 and Visual Studio 2022 Build Tools with Windows App SDK / desktop development support, then retry.'
        }
        $sdks = @(& dotnet --list-sdks)
        Write-Host ('Installed .NET SDKs: ' + $(if ($sdks.Count) { $sdks -join '; ' } else { 'none' }))
        if (!($sdks | Where-Object { $_ -match '^(\d+)\.' -and [int]$Matches[1] -ge 9 })) {
            throw 'No .NET 9 (or newer) SDK is installed; only runtimes were found. Install .NET 9 SDK x64, then retry.'
        }
    }
    Step 'Creating Python build environment'
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .build-venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .build-venv
    } else {
        throw 'Install 64-bit Python 3.12 with Tcl/Tk and the Python launcher, then retry.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python build environment.' }
    $pythonExe = Join-Path $PSScriptRoot '.build-venv\Scripts\python.exe'
    Step 'Checking source files and Python'
    & $pythonExe (Join-Path $PSScriptRoot 'build_checks.py') sources
    if ($LASTEXITCODE -ne 0) { throw 'Source package incomplete. Download and extract the complete ZIP into a new folder.' }
    & $pythonExe (Join-Path $PSScriptRoot 'build_checks.py') validate
    if ($LASTEXITCODE -ne 0) { throw 'Python/Tk validation failed.' }
    Step 'Installing build dependencies'
    & $pythonExe -m pip install --disable-pip-version-check -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'Cannot download PyInstaller. Check network/proxy settings.' }
    Step 'Running tests (about 40 seconds)'
    & $pythonExe (Join-Path $PSScriptRoot 'build_checks.py') tests
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed; refusing to package. Full details: test-results.log' }
    Write-Host 'Tests passed.'
    Step 'Building the manager (PyInstaller)'
    & $pythonExe -m PyInstaller --noconfirm --clean --windowed --onedir --noupx --name FH6CarModManager app.py
    if ($LASTEXITCODE -ne 0) { throw 'Manager build failed.' }
    $output = Join-Path $PSScriptRoot 'dist\FH6CarModManager'
    Step 'Checking the packaged manager'
    & $pythonExe (Join-Path $PSScriptRoot 'build_checks.py') smoke (Join-Path $output 'FH6CarModManager.exe')
    if ($LASTEXITCODE -ne 0) { throw 'Packaged EXE/Tk grid smoke test failed.' }
    if (!$ManagerOnly) {
        $project = Join-Path $PSScriptRoot 'vendor\ForzaTechStudio\ForzaTechStudio\FH6ThumbnailRenderer.csproj'
        $rendererOutput = Join-Path $output 'renderer'
        if (Test-Path $rendererOutput) { Remove-Item $rendererOutput -Recurse -Force }
        # Discard only this renderer project's generated XAML/PRI and NuGet intermediates.
        $rendererIntermediate = Join-Path (Split-Path $project) 'obj\FH6ThumbnailRenderer'
        if (Test-Path $rendererIntermediate) { Remove-Item $rendererIntermediate -Recurse -Force }
        $rendererBin = Join-Path (Split-Path $project) 'bin\FH6ThumbnailRenderer'
        if (Test-Path $rendererBin) { Remove-Item $rendererBin -Recurse -Force }
        Step 'Building the 3D renderer (dotnet publish, several minutes)'
        & dotnet publish $project -c Release -r win-x64 --self-contained true `
            -p:Platform=x64 -p:FH6ThumbnailBuild=true -p:PublishProfile= `
            -p:WindowsAppSDKSelfContained=true -p:PublishSingleFile=false `
            -p:PublishTrimmed=false `
            -p:PublishReadyToRun=false -o (Join-Path $output 'renderer')
        if ($LASTEXITCODE -ne 0) { throw '3D renderer build failed. See build-windows.log; the partial output is not a complete release.' }
        if (!(Test-Path (Join-Path $output 'renderer\ForzaTech Studio.exe'))) {
            throw 'Renderer executable was not created.'
        }
        Step 'Checking renderer resources and footprint'
        & $pythonExe (Join-Path $PSScriptRoot 'build_checks.py') resources (Join-Path $output 'renderer')
        if ($LASTEXITCODE -ne 0) { throw 'Renderer resource/footprint check failed; see renderer-resources.log.' }
        Step 'Renderer startup and PNG self-test'
        & $pythonExe (Join-Path $PSScriptRoot 'build_checks.py') renderer (Join-Path $output 'FH6CarModManager.exe')
        if ($LASTEXITCODE -ne 0) { throw 'Renderer startup/PNG check failed. See renderer-check.log. Close FH6 before building.' }
    }
    Step 'Packaging'
    Copy-Item README.md, THIRD_PARTY_NOTICES.md, WINDOWS_QUICKSTART.md, SaveDiskSpace.bat -Destination $output
    New-Item -ItemType Directory -Force (Join-Path $output 'licenses') | Out-Null
    Copy-Item 'licenses\Pillow.txt' (Join-Path $output 'licenses\Pillow.txt')
    Copy-Item 'vendor\ForzaTechStudio\LICENSE' (Join-Path $output 'licenses\ForzaTechStudio-MIT.txt')
    & $pythonExe (Join-Path $PSScriptRoot 'package_audit.py') $output (Join-Path $PSScriptRoot 'package-size-report.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not write package size report.' }
    $bundle = if ($ManagerOnly) { 'FH6CarModManager-manager-only-win-x64.zip' } else { 'FH6CarModManager-win-x64.zip' }
    Compress-Archive -Path "$output\*" -DestinationPath (Join-Path $PSScriptRoot "dist\$bundle") -Force
    Write-Host "Build complete: $output\FH6CarModManager.exe" -ForegroundColor Green
    if ($ManagerOnly) { Write-Warning 'Manager-only build: automatic 3D thumbnails require the separately built renderer folder.' }
    Write-Host 'Distribute the entire ZIP, including _internal and renderer. Do not copy only the EXE.'
} catch {
    # Record the reason in build-windows.log; otherwise it is printed only after the transcript closes.
    Write-Host ''
    Write-Host ('BUILD FAILED: ' + $_.Exception.Message) -ForegroundColor Red
    if ($_.InvocationInfo) { Write-Host $_.InvocationInfo.PositionMessage }
    throw
} finally {
    Stop-Transcript
}
