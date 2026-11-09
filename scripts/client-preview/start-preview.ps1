param(
    [Parameter(Mandatory=$true)][ValidatePattern('^sha256:[a-f0-9]{64}$')][string]$AppImage,
    [Parameter(Mandatory=$true)][ValidatePattern('^sha256:[a-f0-9]{64}$')][string]$NginxImage
)
. (Join-Path $PSScriptRoot 'common.ps1')
foreach ($file in @($script:ComposeFile, (Join-Path $script:Root 'deploy/client-preview/nginx.conf'), (Join-Path $script:Root 'deploy/client-preview/proxy.conf'))) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "BLOCKED: required preview configuration missing: $file" }
}
$operationLock = Enter-PreviewLock
try {
Require-Docker
$noneNetwork = @(Invoke-PreviewDocker @('network','inspect','none') | ConvertFrom-Json)[0]
if ($noneNetwork.Name -cne 'none' -or $noneNetwork.Driver -cne 'null') { throw 'Unexpected none network' }
foreach ($image in @($AppImage,$NginxImage)) {
    $metadata = @(Invoke-PreviewDocker @('image','inspect',$image) | ConvertFrom-Json)[0]
    if ($metadata.Id -cne $image -or $metadata.Os -ne 'linux' -or $metadata.Config.Volumes) { throw 'Unreviewed image identity, OS or inherited volumes' }
}
$appMetadata = @(Invoke-PreviewDocker @('image','inspect',$AppImage) | ConvertFrom-Json)[0]
if (@($appMetadata.Config.Entrypoint).Count -and $null -ne $appMetadata.Config.Entrypoint) { throw 'App image must clear inherited entrypoint' }
if ($appMetadata.Config.User -cne '10001:10002' -or ($appMetadata.Config.Cmd -join '|') -cne 'gunicorn|config.preview_wsgi:application|--config|/app/preview-gunicorn.py') { throw 'Unexpected app image user/command' }
$probe = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,8765)
try { $probe.Start() } finally { $probe.Stop() }
if (@(Inventory).Count) { throw 'Project resources already exist; no reuse allowed' }
foreach ($entry in @(@('container',"$script:Project-web-1"),@('container',"$script:Project-ingress-1"),@('volume',"${script:Project}_socket"),@('network',"${script:Project}_ingress"))) {
    & docker $entry[0] inspect $entry[1] *> $null
    if ($LASTEXITCODE -eq 0) { throw "Resource name collision: $($entry[1])" }
}
if (Test-Path -LiteralPath $script:StateFile) { throw 'Previous evidence exists; review and archive runtime directory first' }
Confirm-Exact 'START codeventra-client-preview'
if (@(Inventory).Count) { throw 'Ownership changed during confirmation' }
$env:PREVIEW_RUN_ID = [guid]::NewGuid().ToString('N')
$env:PREVIEW_APP_IMAGE = $AppImage
$env:PREVIEW_NGINX_IMAGE = $NginxImage
# Explicit empty env file prevents Compose reading the repository .env.
$runtime = Split-Path $script:StateFile
$null = New-Item -ItemType Directory -Path $runtime -Force
$emptyEnv = Join-Path $runtime 'empty.env'
[IO.File]::WriteAllText($emptyEnv,'')
$composeArgs = @('compose','--env-file',$emptyEnv,'--project-name',$script:Project,'--file',$script:ComposeFile)
@{Project=$script:Project; RunId=$env:PREVIEW_RUN_ID; NoneNetwork=$noneNetwork.Id; Resources=@(); AppImage=$AppImage; NginxImage=$NginxImage} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $script:StateFile
try {
    if (@(Inventory).Count) { throw 'Ownership changed immediately before creation' }
    $null = Invoke-PreviewDocker ($composeArgs + @('create','--no-recreate','--no-build','--pull','never'))
} finally {
    # Record even partial creation. Never automatically delete evidence on failure.
    $resources = @(Inventory)
    if (@($resources | Where-Object { $_.RunId -cne $env:PREVIEW_RUN_ID }).Count) { throw 'Creation ownership uncertain; original intent retained, preserve resources' }
    @{Project=$script:Project; RunId=$env:PREVIEW_RUN_ID; NoneNetwork=$noneNetwork.Id; Resources=$resources; AppImage=$AppImage; NginxImage=$NginxImage} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $script:StateFile
}
$created = @(Assert-Recorded)
if ($created.Count -ne 4 -or @($created | Where-Object Kind -eq 'container').Count -ne 2 -or @($created | Where-Object Kind -eq 'network').Count -ne 1 -or @($created | Where-Object Kind -eq 'volume').Count -ne 1) { throw 'Incomplete creation; preserve evidence' }
foreach ($service in @('web','ingress')) {
    $target = @($created | Where-Object { $_.Kind -eq 'container' -and $_.Name -ceq "$script:Project-$service-1" })[0]
    $null = Assert-Recorded
    Assert-Target $target
    $null = Invoke-PreviewDocker @('container','start',$target.Id)
    if ($service -eq 'web') {
        $deadline = [DateTime]::UtcNow.AddSeconds(90)
        do {
            $obj = @(Invoke-PreviewDocker @('container','inspect',$target.Id) | ConvertFrom-Json)[0]
            if (-not $obj.State.Running) { throw 'Web stopped; preserve evidence' }
            if ($obj.State.Health.Status -eq 'healthy') { break }
            if ($obj.State.Health.Status -eq 'unhealthy' -or [DateTime]::UtcNow -ge $deadline) { throw 'Web health failed; preserve evidence' }
            Start-Sleep -Seconds 1
        } while ($true)
    }
}
& (Join-Path $PSScriptRoot 'check-preview.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Preview checks failed; do not share' }
Write-Host 'Local preview: http://127.0.0.1:8765'
Write-Host 'Tunnel remains stopped. A separate operator approval is required.'

} finally { $operationLock.Dispose() }
