$ErrorActionPreference = "Stop"
$environmentPath = "C:\ProgramData\KDI\SemanticWorker\worker.env"
$applicationPath = "C:\KDIWorker\Asset_Management_AI"
$pythonPath = Join-Path $applicationPath ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $environmentPath -PathType Leaf)) {
    throw "Protected worker environment file is missing"
}

foreach ($line in Get-Content -LiteralPath $environmentPath) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
    $parts = $trimmed.Split("=", 2)
    if ($parts.Count -ne 2 -or -not $parts[0].Trim()) {
        throw "Protected worker environment file contains an invalid entry"
    }
    [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1], "Process")
}

Set-Location -LiteralPath $applicationPath
& $pythonPath -m kdi_media.semantic_worker --poll `
    --benchmark-manifest "data\semantic_local_automatic_pilot_20.json" `
    --staging-only --confirm-clinical-local-processing --concurrency 1
exit $LASTEXITCODE
