param([switch]$ManagerOnly)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if ($env:OS -ne 'Windows_NT') { throw 'Build this project on Windows 10/11 x64.' }
Start-Transcript -Path (Join-Path $PSScriptRoot 'build-windows.log') -Force
try {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .build-venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .build-venv
    } else {
        throw 'Install 64-bit Python 3.12 with Tcl/Tk and the Python launcher, then retry.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python build environment.' }
    $pythonExe = Join-Path $PSScriptRoot '.build-venv\Scripts\python.exe'
    & $pythonExe (Join-Path $PSScriptRoot 'build_checks.py') sources
    if ($LASTEXITCODE -ne 0) { throw 'Source package incomplete. Download and extract the complete ZIP into a new folder.' }
    & $pythonExe (Join-Path $PSScriptRoot 'build_checks.py') validate
    if ($LASTEXITCODE -ne 0) { throw 'Python/Tk validation failed.' }
    & $pythonExe -m pip install --disable-pip-version-check -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'Cannot download PyInstaller. Check network/proxy settings.' }
    & $pythonExe (Join-Path $PSScriptRoot 'build_checks.py') tests
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed; refusing to package. Full details: test-results.log' }
    if (!$ManagerOnly -and !(Get-Command dotnet -ErrorAction SilentlyContinue)) {
        throw 'Install .NET 9 SDK x64 and Visual Studio 2022 Build Tools with Windows App SDK / desktop development support, then retry.'
    }
    & $pythonExe -m PyInstaller --noconfirm --clean --windowed --onedir --noupx --name FH6CarModManager app.py
    if ($LASTEXITCODE -ne 0) { throw 'Manager build failed.' }
    $output = Join-Path $PSScriptRoot 'dist\FH6CarModManager'
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
        & dotnet publish $project -c Release -r win-x64 --self-contained true `
            -p:Platform=x64 -p:FH6ThumbnailBuild=true -p:PublishProfile= `
            -p:WindowsAppSDKSelfContained=true -p:PublishSingleFile=false `
            -p:PublishTrimmed=false `
            -p:PublishReadyToRun=false -o (Join-Path $output 'renderer')
        if ($LASTEXITCODE -ne 0) { throw '3D renderer build failed. See build-windows.log; the partial output is not a complete release.' }
        if (!(Test-Path (Join-Path $output 'renderer\ForzaTech Studio.exe'))) {
            throw 'Renderer executable was not created.'
        }
        & $pythonExe (Join-Path $PSScriptRoot 'build_checks.py') resources (Join-Path $output 'renderer')
        if ($LASTEXITCODE -ne 0) { throw 'Renderer resource publish check failed; see renderer-resources.log.' }
        & $pythonExe (Join-Path $PSScriptRoot 'build_checks.py') renderer (Join-Path $output 'FH6CarModManager.exe')
        if ($LASTEXITCODE -ne 0) { throw 'Renderer startup/PNG check failed. See renderer-check.log. Close FH6 before building.' }
    }
    Copy-Item README.md, THIRD_PARTY_NOTICES.md, WINDOWS_QUICKSTART.md -Destination $output
    New-Item -ItemType Directory -Force (Join-Path $output 'licenses') | Out-Null
    Copy-Item 'vendor\ForzaTechStudio\LICENSE' (Join-Path $output 'licenses\ForzaTechStudio-MIT.txt')
    & $pythonExe (Join-Path $PSScriptRoot 'package_audit.py') $output (Join-Path $PSScriptRoot 'package-size-report.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not write package size report.' }
    $bundle = if ($ManagerOnly) { 'FH6CarModManager-manager-only-win-x64.zip' } else { 'FH6CarModManager-win-x64.zip' }
    Compress-Archive -Path "$output\*" -DestinationPath (Join-Path $PSScriptRoot "dist\$bundle") -Force
    Write-Host "Build complete: $output\FH6CarModManager.exe" -ForegroundColor Green
    if ($ManagerOnly) { Write-Warning 'Manager-only build: automatic 3D thumbnails require the separately built renderer folder.' }
    Write-Host 'Distribute the entire ZIP, including _internal and renderer. Do not copy only the EXE.'
} finally {
    Stop-Transcript
}
