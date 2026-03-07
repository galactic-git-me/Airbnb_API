@echo off
echo Heartbeat script running at %time% on %date%
REM This is a placeholder for any actions you want to take when a new booking comes in
REM For example, you could add commands to flash LEDs, play sounds, etc.
echo Booking received! >> "%~dp0heartbeat_log.txt"
echo %date% %time% >> "%~dp0heartbeat_log.txt"
