@echo off
cd /d C:\Users\GUNES\git\Etiket
python -c "from scraper.dogtas import run; run()" >> scraper.log 2>&1
