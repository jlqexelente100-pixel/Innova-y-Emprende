# Imagen base oficial de Python
FROM python:3.11

# Carpeta de trabajo dentro del contenedor
WORKDIR /app

# Copiar archivos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el proyecto
COPY . .

# Puerto que usará Flask
EXPOSE 5000

# Comando para ejecutar la app
CMD ["python", "app.py"]