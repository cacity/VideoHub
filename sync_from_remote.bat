@echo off
REM Check if the current directory is a Git repository
git rev-parse --is-inside-work-tree 1>nul 2>nul
IF %ERRORLEVEL% NEQ 0 (
    echo This directory is not a Git repository.
    exit /b 1
)

REM Fetch the latest changes from the remote repository
echo Fetching the latest changes from the remote repository...
git fetch origin

REM Check if fetch was successful
IF %ERRORLEVEL% NEQ 0 (
    echo Failed to fetch changes.
    exit /b 1
)

REM Reset the local branch to match the remote branch
echo Resetting the local branch to match the remote branch...
git reset --hard origin/main

REM Check if reset was successful
IF %ERRORLEVEL% EQU 0 (
    echo Local branch successfully reset to match the remote branch.
) ELSE (
    echo Failed to reset local branch.
    exit /b 1
)

echo Script completed.
exit /b 0
