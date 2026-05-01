Set-Location $PSScriptRoot

$streamlitHome = Join-Path $PSScriptRoot "data\streamlit_home"
$streamlitConfig = Join-Path $streamlitHome ".streamlit"
$streamlitTemp = Join-Path $PSScriptRoot "data\streamlit_tmp"

New-Item -ItemType Directory -Force -Path $streamlitConfig | Out-Null
New-Item -ItemType Directory -Force -Path $streamlitTemp | Out-Null

$env:HOME = $streamlitHome
$env:USERPROFILE = $streamlitHome
$env:TMP = $streamlitTemp
$env:TEMP = $streamlitTemp
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = "false"
$env:PYTHONDONTWRITEBYTECODE = "1"

.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
