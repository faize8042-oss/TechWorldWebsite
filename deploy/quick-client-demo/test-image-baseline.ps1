# No Docker, Python, image inspection, or audit report writes.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'image-baseline.ps1')
$source = Join-Path $PSScriptRoot 'verified-images.json'
$expected = 'sha256:69c0b8cdfa8a03b9517d6bd9a80bb1afc7c024ee355e78ac79effa3c62587cdf'
$original = [IO.File]::ReadAllText($source)
$temp = [IO.Path]::GetTempFileName()
$count = 0
function Check([string]$Json, $Category, [string[]]$Missing = @()) {
    [IO.File]::WriteAllText($temp, $Json, [Text.UTF8Encoding]::new($false))
    $result = Read-ImageBaseline $temp $expected
    if ($result.Category -cne $Category -or ($result.Missing -join ',') -cne ($Missing -join ',')) { throw "Unexpected validation result at case $script:count; expected $Category; received $($result.Category); missing $($result.Missing -join ',')" }
    if ($null -eq $Category -and $result.Record.Id -cne $expected) { throw 'Wrong record selected' }
    $script:count++
}
try {
    $actual = Read-ImageBaseline $source $expected
    if ($null -ne $actual.Category -or $actual.Record.Id -cne $expected) { throw 'Actual baseline rejected' }
    $count++
    Check $original $null
    Check ([string][char]0xFEFF + $original) $null
    Check '{' 'baseline-format-error'
    Check '{}' 'baseline-format-error'
    Check '[]' 'baseline-format-error'
    Check '[null]' 'baseline-format-error'
    Check '[{}]' 'baseline-missing-fields' @('Id','RepoTags')
    $records = ConvertFrom-Json $original
    Check ($records[0] | ConvertTo-Json -Depth 100) 'baseline-format-error'
    Check ($original.Replace($expected, ('sha256:' + ('0' * 64)))) 'baseline-identity-mismatch'
    Check ($original.Replace($expected, ($expected + '0'))) 'baseline-format-error'
    Check ($original.Replace('techworld-django:local', 'other:local')) 'baseline-tag-selection-error'
    Check ('[' + ($records[0] | ConvertTo-Json -Depth 100) + ',' + ($records[0] | ConvertTo-Json -Depth 100) + ']') 'baseline-tag-selection-error'
    $records[0].PSObject.Properties.Remove('Config')
    Check (ConvertTo-Json -InputObject @($records | ForEach-Object { $_ }) -Depth 100) 'baseline-missing-fields' @('Config')
    $records = ConvertFrom-Json $original
    $records[0].RootFS.PSObject.Properties.Remove('Layers')
    Check (ConvertTo-Json -InputObject @($records | ForEach-Object { $_ }) -Depth 100) 'baseline-missing-fields' @('RootFS.Layers')
    [IO.File]::WriteAllBytes($temp, [byte[]]@(255,254,91,0,93,0))
    if ((Read-ImageBaseline $temp $expected).Category -cne 'baseline-format-error') { throw 'Encoding accepted' }
    $count++
    foreach ($file in @('audit-image.ps1','image-baseline.ps1','test-image-baseline.ps1')) {
        $tokens = $null; $errors = $null
        $null = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $file), [ref]$tokens, [ref]$errors)
        if ($errors.Count) { throw 'PowerShell syntax failure' }
    }
    Write-Output "Offline baseline regressions: PASS ($count cases); PowerShell syntax: PASS"
} finally { Remove-Item -LiteralPath $temp -Force }
