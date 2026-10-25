Write-Host "==========================================" -ForegroundColor Green
Write-Host "Demarrage du serveur Django (VersLeVert)..." -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Application:    http://127.0.0.1:8000/" -ForegroundColor Cyan
Write-Host "Administration: http://127.0.0.1:8000/admin/" -ForegroundColor Cyan

.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
