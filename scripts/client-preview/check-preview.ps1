. (Join-Path $PSScriptRoot 'common.ps1')
try {
    Require-Docker
    $owned = @(Assert-Recorded)
    $containers = @($owned | Where-Object Kind -eq 'container')
    $snapshot = @{containers=@(); networks=@(); volumes=@()}
    foreach ($item in $owned) {
        $group = switch ($item.Kind) { container {'containers'} network {'networks'} volume {'volumes'} }
        $snapshot[$group] += @(Invoke-PreviewDocker @($item.Kind,'inspect',$item.Id.Split('|')[0]) | ConvertFrom-Json)[0]
    }
    $python = Join-Path $script:Root '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw 'BLOCKED: offline policy Python missing' }
    $snapshotFile = Join-Path (Split-Path $script:StateFile) ('inspect-' + [guid]::NewGuid().ToString('N') + '.json')
    $snapshot | ConvertTo-Json -Depth 40 | Set-Content -Encoding UTF8 -LiteralPath $snapshotFile
    & $python -B (Join-Path $PSScriptRoot 'inspect-policy.py') $snapshotFile $script:StateFile $script:Root
    if ($LASTEXITCODE -ne 0) { throw 'Inspect metadata policy failed; snapshot preserved' }
    $null = Assert-Recorded
    Add-Type -AssemblyName System.Net.Http
    $handler = [Net.Http.HttpClientHandler]::new()
    $handler.UseProxy = $false
    $handler.AllowAutoRedirect = $false
    $client = [Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(5)
    function Request([string]$Path,[int]$Expected,[string]$HostHeader='localhost',[string]$Method='GET') {
        $req = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::new($Method),"http://127.0.0.1:8765$Path")
        $req.Headers.Host = $HostHeader
        $null = $req.Headers.TryAddWithoutValidation('X-Forwarded-Host','attacker.invalid')
        $null = $req.Headers.TryAddWithoutValidation('X-Forwarded-Proto','https')
        $res = $client.SendAsync($req).GetAwaiter().GetResult()
        $body = $res.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if ([int]$res.StatusCode -ne $Expected -or $body -match 'Traceback|Technical 404|Environment:') { throw "HTTP check failed: $Path" }
        return $body
    }
    foreach ($path in @('/','/services/','/about/','/projects/','/contact/','/privacy/','/terms/','/static/css/style.css','/static/js/main.js')) { $null = Request $path 200 }
    foreach ($path in @('/admin/','/accounts/','/api/','/media/','/private/','/debug/','/metrics','/health/','/.env','/config/settings.py','/pgadmin/')) { $null = Request $path 404 }
    $null = Request '/' 400 'attacker.invalid'
    $null = Request '/' 400 'a.b.trycloudflare.com'
    $null = Request '/' 200 'synthetic-preview.trycloudflare.com'
    $null = Request '/contact/' 405 'localhost' 'POST'
    if ((Request '/contact/' 200) -match '<form') { throw 'Contact form unexpectedly enabled' }
    $web = @($containers | Where-Object Name -eq "$script:Project-web-1")[0]
    $null = Invoke-PreviewDocker @('exec',$web.Id,'python','-c',"import os; os.environ['DJANGO_SETTINGS_MODULE']='config.preview_settings'; from django.conf import settings; assert settings.DEBUG is False; assert settings.DATABASES['default']['ENGINE']=='django.db.backends.dummy'; assert settings.EMAIL_BACKEND=='django.core.mail.backends.dummy.EmailBackend'; assert settings.SECURE_PROXY_SSL_HEADER is None")
    $null = Invoke-PreviewDocker @('exec',$web.Id,'python','-c',"import os,stat; d=os.stat('/run/preview'); s=os.stat('/run/preview/gunicorn.sock'); assert (d.st_uid,d.st_gid,stat.S_IMODE(d.st_mode))==(10001,10002,0o2750); assert stat.S_ISSOCK(s.st_mode); assert (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))==(10001,10002,0o660); assert os.getuid()==10001 and os.getgid()==10002; status=open('/proc/self/status').read(); assert 'NoNewPrivs:\t1' in status; assert 'CapEff:\t0000000000000000' in status")
    $null = Assert-Recorded
    Write-Host 'PASS: local HTTP routes, hosts, forms, settings; observed socket permissions and exec security status'
    Write-Host 'INDETERMINATE: browser layout, public HTTPS, image provenance and absence of concurrent daemon mutation require separate review'
    exit 0
} catch {
    if ($_.Exception.Message -match 'BLOCKED|Docker CLI|Docker operation|ownership record') { Write-Host "INDETERMINATE: $($_.Exception.Message)" } else { Write-Host "FAIL: $($_.Exception.Message)" }
    exit 1
}
