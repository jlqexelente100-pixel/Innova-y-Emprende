# 🚀 Guía para levantar el proyecto (demo)

Pasos para clonar **Innova y Emprende** y levantar todo con Docker para ver el front y todos los servicios.

## Requisitos previos
- **Docker Desktop** instalado y **abierto** (debe estar corriendo).
- Git.

## Pasos

### 1. Clonar el repo
```bash
git clone https://github.com/jlqexelente100-pixel/Innova-y-Emprende.git
cd Innova-y-Emprende
```

### 2. Colocar el `.env`
Pegá el archivo `.env` (el que les pasaron) **en la raíz del proyecto**, al lado de `docker-compose.yml`.

> ⚠️ Es obligatorio: el `docker-compose.yml` tiene `env_file: .env`, así que **si falta el `.env`, `docker compose` ni arranca**.

### 3. Levantar todo con un solo comando
```bash
docker compose up --build
```

Esto levanta los **2 servicios**:

| Servicio | Qué es | Puerto |
|----------|--------|--------|
| `web` | App Flask (el front + backend) | **5000** |
| `db` | PostgreSQL (base `Emprende`) | 5432 |

La **primera vez** tarda un poco: descarga la imagen `python:3.11`, instala el `requirements.txt` y Postgres inicializa la base. Al arrancar, la app **crea las tablas sola y carga datos demo** (cursos, lecciones, usuarios) — no hay que correr migraciones ni nada manual.

### 4. Abrir el front
👉 **http://localhost:5000**

### 5. Usuarios demo para iniciar sesión (ya vienen sembrados)

| Rol | Correo | Contraseña |
|-----|--------|-----------|
| Admin | `admin@demo.test` | `admin123` |
| Profesor | `profesor@demo.test` | `profesor123` |

También se puede registrar un alumno nuevo desde la pantalla de registro.

## Para apagar
```bash
docker compose down          # detiene y elimina los contenedores (la BD se conserva)
docker compose down -v       # además borra la base de datos (empieza de cero)
```

---

## ⚠️ Detalle del primer arranque
Como `web` y `db` arrancan casi a la vez, a veces la app intenta conectarse **antes** de que Postgres termine de inicializar y muestra un error de conexión. Si pasa, simplemente:

```bash
docker compose restart web
```

y listo (Postgres ya estará listo en el segundo intento).
