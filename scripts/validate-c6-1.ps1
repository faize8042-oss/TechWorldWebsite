#requires -Version 5.1
# Operator instructions and coverage: docs/c6-1-harness-review.md
[CmdletBinding()]
param([ValidateRange(60,7200)][int]$TimeoutSeconds = 1200, [switch]$PreflightOnly)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$run = 'codeventra-c61-validation-' + [guid]::NewGuid().ToString('N')
$label = 'io.codeventra.c61.validation'
$work = Join-Path ([IO.Path]::GetTempPath()) $run
$results = Join-Path $root ('validation-results/' + $run)
$context = $null
$owned = $false
$cleanupComplete = $true
$nativeTimedOut = $false
$validationStage = 'preflight'
$syntheticKeys = @('CODEVENTRA_SKIP_DOTENV','SECRET_KEY','DEBUG','ALLOWED_HOSTS','CSRF_TRUSTED_ORIGINS','CONTACT_EMAIL','DEFAULT_FROM_EMAIL','EMAIL_HOST','EMAIL_HOST_USER','EMAIL_HOST_PASSWORD','DATABASE_URL','REDIS_URL','POSTGRES_DB','POSTGRES_USER','POSTGRES_PASSWORD','REDIS_PASSWORD','APP_IMAGE','NGINX_IMAGE','PRODUCTION_ENV_FILE','COMPOSE_ENV_FILES','COMPOSE_PROFILES','COMPOSE_FILE','COMPOSE_PROJECT_NAME')
$utf8 = New-Object Text.UTF8Encoding($false)
function Write-Utf8($Path, $Value) { [IO.File]::WriteAllText($Path, $Value, $utf8) }
function Quote-Arg([string]$Value) {
    '"' + ([regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1')) + '"'
}
function Format-SafeCommand([string]$Exe, [string[]]$Arguments) {
    # Never echo values, shell/Python payloads, paths or environment assignments.
    $safe = @('context','show','inspect','info','compose','version','container','network','volume','image','ls','config','build','create','run','up','exec','ps','logs','rm','web','nginx','db','redis','python','gunicorn','sh','git','docker')
    $parts = @($Exe)
    foreach ($arg in $Arguments) {
        if ($arg -in $safe -or $arg -cmatch '^--?[a-zA-Z][a-zA-Z-]*$') { $parts += $arg }
        else { $parts += '[redacted]' }
    }
    $parts -join ' '
}
function Get-SafeProbeFailure([string]$Output) {
    # Only fixed check identifiers and numeric metadata may cross this boundary.
    $matches = [regex]::Matches($Output, '(?m)^C61_FAIL check=(directory_metadata|socket_type|socket_metadata|process_identity|tcp_listeners|probe_error) detail=[0-9,:;.-]+\r?$')
    ($matches | ForEach-Object { $_.Value.TrimEnd("`r") }) -join '; '
}
function Native([string]$Exe, [string[]]$Arguments, [int]$Limit = $TimeoutSeconds) {
    $p = New-Object Diagnostics.Process
    $p.StartInfo = New-Object Diagnostics.ProcessStartInfo
    $p.StartInfo.FileName = $Exe
    $p.StartInfo.Arguments = ($Arguments | ForEach-Object { Quote-Arg $_ }) -join ' '
    $p.StartInfo.UseShellExecute = $false
    $p.StartInfo.CreateNoWindow = $true
    $p.StartInfo.RedirectStandardOutput = $true
    $p.StartInfo.RedirectStandardError = $true
    if ($Exe -eq 'docker') {
        # Clear inherited interpolation keys in the child only, without reading
        # their values. Explicit synthetic --env-file remains the sole input.
        foreach ($key in @($p.StartInfo.EnvironmentVariables.Keys)) {
            if ($key -in $syntheticKeys -or $key -like 'COMPOSE_*') { $p.StartInfo.EnvironmentVariables.Remove($key) }
        }
        $p.StartInfo.EnvironmentVariables['COMPOSE_DISABLE_ENV_FILE'] = '1'
        $p.StartInfo.EnvironmentVariables.Remove('DOCKER_HOST')
        $p.StartInfo.EnvironmentVariables.Remove('DOCKER_CONTEXT')
    }
    $command = Format-SafeCommand $Exe $Arguments
    try { [void]$p.Start() } catch { throw "Stage '$validationStage': could not start $command" }
    $stdout = $p.StandardOutput.ReadToEndAsync()
    $stderr = $p.StandardError.ReadToEndAsync()
    if (-not $p.WaitForExit($Limit * 1000)) {
        $script:nativeTimedOut = $true
        $p.Kill(); $p.WaitForExit()
        throw "Stage '$validationStage': timed out: $command; daemon work may continue. See cleanup documentation."
    }
    $out = $stdout.Result + $stderr.Result
    if ($p.ExitCode -ne 0) {
        $detail = Get-SafeProbeFailure $out
        throw "Stage '$validationStage': command failed (exit $($p.ExitCode)): $command. Sanitized probe details: $detail. Other output omitted to protect secrets."
    }
    return $out.Trim()
}
function Docker([string[]]$Arguments) { Native 'docker' (@('--context', $context) + $Arguments) }
function Compose([string[]]$Arguments) {
    Docker (@('compose','--project-name',$run,'--project-directory',$work,'--env-file',"$work/synthetic.env",'-f',"$work/isolated.json") + $Arguments)
}
function Exec-Web([string[]]$Arguments) { Compose (@('exec','-T','web') + $Arguments) }
function ConvertTo-IsolatedComposeJson($Model) {
    # Compose config JSON already preserves $$ for replay. Do not escape it again.
    $Model | ConvertTo-Json -Depth 60
}
function Assert-ComposeShellCommands($Model) {
    # Exact contracts catch both host interpolation and shell PID ($$) expansion.
    $expectedDb = @('CMD-SHELL', 'pg_isready -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"')
    $expectedRedis = @('CMD-SHELL', 'REDISCLI_AUTH="$$REDIS_PASSWORD" redis-cli ping | grep -q PONG')
    $expectedCommand = @('sh', '-ec', 'exec redis-server --save '''' --appendonly no --maxmemory 128mb --maxmemory-policy allkeys-lru --requirepass "$${REDIS_PASSWORD}"')
    foreach ($pair in @(
        @{ Actual=$Model.services.db.healthcheck.test; Expected=$expectedDb },
        @{ Actual=$Model.services.redis.healthcheck.test; Expected=$expectedRedis },
        @{ Actual=$Model.services.redis.command; Expected=$expectedCommand }
    )) {
        if ((ConvertTo-Json -Compress -InputObject @($pair.Actual)) -cne (ConvertTo-Json -Compress -InputObject @($pair.Expected))) {
            # Never include command values: a future regression could embed secrets.
            throw 'Compose shell variable expansion contract changed.'
        }
    }
}
function Assert-SocketTopology($Model) {
    # Pure contract: safe to load in offline regression tests.
    foreach ($name in @('web','nginx')) {
        $service = $Model.services.$name
        $targets = @()
        if ($service.PSObject.Properties['tmpfs']) { $targets += @($service.tmpfs | ForEach-Object { ($_ -split ':', 2)[0] }) }
        $targets += @($service.volumes | Where-Object { $_.type -eq 'tmpfs' } | ForEach-Object { $_.target })
        foreach ($target in $targets) {
            # Linux lexical normalization plus the image's /var/run -> /run alias.
            $parts = New-Object 'System.Collections.Generic.List[string]'
            if (-not $target.StartsWith('/')) { throw 'Tmpfs target must be absolute.' }
            foreach ($part in ($target -split '/')) {
                if (-not $part -or $part -eq '.') { continue }
                if ($part -eq '..') { if ($parts.Count) { $parts.RemoveAt($parts.Count - 1) }; continue }
                $parts.Add($part)
                if (($parts -join '/') -eq 'var/run') { $parts.Clear(); $parts.Add('run') }
            }
            $normalized = '/' + ($parts -join '/')
            if ($normalized -eq '/var' -or $normalized -eq '/' -or '/run/codeventra' -eq $normalized -or '/run/codeventra'.StartsWith($normalized + '/')) {
                throw 'Tmpfs mount hides the private socket volume.'
            }
        }
        $mounts = @($Model.services.$name.volumes | Where-Object { $_.target -eq '/run/codeventra' })
        if ($mounts.Count -ne 1 -or $mounts[0].type -ne 'volume' -or $mounts[0].source -ne 'gunicorn_socket') {
            throw 'Private socket must use the same named volume and target.'
        }
        $ro = $mounts[0].PSObject.Properties['read_only']
        if (($name -eq 'nginx' -and (-not $ro -or -not $ro.Value)) -or
            ($name -eq 'web' -and $ro -and $ro.Value)) {
            throw 'Private socket mount access changed.'
        }
    }
    if (-not $Model.volumes.PSObject.Properties['gunicorn_socket']) { throw 'Missing socket volume.' }
}
if ($PreflightOnly) {
    # No processes, Docker calls, builds, filesystem writes or secret reads.
    foreach ($exe in @('docker','git')) { Get-Command $exe -CommandType Application -ErrorAction Stop | Out-Null }
    foreach ($file in @('Dockerfile','requirements.txt','deploy/compose.production.yaml','deploy/gunicorn.production.py','deploy/nginx/Dockerfile','deploy/nginx/production.conf.example')) {
        if (-not (Test-Path -LiteralPath (Join-Path $root $file) -PathType Leaf)) { throw "Missing prerequisite: $file" }
    }
    Write-Host "Project: $run; label: $label=$run"
    Write-Host "Images: ${run}-app, ${run}-nginx"
    Write-Host "Containers: ${run}-web-1, ${run}-nginx-1, ${run}-db-1, ${run}-redis-1; labeled ephemeral helpers"
    Write-Host "Networks: ${run}_data, ${run}_proxy"
    Write-Host "Volumes: ${run}_tls, ${run}_gunicorn_socket, ${run}_postgres_data, ${run}_private_uploads, ${run}_public_media"
    Write-Host "Work: $work; results: $results"
    Write-Host 'Local prerequisites passed. Names are proposals; execution generates a fresh GUID.'
    Write-Host 'Not checked: daemon/context, Linux/Desktop, Compose capabilities, collisions, registry, certificate tooling or runtime readiness.'
    return
}
function Wait-Ready([string]$Name, [scriptblock]$Probe) {
    $deadline = [DateTime]::UtcNow.AddSeconds(120)
    do {
        try { & $Probe; return } catch { $lastFailure = $_.Exception.Message }
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Name readiness failed: $lastFailure"
}
try {
    Get-Command docker, git -ErrorAction Stop | Out-Null
    New-Item -ItemType Directory -Path $work,$results | Out-Null
    Write-Utf8 "$results/run.txt" "Run: $run`nLabel: $label=$run`nWork: $work`nResults: $results`n"
    $validationStage = 'Docker preflight'
    $context = Native docker @('context','show') 30
    Add-Content "$results/run.txt" "Context: $context"
    if ((Docker @('info','--format','{{.OSType}}')) -ne 'linux') { throw 'Select Docker Desktop Linux containers first.' }
    if ((Docker @('info','--format','{{.OperatingSystem}}')) -notmatch 'Docker Desktop') { throw 'Docker Desktop engine is required.' }
    # Reject remote engines; this harness is specifically for local Docker Desktop.
    $endpoint = Native docker @('context','inspect',$context,'--format','{{.Endpoints.docker.Host}}') 30
    if ($endpoint -notlike 'npipe:/*') { throw 'A local Docker Desktop named-pipe context is required.' }
    $null = Docker @('compose','version')
    foreach ($kind in @('container','network','volume','image')) {
        if ((Docker @($kind,'ls','--filter',"label=$label=$run",'-q'))) { throw "Run-label collision: $kind" }
        $nameFormat = switch ($kind) { 'container' { '{{.Names}}' } 'image' { '{{.Repository}}' } default { '{{.Name}}' } }
        $nameArgs = @($kind,'ls','--format',$nameFormat)
        if ($kind -eq 'container') { $nameArgs += '-a' }
        $names = Docker $nameArgs
        if (($names -split '\s+' | Where-Object { $_ -like "$run*" })) { throw "Resource-name collision: $kind" }
    }
    $validationStage = 'source staging'
    $stage = Join-Path $work 'source'
    New-Item -ItemType Directory -Path $stage | Out-Null
    # Explicit source allowlist: never copy worktree uploads, .env, Git metadata or backups.
    $files = (Native git @('-C',$root,'ls-files','--','Dockerfile','requirements.txt','manage.py','config','core','contact','analytics','projects','templates','static','deploy')).Split("`n")
    $files += @('deploy/gunicorn.production.py','deploy/nginx/Dockerfile')
    foreach ($relative in ($files | Sort-Object -Unique)) {
        $relative = $relative.Trim()
        if (-not $relative) { continue }
        if ($relative -match '(^|/)(\.env[^/]*|media|private_uploads|backups|__pycache__)(/|$)' -or $relative -match '\.(pem|key|sqlite3|dump|sql|pyc)$') { throw "Disallowed staging path: $relative" }
        $source = Join-Path $root $relative
        $item = Get-Item -LiteralPath $source
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Source links are prohibited.' }
        $parent = $item.Directory
        while ($parent -and $parent.FullName -ne $root) {
            if ($parent.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Source junctions are prohibited.' }
            $parent = $parent.Parent
        }
        $target = Join-Path $stage $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -LiteralPath $source -Destination $target
    }
    Write-Utf8 "$stage/.dockerignore" "__pycache__/`n*.pyc`n"
    $synthetic = @'
CODEVENTRA_SKIP_DOTENV=1
SECRET_KEY=synthetic-validation-only-abcdefghijklmnopqrstuvwxyz-0123456789-ABCDE
DEBUG=False
ALLOWED_HOSTS=codeventralabs.com,www.codeventralabs.com
CSRF_TRUSTED_ORIGINS=https://codeventralabs.com
CONTACT_EMAIL=validation@example.invalid
DEFAULT_FROM_EMAIL=validation@example.invalid
EMAIL_HOST=smtp.example.invalid
EMAIL_HOST_USER=synthetic
EMAIL_HOST_PASSWORD=synthetic-only
DATABASE_URL=postgres://synthetic:synthetic-only@db:5432/synthetic
REDIS_URL=redis://:synthetic-only@redis:6379/0
POSTGRES_DB=synthetic
POSTGRES_USER=synthetic
POSTGRES_PASSWORD=synthetic-only
REDIS_PASSWORD=synthetic-only
'@
    $synthetic += "`nAPP_IMAGE=${run}-app`nNGINX_IMAGE=${run}-nginx`nPRODUCTION_ENV_FILE=$($work.Replace('\','/'))/synthetic.env`n"
    Write-Utf8 "$work/synthetic.env" $synthetic
    $validationStage = 'production Compose rendering'
    $render = Docker @('compose','--project-name',$run,'--project-directory',"$stage/deploy",'--env-file',"$work/synthetic.env",'-f',"$stage/deploy/compose.production.yaml",'config','--format','json')
    Write-Utf8 "$results/production-compose.synthetic.json" $render
    $model = $render | ConvertFrom-Json
    Assert-ComposeShellCommands $model
    Assert-SocketTopology $model
    if ((($model.services.PSObject.Properties.Name | Sort-Object) -join ',') -ne 'db,nginx,redis,web') { throw 'Unexpected services.' }
    $model.PSObject.Properties.Remove('name')
    $model.services.nginx.PSObject.Properties.Remove('ports')
    $model.services.nginx.volumes = @(
        @{type='bind';source="$stage/deploy/nginx/production.conf.example";target='/etc/nginx/conf.d/default.conf';read_only=$true},
        @{type='volume';source='tls';target='/etc/letsencrypt';read_only=$true},
        @{type='volume';source='public_media';target='/srv/media';read_only=$true},
        @{type='volume';source='gunicorn_socket';target='/run/codeventra';read_only=$true})
    $model.volumes | Add-Member -NotePropertyName tls -NotePropertyValue ([pscustomobject]@{})
    foreach ($entry in $model.volumes.PSObject.Properties) { $entry.Value | Add-Member -Force -NotePropertyName name -NotePropertyValue "${run}_$($entry.Name)"; $entry.Value | Add-Member -Force -NotePropertyName labels -NotePropertyValue @{$label=$run} }
    foreach ($entry in $model.networks.PSObject.Properties) { $entry.Value | Add-Member -Force -NotePropertyName name -NotePropertyValue "${run}_$($entry.Name)"; $entry.Value | Add-Member -Force -NotePropertyName labels -NotePropertyValue @{$label=$run} }
    foreach ($entry in $model.services.PSObject.Properties) {
        foreach ($forbidden in @('container_name','build','privileged','network_mode','pid','ipc','devices','volumes_from','extends','develop')) {
            if ($entry.Value.PSObject.Properties[$forbidden]) { throw "Unexpected service property: $forbidden" }
        }
        $entry.Value.restart = 'no'
        $entry.Value | Add-Member -Force -NotePropertyName labels -NotePropertyValue @{$label=$run}
    }
    $model.services.web.environment | Add-Member -Force -NotePropertyName DJANGO_SETTINGS_MODULE -NotePropertyValue 'config.settings'
    $model.services.web.command = @('gunicorn','validation_wsgi:application','--config','deploy/gunicorn.production.py')
    # Fail closed if a future template introduces extra host resources or ports.
    foreach ($entry in $model.services.PSObject.Properties) {
        $service = $entry.Value
        if ($service.PSObject.Properties['ports'] -and @($service.ports).Count) { throw 'Published ports prohibited.' }
        $mounts = @()
        if ($service.PSObject.Properties['volumes']) { $mounts = $service.volumes }
        foreach ($mount in $mounts) {
            if ($mount.type -eq 'bind') {
                if ($entry.Name -ne 'nginx' -or $mount.source -ne "$stage/deploy/nginx/production.conf.example") { throw 'Unexpected host mount.' }
            } elseif ($mount.type -ne 'volume' -or -not $model.volumes.PSObject.Properties[$mount.source]) { throw 'Unexpected volume source.' }
        }
    }
    foreach ($entry in @($model.volumes.PSObject.Properties) + @($model.networks.PSObject.Properties)) {
        if ($entry.Value.PSObject.Properties['external'] -and $entry.Value.external) { throw 'External resources prohibited.' }
    }
    Write-Utf8 "$work/isolated.json" (ConvertTo-IsolatedComposeJson $model)
    Assert-ComposeShellCommands (Get-Content -LiteralPath "$work/isolated.json" -Raw | ConvertFrom-Json)
    Assert-SocketTopology (Get-Content -LiteralPath "$work/isolated.json" -Raw | ConvertFrom-Json)
    # Check the replayed model before any builds or owned resources are created.
    $validationStage = 'isolated Compose replay'
    $replayed = Compose @('config','--format','json')
    Assert-ComposeShellCommands ($replayed | ConvertFrom-Json)
    Assert-SocketTopology ($replayed | ConvertFrom-Json)
    Write-Utf8 "$results/isolated-compose.synthetic.json" $replayed
    Write-Utf8 "$stage/validation_wsgi.py" @'
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from django.conf import settings
assert settings.SETTINGS_MODULE == 'config.settings'
assert settings.DEPLOYMENT_MODE == 'production' and not settings.DEBUG
assert settings.PRODUCTION_PROXY_TRANSPORT == 'unix'
assert settings.ENABLE_HTTPS and settings.SECURE_SSL_REDIRECT
assert settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE
assert settings.SECURE_PROXY_SSL_HEADER == ('HTTP_X_FORWARDED_PROTO', 'https')
assert settings.MIDDLEWARE[:2] == ['config.middleware.TrustedProxyIPMiddleware', 'django.middleware.security.SecurityMiddleware']
assert not settings.SECURE_HSTS_SECONDS and not settings.SEO_INDEXING_ENABLED
from django.http import JsonResponse
from django.core.handlers.wsgi import WSGIRequest
from django.middleware.security import SecurityMiddleware
from config.middleware import TrustedProxyIPMiddleware
def endpoint(r):
    return JsonResponse({'secure': r.is_secure(), 'ip': r.META.get('REMOTE_ADDR'),
                         'xff': r.META.get('HTTP_X_FORWARDED_FOR')})
handler = TrustedProxyIPMiddleware(SecurityMiddleware(endpoint))
def application(environ, start_response):
    response = handler(WSGIRequest(environ))
    start_response(f'{response.status_code} result', list(response.items()))
    return [response.content]
'@
    Write-Utf8 "$stage/validation_settings.py" @'
from config.settings import *
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
MEDIA_ROOT = '/tmp/test-media'
'@
    Write-Utf8 "$stage/validation_probe.py" @'
import socket, ssl, http.client, json, os, stat, time
if os.environ.get('PEER_CHECK'):
    targets = json.loads(os.environ['WEB_IPS'])
    assert targets
    for ip in targets:
        for port in (8000, 8001, 8080, 80, 443):
            try:
                with socket.create_connection((ip, port), timeout=2):
                    raise AssertionError(('peer reached web TCP', ip, port))
            except ConnectionRefusedError:
                pass
            # Timeouts and routing errors are inconclusive and fail the check.
    print('PASS peer namespace TCP connections refused', targets)
elif os.environ.get('READY_CHECK'):
    with socket.socket(socket.AF_UNIX) as peer:
        peer.settimeout(3)
        peer.connect('/run/codeventra/gunicorn.sock')
        peer.sendall(b'GET /probe HTTP/1.0\r\nHost: codeventralabs.com\r\nX-Forwarded-Proto: https\r\n\r\n')
        response = http.client.HTTPResponse(peer); response.begin()
        assert response.status == 200, response.status
        assert json.loads(response.read())['secure'] is True
    print('PASS Gunicorn application ready')
elif os.environ.get('SOCKET_CHECK'):
    def require(check, condition, detail):
        if not condition:
            print(f'C61_FAIL check={check} detail={detail}', flush=True)
            raise AssertionError(check)
    try:
        d, s = os.stat('/run/codeventra'), os.stat('/run/codeventra/gunicorn.sock')
        metadata = lambda node: (node.st_uid, node.st_gid, stat.S_IMODE(node.st_mode))
        describe = lambda node: f'{node.st_uid}:{node.st_gid}:{stat.S_IMODE(node.st_mode):o}'
        require('directory_metadata', metadata(d) == (10001,10002,0o2750), describe(d))
        require('socket_type', stat.S_ISSOCK(s.st_mode), str(stat.S_IFMT(s.st_mode)))
        require('socket_metadata', metadata(s) == (10001,10002,0o660), describe(s))
        require('process_identity', (os.getuid(), os.getgid()) == (10001,10002), f'{os.getuid()}:{os.getgid()}')
        def tcp_snapshot():
            result = []
            for version, path in ((4, '/proc/net/tcp'), (6, '/proc/net/tcp6')):
                with open(path) as table:
                    for line in table.readlines()[1:]:
                        fields = line.split()
                        if fields[3] == '0A':
                            addr, port = fields[1].split(':')
                            result.append((version, int(addr, 16), int(port, 16),
                                           int(fields[7]), int(fields[9])))
            return sorted(result)

        def process_ids():
            return sorted(name for name in os.listdir('/proc') if name.isdigit())

        before = tcp_snapshot()
        pids = process_ids()
        owners = {}
        # Inspect every visible process, including inherited sockets. A denied
        # or racing fd scan is inconclusive, never evidence of no ownership.
        for pid in pids:
            with os.scandir('/proc/' + pid + '/fd') as descriptors:
                for fd in descriptors:
                    target = os.readlink(fd.path)
                    if target.startswith('socket:[') and target.endswith(']'):
                        inode = int(target[8:-1])
                        owners.setdefault(inode, set()).add(pid)
        require('tcp_listeners', pids == process_ids() and before == tcp_snapshot(), '1')
        for version, addr, port, uid, inode in before:
            detail = f'{version}:{addr}:{port}:{uid}:{inode}'
            require('tcp_listeners', inode > 0, detail)
            # This isolated web PID namespace contains the application only.
            # Reject any process-owned TCP listener, even outside Gunicorn.
            # Docker's embedded DNS lives in the network namespace but outside
            # this PID namespace: root-created inode, no local fd owner. Require
            # both pieces of kernel evidence and a complete stable fd census.
            unrelated = uid != os.getuid() and inode not in owners
            require('tcp_listeners', unrelated, detail)
    except OSError as error:
        print(f'C61_FAIL check=probe_error detail={error.errno or 0}', flush=True)
        raise
    print('PASS socket metadata, nonroot and no application TCP listeners')
elif os.environ.get('DENY_CHECK'):
    s = socket.socket(socket.AF_UNIX)
    try:
        s.connect('/run/codeventra/gunicorn.sock')
    except PermissionError:
        print('PASS unauthorized UID denied')
    else:
        raise AssertionError('unauthorized connection succeeded')
else:
    # TLS is deliberately synthetic; certificate trust/real DNS are outside scope.
    ip = socket.gethostbyname('nginx')
    peer = socket.socket(); peer.connect((ip,443)); local_ip = peer.getsockname()[0]; peer.close()
    def request(tls, headers):
        raw = socket.create_connection((ip,443 if tls else 80),timeout=10)
        if tls: raw = ssl._create_unverified_context().wrap_socket(raw,server_hostname='codeventralabs.com')
        raw.sendall(('GET /probe?x=1 HTTP/1.1\r\nHost: codeventralabs.com\r\nConnection: close\r\n'+headers+'\r\n').encode())
        r = http.client.HTTPResponse(raw); r.begin(); body=r.read(); raw.close()
        return r, body
    forged = 'X-Forwarded-Proto: http\r\nX-Real-IP: 203.0.113.9\r\nX-Forwarded-For: 203.0.113.9, 198.51.100.1\r\nX-Forwarded-Ssl: on\r\nX-Forwarded-Protocol: ssl\r\nCodeventra-Private-Socket: True\r\n'
    for attempt in range(30):
        try:
            r,b = request(True,forged)
            assert r.status == 200, (r.status,b)
            break
        except (OSError, AssertionError):
            if attempt == 29: raise
            time.sleep(1)
    data = json.loads(b)
    assert data == {'secure':True,'ip':local_ip,'xff':local_ip}, data
    r,b = request(False,'X-Forwarded-Proto: https\r\n')
    assert r.status == 301 and r.getheader('Location') == 'https://codeventralabs.com/probe?x=1'
    print('PASS Nginx socket connection, TLS scheme, redirect, forged headers and IPv4 peer identity')
'@
    # Explicit CLI dependency in the disposable image only; slim does not
    # guarantee openssl. Production Dockerfile is never changed.
    Add-Content "$stage/Dockerfile" "`nUSER root`nRUN apt-get update && apt-get install -y --no-install-recommends openssl && rm -rf /var/lib/apt/lists/*`nUSER appuser"
    $validationStage = 'image builds'
    $owned = $true
    Write-Utf8 "$results/build-app.log" (Docker @('build','--label',"$label=$run",'-t',"${run}-app",$stage))
    $validationStage = 'Nginx image build'
    Write-Utf8 "$results/build-nginx.log" (Docker @('build','--label',"$label=$run",'-t',"${run}-nginx",'-f',"$stage/deploy/nginx/Dockerfile",$stage))
    $validationStage = 'synthetic TLS setup'
    $null = Docker @('volume','create','--label',"$label=$run",'--label',"com.docker.compose.project=$run",'--label','com.docker.compose.volume=tls',"${run}_tls")
    Write-Utf8 "$results/certificate.log" (Docker @('run','--rm','--label',"$label=$run",'--network','none','--user','0:0','-v',"${run}_tls:/certs","${run}-app",'sh','-ec','umask 077; openssl version; mkdir -p /certs/live/REPLACE_WITH_CONFIRMED_HOST; openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=codeventralabs.com -keyout /certs/live/REPLACE_WITH_CONFIRMED_HOST/privkey.pem -out /certs/live/REPLACE_WITH_CONFIRMED_HOST/fullchain.pem; openssl verify -CAfile /certs/live/REPLACE_WITH_CONFIRMED_HOST/fullchain.pem /certs/live/REPLACE_WITH_CONFIRMED_HOST/fullchain.pem; openssl x509 -in /certs/live/REPLACE_WITH_CONFIRMED_HOST/fullchain.pem -checkend 0 -noout'))
    $validationStage = 'Compose validation'
    Write-Utf8 "$results/compose-validation.log" (Compose @('config','--quiet'))
    $validationStage = 'isolated startup'
    Write-Utf8 "$results/startup.log" (Compose @('up','-d','--wait','--wait-timeout','120'))
    $validationStage = 'Gunicorn readiness'
    Wait-Ready 'Gunicorn' { $null = Compose @('exec','-T','-e','READY_CHECK=1','web','python','validation_probe.py') }
    Write-Utf8 "$results/gunicorn-ready.log" 'PASS Unix HTTP application response'
    # Inspect the consumer namespace before spending time on TLS retries.
    # No chmod, writes, TCP listener or permission workaround is permitted.
    $validationStage = 'Nginx socket visibility'
    Write-Utf8 "$results/nginx-socket-visible.log" (Compose @('exec','-T','nginx','sh','-ec','test -S /run/codeventra/gunicorn.sock; stat -c "%u:%g %a %F %d:%i %n" /run/codeventra /run/codeventra/gunicorn.sock'))
    $validationStage = 'Nginx TLS readiness'
    Wait-Ready 'Nginx TLS/proxy' { $null = Docker @('run','--rm','--label',"$label=$run",'--network',"${run}_proxy","${run}-app",'python','validation_probe.py') }
    Write-Utf8 "$results/nginx-ready.log" 'PASS TLS and proxied application response'
    $validationStage = 'runtime security checks'
    Write-Utf8 "$results/gunicorn-version.log" (Exec-Web @('gunicorn','--version'))
    $null = Exec-Web @('python','-c','import gunicorn; assert gunicorn.__version__.split(".")[0] == "23"')
    Write-Utf8 "$results/gunicorn-config.log" (Exec-Web @('gunicorn','validation_wsgi:application','--config','deploy/gunicorn.production.py','--check-config'))
    Write-Utf8 "$results/nginx-config.log" (Compose @('exec','-T','nginx','nginx','-T'))
    $validationStage = 'runtime security: socket metadata, identity and TCP listeners'
    Write-Utf8 "$results/socket.log" (Compose @('exec','-T','-e','SOCKET_CHECK=1','web','python','validation_probe.py'))
    $validationStage = 'runtime security: unauthorized socket access'
    Write-Utf8 "$results/unauthorized.log" (Compose @('exec','-T','--user','10003:10003','-e','DENY_CHECK=1','web','python','validation_probe.py'))
    Write-Utf8 "$results/proxy.log" (Docker @('run','--rm','--label',"$label=$run",'--network',"${run}_proxy","${run}-app",'python','validation_probe.py'))
    $webId = Compose @('ps','-q','web')
    $webInspection = (Docker @('inspect',$webId)) | ConvertFrom-Json
    $webIps = ConvertTo-Json -Compress -InputObject @($webInspection[0].NetworkSettings.Networks.PSObject.Properties | ForEach-Object { $_.Value.IPAddress } | Where-Object { $_ })
    foreach ($service in @('db','redis')) {
        $id = Compose @('ps','-q',$service)
        $inspection = (Docker @('inspect',$id)) | ConvertFrom-Json
        if (@($inspection[0].Mounts | Where-Object { $_.Destination -eq '/run/codeventra' }).Count) { throw "$service has socket mount" }
        Write-Utf8 "$results/peer-$service-tcp.log" (Docker @('run','--rm','--label',"$label=$run",'--network',"container:$id",'-e','PEER_CHECK=1','-e',"WEB_IPS=$webIps","${run}-app",'python','validation_probe.py'))
        Write-Utf8 "$results/peer-$service.log" (Compose @('exec','-T',$service,'sh','-ec','test ! -e /run/codeventra/gunicorn.sock'))
    }
    $validationStage = 'Django checks'
    Write-Utf8 "$results/deploy-check.log" (Exec-Web @('python','manage.py','check','--deploy'))
    foreach ($scope in @('focused','full')) {
        $testArgs = @('run','--rm','--no-deps','-e','DEPLOYMENT_MODE=development','-e','ENABLE_HTTPS=False','-e','DJANGO_SETTINGS_MODULE=validation_settings','web','python','manage.py','test')
        if ($scope -eq 'focused') { $testArgs += 'config' }
        Write-Utf8 "$results/django-$scope.log" (Compose $testArgs)
    }
    Write-Utf8 "$results/outcome.txt" 'Implemented checks passed in this run. Consult documented gaps; this is not production validation.'
}
catch {
    if (Test-Path $results) { Write-Utf8 "$results/failure.txt" $_.Exception.Message }
    Write-Error $_ -ErrorAction Continue
    $script:failed = $true
}
finally {
    $validationStage = 'owned-resource diagnostics and cleanup'
    if ($owned) {
        # Never use compose down or prune. Discover exact IDs, recheck their run
        # label immediately before removal, and remove containers before volumes.
        try {
            try { Write-Utf8 "$results/runtime.log" (Compose @('logs','--no-color','--tail','200')) } catch { Write-Warning $_ }
            foreach ($kind in @('container','network','volume','image')) {
                $listArgs = @($kind,'ls','--filter',"label=$label=$run",'-q')
                if ($kind -eq 'container') { $listArgs += '-a' }
                try { $ids = Docker $listArgs } catch {
                    $cleanupComplete = $false
                    Add-Content "$results/cleanup-error.txt" "Cannot list $kind : $_"
                    continue
                }
                foreach ($id in ($ids -split '\s+' | Where-Object { $_ } | Sort-Object -Unique)) {
                    try {
                    $format = if ($kind -in @('container','image')) { '{{json .Config.Labels}}' } else { '{{json .Labels}}' }
                    $labels = (Docker @($kind,'inspect','--format',$format,$id)) | ConvertFrom-Json
                    if (-not $labels.PSObject.Properties[$label] -or $labels.$label -ne $run) { throw "Cleanup label mismatch: $kind $id" }
                    if ($kind -eq 'container') {
                        # Exact-label ownership was checked above. Save only mounts
                        # and filesystem metadata, never Config/Env or socket data.
                        try {
                            Write-Utf8 "$results/mounts-$id.json" (Docker @('container','inspect','--format','{{json .Mounts}}',$id))
                            $serviceLabel = $labels.PSObject.Properties['com.docker.compose.service']
                            if ($serviceLabel -and $serviceLabel.Value -in @('web','nginx')) {
                                Write-Utf8 "$results/socket-namespace-$id.log" (Docker @('exec',$id,'sh','-c','id; readlink /var/run; for p in /run /var/run /run/codeventra /run/codeventra/gunicorn.sock; do ls -ldn "$p" 2>&1; stat -c "%u:%g %a %F %d:%i %n" "$p" 2>&1; done; cat /proc/self/mountinfo'))
                            }
                        } catch { Add-Content "$results/socket-diagnostic-errors.txt" "Mount/socket capture failed for container $id" }
                        # Capture only health state, never full inspect (which includes env).
                        # Diagnostic failures must not prevent removal of owned resources.
                        try {
                            $health = Docker @('container','inspect','--format','{{json .State.Health}}',$id)
                            foreach ($line in ($synthetic -split "`n")) {
                                $parts = $line.TrimEnd("`r") -split '=', 2
                                if ($parts.Count -eq 2 -and $parts[0] -in @('SECRET_KEY','EMAIL_HOST_PASSWORD','DATABASE_URL','REDIS_URL','POSTGRES_PASSWORD','REDIS_PASSWORD') -and $parts[1]) {
                                    $health = $health.Replace($parts[1], '[REDACTED]')
                                }
                            }
                            Write-Utf8 "$results/health-$id.json" $health
                        } catch { Add-Content "$results/health-errors.txt" "Health capture failed for container $id" }
                    }
                    $remove = @($kind,'rm')
                    if ($kind -eq 'container') { $remove += '-f' }
                    $null = Docker ($remove + $id)
                    Add-Content "$results/cleanup.log" "Removed $kind $id"
                    } catch {
                        $cleanupComplete = $false
                        Add-Content "$results/cleanup-error.txt" "$kind $id : $_"
                    }
                }
            }
        } catch { $cleanupComplete = $false; Write-Warning "Cleanup incomplete: $_"; Add-Content "$results/cleanup-error.txt" "$_" }
        foreach ($kind in @('container','network','volume','image')) {
            try {
                $query = @($kind,'ls','--filter',"label=$label=$run",'-q')
                if ($kind -eq 'container') { $query += '-a' }
                $remaining = Docker $query
                Add-Content "$results/cleanup-verification.txt" "$kind : $remaining"
                if ($remaining) { throw "Owned $kind remain: $remaining" }
            } catch {
                $cleanupComplete = $false
                Add-Content "$results/cleanup-error.txt" "Verification $kind : $_"
            }
        }
    }
    if ($nativeTimedOut) {
        $cleanupComplete = $false
        if (Test-Path $results) { Add-Content "$results/cleanup-error.txt" 'Native timeout: daemon work may continue. Recheck exact labels after it finishes.' }
    }
    if (-not $cleanupComplete) {
        $script:failed = $true
        Write-Warning "Cleanup incomplete or uncertain. Preserve $work and $results; see run.txt."
    } elseif (Test-Path -LiteralPath $work) {
        # Verify absolute destination before recursive deletion, in this shell.
        $resolvedWork = (Resolve-Path -LiteralPath $work).ProviderPath
        $expectedWork = [IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetTempPath()) $run))
        if ($resolvedWork -ne $expectedWork -or ((Get-Item -LiteralPath $work).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            $script:failed = $true
            Write-Warning 'Unsafe staging path; retained for manual review.'
        } else {
            try { Remove-Item -LiteralPath $resolvedWork -Recurse -Force } catch { $script:failed = $true; Write-Warning "Staging removal failed: $_" }
        }
    }
    Write-Host "Results: $results"
}
if (Get-Variable failed -Scope Script -ErrorAction SilentlyContinue) { exit 1 }
