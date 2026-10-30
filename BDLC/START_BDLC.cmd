@echo off
rem BDLC: muhit -> paketlar -> testlar -> development benchmark (52 CTC GT/SEG xaritasi).
rem Natija: runs\<sana_vaqt>_development\  (status.json, comparison.csv, tables\, paper\ ...)
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] .venv yaratilmoqda...
  py -3.14 -m venv .venv 2>nul || python -m venv .venv || goto :fail
) else (
  echo [1/4] .venv mavjud
)

echo [2/4] Paketlar (requirements.txt, pin qilingan)...
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail

echo [3/4] Kodek muzlatilganini tekshirish va unit testlar...
".venv\Scripts\python.exe" tools\write_freeze.py --check || goto :fail
".venv\Scripts\python.exe" -m unittest discover -s tests -v || goto :fail

echo [4/4] Development benchmark (9 takror, CPU 2 ga pin)...
".venv\Scripts\python.exe" bench\run_bench.py --manifest ..\real_manifest.csv --split development --repeats 9 || goto :fail

echo.
echo TAYYOR. Natijalar runs\ papkasida.
exit /b 0

:fail
echo.
echo XATO: yuqoridagi qadam muvaffaqiyatsiz tugadi.
exit /b 1
