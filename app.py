from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__, static_folder="static")
app.secret_key = "CAMBIA_ESTA_CLAVE_POR_ALGO_SEGURO"



######se actualiza datos #########33
# -------------------------
# CONFIGURACIÓN BD (POSTGRES)
# Ajusta los valores según tu entorno pgAdmin4
# -------------------------
DB_CONFIG = {
    'host': 'localhost',
    'database': 'plataforma_cursos',
    'user': 'postgres',
    'password': '123456',
    'port': 5432
}

# Ruta local del archivo de imagen subido (proporcionado por ti)
DEFAULT_IMAGE_PATH = "/mnt/data/IMG_B80A0F22-F08C-4BFA-B5F6-421E434D56D6.jpeg"

def conectar_bd():
    try:
        conexion = psycopg2.connect(**DB_CONFIG)
        return conexion
    except Exception as e:
        print("Error al conectar a la BD:", e)
        return None

# -----------------------------------
# Crear tablas si no existen
# -----------------------------------
def crear_tablas():
    conn = conectar_bd()
    if not conn:
        return
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nombre TEXT NOT NULL,
            correo TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            rol TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cursos (
            id SERIAL PRIMARY KEY,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            precio NUMERIC,
            imagen_url TEXT,
            profesor_id INTEGER REFERENCES usuarios(id),
            creado_en TIMESTAMP DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lecciones (
            id SERIAL PRIMARY KEY,
            curso_id INTEGER REFERENCES cursos(id),
            titulo TEXT,
            video_url TEXT,
            contenido TEXT,
            creado_en TIMESTAMP DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS metodos_pago (
            id SERIAL PRIMARY KEY,
            nombre TEXT,
            tipo TEXT,
            habilitado BOOLEAN DEFAULT TRUE
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id),
            curso_id INTEGER REFERENCES cursos(id),
            metodo_pago_id INTEGER REFERENCES metodos_pago(id),
            monto NUMERIC,
            estado TEXT,
            fecha TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()

    # Insertar un método de pago de ejemplo si la tabla está vacía
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM metodos_pago;")
    count = cur.fetchone()[0]
    if count == 0:
        cur.execute("INSERT INTO metodos_pago(nombre, tipo, habilitado) VALUES (%s,%s,%s), (%s,%s,%s);",
                    ("Stripe (tarjeta)","tarjeta",True, "Transferencia Bancaria","transferencia",True))
        conn.commit()

    # Insertar un curso de ejemplo si no hay cursos
    cur.execute("SELECT COUNT(*) FROM cursos;")
    ccount = cur.fetchone()[0]
    if ccount == 0:
        # crear un profesor ejemplo
        cur.execute("SELECT id FROM usuarios WHERE correo = %s;", ("profesor@demo.test",))
        r = cur.fetchone()
        if not r:
            phash = generate_password_hash("profesor123")
            cur.execute("INSERT INTO usuarios(nombre, correo, password_hash, rol) VALUES (%s,%s,%s,%s) RETURNING id;",
                        ("Profesor Demo","profesor@demo.test", phash, "profesor"))
            profesor_id = cur.fetchone()[0]
        else:
            profesor_id = r[0]

        cur.execute("""
            INSERT INTO cursos(titulo, descripcion, precio, imagen_url, profesor_id)
            VALUES (%s,%s,%s,%s,%s);
        """, ("Introducción a Python", "Curso demo de Python para principiantes", 9.99, DEFAULT_IMAGE_PATH, profesor_id))
        conn.commit()

    cur.close()
    conn.close()
    print("Tablas creadas/verificadas y datos iniciales insertados (si hacía falta).")

crear_tablas()

# --------------------------
# RUTAS DE FRONTEND (HTML)
# --------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    # POST: validar
    correo = request.form.get("correo")
    password = request.form.get("password")
    conn = conectar_bd()
    if not conn:
        flash("No se pudo conectar a la base de datos.")
        return redirect(url_for("login"))
    cur = conn.cursor()
    cur.execute("SELECT id, nombre, password_hash, rol FROM usuarios WHERE correo = %s;", (correo,))
    r = cur.fetchone()
    cur.close()
    conn.close()
    if not r:
        flash("Usuario no encontrado.")
        return redirect(url_for("login"))
    user_id, nombre, password_hash, rol = r
    if not check_password_hash(password_hash, password):
        flash("Contraseña incorrecta.")
        return redirect(url_for("login"))
    # Login correcto: guardar en session
    session["user_id"] = user_id
    session["nombre"] = nombre
    session["rol"] = rol
    flash("Bienvenido/a " + nombre)
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada.")
    return redirect(url_for("index"))

@app.route("/registrar", methods=["GET","POST"])
def registrar():
    if request.method == "GET":
        return render_template("registrar.html")
    nombre = request.form.get("nombre")
    correo = request.form.get("correo")
    password = request.form.get("password")
    rol = request.form.get("rol") or "alumno"
    password_hash = generate_password_hash(password)

    conn = conectar_bd()
    if not conn:
        flash("Error de conexión.")
        return redirect(url_for("registrar"))
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO usuarios(nombre, correo, password_hash, rol) VALUES (%s,%s,%s,%s);",
                    (nombre, correo, password_hash, rol))
        conn.commit()
    except Exception as e:
        conn.rollback()
        flash("Error al registrar: " + str(e))
        cur.close()
        conn.close()
        return redirect(url_for("registrar"))
    cur.close()
    conn.close()
    flash("Registrado correctamente. Inicia sesión.")
    return redirect(url_for("login"))

# --------------------------
# API: Obtener cursos (JSON)
# --------------------------
@app.route("/cursos")
def api_cursos():
    conn = conectar_bd()
    if not conn:
        return jsonify({"error":"No hay conexión"}), 500
    cur = conn.cursor()
    cur.execute("SELECT id, titulo, descripcion, precio, imagen_url FROM cursos ORDER BY creado_en DESC;")
    filas = cur.fetchall()
    cur.close()
    conn.close()
    cursos = []
    for f in filas:
        cursos.append({
            "id": f[0],
            "titulo": f[1],
            "descripcion": f[2],
            "precio": float(f[3]) if f[3] is not None else 0,
            "imagen_url": f[4] or ""
        })
    return jsonify(cursos)

# --------------------------
# Panel profesor: ver cursos propios
# --------------------------
def requiere_profesor():
    return session.get("rol") == "profesor"

@app.route("/profesor/dashboard")
def profesor_dashboard():
    if not session.get("user_id") or not requiere_profesor():
        flash("Acceso restringido. Debes iniciar sesión como profesor.")
        return redirect(url_for("login"))
    profesor_id = session["user_id"]
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("SELECT id, titulo, descripcion, precio, imagen_url FROM cursos WHERE profesor_id = %s;", (profesor_id,))
    filas = cur.fetchall()
    cur.close()
    conn.close()
    cursos = [{"id":f[0],"titulo":f[1],"descripcion":f[2],"precio":float(f[3]) if f[3] else 0,"imagen_url":f[4]} for f in filas]
    return render_template("dashboard_profesor.html", cursos=cursos, nombre=session.get("nombre"))

@app.route("/profesor/crear_curso", methods=["GET","POST"])
def profesor_crear_curso():
    if not session.get("user_id") or not requiere_profesor():
        flash("Debes ser profesor para esta acción.")
        return redirect(url_for("login"))
    if request.method == "GET":
        return render_template("crear_curso.html")
    titulo = request.form.get("titulo")
    descripcion = request.form.get("descripcion")
    precio = request.form.get("precio") or 0
    imagen_url = request.form.get("imagen_url") or DEFAULT_IMAGE_PATH
    profesor_id = session["user_id"]

    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO cursos (titulo, descripcion, precio, imagen_url, profesor_id)
        VALUES (%s,%s,%s,%s,%s);
    """, (titulo, descripcion, precio, imagen_url, profesor_id))
    conn.commit()
    cur.close()
    conn.close()
    flash("Curso creado correctamente.")
    return redirect(url_for("profesor_dashboard"))

# --------------------------
# Añadir lección a curso
# --------------------------
@app.route("/profesor/curso/<int:curso_id>/añadir_leccion", methods=["GET","POST"])
def profesor_añadir_leccion(curso_id):
    if not session.get("user_id") or not requiere_profesor():
        flash("Debes ser profesor.")
        return redirect(url_for("login"))
    if request.method == "GET":
        return render_template("añadir_leccion.html", curso_id=curso_id)
    titulo = request.form.get("titulo")
    video_url = request.form.get("video_url")
    contenido = request.form.get("contenido")
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("INSERT INTO lecciones(curso_id, titulo, video_url, contenido) VALUES (%s,%s,%s,%s);",
                (curso_id, titulo, video_url, contenido))
    conn.commit()
    cur.close()
    conn.close()
    flash("Lección añadida.")
    return redirect(url_for("profesor_dashboard"))

# --------------------------
# Página detalle curso (alumno)
# --------------------------
@app.route("/curso/<int:curso_id>")
def curso_detalle(curso_id):
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("SELECT id, titulo, descripcion, precio, imagen_url, profesor_id FROM cursos WHERE id = %s;", (curso_id,))
    curso = cur.fetchone()
    if not curso:
        cur.close()
        conn.close()
        return "Curso no encontrado", 404
    cur.execute("SELECT id, titulo, video_url FROM lecciones WHERE curso_id = %s ORDER BY creado_en;", (curso_id,))
    lecciones = cur.fetchall()
    cur.close()
    conn.close()
    datos_curso = {
        "id": curso[0],
        "titulo": curso[1],
        "descripcion": curso[2],
        "precio": float(curso[3]) if curso[3] else 0,
        "imagen_url": curso[4],
        "profesor_id": curso[5]
    }
    lista_lecciones = [{"id":l[0],"titulo":l[1],"video_url":l[2]} for l in lecciones]
    return render_template("curso_detalle.html", curso=datos_curso, lecciones=lista_lecciones)

# --------------------------
# Ver lección
# --------------------------
@app.route("/leccion/<int:leccion_id>")
def ver_leccion(leccion_id):
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("SELECT id, curso_id, titulo, video_url, contenido FROM lecciones WHERE id = %s;", (leccion_id,))
    l = cur.fetchone()
    cur.close()
    conn.close()
    if not l:
        return "Lección no encontrada", 404
    datos = {"id": l[0], "curso_id": l[1], "titulo": l[2], "video_url": l[3], "contenido": l[4]}
    return render_template("leccion.html", leccion=datos)

# --------------------------
# Métodos de pago (API)
# --------------------------
@app.route("/metodos_pago")
def metodos_pago():
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("SELECT id, nombre, tipo FROM metodos_pago WHERE habilitado = TRUE;")
    filas = cur.fetchall()
    cur.close()
    conn.close()
    metodos = [{"id":f[0],"nombre":f[1],"tipo":f[2]} for f in filas]
    return jsonify(metodos)

# --------------------------
# Comprar (simulado)
# --------------------------
@app.route("/comprar", methods=["POST"])
def comprar():
    if not session.get("user_id"):
        return jsonify({"error":"Debes iniciar sesión"}), 401
    data = request.form or request.json
    curso_id = data.get("curso_id")
    metodo_pago_id = data.get("metodo_pago_id")
    monto = data.get("monto") or 0

    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("INSERT INTO compras(usuario_id, curso_id, metodo_pago_id, monto, estado) VALUES (%s,%s,%s,%s,%s);",
                (session["user_id"], curso_id, metodo_pago_id, monto, "pagado"))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"mensaje":"Compra registrada (simulada)"}), 201

# --------------------------
# Mis compras (alumno)
# --------------------------
@app.route("/mis_compras")
def mis_compras():
    if not session.get("user_id"):
        flash("Debes iniciar sesión")
        return redirect(url_for("login"))
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, cursos.titulo, c.monto, c.estado, c.fecha
        FROM compras c JOIN cursos ON c.curso_id = cursos.id
        WHERE c.usuario_id = %s ORDER BY c.fecha DESC;
    """, (session["user_id"],))
    filas = cur.fetchall()
    cur.close()
    conn.close()
    compras = [{"id":f[0],"titulo":f[1],"monto":float(f[2]),"estado":f[3],"fecha":f[4]} for f in filas]
    return render_template("mis_compras.html", compras=compras)

# --------------------------
# Ejecutar app
# --------------------------
if __name__ == "__main__":
    app.run(debug=True)

