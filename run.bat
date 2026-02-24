@echo off
REM PROSPECT-AI — Lancement de l'application
REM Double-cliquez sur ce fichier pour démarrer

echo ========================================
echo   PROSPECT-AI — Demarrage...
echo ========================================

REM Vérification du fichier .env
if not exist .env (
    echo ATTENTION: Fichier .env manquant!
    echo Copiez .env.example en .env et ajoutez votre cle ANTHROPIC_API_KEY
    echo.
    copy .env.example .env
    echo Fichier .env cree depuis le modele. Editez-le maintenant.
    pause
    notepad .env
)

REM Installation des dépendances si nécessaire
echo Installation des dependances...
pip install -r requirements.txt -q

REM Lancement Streamlit
echo.
echo Lancement de PROSPECT-AI sur http://localhost:8501
echo Appuyez sur Ctrl+C pour arreter
echo.
streamlit run app.py --server.port 8501 --server.headless false

pause
