#requires -Version 5.1
# Offline regression tests. Loads only pure functions, never the harness body.
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $PSScriptRoot 'validate-c6-1.ps1'), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Harness syntax errors.' }
foreach ($name in @('ConvertTo-IsolatedComposeJson','Assert-ComposeShellCommands','Assert-SocketTopology','Format-SafeCommand','Get-SafeProbeFailure')) {
    $definition = $ast.Find({ param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name
    }, $false)
    if (-not $definition) { throw "Missing pure function: $name" }
    . ([scriptblock]::Create($definition.Extent.Text))
}
# Match the saved Compose config representation; no environment values required.
$fixture = @'
{"services":{"db":{"healthcheck":{"test":["CMD-SHELL","pg_isready -U \"$$POSTGRES_USER\" -d \"$$POSTGRES_DB\""]}},"redis":{"command":["sh","-ec","exec redis-server --save '' --appendonly no --maxmemory 128mb --maxmemory-policy allkeys-lru --requirepass \"$${REDIS_PASSWORD}\""],"healthcheck":{"test":["CMD-SHELL","REDISCLI_AUTH=\"$$REDIS_PASSWORD\" redis-cli ping | grep -q PONG"]}}}}
'@
$model = $fixture | ConvertFrom-Json
Assert-ComposeShellCommands $model
$generated = ConvertTo-IsolatedComposeJson $model
Assert-ComposeShellCommands ($generated | ConvertFrom-Json)
# Each mutation represents a distinct expansion failure. All must fail closed.
foreach ($bad in @(
    $generated.Replace('$', '$$'),
    $generated.Replace('$$', '$'),
    $generated.Replace('$$POSTGRES_USER', 'host-resolved-user'),
    $generated.Replace('$$POSTGRES_DB', 'host-resolved-db'),
    $generated.Replace('$$REDIS_PASSWORD', 'host-resolved-auth'),
    $generated.Replace('$${REDIS_PASSWORD}', 'host-resolved-password')
)) {
    $rejected = $false
    try { Assert-ComposeShellCommands ($bad | ConvertFrom-Json) } catch { $rejected = $true }
    if (-not $rejected) { throw 'Expansion regression was not rejected.' }
}
Write-Output 'PASS offline Compose command serialization and expansion contracts'

