@echo off
echo ==========================================
echo Demarrage du serveur Django (VersLeVert)...
echo ==========================================
call venv\Scripts\activate.bat
echo L'application sera disponible sur http://127.0.0.1:8000/
echo Administration : http://127.0.0.1:8000/admin/
python manage.py runserver 127.0.0.1:8000
pause
