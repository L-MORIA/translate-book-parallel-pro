@echo off
chcp 65001 >nul
title Translate Book Pro

:: ============================================================
:: Translate Book Parallel Pro — Launcher
:: Supported: EPUB, PDF, DOCX, TXT
:: Output: EPUB + DOCX + PDF + HTML
:: ============================================================

setlocal enabledelayedexpansion

set "REPO_DIR=%~dp0.."
set "SCRIPTS_DIR=%REPO_DIR%\scripts"
set "OUTPUT_ROOT=%REPO_DIR%\translations"

:: ─── Header ──────────────────────────────────────────────────
cls
echo.
echo ============================================
echo   translate-book-parallel-pro  v1.0
echo   AI-powered book translation (Hermes)
echo ============================================
echo.

:: ─── Input file ──────────────────────────────────────────────
:input_file
set "INPUT_FILE=%1"
if "%INPUT_FILE%"=="" (
    echo Drop a file here or type the path:
    echo Formats: EPUB, PDF, DOCX, TXT
    echo.
    set /p "INPUT_FILE=^> "
    echo.
)

set "INPUT_FILE=%INPUT_FILE:"=%"

if not exist "%INPUT_FILE%" (
    echo Error: file not found!
    echo.
    goto input_file
)

:: ─── Detect format ───────────────────────────────────────────
set "EXT=%~xINPUT_FILE%"
set "EXT=%EXT:.=%"

echo File: %~nxINPUT_FILE%
echo Format: %EXT%

echo %EXT% | findstr /i "epub pdf docx txt" >nul
if errorlevel 1 (
    echo Format .%EXT% not supported.
    echo Supported: EPUB, PDF, DOCX, TXT
    pause
    exit /b 1
)
echo.

:: ─── Target language ─────────────────────────────────────────
:input_lang
echo Target language code:
echo   ru  = Russian     en  = English
echo   zh  = Chinese     de  = German
echo   fr  = French      es  = Spanish
echo   ja  = Japanese    ko  = Korean
echo.
set /p "TARGET_LANG=^> "
if "%TARGET_LANG%"=="" set "TARGET_LANG=ru"
echo.

:: ─── Book name ───────────────────────────────────────────────
set "BOOK_NAME=%~nINPUT_FILE%"
echo Book: %BOOK_NAME%
echo.

:: ─── Create output dir ───────────────────────────────────────
for /f %%d in ('wmic os get localdatetime ^| findstr /r "^"') do set "DT=%%d" 2>nul
if "%DT%"=="" for /f "tokens=2 delims==" %%d in ('wmic os get localdatetime /format:value') do set "DT=%%d"
set "TIMESTAMP=%DT:~0,4%-%DT:~4,2%-%DT:~6,2%_%DT:~8,2%-%DT:~10,2%"
set "OUT_DIR=%OUTPUT_ROOT%\%BOOK_NAME%_%TIMESTAMP%"
md "%OUT_DIR%" 2>nul

echo Output: %OUT_DIR%
echo.

:: ─── Step 1: Convert ─────────────────────────────────────────
echo [1/2] Converting to chunks...
echo.

set "START_TIME=%TIME%"
echo Started: %START_TIME%
echo.

call "%SCRIPTS_DIR%\convert.py" "%INPUT_FILE%" --olang %TARGET_LANG% --temp-root "%OUT_DIR%"
if errorlevel 1 (
    echo Conversion failed!
    pause
    exit /b 1
)

echo.
echo Done - conversion complete.
echo.

:: ─── Pause for Hermes translation ────────────────────────────
echo ============================================
echo   NOW TRANSLATE VIA HERMES AGENT
echo ============================================
echo.
echo Tell the agent in chat:
echo.
echo   Translate the book in "%OUT_DIR%\%BOOK_NAME%_temp" to %TARGET_LANG%
echo.
echo When done, press any key...
pause >nul

:: ─── Step 2: Build ───────────────────────────────────────────
echo.
echo [2/2] Building output formats...
echo.

set "TEMP_DIR=%OUT_DIR%\%BOOK_NAME%_temp"
call "%SCRIPTS_DIR%\merge_and_build.py" --temp-dir "%TEMP_DIR%" --title "%BOOK_NAME%" --cleanup
if errorlevel 1 (
    echo Build failed - translation may not be complete yet.
    pause
    exit /b 1
)

:: ─── Move results ────────────────────────────────────────────
if exist "%TEMP_DIR%\book.epub" (
    move "%TEMP_DIR%\book.epub" "%OUT_DIR%\" >nul 2>&1
    move "%TEMP_DIR%\book.docx" "%OUT_DIR%\" >nul 2>&1
    move "%TEMP_DIR%\book.pdf"  "%OUT_DIR%\" >nul 2>&1
    move "%TEMP_DIR%\book.html" "%OUT_DIR%\" >nul 2>&1
)

:: ─── Finish ──────────────────────────────────────────────────
set "END_TIME=%TIME%"

echo.
echo ============================================
echo        TRANSLATION COMPLETE!
echo ============================================
echo.
echo Folder: %OUT_DIR%
echo.
echo Files:
dir "%OUT_DIR%\book.*" /b 2>nul
echo.
echo Started: %START_TIME%
echo Ended:   %END_TIME%
echo.

start explorer "%OUT_DIR%"

echo Press Enter to exit...
pause >nul
exit /b 0
