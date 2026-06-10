$ErrorActionPreference = "Stop"

$be = Start-Process -FilePath "python" -ArgumentList "-m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --log-level warning" -WorkingDirectory "C:\Users\cex\Desktop\sports_quant" -NoNewWindow -PassThru

$fe = Start-Process -FilePath "npx.cmd" -ArgumentList "next dev" -WorkingDirectory "C:\Users\cex\Desktop\sports_quant\frontend" -NoNewWindow -PassThru

Write-Host "Backend PID: $($be.Id)"
Write-Host "Frontend PID: $($fe.Id)"

while ($true) { Start-Sleep -Seconds 10 }
