@echo off
REM Build script for the reporting tool
set TARGET=staging
set VERSION=1.4.2
echo Building %VERSION% for %TARGET%
python -m build --outdir dist
echo Done.
