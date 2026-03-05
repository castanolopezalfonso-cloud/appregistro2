@echo off
:: Esto asegura que el script se ejecute en su propia carpeta
cd /d "%~dp0"
title Lanzador Control Fluge

echo ----------------------------------------------
echo Verificando entorno de ejecucion...
echo ----------------------------------------------

:: Si no existe el entorno virtual, lo creamos
if not exist "env_fluge" (
    echo Creando entorno virtual limpio...
    python -m venv env_fluge
)

:: Activamos el entorno e instalamos las dependencias
echo Cargando librerias...
call env_fluge\Scripts\activate

:: Forzamos la instalacion buscando el archivo en la ruta actual
python -m pip install --upgrade pip
pip install -r "%~dp0requirements.txt"

echo ----------------------------------------------
echo Lanzando App en el navegador...
echo ----------------------------------------------
streamlit run app.py

pause