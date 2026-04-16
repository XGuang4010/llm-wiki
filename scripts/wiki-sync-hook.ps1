# wiki-sync-hook.ps1
# Example startup hook for Windows PowerShell.
# Add this to your PowerShell profile or run it before starting your agent.

$WikiRoot = if ($env:WIKI_ROOT) { $env:WIKI_ROOT } else { "$HOME\wiki" }
$ScannerScript = "$WikiRoot\scripts\learning_scanner.py"
$ReportFile = "$env:TEMP\wiki_sync_report.json"

if (-not (Test-Path $ScannerScript)) {
    Write-Host "[wiki-sync-hook] Scanner not found: $ScannerScript"
    exit 0
}

# Run scanner with auto-stage
& python $ScannerScript `
    --wiki-root $WikiRoot `
    --auto-stage `
    --output $ReportFile `
    --update-index

if ($LASTEXITCODE -ne 0) {
    Write-Host "[wiki-sync-hook] New learnings staged. Run '/wiki sync' in your agent to ingest them."
    # Optional: if your agent CLI supports it, auto-trigger:
    # & opencode wiki sync $WikiRoot
} else {
    Write-Host "[wiki-sync-hook] No new learnings to sync."
}
