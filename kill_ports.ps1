foreach ($port in @(7777, 3000, 3001, 3002, 3003)) {
    $process = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
    if ($process) {
        $processInfo = Get-Process -Id $process -ErrorAction SilentlyContinue
        if ($processInfo) {
            Write-Host "Killing process $($processInfo.ProcessName) (PID: $process) on port $port"
            try {
                Stop-Process -Id $process -Force
                Write-Host "Successfully terminated process on port $port"
            } catch {
                Write-Host "Failed to kill process on port $port. Error: $_"
                Write-Host "Try running this script as Administrator"
            }
        }
    } else {
        Write-Host "No process found on port $port"
    }
}
