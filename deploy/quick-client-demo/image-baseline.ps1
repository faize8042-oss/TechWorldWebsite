# Offline, read-only baseline validation. Return only fixed diagnostic vocabulary.
function Read-ImageBaseline([string]$Path, [string]$Expected) {
    $result = @{ Category = 'baseline-format-error'; Missing = @(); Record = $null }
    if ($Expected -cnotmatch '^sha256:[a-f0-9]{64}$') {
        $result.Category = 'expected-identity-format-error'; return [pscustomobject]$result
    }
    try {
        $bytes = [IO.File]::ReadAllBytes($Path)
        $text = [Text.UTF8Encoding]::new($false, $true).GetString($bytes).TrimStart([char]0xFEFF)
        # Assignment unwraps ConvertFrom-Json's array on Windows PowerShell 5.1.
        # Wrapping the pipeline itself in @() instead retains a nested array.
        $parsed = ConvertFrom-Json -InputObject $text -ErrorAction Stop
    } catch { return [pscustomobject]$result }
    if (-not $text.TrimStart().StartsWith('[')) { return [pscustomobject]$result }
    $records = @($parsed)
    if ($records.Count -eq 0) { return [pscustomobject]$result }
    foreach ($record in $records) {
        if ($null -eq $record -or $record -isnot [pscustomobject]) { return [pscustomobject]$result }
        $missing = @('Id','RepoTags' | Where-Object { $_ -cnotin @($record.PSObject.Properties | ForEach-Object { $_.Name }) })
        if ($missing.Count) {
            $result.Category = 'baseline-missing-fields'; $result.Missing = $missing
            return [pscustomobject]$result
        }
        if ($record.Id -isnot [string] -or $record.Id -cnotmatch '^sha256:[a-f0-9]{64}$' -or
            $record.RepoTags -isnot [array] -or @($record.RepoTags | Where-Object { $_ -isnot [string] }).Count) {
            return [pscustomobject]$result
        }
    }
    $matches = @($records | Where-Object { $_.RepoTags -ccontains 'techworld-django:local' })
    if ($matches.Count -ne 1) { $result.Category = 'baseline-tag-selection-error'; return [pscustomobject]$result }
    $record = $matches[0]
    if ($record.Id -cne $Expected) { $result.Category = 'baseline-identity-mismatch'; return [pscustomobject]$result }
    $missing = @('Config','RootFS','Os','Architecture' | Where-Object { $_ -cnotin @($record.PSObject.Properties | ForEach-Object { $_.Name }) })
    foreach ($group in @(@('Config','User','WorkingDir','Cmd','Env'), @('RootFS','Type','Layers'))) {
        $property = $record.PSObject.Properties[$group[0]]
        if ($null -eq $property) { continue }
        if ($property.Value -isnot [pscustomobject]) { return [pscustomobject]$result }
        foreach ($name in $group[1..($group.Count-1)]) {
            if ($name -cnotin @($property.Value.PSObject.Properties | ForEach-Object { $_.Name })) { $missing += $group[0] + '.' + $name }
        }
    }
    if ($missing.Count) {
        $result.Category = 'baseline-missing-fields'; $result.Missing = $missing
        return [pscustomobject]$result
    }
    if ($record.Os -isnot [string] -or $record.Architecture -isnot [string] -or
        $record.Config.User -isnot [string] -or $record.Config.WorkingDir -isnot [string] -or
        $record.Config.Cmd -isnot [array] -or $record.Config.Env -isnot [array] -or
        $record.RootFS.Type -cne 'layers' -or $record.RootFS.Layers -isnot [array] -or
        $record.RootFS.Layers.Count -eq 0 -or
        @($record.RootFS.Layers | Where-Object { $_ -isnot [string] -or $_ -cnotmatch '^sha256:[a-f0-9]{64}$' }).Count -or
        @(@($record.Config.Cmd) + @($record.Config.Env) | Where-Object { $_ -isnot [string] }).Count) {
        return [pscustomobject]$result
    }
    $result.Category = $null; $result.Record = $record
    return [pscustomobject]$result
}
