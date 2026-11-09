#requires -Version 5.1
<## Read-only deployment probes plus tests in an ephemeral PostgreSQL database. ##>
[CmdletBinding()]
param([switch]$DiagnoseStartup)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$results = New-Object 'System.Collections.Generic.List[object]'
$compose = @('compose', '-f', (Join-Path $root 'compose.yaml'), '-f', (Join-Path $root 'compose.development-build.yaml'))

function Record([string]$Status, [string]$Name, [string]$Detail) {
    $results.Add([pscustomobject]@{ Status = $Status; Name = $Name })
    Write-Host ("[{0}] {1}: {2}" -f $Status, $Name, $Detail)
}

function Native([string]$Command, [string[]]$Arguments, [string]$InputText = '') {
    # Capture stderr too: Docker/DB diagnostics can include connection secrets.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($InputText) { $lines = @($InputText | & $Command @Arguments 2>&1) }
        else { $lines = @(& $Command @Arguments 2>&1) }
        $code = $LASTEXITCODE
        return [pscustomobject]@{ Code = $code; Text = ($lines -join "`n") }
    } finally { $ErrorActionPreference = $previous }
}

function StartupDiagnostics([string]$Text) {
    # Classify untrusted native stderr; never echo messages, paths or values.
    $patterns = [ordered]@{
        'Docker engine access denied' = '(?i)permission denied.*(docker|pipe)|access is denied|error during connect'
        'Invalid bind mount or missing mount source' = '(?i)invalid (mount|volume)|mount.*(denied|not found)|bind source path does not exist|not a directory'
        'Container runtime could not start Python' = '(?i)OCI runtime|exec.*python.*(not found|no such file)|unable to start container'
        'Python helper could not be opened' = "(?i)python.*can.t open file"
        'Python file missing or unreadable' = '(?m)(FileNotFoundError|PermissionError|IsADirectoryError):'
        'Python import failed before helper diagnostics' = '(?m)(ModuleNotFoundError|ImportError):'
        'Python syntax error before helper diagnostics' = '(?m)(SyntaxError|IndentationError):'
        'Compose rejected an argument' = '(?i)unknown flag|unknown shorthand flag|requires.*argument'
    }
    $matched = $false
    foreach ($entry in $patterns.GetEnumerator()) {
        if ($Text -match $entry.Value) { Write-Host ('  FAIL: startup category=' + $entry.Key); $matched = $true }
    }
    if (-not $matched) { Write-Host '  INFO: startup category=unclassified; raw native output withheld.' }
}

