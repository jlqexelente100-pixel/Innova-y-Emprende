# init_db.py
# Script para crear/verificar las tablas en la base de datos de producción (Render).
#
# CÓMO USARLO:
# 1. Sube este archivo junto a app.py en tu repositorio.
# 2. Despliega normalmente en Render con el Start Command: gunicorn app:app
# 3. Una vez que el deploy esté activo, ve a tu Web Service en Render -> pestaña "Shell"
# 4. Ejecuta:
#       python init_db.py
# 5. Esto creará todas las tablas y los datos de demo (cursos, profesor demo, admin demo).
# 6. Solo necesitas correrlo UNA VEZ (o cada vez que agregues una tabla nueva,
#    ya que las queries usan "CREATE TABLE IF NOT EXISTS").

from app import crear_tablas

if __name__ == "__main__":
    print("Iniciando creación/verificación de tablas...")
    crear_tablas()
    print("Listo. Tablas verificadas/creadas correctamente.")