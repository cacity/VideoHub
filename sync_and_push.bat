@echo off
REM Check if the current directory is a Git repository
git rev-parse --is-inside-work-tree 1>nul 2>nul
IF %ERRORLEVEL% NEQ 0 (
    echo This directory is not a Git repository.
    exit /b 1
)

REM Stage all changes
echo Staging all changes...
git add .

REM Commit changes with a default message
echo Committing changes...
set /p commit_message="Enter commit message (default: 'Sync changes'): "
IF "%commit_message%"=="" (
    set commit_message=Sync changes
)
git commit -m "%commit_message%"

REM Push changes to the remote repository
echo Pushing changes to the remote repository...
git push origin

REM Check if the push was successful
IF %ERRORLEVEL% EQU 0 (
    echo Changes pushed successfully.
) ELSE (
    echo Failed to push changes.
    exit /b 1
)

echo Script completed.
exit /b 0
