@echo off
REM ===========================================================================
REM  Ambilight Desktop - one-line installer build (Windows)
REM ===========================================================================
REM  Builds the PyInstaller service bundle AND the electron-builder NSIS
REM  installer for this OS in one shot (wraps `python build.py`).
REM
REM  Usage:
REM    build-installer              full build  -> ui\release\*.exe
REM    build-installer --service    service binary only
REM    build-installer --ui         app + installer only (service must exist)
REM    build-installer --gpu        bundle CuPy/CUDA + OpenCV (large GPU build)
REM
REM  Output: ui\release\Ambilight Desktop Setup <version>.exe (+ latest.yml)
REM ===========================================================================
setlocal
cd /d "%~dp0"
python build.py %*
exit /b %ERRORLEVEL%
