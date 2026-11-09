[CmdletBinding()]
param(
    [switch]$PreflightOnly,
    [switch]$ExecuteIsolatedValidation,
    [ValidateRange(60,3600)][int]$TimeoutSeconds = 600,
    [string]$PostgresImage = 'postgres:17',
    [string]$PythonImage = '',
    [string]$OperatorConfirmation = ''
)
$ErrorActionPreference = 'Stop'
if ($PreflightOnly -and $ExecuteIsolatedValidation) { throw 'Conflicting execution modes.' }
$parseTokens = $null
$parseErrors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$parseTokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Harness syntax validation failed.' }
$engine = Join-Path $PSScriptRoot 'c621/harness.py'
$argsList = @('-I', $engine, '--timeout', "$TimeoutSeconds", '--postgres-image', $PostgresImage)
if ($ExecuteIsolatedValidation) {
    if ($OperatorConfirmation -cne 'APPROVE DISPOSABLE C6.2.1 VALIDATION') { throw 'Explicit operator approval phrase is required.' }
    $argsList += @('--execute', '--approval', $OperatorConfirmation, '--python-image', $PythonImage)
}
# Default path performs offline preflight only. Python isolates inherited configuration.
& python @argsList
if ($LASTEXITCODE -ne 0) { throw 'C6.2.1 harness failed; see sanitized status.' }
