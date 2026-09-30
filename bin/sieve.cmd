@echo off
rem Sieve launcher for Windows (cmd and PowerShell). Runs bin\sieve.py with the first Python it finds.
setlocal
set "SIEVE_BIN=%~dp0"
if defined SIEVE_PYTHON (
  "%SIEVE_PYTHON%" "%SIEVE_BIN%sieve.py" %*
) else (
  where python >nul 2>nul && (python "%SIEVE_BIN%sieve.py" %*) || (py -3 "%SIEVE_BIN%sieve.py" %*)
)
exit /b %ERRORLEVEL%
