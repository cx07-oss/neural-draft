$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Add-Type -AssemblyName System.Speech
$narrator = New-Object System.Speech.Synthesis.SpeechSynthesizer
$narrator.SelectVoice('Microsoft Catherine')
$narrator.Rate = 2
$narrator.Volume = 100
$scenes = Get-Content -LiteralPath 'scenes.json' -Raw -Encoding UTF8 | ConvertFrom-Json
for ($i = 0; $i -lt $scenes.Count; $i++) {
    $path = Join-Path $PSScriptRoot ('audio/{0:D2}.wav' -f ($i + 1))
    $narrator.SetOutputToWaveFile($path)
    $narrator.Speak($scenes[$i].narration)
    $narrator.SetOutputToNull()
}
$narrator.Dispose()
Write-Output ('Generated {0} narration segments with an offline synthetic voice.' -f $scenes.Count)
