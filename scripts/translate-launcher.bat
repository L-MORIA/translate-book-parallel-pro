@echo off
chcp 65001 >nul
title translate-book-parallel-pro — Перевод книг

:: ============================================================
:: translate-book-parallel-pro — Лаунчер перевода книг
:: Поддерживаемые форматы: EPUB, PDF, DOCX, TXT
:: Результат: EPUB + DOCX + PDF + HTML
:: ============================================================

setlocal enabledelayedexpansion

set "REPO_DIR=%~dp0.."
set "SCRIPTS_DIR=%REPO_DIR%\scripts"
set "OUTPUT_ROOT=%REPO_DIR%\translations"

:: ─── Цвета ───────────────────────────────────────────────────
set "ESC=["
set "GREEN=%ESC%92m"
set "CYAN=%ESC%96m"
set "YELLOW=%ESC%93m"
set "RED=%ESC%91m"
set "BOLD=%ESC%1m"
set "RESET=%ESC%0m"

:: ─── Заголовок ───────────────────────────────────────────────
cls
echo.
echo %BOLD%%CYAN%╔══════════════════════════════════════════════════╗%RESET%
echo %BOLD%%CYAN%║      translate-book-parallel-pro — v1.0        ║%RESET%
echo %BOLD%%CYAN%║         Перевод книг через ИИ (Hermes)         ║%RESET%
echo %BOLD%%CYAN%╚══════════════════════════════════════════════════╝%RESET%
echo.

:: ─── Ввод файла ──────────────────────────────────────────────
:input_file
set "INPUT_FILE=%1"
if "%INPUT_FILE%"=="" (
    echo %BOLD%Перетащите файл в это окно или введите путь:%RESET%
    echo %YELLOW%Поддерживаемые форматы: EPUB, PDF, DOCX, TXT%RESET%
    echo.
    set /p "INPUT_FILE=^> "
    echo.
)

:: Удаляем кавычки если были
set "INPUT_FILE=%INPUT_FILE:"=%"

if not exist "%INPUT_FILE%" (
    echo %RED%Ошибка: файл не найден!%RESET%
    echo.
    goto input_file
)

:: ─── Определяем формат ───────────────────────────────────────
set "EXT=%~x1"
if "%EXT%"=="" set "EXT=%~xINPUT_FILE%"
set "EXT=%EXT:.=%"
set "EXT=%EXT: =%"

echo %CYAN%Файл: %BOLD%%~nxINPUT_FILE%%RESET%
echo %CYAN%Формат: %BOLD%%EXT%%RESET%

:: Проверка поддержки
echo %EXT% | findstr /i "epub pdf docx txt" >nul
if errorlevel 1 (
    echo %RED%Формат .%EXT% не поддерживается.%RESET%
    echo %YELLOW%Поддерживаются: EPUB, PDF, DOCX, TXT%RESET%
    pause
    exit /b 1
)
echo.

:: ─── Язык перевода ────────────────────────────────────────────
:input_lang
echo %BOLD%Язык перевода (код):%RESET%
echo  %GREEN%ru%RESET% — русский    %GREEN%en%RESET% — английский
echo  %GREEN%zh%RESET% — китайский  %GREEN%de%RESET% — немецкий
echo  %GREEN%fr%RESET% — французский %GREEN%es%RESET% — испанский
echo  %GREEN%ja%RESET% — японский   %GREEN%ko%RESET% — корейский
echo.
set /p "TARGET_LANG=^> "
if "%TARGET_LANG%"=="" set "TARGET_LANG=ru"
echo.

:: ─── Название книги ──────────────────────────────────────────
set "BOOK_NAME=%~nINPUT_FILE%"
echo %CYAN%Название книги: %BOLD%%BOOK_NAME%%RESET%
echo.

:: ─── Создаём папку результата ────────────────────────────────
for /f "skip=1" %%d in ('wmic os get localdatetime') do if not defined DT set "DT=%%d"
set "TIMESTAMP=%DT:~0,4%-%DT:~4,2%-%DT:~6,2%_%DT:~8,2%-%DT:~10,2%-%DT:~12,2%"
set "OUT_DIR=%OUTPUT_ROOT%\%BOOK_NAME%_%TIMESTAMP%"
mkdir "%OUT_DIR%" 2>nul

echo %YELLOW%Результат будет сохранён в:%RESET%
echo %BOLD%%OUT_DIR%%RESET%
echo.