$socketFixture = @'
{"services":{"web":{"volumes":[{"type":"volume","source":"gunicorn_socket","target":"/run/codeventra"}]},"nginx":{"volumes":[{"type":"volume","source":"gunicorn_socket","target":"/run/codeventra","read_only":true}]}},"volumes":{"gunicorn_socket":{}}}
'@
Assert-SocketTopology ($socketFixture | ConvertFrom-Json)
foreach ($mutation in @('source','target','nginx-writable','web-readonly','missing','duplicate','bind','undefined')) {
    $candidate = $socketFixture | ConvertFrom-Json
    switch ($mutation) {
        'source' { $candidate.services.nginx.volumes[0].source = 'other_socket' }
        'target' { $candidate.services.nginx.volumes[0].target = '/var/run/codeventra' }
        'nginx-writable' { $candidate.services.nginx.volumes[0].read_only = $false }
        'web-readonly' { $candidate.services.web.volumes[0] | Add-Member read_only $true }
        'missing' { $candidate.services.nginx.volumes = @() }
        'duplicate' { $candidate.services.nginx.volumes += $candidate.services.nginx.volumes[0] }
        'bind' { $candidate.services.nginx.volumes[0].type = 'bind' }
        'undefined' { $candidate.volumes.PSObject.Properties.Remove('gunicorn_socket') }
    }
    $rejected = $false
    try { Assert-SocketTopology $candidate } catch { $rejected = $true }
    if (-not $rejected) { throw "Socket topology regression was not rejected: $mutation" }
}
# Parent aliases, normalization and both Compose tmpfs representations.
foreach ($target in @('/','/var','/var/./','/run','/run/','//run/./','/var/run','/var//run/','/var/run/../run','/tmp/../run','/run/codeventra','/var/run/codeventra')) {
    foreach ($form in @('short','long')) {
        $candidate = $socketFixture | ConvertFrom-Json
        if ($form -eq 'short') { $candidate.services.nginx | Add-Member tmpfs @("${target}:rw,noexec,nosuid") }
        else { $candidate.services.nginx.volumes += [pscustomobject]@{type='tmpfs';target=$target} }
        $rejected = $false
        try { Assert-SocketTopology $candidate } catch { $rejected = $true }
        if (-not $rejected) { throw "Covering tmpfs accepted: $target ($form)" }
    }
}
foreach ($target in @('/run/nginx','/var/cache/nginx','/tmp','/runner','/run/codeventra-other')) {
    $candidate = $socketFixture | ConvertFrom-Json
    $candidate.services.nginx | Add-Member tmpfs @("${target}:rw")
    Assert-SocketTopology ((ConvertTo-IsolatedComposeJson $candidate) | ConvertFrom-Json)
}
# Inspect only checked-in configuration; never load environment files or Docker.
$root = Split-Path $PSScriptRoot -Parent
$compose = Get-Content -LiteralPath "$root/deploy/compose.production.yaml" -Raw
$nginx = [regex]::Match($compose, '(?ms)^  nginx:\r?\n(.*?)(?=^volumes:)').Groups[1].Value
$targets = @([regex]::Matches($nginx, '(?m)^      - (/[^: \r\n]+):rw') | ForEach-Object { $_.Groups[1].Value })
if (-not $targets.Count -or $nginx -notmatch 'read_only: true') { throw 'Missing Nginx runtime restrictions.' }
$candidate = $socketFixture | ConvertFrom-Json
$candidate.services.nginx | Add-Member tmpfs $targets
Assert-SocketTopology $candidate
if ('/run/nginx' -notin $targets) { throw 'Missing dedicated PID tmpfs.' }
$image = Get-Content -LiteralPath "$root/deploy/nginx/Dockerfile" -Raw
if ($image -notmatch 'pid /run/nginx/nginx.pid;') { throw 'Nginx PID path does not match dedicated tmpfs.' }
$diagnostic = Format-SafeCommand docker @('compose','exec','-e','TOKEN=secret-sentinel','web','sh','-ec','echo secret-sentinel','/private/path')
if ($diagnostic -match 'secret-sentinel|/private/path' -or $diagnostic -notmatch 'compose exec') { throw 'Unsafe or unhelpful command diagnostic.' }
Write-Output 'PASS offline socket topology, covering tmpfs rejection, PID path and safe diagnostics'

# Reproduce the confirmed diagnostic loss: nonzero probes must retain a safe
# assertion identifier while arbitrary stderr and secret-bearing lines disappear.
foreach ($check in @('directory_metadata','socket_type','socket_metadata','process_identity','tcp_listeners','probe_error')) {
    $marker = "C61_FAIL check=$check detail=4:167772287:8000"
    $safe = Get-SafeProbeFailure "Traceback secret-sentinel`n$marker`nAssertionError secret-sentinel"
    if ($safe -cne $marker) { throw "Lost safe probe diagnostic: $check" }
}
foreach ($unsafe in @('C61_FAIL check=unknown detail=1','C61_FAIL check=socket_metadata detail=secret-sentinel','prefix C61_FAIL check=tcp_listeners detail=1','C61_FAIL check=tcp_listeners detail=1 secret-sentinel')) {
    if (Get-SafeProbeFailure $unsafe) { throw 'Unsafe probe diagnostic accepted.' }
}
Write-Output 'PASS offline failing-probe diagnostic preservation and secret rejection'
python (Join-Path $PSScriptRoot 'test_c61_probe.py')
if ($LASTEXITCODE -ne 0) { throw 'Generated Python probe regression failed.' }
