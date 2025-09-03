# This script starts the Python health dashboard server in the background using a full, explicit path.

# Set the script's location to the current directory to ensure files are found.
Set-Location $PSScriptRoot

# --- ACTION REQUIRED ---
# Replace the placeholder below with the full path to your py.exe from the 'where.exe py' command.
$pythonExecutablePath = "C:\Windows\py.exe"


# --- No changes needed below this line ---
$scriptToRun = "health_dashboard_final.py"
$scriptArguments = "serve"

# Start the Python script as a hidden background process using the full path.
Start-Process -FilePath $pythonExecutablePath -ArgumentList "$scriptToRun $scriptArguments" -WindowStyle Hidden

Write-Host "Health dashboard server has been started in the background."