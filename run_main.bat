@echo off
REM Create venv, install requirements, ensure ffmpeg is available, then run main.py
SETLOCAL ENABLEDELAYEDEXPANSION
REM create venv if missing
if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate

REM install python requirements
pip install -r requirements.txt

REM Check for ffmpeg on PATH
where ffmpeg >nul 2>nul
if %ERRORLEVEL%==0 (
    echo ffmpeg found on PATH
) else (
    echo ffmpeg not found on PATH. Attempting automatic install...

    REM Try winget first
    powershell -NoProfile -Command "if (Get-Command winget -ErrorAction SilentlyContinue) { try { winget install --id Gyan.FFmpeg -e -h } catch { exit 1 } } else { exit 2 }"
    if %ERRORLEVEL%==0 (
        echo Installed ffmpeg with winget.
    ) else (
        REM Try chocolatey
        powershell -NoProfile -Command "if (Get-Command choco -ErrorAction SilentlyContinue) { try { choco install ffmpeg -y } catch { exit 1 } } else { exit 2 }"
        if %ERRORLEVEL%==0 (
            echo Installed ffmpeg with chocolatey.
        ) else (
            REM Fallback: download portable build and extract ffmpeg.exe into vendor\ffmpeg
            echo Downloading portable ffmpeg and extracting to vendor\ffmpeg ...
            powershell -NoProfile -Command "try{ $url='https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'; $out=Join-Path $env:TEMP 'ffmpeg_portable.zip'; Invoke-WebRequest -Uri $url -OutFile $out; $extract=Join-Path $env:TEMP 'ffmpeg_extract'; if(Test-Path $extract){ Remove-Item -Recurse -Force $extract } Expand-Archive -Path $out -DestinationPath $extract; $exe=Get-ChildItem -Path $extract -Recurse -Filter 'ffmpeg.exe' | Select-Object -First 1; if($exe){ $dest=Join-Path (Join-Path (Get-Location) 'vendor') 'ffmpeg'; New-Item -ItemType Directory -Path $dest -Force | Out-Null; Copy-Item $exe.FullName -Destination (Join-Path $dest 'ffmpeg.exe') -Force; Write-Output 'ok' } else { Write-Error 'ffmpeg.exe not found in archive'; exit 3 } } catch { exit 4 }"
            if %ERRORLEVEL%==0 (
                echo Portable ffmpeg downloaded.
                REM add vendor\ffmpeg to PATH for this session
                set "PATH=%CD%\vendor\ffmpeg;%PATH%"
            ) else (
                echo Failed to install ffmpeg automatically. Please install ffmpeg manually and ensure it's on PATH.
            )
        )
    )
)

REM Run main.py with any provided args
python main.py %*
ENDLOCAL
