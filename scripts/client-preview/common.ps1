Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:Project = 'codeventra-client-preview'
$script:Root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$script:ComposeFile = Join-Path $script:Root 'deploy/client-preview/compose.yaml'
$script:StateFile = Join-Path $PSScriptRoot 'runtime/state.json'
function Invoke-PreviewDocker([string[]]$Arguments) {
    $result = & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker operation failed: $($Arguments[0])" }
    return $result
}
function Require-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'BLOCKED: Docker CLI missing' }
    $null = Invoke-PreviewDocker @('info','--format','{{.OSType}}')
    if ((Invoke-PreviewDocker @('info','--format','{{.OSType}}')) -ne 'linux') { throw 'Linux containers required' }
    $null = Invoke-PreviewDocker @('compose','version')
}
function Confirm-Exact([string]$Text) {
    if ((Read-Host "Type $Text to confirm") -cne $Text) { throw 'Operator confirmation declined' }
}
function Inventory {
    $items = @()
    foreach ($kind in @('container','volume','network')) {
        $projectArgs = @($kind,'ls','-q')
        if ($kind -eq 'container') { $projectArgs += @('-a','--no-trunc') }
        $ids = @(Invoke-PreviewDocker ($projectArgs + @('--filter',"label=com.docker.compose.project=$script:Project")))
        $ids += @(Invoke-PreviewDocker ($projectArgs + @('--filter','label=com.codeventra.preview=public-only-v1')))
        # Also find exact reserved names whose ownership labels were removed/changed.
        $reserved = switch ($kind) {
            container { @("$script:Project-web-1", "$script:Project-ingress-1") }
            volume { @("${script:Project}_socket") }
            network { @("${script:Project}_ingress") }
        }
        foreach ($reservedName in $reserved) {
            $listArgs = @($kind,'ls','-q')
            if ($kind -eq 'container') { $listArgs += @('-a','--no-trunc') }
            $ids += @(Invoke-PreviewDocker ($listArgs + @('--filter',"name=^/?$reservedName`$")))
        }
        $ids = @($ids | Sort-Object -Unique)
        foreach ($id in $ids) {
            if (-not $id) { continue }
            $obj = @(Invoke-PreviewDocker @($kind,'inspect',$id) | ConvertFrom-Json)[0]
            $labels = if ($kind -eq 'container') { $obj.Config.Labels } else { $obj.Labels }
            if ($labels.'com.docker.compose.project' -cne $script:Project -or $labels.'com.codeventra.preview' -cne 'public-only-v1') { throw 'Ambiguous ownership; preserve evidence' }
            $name = $obj.Name.TrimStart('/')
            $expected = switch ($kind) {
                container { @("$script:Project-web-1", "$script:Project-ingress-1") }
                volume { @("${script:Project}_socket") }
                network { @("${script:Project}_ingress") }
            }
            if ($name -cnotin $expected) { throw "Unexpected owned resource: $name; preserve evidence" }
            if ($kind -eq 'container') {
                $service = $labels.'com.docker.compose.service'
                if ($service -cnotin @('web','ingress') -or $name -cne "$script:Project-$service-1") { throw 'Service identity mismatch' }
            }
            $identity = if ($kind -eq 'volume') { $name + '|' + $obj.CreatedAt + '|' + $obj.Mountpoint + '|' + $obj.Driver } else { $obj.Id }
            $items += [pscustomobject]@{Kind=$kind; Name=$name; Id=$identity; RunId=$labels.'com.codeventra.preview.run'}
        }
    }
    return $items
}
function Assert-Recorded([switch]$AllowMissing) {
    if (-not (Test-Path -LiteralPath $script:StateFile)) { throw 'BLOCKED: no ownership record; preserve resources for manual investigation' }
    $state = Get-Content -LiteralPath $script:StateFile -Raw | ConvertFrom-Json
    if ($state.Project -cne $script:Project) { throw 'State project mismatch' }
    if (-not $state.RunId) { throw 'Missing run ownership token' }
    $current = @(Inventory)
    if (-not $AllowMissing -and $current.Count -ne @($state.Resources).Count) { throw 'Recorded resources missing; preserve evidence' }
    foreach ($item in $current) {
        $match = @($state.Resources | Where-Object { $_.Kind -ceq $item.Kind -and $_.Name -ceq $item.Name -and $_.Id -ceq $item.Id -and $item.RunId -ceq $state.RunId })
        if ($match.Count -ne 1) { throw 'Resource identity changed; preserve evidence' }
    }
    return $current
}

# This lock serializes these scripts only. Docker/host administrators must not
# mutate preview resources concurrently; Docker has no transaction/CAS for volumes.
function Enter-PreviewLock {
    $directory = Split-Path $script:StateFile
    $null = New-Item -ItemType Directory -Path $directory -Force
    try { return [IO.File]::Open((Join-Path $directory 'operation.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
    catch { throw 'Another preview operation is active; preserve evidence' }
}
function Assert-Target($Item) {
    $current = @(Assert-Recorded -AllowMissing)
    if (@($current | Where-Object { $_.Kind -ceq $Item.Kind -and $_.Id -ceq $Item.Id -and $_.Name -ceq $Item.Name }).Count -ne 1) {
        throw 'Target ownership revalidation failed; preserve evidence'
    }
}