:: ─── Шаг 1: Конвертация ──────────────────────────────────────
echo %BOLD%%CYAN%[1/2] Конвертация в чанки...%RESET%
echo.

set "START_TIME=%TIME%"
echo %YELLOW%Старт: %START_TIME%%RESET%
echo.

call "%SCRIPTS_DIR%\convert.py" "%INPUT_FILE%" --olang %TARGET_LANG% --temp-root "%OUT_DIR%"
if errorlevel 1 (
    echo %RED%Ошибка конвертации!%RESET%
    pause
    exit /b 1
)

echo.
echo %GREEN%✅ Конвертация завершена.%RESET%
echo.

:: ─── Определяем имя temp папки ───────────────────────────────
:: convert.py создаёт <имя>_temp внутри OUT_DIR
set "TEMP_DIR=%OUT_DIR%\%BOOK_NAME%_temp"

:: Считаем чанки
set "CHUNK_COUNT=0"
if exist "%TEMP_DIR%\manifest.json" (
    for /f "usebackq" %%c in (`python -c "import json; print(len(json.load(open(r'%TEMP_DIR:\=\\%\\manifest.json'))))" 2^>nul ^|^| echo 0`) do set "CHUNK_COUNT=%%c"
)

if %CHUNK_COUNT% gtr 0 (
    echo %CYAN%Создано %BOLD%%CHUNK_COUNT%%RESET%%CYAN% чанков по ~15000 символов.%RESET%
    echo.
)

:: ─── Инструкция для перевода ─────────────────────────────────
echo %BOLD%%YELLOW%╔══════════════════════════════════════════════════════════╗%RESET%
echo %BOLD%%YELLOW%║            ТРЕБУЕТСЯ ПЕРЕВОД ЧЕРЕЗ HERMES             ║%RESET%
echo %BOLD%%YELLOW%╚══════════════════════════════════════════════════════════╝%RESET%
echo.
echo %CYAN%Сейчас нужно перевести чанки через Hermes.%RESET%
echo %CYAN%Скажите агенту в чате:%RESET%
echo.
echo %BOLD%  Переведи книгу из папки "%TEMP_DIR%" на %TARGET_LANG% языке%RESET%
echo.
echo %YELLOW%После выполнения перевода нажмите любую клавишу для сборки финальных файлов...%RESET%
pause >nul

:: ─── Шаг 2: Сборка ────────────────────────────────────────────
echo.
echo %BOLD%%CYAN%[2/2] Сборка финальных форматов...%RESET%
echo.

call "%SCRIPTS_DIR%\merge_and_build.py" --temp-dir "%TEMP_DIR%" --title "%BOOK_NAME%" --cleanup
if errorlevel 1 (
    echo %RED%Ошибка сборки! Возможно перевод ещё не завершён.%RESET%
    pause
    exit /b 1
)

:: ─── Копируем результат ──────────────────────────────────────
if exist "%TEMP_DIR%\book.epub" (
    move "%TEMP_DIR%\book.epub" "%OUT_DIR%\" >nul 2>&1
    move "%TEMP_DIR%\book.docx" "%OUT_DIR%\" >nul 2>&1
    move "%TEMP_DIR%\book.pdf" "%OUT_DIR%\" >nul 2>&1
    move "%TEMP_DIR%\book.html" "%OUT_DIR%\" >nul 2>&1
    move "%TEMP_DIR%\book_doc.html" "%OUT_DIR%\" >nul 2>&1
)

:: ─── ФИНИШ ────────────────────────────────────────────────────
set "END_TIME=%TIME%"

echo.
echo %BOLD%%GREEN%╔══════════════════════════════════════════════════╗%RESET%
echo %BOLD%%GREEN%║                 ПЕРЕВОД ГОТОВ!                ║%RESET%
echo %BOLD%%GREEN%╚══════════════════════════════════════════════════╝%RESET%
echo.
echo %CYAN%Папка с результатом:%RESET%
echo %BOLD%%OUT_DIR%%RESET%
echo.
echo %BOLD%Файлы:%RESET%
dir "%OUT_DIR%\book.*" /b 2>nul | findstr /v "_temp"
echo.
echo %CYAN%Старт: %START_TIME%%RESET%
echo %CYAN%Финиш: %END_TIME%%RESET%
echo.

explorer "%OUT_DIR%"

echo %YELLOW%Нажмите Enter для выхода...%RESET%
pause >nul
exit /b 0
