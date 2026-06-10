$be = Start-Process -FilePath "python" -ArgumentList "-m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --log-level warning" -WorkingDirectory "C:\Users\cex\Desktop\sports_quant" -WindowStyle Hidden -PassThru
Write-Host "Backend started (PID: $($be.Id))"
$fe = Start-Process -FilePath "cmd.exe" -ArgumentList "/c npm run dev" -WorkingDirectory "C:\Users\cex\Desktop\sports_quant\frontend" -WindowStyle Hidden -PassThru
Write-Host "Frontend started (PID: $($fe.Id))"
Write-Host "Waiting for servers to initialize..."
Start-Sleep -Seconds 8
Write-Host "Checking ports..."
netstat -ano | Select-String ":8000" | Select-String "LISTENING"
netstat -ano | Select-String ":3000" | Select-String "LISTENING"
