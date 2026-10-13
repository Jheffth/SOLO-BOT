param([switch]$SemDownload, [switch]$PrepararAtualizacao)
$ErrorActionPreference = 'Stop'
$raizBella = $PSScriptRoot
$cacheBella = Join-Path $raizBella '.cache'
$saidaBella = Join-Path $raizBella $(if ($PrepararAtualizacao) { 'dist\atualizacao\Bella' } else { 'dist\Bella' })
New-Item -ItemType Directory -Force -Path $cacheBella, $saidaBella | Out-Null
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Obter-Pacote($nome, $url, $sha) {
    $arquivoBella = Join-Path $cacheBella $nome
    if (-not (Test-Path -LiteralPath $arquivoBella)) {
        if ($SemDownload) { throw "Falta $nome na pasta de compilação." }
        Invoke-WebRequest -Uri $url -OutFile $arquivoBella -UseBasicParsing
    }
    if ((Get-FileHash -LiteralPath $arquivoBella -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha) {
        throw "O pacote $nome não corresponde à versão verificada. Compilação interrompida."
    }
    return $arquivoBella
}
$motorBella = Obter-Pacote 'vosk.zip' 'https://github.com/alphacep/vosk-api/releases/download/v0.3.45/vosk-win64-0.3.45.zip' 'f1dcc9cca460630f81ea8f71794f69c80bed6556d2a4e6237b5785e1d2dff34b'
$modeloBella = Obter-Pacote 'modelo.zip' 'https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip' '6e1ce909032e1afa7a88e68a3d628ecafff302bdf195befab308826c395e93b7'
Expand-Archive -LiteralPath $motorBella -DestinationPath (Join-Path $cacheBella 'motor') -Force
Expand-Archive -LiteralPath $modeloBella -DestinationPath (Join-Path $cacheBella 'modelo') -Force
Get-ChildItem -LiteralPath (Join-Path $cacheBella 'motor\vosk-win64-0.3.45') -Filter '*.dll' | Copy-Item -Destination $saidaBella -Force
New-Item -ItemType Directory -Force -Path (Join-Path $saidaBella 'modelo') | Out-Null
Get-ChildItem -LiteralPath (Join-Path $cacheBella 'modelo\vosk-model-small-pt-0.3') | Copy-Item -Destination (Join-Path $saidaBella 'modelo') -Recurse -Force

# WebView2 (desenha a tela da Bella). Pacote oficial da Microsoft no NuGet. Em vez de fixar
# o SHA256, cada DLL precisa ter assinatura digital válida da própria Microsoft.
$versaoWebView2 = '1.0.2903.40'
$pacoteWebView2 = Join-Path $cacheBella "webview2-$versaoWebView2.zip"
if (-not (Test-Path -LiteralPath $pacoteWebView2)) {
    if ($SemDownload) { throw "Falta o pacote WebView2 $versaoWebView2 na pasta de compilação." }
    Invoke-WebRequest -Uri "https://www.nuget.org/api/v2/package/Microsoft.Web.WebView2/$versaoWebView2" -OutFile $pacoteWebView2 -UseBasicParsing
}
$pastaWebView2 = Join-Path $cacheBella "webview2-$versaoWebView2"
Expand-Archive -LiteralPath $pacoteWebView2 -DestinationPath $pastaWebView2 -Force
function Obter-DllWebView2($padrao, $nome) {
    $achado = Get-ChildItem -LiteralPath $pastaWebView2 -Recurse -Filter $nome |
        Where-Object { $_.FullName -like $padrao } | Sort-Object FullName -Descending | Select-Object -First 1
    if ($null -eq $achado) { throw "O pacote WebView2 não tem $nome." }
    $assinatura = Get-AuthenticodeSignature -LiteralPath $achado.FullName
    if ($assinatura.Status -ne 'Valid' -or $assinatura.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
        throw "$nome não tem assinatura válida da Microsoft. Compilação interrompida."
    }
    return $achado.FullName
}
$coreWebView2 = Obter-DllWebView2 '*\lib\net4*' 'Microsoft.Web.WebView2.Core.dll'
$formsWebView2 = Obter-DllWebView2 '*\lib\net4*' 'Microsoft.Web.WebView2.WinForms.dll'
$loaderWebView2 = Obter-DllWebView2 '*\runtimes\win-x64\native\*' 'WebView2Loader.dll'
Copy-Item -LiteralPath $coreWebView2, $formsWebView2, $loaderWebView2 -Destination $saidaBella -Force

# A tela (HTML/CSS/JS) vai inteira, ao lado do Bella.exe.
$uiSaida = Join-Path $saidaBella 'ui'
if (Test-Path -LiteralPath $uiSaida) {
    $uiEsperada = [IO.Path]::GetFullPath((Join-Path $saidaBella 'ui'))
    if ((Resolve-Path -LiteralPath $uiSaida).Path -ne $uiEsperada) { throw 'Pasta de tela fora da saída de compilação.' }
    Remove-Item -LiteralPath $uiSaida -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $raizBella 'ui') -Destination $uiSaida -Recurse -Force

$compiladorBella = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiladorBella)) { throw 'A Bella precisa de Windows 64 bits com .NET Framework 4.8.' }
$fontesBella = (Get-ChildItem -LiteralPath $raizBella -Filter '*.cs').FullName
$falaBella = [Reflection.Assembly]::LoadWithPartialName('System.Speech')
if ($null -eq $falaBella) { throw 'O componente de voz do .NET Framework não está disponível.' }
& $compiladorBella /nologo /target:winexe /platform:x64 /optimize+ /codepage:65001 /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.Net.Http.dll /r:System.Web.Extensions.dll /r:System.Security.dll /r:Microsoft.VisualBasic.dll "/r:$($falaBella.Location)" "/r:$coreWebView2" "/r:$formsWebView2" "/out:$saidaBella\Bella.exe" $fontesBella
if ($LASTEXITCODE -ne 0) { throw 'Erro ao compilar a Bella.' }
Copy-Item -LiteralPath (Join-Path $raizBella 'LEIA-ME.md'), (Join-Path $raizBella 'TERCEIROS.md') -Destination $saidaBella -Force
$licencasBella = Join-Path $saidaBella 'licencas'
New-Item -ItemType Directory -Force -Path $licencasBella | Out-Null
foreach ($licencaBella in @(
    @('Apache-2.0.txt','https://www.apache.org/licenses/LICENSE-2.0.txt'),
    @('GCC-runtime-exception.txt','https://raw.githubusercontent.com/gcc-mirror/gcc/master/COPYING.RUNTIME'),
    @('GPL-3.0.txt','https://raw.githubusercontent.com/gcc-mirror/gcc/master/COPYING3')
)) {
    $arquivoLicenca = Join-Path $licencasBella $licencaBella[0]
    if (-not (Test-Path -LiteralPath $arquivoLicenca)) { Invoke-WebRequest -Uri $licencaBella[1] -OutFile $arquivoLicenca -UseBasicParsing }
}
$testeBella = Start-Process -FilePath (Join-Path $saidaBella 'Bella.exe') -ArgumentList '--self-test' -WorkingDirectory $saidaBella -WindowStyle Hidden -Wait -PassThru
if ($testeBella.ExitCode -ne 0) { Get-Content -LiteralPath (Join-Path $saidaBella 'self-test.txt'); throw 'O teste interno da Bella falhou.' }
Remove-Item -LiteralPath (Join-Path $saidaBella 'self-test.txt')
Compress-Archive -Path $saidaBella -DestinationPath (Join-Path $raizBella 'dist\Bella-Windows.zip') -Force
Write-Output "Bella compilada e testada: $saidaBella\Bella.exe"
