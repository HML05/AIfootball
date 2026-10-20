@echo off
rem Pitch calibration launcher (ASCII only on purpose).
rem
rem Why English inside a .bat: cmd.exe parses the file in the console OEM codepage
rem (936/GBK on Chinese Windows), so a UTF-8 file with Chinese text makes it try to
rem execute mojibake fragments -- the user sees a wall of
rem "'...' is not recognized as an internal or external command". Keep this file
rem ASCII and let the Python side print the Chinese guidance (Python talks to the
rem console through WriteConsoleW, so Chinese shows up correctly there).
setlocal
cd /d "%~dp0.."
set "FRAME=%~1"
if "%FRAME%"=="" set "FRAME=0"
rem optional 2nd argument = anchor list. If one anchor is unreachable in this frame,
rem swap the list, e.g.
rem   scripts\vision_calibrate.bat 0 halfway_top,halfway_bottom,penalty_spot_right,pa_right_goal_top
set "ANCHORS=%~2"
if "%ANCHORS%"=="" set "ANCHORS=halfway_top,halfway_bottom,penalty_spot_right,goal_right_top,goal_right_bottom"
set "PY=.venv-vision\Scripts\python.exe"
set "VID=data\vision\videos\v2.mp4"
set "OUT=data\vision\calib\v2.json"
set "GRID=data\vision\calib\v2.grid.jpg"

echo.
echo   Pitch calibration - frame %FRAME%
echo.
echo   Anchors in click order: %ANCHORS%
echo.
echo   Default set (5 clicks; the program keeps the best 4 and validates with
echo   the rest, so one sloppy click does not ruin it):
echo     1) halfway line x TOP touchline (far side)      halfway_top
echo     2) halfway line x BOTTOM touchline (near side)  halfway_bottom
echo     3) RIGHT penalty spot (the painted dot)         penalty_spot_right
echo     4) RIGHT goal: base of the FAR post              goal_right_top
echo     5) RIGHT goal: base of the NEAR post             goal_right_bottom
echo.
echo   All five are long lines / painted dots / post bases -- no "16.5 m
echo   line corner" hunting. Zoom in with the wheel for the spot and posts.
echo.
echo   Mouse: left click = pick, WHEEL = zoom, RIGHT-DRAG = pan,
echo          u = undo last, r = reset, Esc = cancel
echo.
echo   THEN a check window appears: red outline / magenta penalty box /
echo   green halfway line must sit ON the real white lines.
echo     y = save     n = click again     Esc = cancel
echo   It refuses to save if any of those lines misses the paint.
echo.

if not exist "%PY%" goto nopy
if not exist "%VID%" goto novid

"%PY%" -u scripts\vision_calibrate.py --video "%VID%" --frame %FRAME% --anchors %ANCHORS% --out "%OUT%"
set "RC=%ERRORLEVEL%"

rem Exit 3 = the interpreter could not write the output folder. That happens when the
rem venv tree carries a "Low Mandatory Level" label, because a low-integrity process may
rem not write to medium-integrity files. Retry with the system Python (calibration only
rem needs numpy + cv2, not torch), and point at the permanent fix.
if "%RC%"=="3" goto retry
echo.
echo   Exit code %RC%  ^(0 = ok, 2 = points too clustered, 1 = other error^)
if exist "%GRID%" start "" "%GRID%"
goto done

:retry
echo.
echo   [!] the venv interpreter cannot write the output folder.
echo       retrying with the system Python 3.13 ...
set "PY2="
if exist "C:\Python313\python.exe" set "PY2=C:\Python313\python.exe"
if not defined PY2 for /f "delims=" %%i in ('where python 2^>nul') do if not defined PY2 set "PY2=%%i"
if not defined PY2 goto nopy2
"%PY2%" -u scripts\vision_calibrate.py --video "%VID%" --frame %FRAME% --anchors %ANCHORS% --out "%OUT%"
set "RC=%ERRORLEVEL%"
echo.
echo   Exit code %RC%  ^(from %PY2%^)
if "%RC%"=="0" echo   [i] permanent fix: run scripts\fix_venv_permissions.ps1 (needs admin, UAC)
if exist "%GRID%" start "" "%GRID%"
goto done

:nopy2
echo   [x] no system Python found either.
echo       permanent fix: run scripts\fix_venv_permissions.ps1 (needs admin, UAC)
goto done

:nopy
echo   [x] missing "%PY%"
echo       run: powershell -ExecutionPolicy Bypass -File scripts\vision_setup.ps1
goto done

:novid
echo   [x] missing "%VID%"
echo       put a football clip there named v2.mp4
goto done

:done
echo.
pause
