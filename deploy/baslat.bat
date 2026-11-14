@echo off
REM Forex botunu baslatir; kapanirsa 30 sn sonra yeniden acar.
REM Windows bilgisayarda / Windows VPS te: bu dosyaya cift tikla,
REM ya da Gorev Zamanlayici ile "oturum acildiginda" calistir.
cd /d "%~dp0.."
if not exist bot_data mkdir bot_data
:dongu
call .venv\Scripts\activate.bat
python -u -m borsa_bot calistir >> bot_data\log.txt 2>&1
echo Bot kapandi, 30 sn sonra yeniden basliyor...
timeout /t 30 /nobreak >nul
goto dongu