function Probe([string]$Name, [string]$Mode, [bool]$Container = $false, [bool]$Running = $false) {
    if ($Running) {
        # Execute current probe source in the running image without copying files
        # or changing its settings. Application imports come from that image.
        $probeText = [System.IO.File]::ReadAllText((Join-Path $root 'scripts/publishing_verify.py'))
        $run = Native 'docker' ($compose + @('exec', '-T', 'web', 'python', '-c',
            "import sys; __file__='/app/scripts/publishing_verify.py'; exec(compile(sys.stdin.read(),__file__,'exec'))", $Mode)) $probeText
    } elseif ($Container) {
        # Overlay files only: retain complete installed application packages.
        # Compose run supports --volume; validate each file before requesting it.
        $verificationFiles = @('scripts/publishing_verify.py', 'scripts/publishing_test_runner.py',
            'config/verification_test_settings.py', 'nginx/default.conf', 'deploy/gunicorn.production.py')
        foreach ($package in @('config', 'core', 'projects', 'contact', 'analytics', 'blog', 'news', 'publishing')) {
            $verificationFiles += @(Get-ChildItem -LiteralPath (Join-Path $root $package) -Filter 'test*.py' -File -Recurse |
                ForEach-Object { $_.FullName.Substring($root.Length + 1).Replace('\', '/') })
        }
        $argsList = $compose + @('run', '--rm', '--no-deps', '--pull', 'never', '-T',
            '--workdir', '/app', '--entrypoint', 'python',
            '-e', 'PYTHONDONTWRITEBYTECODE=1')
        foreach ($relative in ($verificationFiles | Sort-Object -Unique)) {
            $source = Join-Path $root $relative
            if (-not (Test-Path -LiteralPath $source -PathType Leaf) -or $source.Contains(',')) {
                Record 'FAIL' $Name 'Verification source missing or unsupported mount path; no container launched.'
                return
            }
            $argsList += @('--volume', "${source}:/app/${relative}:ro")
        }
        # No embedded double quotes or shell layer: compatible with PS 5.1's
        # native argument marshalling, including roots containing spaces.
        $bootstrap = "import os,sys,runpy; p='/app/scripts/publishing_verify.py'; print('INFO: python-started helper-file=' + str(os.path.isfile(p)) + ' helper-readable=' + str(os.access(p,os.R_OK)),flush=True); sys.argv=[p,sys.argv[1]]; runpy.run_path(p,run_name='__main__')"
        if ($DiagnoseStartup) {
            # Import discovery only: no settings execution, DB connection or tests.
            $bootstrap = "import os,sys,importlib.util; sys.path.insert(0,'/app'); print('INFO: python-started',flush=True); paths=sys.argv[2:]; [print('INFO: mount=' + p + ' file=' + str(os.path.isfile(p)) + ' readable=' + str(os.access(p,os.R_OK)),flush=True) for p in paths]; [print('INFO: import=' + n + ' origin=' + str(getattr(importlib.util.find_spec(n),'origin',None)),flush=True) for n in ['config','scripts','config.verification_test_settings','scripts.publishing_test_runner']]; print('QA_COMPLETE:' + sys.argv[1])"
        }
        $argsList += @('web', '-c', $bootstrap, $Mode)
        if ($DiagnoseStartup) {
            $argsList += @($verificationFiles | Sort-Object -Unique | ForEach-Object { '/app/' + $_ })
            Write-Host ('Docker argv (JSON array; each element is one argument): ' + (ConvertTo-Json -InputObject @($argsList) -Compress))
        }
        $run = Native 'docker' $argsList
    } else {
        $run = Native $python @((Join-Path $root 'scripts/publishing_verify.py'), $Mode)
    }
    # Only helper-authored safe diagnostics reach the console. Never print raw
    # Docker output, Compose interpolation, settings, tracebacks or HTTP bodies.
    foreach ($line in ($run.Text -split "`r?`n")) {
        if ($line -match '^(PASS:|INFO:|FAIL:|Ran [0-9]+ tests|OK$|FAILED \(|ERROR: test_)') { Write-Host "  $line" }
        if ($line -match '^SKIP: (.+)$') { Record 'SKIP' $Name $Matches[1] }
    }
    $completed = $run.Text -match ("(?m)^QA_COMPLETE:" + [regex]::Escape($Mode) + "`r?$")
    if ($run.Code -eq 0 -and $completed) { Record 'PASS' $Name 'Executed successfully.' }
    elseif ($run.Code -eq 2 -and $Mode -eq 'browser' -and -not $Container -and -not $Running) {
        Record 'SKIP' $Name 'NOT VERIFIED; browser automation/runtime unavailable.'
    }
    else {
        StartupDiagnostics $run.Text
        Record 'FAIL' $Name ("Probe mode={0}, exit={1}, completion={2}." -f $Mode, $run.Code, $completed)
        if ($run.Text -notmatch '(?m)^(PASS:|INFO:|FAIL:)') {
            Write-Host '  FAIL: No helper diagnostics received; container launch, source mount, or Python startup failed before probe execution. Raw output withheld.'
        }
    }
}

if ($DiagnoseStartup) {
    Probe 'Migration drift startup only' 'drift' $true
    Probe 'PostgreSQL suite startup only' 'tests' $true
    if (@($results | Where-Object { $_.Status -eq 'FAIL' }).Count) { exit 1 }
    exit 0
}

Push-Location $root
try {
    Write-Host 'Codeventra Labs publishing verification (development HTTP, existing services only)'
    $python = $null
    $localPython = Join-Path $root '.venv/Scripts/python.exe'
    if (Test-Path -LiteralPath $localPython) { $python = $localPython }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { $python = 'python' }
    if ($python) {
        $version = Native $python @('-c', 'import sys; assert sys.version_info >= (3, 10)')
        if ($version.Code -ne 0) { $python = $null }
    }
    if ($python) {
        Record 'PASS' 'Python prerequisite' 'Python 3.10+ available.'
        Probe 'Source security contracts' 'source'
        Probe 'Live Nginx HTTP smoke and CSRF' 'live'
        Probe 'Mobile/tablet/desktop browser layout' 'browser'
    } else {
        Record 'FAIL' 'Python prerequisite' 'Install Python 3.10+ or restore .venv; no dependencies are installed automatically.'
        Record 'SKIP' 'Source/live/browser probes' 'Python unavailable; NOT VERIFIED.'
    }

    $dockerReady = $false
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        $engine = Native 'docker' @('info', '--format', '{{.ServerVersion}}')
        $plugin = Native 'docker' @('compose', 'version', '--short')
        $dockerReady = $engine.Code -eq 0 -and $plugin.Code -eq 0
    }
    if (-not $dockerReady) {
        Record 'FAIL' 'Docker prerequisite' 'Docker engine or Compose v2 inaccessible. Start Docker Desktop or fix engine permissions, then rerun.'
        foreach ($name in @('Compose configuration', 'Container health', 'Nginx syntax and active forwarding',
            'Runtime Django security/system checks', 'Pending migrations/PostgreSQL', 'Migration drift',
            'PostgreSQL Django regression suite', 'Private storage and mount isolation')) {
            Record 'SKIP' $name 'Requires accessible Docker and already running development services; NOT VERIFIED.'
        }
    } else {
        Record 'PASS' 'Docker prerequisite' 'Engine and Compose v2 accessible.'
        $configResult = Native 'docker' ($compose + @('config', '--format', 'json'))
        $configValid = $false
        if ($configResult.Code -eq 0) {
            try {
                $config = $configResult.Text | ConvertFrom-Json
                # Never display this object: resolved Compose includes secrets.
                if ($config.services.web.environment.DEPLOYMENT_MODE -ne 'development') { throw 'mode' }
                $configValid = $true
                Record 'PASS' 'Compose configuration' 'Both files resolve to the development deployment.'
            } catch { Record 'FAIL' 'Compose configuration' 'Invalid resolved configuration or non-development mode; details withheld.' }
        } else { Record 'FAIL' 'Compose configuration' 'Compose failed; check required environment variables privately (do not paste config or .env).' }
        if ($configValid) {
            $healthy = $true
            $mounts = @{}
            foreach ($service in @('web', 'db', 'redis', 'nginx')) {
                $ids = Native 'docker' ($compose + @('ps', '-q', $service))
                $id = $ids.Text.Trim()
                if ($ids.Code -ne 0 -or $id -notmatch '^[a-f0-9]{12,64}$') {
                    Record 'FAIL' "Container $service" 'Expected exactly one running container; suite does not start services.'
                    $healthy = $false
                    continue
                }
                $stateResult = Native 'docker' @('inspect', '--format', '{{json .State}}', $id)
                $mountResult = Native 'docker' @('inspect', '--format', '{{json .Mounts}}', $id)
                try {
                    if ($stateResult.Code -ne 0 -or $mountResult.Code -ne 0) { throw 'inspect' }
                    $state = $stateResult.Text | ConvertFrom-Json
                    # Windows PowerShell 5.1 emits a JSON array as ONE pipeline
                    # object. Assign first, then enumerate its elements.
                    $parsedMounts = $mountResult.Text | ConvertFrom-Json
                    $mounts[$service] = @($parsedMounts)
                    if (-not $state.Running) { throw 'stopped' }
                    $healthProperty = $state.PSObject.Properties['Health']
                    if ($healthProperty -and $state.Health.Status -ne 'healthy') { throw 'unhealthy' }
                    if ($service -in @('db', 'redis') -and -not $healthProperty) { throw 'healthcheck missing' }
                    if ($service -in @('db', 'redis')) {
                        $bindingsResult = Native 'docker' @('inspect', '--format', '{{json .NetworkSettings.Ports}}', $id)
                        if ($bindingsResult.Code -ne 0) { throw 'port inspection' }
                        $bindings = $bindingsResult.Text | ConvertFrom-Json
                        if ($null -ne $bindings) {
                            foreach ($bindingProperty in $bindings.PSObject.Properties) {
                                foreach ($binding in @($bindingProperty.Value)) {
                                    if ($null -ne $binding -and ($service -eq 'redis' -or $binding.HostIp -notin @('127.0.0.1', '::1'))) {
                                        throw 'public running datastore port'
                                    }
                                }
                            }
                        }
                    }
                    Record 'PASS' "Container $service" $(if ($healthProperty) { 'Running and healthy.' } else { 'Running; no healthcheck configured. HTTP probe verifies service response.' })
                } catch { Record 'FAIL' "Container $service" 'Stopped, unhealthy, missing healthcheck, unsafe datastore port, or inspect failed.'; $healthy = $false }
            }
            try {
                foreach ($service in @('db', 'redis')) {
                    $portsProperty = $config.services.$service.PSObject.Properties['ports']
                    if ($portsProperty) {
                        foreach ($port in $portsProperty.Value) {
                            if ($service -eq 'redis' -or $port.host_ip -notin @('127.0.0.1', '::1')) { throw 'public datastore' }
                        }
                    }
                }
                Record 'PASS' 'Datastore port exposure' 'No public DB/Redis bind; existing loopback PostgreSQL development bind is permitted.'
            } catch { Record 'FAIL' 'Datastore port exposure' 'Remove Redis port publishing and non-loopback PostgreSQL ports.' }
            try {
                if (-not $mounts.ContainsKey('web') -or -not $mounts.ContainsKey('nginx')) { throw 'missing mount inspection' }
                $planned = @($config.services.web.volumes | Where-Object { $_.target -eq '/app/private_publishing' })
                if ($planned.Count -ne 1 -or $planned[0].type -ne 'volume') { throw 'Compose web private volume missing or not writable' }
                if ($planned[0].PSObject.Properties['read_only'] -and $planned[0].read_only) { throw 'Compose web private volume missing or not writable' }
                foreach ($mount in $config.services.nginx.volumes) {
                    if ($mount.source -eq $planned[0].source -or $mount.target -match 'private_publishing') { throw 'Compose Nginx private volume exposure' }
                }
                $private = @($mounts['web'] | Where-Object { $_.Destination -eq '/app/private_publishing' })
                if ($private.Count -ne 1 -or $private[0].Type -ne 'volume' -or -not $private[0].RW) { throw 'running web private volume missing or not writable' }
                $expectedName = $config.volumes.($planned[0].source).name
                if ($private[0].Name -ne $expectedName) { throw 'running private volume differs from merged Compose' }
                foreach ($mount in $mounts['nginx']) {
                    if ($mount.Source -eq $private[0].Source -or $private[0].Source.StartsWith($mount.Source.TrimEnd('/') + '/') -or
                        $mount.Destination -match 'private_publishing') { throw 'running Nginx private volume or ancestor exposure' }
                }
                Record 'PASS' 'Persistent publishing mount isolation' 'Writable named volume on web; private volume and ancestors absent from Nginx.'
            } catch {
                # Only literal conditions authored above are safe to disclose.
                $reason = $_.Exception.Message
                if ($reason -notmatch '^(missing mount inspection|Compose web private volume missing or not writable|Compose Nginx private volume exposure|running web private volume missing or not writable|running private volume differs from merged Compose|running Nginx private volume or ancestor exposure)$') { $reason = 'mount inspection schema/processing error' }
                Record 'FAIL' 'Persistent publishing mount isolation' $reason
            }
            if ($healthy) {
                $syntax = Native 'docker' ($compose + @('exec', '-T', 'nginx', 'nginx', '-t'))
                if ($syntax.Code -eq 0) { Record 'PASS' 'Nginx syntax' 'nginx -t passed.' }
                else { Record 'FAIL' 'Nginx syntax' 'nginx -t failed; inspect configuration privately.' }
                $active = Native 'docker' ($compose + @('exec', '-T', 'nginx', 'nginx', '-T'))
                if ($active.Code -eq 0 -and $active.Text -match 'proxy_set_header Host \$http_host;' -and
                    $active.Text -match 'proxy_set_header X-Forwarded-Proto \$scheme;' -and $active.Text -notmatch 'private_publishing') {
                    Record 'PASS' 'Active Nginx forwarding' 'Loaded config preserves Host port and overwrites forwarded protocol; no private storage reference.'
                } else { Record 'FAIL' 'Active Nginx forwarding' 'Unexpected forwarding or private-storage reference in loaded Nginx configuration.' }
                Probe 'Runtime Django security/system checks' 'runtime' $true $true
                Probe 'Pending migrations/PostgreSQL' 'database' $true $true
                # Compose may build a service image if it is missing. Refuse
                # that situation before any one-off container is requested.
                $imageCheck = Native 'docker' @('image', 'inspect', '--format', '{{.Id}}', $config.services.web.image)
                if ($imageCheck.Code -eq 0) {
                    Record 'PASS' 'Existing development image' 'Local image exists; no build/pull required.'
                    Probe 'Migration drift' 'drift' $true
                    Probe 'PostgreSQL Django regression suite' 'tests' $true
                } else {
                    Record 'FAIL' 'Existing development image' 'Expected local development image is missing; verifier will not build or pull it.'
                    Record 'SKIP' 'Migration drift and PostgreSQL tests' 'Missing local image; NOT VERIFIED.'
                }
                Probe 'Private storage permissions' 'storage' $true $true
            } else {
                Record 'SKIP' 'Nginx, runtime, database, drift, tests and storage probes' 'Required containers unavailable/unhealthy; NOT VERIFIED.'
            }
        } else { Record 'SKIP' 'Container-dependent probes' 'Compose prerequisite failed; NOT VERIFIED.' }
    }
    Record 'SKIP' 'Production HTTPS transport and cookies' 'NOT VERIFIED on local HTTP; verify real TLS deployment separately.'
    Record 'SKIP' 'Historical credential/log audit' 'NOT VERIFIED automatically; review access-controlled logs using the documented procedure.'
} catch {
    Record 'FAIL' 'Runner' ('Unexpected PowerShell failure (' + $_.Exception.GetType().Name + '); no raw exception output to avoid secrets.')
} finally {
    Pop-Location
    $passed = @($results | Where-Object { $_.Status -eq 'PASS' }).Count
    $failed = @($results | Where-Object { $_.Status -eq 'FAIL' }).Count
    $skipped = @($results | Where-Object { $_.Status -eq 'SKIP' }).Count
    Write-Host "`nSummary: PASS=$passed FAIL=$failed SKIP=$skipped TOTAL=$($results.Count)"
    Write-Host 'SKIP means NOT VERIFIED. Totals count probe groups, not individual Django assertions.'
}
if ($failed -gt 0) { exit 1 }
exit 0
