param([switch]$DeleteDisposableData)
. (Join-Path $PSScriptRoot 'common.ps1')
$operationLock = Enter-PreviewLock
try {
Require-Docker
$owned = @(Assert-Recorded -AllowMissing)
Confirm-Exact 'STOP codeventra-client-preview'
# Validate all resources before any mutation; operate by recorded IDs only.
foreach ($item in @($owned | Where-Object Kind -eq 'container')) {
    Assert-Target $item
    $null = Invoke-PreviewDocker @('container','stop','--time','15',$item.Id)
    Assert-Target $item
    $null = Invoke-PreviewDocker @('container','rm',$item.Id)
}
foreach ($item in @($owned | Where-Object Kind -eq 'network')) {
    Assert-Target $item
    $null = Invoke-PreviewDocker @('network','rm',$item.Id)
}
if ($DeleteDisposableData) {
    Confirm-Exact 'DELETE codeventra-client-preview SOCKET DATA'
    $null = Assert-Recorded -AllowMissing
    foreach ($item in @($owned | Where-Object Kind -eq 'volume')) {
        # Name-only Docker API: exclusive trusted daemon access is required.
        Assert-Target $item
        $null = Invoke-PreviewDocker @('volume','rm',$item.Name)
    }
}
Write-Host 'PASS: exact demo containers stopped/removed. Evidence retained in runtime/state.json.'
Write-Host 'Volume retained unless deletion was separately confirmed; archive evidence before a fresh start.'

} finally { $operationLock.Dispose() }
