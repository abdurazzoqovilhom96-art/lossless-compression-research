# Protokol B eksperimenti: boshidan oxirigacha (hajm + tezlik + natijalar). Ishga tushirish: .\START_B.ps1
$docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
if (-not (Test-Path $docker)) { $docker = "docker" }
& $docker run --rm --name bdlc-B --cap-add SYS_NICE --mount "type=bind,source=$PSScriptRoot,target=/proj" bdlc-bench:2026-10-29 bash /proj/BDLC/docker/run_B.sh run
