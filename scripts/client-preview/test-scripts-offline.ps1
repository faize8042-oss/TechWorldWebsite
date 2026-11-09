$ErrorActionPreference = 'Stop'
$files = Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps1'
foreach ($file in $files) {
    $tokens = $null; $errors = $null
    $null = [Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors)
    if ($errors.Count) { throw ($errors | Out-String) }
}
. (Join-Path $PSScriptRoot 'common.ps1')
# Replace the Docker wrapper before calling anything that could use the CLI.
$script:FakeName = '/codeventra-client-preview-web-1'
$script:FakeId = 'synthetic-container-id'
$script:FakeProject = 'codeventra-client-preview'
function Invoke-PreviewDocker([string[]]$Arguments) {
    if ($Arguments[1] -eq 'ls') {
        if ($Arguments[0] -eq 'container') { return 'synthetic-container-id' }
        return
    }
    if ($Arguments[0] -eq 'container' -and $Arguments[1] -eq 'inspect') {
        return (@{Name=$script:FakeName;Id=$script:FakeId;Config=@{Labels=@{
            'com.docker.compose.project'=$script:FakeProject
            'com.codeventra.preview'='public-only-v1'
            'com.codeventra.preview.run'='offline-run'
            'com.docker.compose.service'='web'
        }}} | ConvertTo-Json -Depth 8)
    }
    throw 'Unexpected mock operation; no real Docker allowed'
}
function Must-Reject([scriptblock]$Action) {
    $rejected = $false
    try { & $Action } catch { $rejected = $true }
    if (-not $rejected) { throw 'Expected fail-closed rejection' }
}
if (@(Inventory).Count -ne 1) { throw 'Valid ownership rejected' }
$script:FakeProject = 'techworldwebsite'
Must-Reject { Inventory }
$script:FakeProject = $script:Project
$script:FakeName = '/techworldwebsite-web-1'
Must-Reject { Inventory }
$script:FakeName = '/codeventra-client-preview-web-1'
$script:StateFile = Join-Path ([IO.Path]::GetTempPath()) ('preview-offline-' + [guid]::NewGuid().ToString('N') + '.json')
try {
    Must-Reject { Assert-Recorded }
    @{Project=$script:Project;RunId='offline-run';Resources=@(Inventory)} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $script:StateFile
    if (@(Assert-Recorded).Count -ne 1) { throw 'Recorded identity rejected' }
    $script:FakeId = 'replacement-container-id'
    Must-Reject { Assert-Recorded }
    function Read-Host { return 'NO' }
    Must-Reject { Confirm-Exact 'START codeventra-client-preview' }
    Must-Reject { Confirm-Exact 'DELETE codeventra-client-preview SOCKET DATA' }

    # Exercise the real cleanup script with an injected Docker boundary only.
    $script:FakeId = 'synthetic-container-id'
    $script:Items = @(
        [pscustomobject]@{Kind='container';Name="$script:Project-web-1";Id='container-id';RunId='offline-run'},
        [pscustomobject]@{Kind='network';Name="${script:Project}_ingress";Id='network-id';RunId='offline-run'},
        [pscustomobject]@{Kind='volume';Name="${script:Project}_socket";Id='volume|time|mountpoint|local';RunId='offline-run'}
    )
    function Inventory { return $script:Items }
    function Save-Fixture {
        @{Project=$script:Project;RunId='offline-run';Resources=$script:Items} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $script:StateFile
    }
    foreach ($kind in @('container','network','volume')) {
        Save-Fixture
        $entry = @($script:Items | Where-Object Kind -eq $kind)[0]
        $original = $entry.Id
        $entry.Id = 'replacement'
        Must-Reject { Assert-Recorded }
        $entry.Id = $original
    }
    Save-Fixture
    $saved = $script:Items
    $script:Items = @($saved | Where-Object Kind -ne 'network')
    Must-Reject { Assert-Recorded }
    $script:Items = $saved
    $script:Mutations = @()
    function Require-Docker {}
    function Invoke-PreviewDocker([string[]]$Arguments) {
        if ($Arguments[0] -notin @('container','network','volume') -or $Arguments[1] -notin @('stop','rm')) { throw 'Unexpected cleanup operation' }
        if ($Arguments[-1] -match 'techworldwebsite') { throw 'Development resource mutation' }
        $script:Mutations += ,$Arguments
        if ($Arguments[1] -eq 'rm') { $script:Items = @($script:Items | Where-Object { $_.Id -cne $Arguments[-1] -and $_.Name -cne $Arguments[-1] }) }
    }
    $stopText = Get-Content -Raw (Join-Path $PSScriptRoot 'stop-preview.ps1')
    $stopText = $stopText.Replace(". (Join-Path `$PSScriptRoot 'common.ps1')", '# injected common functions')
    $stopScript = [scriptblock]::Create($stopText)
    function Read-Host {
        # Simulate replacement during operator confirmation: first mutation must refuse.
        $script:Items[0].Id = 'replaced-during-confirmation'
        return 'STOP codeventra-client-preview'
    }
    Must-Reject { & $stopScript }
    if ($script:Mutations.Count) { throw 'Unsafe cleanup mutated before ownership revalidation' }
    $script:Items[0].Id = 'container-id'
    function Read-Host { return 'STOP codeventra-client-preview' }
    & $stopScript
    if ($script:Mutations.Count -ne 3 -or @($script:Items).Count -ne 1 -or $script:Items[0].Kind -ne 'volume') { throw 'Exact cleanup or volume preservation failed' }
    function Read-Host([string]$Prompt) {
        if ($Prompt -match 'DELETE') {
            $script:Items[0].Id = 'replacement-volume'
            return 'DELETE codeventra-client-preview SOCKET DATA'
        }
        return 'STOP codeventra-client-preview'
    }
    Must-Reject { & $stopScript -DeleteDisposableData }
    if ($script:Mutations.Count -ne 3) { throw 'Replaced volume was mutated' }
    $script:Items[0].Id = 'volume|time|mountpoint|local'
    function Read-Host([string]$Prompt) {
        if ($Prompt -match 'DELETE') { return 'DELETE codeventra-client-preview SOCKET DATA' }
        return 'STOP codeventra-client-preview'
    }
    & $stopScript -DeleteDisposableData
    if ($script:Mutations.Count -ne 4 -or @($script:Items).Count -ne 0 -or $script:Mutations[-1][-1] -cne "${script:Project}_socket") { throw 'Exact verified volume cleanup failed' }

} finally {
    if (Test-Path -LiteralPath $script:StateFile) { Remove-Item -LiteralPath $script:StateFile }
}
Write-Host 'PASS: PowerShell syntax; ownership, all replacement identities, missing evidence, declined approval, unsafe cleanup refusal, exact cleanup and development preservation (mocks only)'
