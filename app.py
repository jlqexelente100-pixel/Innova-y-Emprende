from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from itsdangerous import URLSafeTimedSerializer
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from werkzeug.utils import secure_filename
import uuid
import stripe
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import urlparse
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

print("ENV PATH:", env_path)
print("STRIPE KEY:", os.getenv("STRIPE_SECRET_KEY"))

# --------------------------
# Cargar variables de entorno
# --------------------------
load_dotenv()  # FIX: antes faltaba el ()

# --------------------------
# Funcion Video YouTube: convierte URL a formato embed
# --------------------------
def convertir_youtube(url):
    if not url:
        return None
    if "watch?v=" in url:
        return url.replace("watch?v=", "embed/")
    if "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1]
        return f"https://www.youtube.com/embed/{video_id}"
    return url


app = Flask(__name__, static_folder="static")

# FIX: secret_key desde .env
app.secret_key = os.getenv("SECRET_KEY", "CAMBIA_ESTA_CLAVE_EN_EL_ENV")

# --------------------------
# Stripe — API key desde .env
# --------------------------
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# FIX: BASE_URL desde .env para no hardcodear localhost
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")   

print("Stripe inicializado")

# =============================
# CONFIG SUBIDA IMÁGENES
# =============================
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

serializer = URLSafeTimedSerializer(app.secret_key)

# -------------------------
# CONFIGURACIÓN BD (POSTGRES)
# -------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': 'Emprende',
    'user': 'postgres',
    'password': '123456',
    'port': 5432
}


def conectar_bd():
    try:
        if DATABASE_URL:
            # Producción (Render)
            conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        else:
            # Desarrollo local
            conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.OperationalError as e:
        print("Error al conectar a la BD:", e)
        return None


def enviar_correo(destinatario, enlace):
    remitente = "innovayemprende1.2@gmail.com"
    password = "cwbd dprx ncgc zyyf"

    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = "Recuperación de contraseña"
    mensaje["From"] = remitente
    mensaje["To"] = destinatario

    html = f"""
    <p>Haz clic en el siguiente enlace para restablecer tu contraseña (válido 1 hora):</p>
    <p><a href="{enlace}">{enlace}</a></p>
    """

    mensaje.attach(MIMEText(html, "html"))

    try:
        servidor = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
        servidor.ehlo()
        servidor.starttls()
        servidor.login(remitente, password)
        servidor.sendmail(remitente, destinatario, mensaje.as_string())
        servidor.quit()
        print("Correo enviado correctamente a:", destinatario)
        return True
    except Exception as e:
        print("Error al enviar correo:", e)
        return False


# ------------------------------------------------
# 1. Página para pedir el correo
# ------------------------------------------------
@app.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    if request.method == "GET":
        return render_template("recuperar.html")

    correo = request.form.get("correo") or request.form.get("email")
    if not correo:
        flash("Ingresa un correo válido.", "error")
        return redirect(url_for("recuperar"))

    conn = conectar_bd()
    if not conn:
        flash("Error de conexión a la base de datos. Intenta más tarde.", "error")
        return redirect(url_for("recuperar"))

    cur = conn.cursor()
    cur.execute("SELECT id FROM usuarios WHERE correo = %s", (correo,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if user:
        token = serializer.dumps(correo, salt="recuperar-salt")
        link = url_for('restablecer', token=token, _external=True)
        enviado = enviar_correo(correo, link)
        if enviado:
            flash("Hemos enviado un enlace de recuperación a tu correo electrónico.", "success")
        else:
            flash("No se pudo enviar el correo. Verifica la configuración del servidor de correo.", "error")
    else:
        flash("Hemos enviado un enlace de recuperación a tu correo electrónico.", "success")

    return redirect(url_for("login"))


# ------------------------------------------------
# 2. Página del enlace recibido por correo
# ------------------------------------------------
@app.route("/restablecer/<token>", methods=["GET", "POST"])
def restablecer(token):
    try:
        email = serializer.loads(token, salt="recuperar-salt", max_age=3600)
    except:
        return "El enlace ha expirado o no es válido."

    if request.method == "POST":
        nueva = request.form["password"]
        nueva_hash = generate_password_hash(nueva)

        conn = conectar_bd()
        cur = conn.cursor()
        cur.execute(
            "UPDATE usuarios SET password_hash = %s WHERE correo = %s",
            (nueva_hash, email)
        )
        conn.commit()
        cur.close()
        conn.close()

        return "Contraseña actualizada correctamente."

    return render_template("restablecer.html")


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
        apellido TEXT,
        username TEXT UNIQUE,
        correo TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        rol TEXT NOT NULL,
        foto_perfil TEXT,
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
        fecha TIMESTAMP,
        creado_en TIMESTAMP DEFAULT NOW()
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reuniones_meet (
        id SERIAL PRIMARY KEY,
        leccion_id INTEGER REFERENCES lecciones(id),
        url_meet TEXT NOT NULL,
        hora_inicio TIMESTAMP NOT NULL,
        hora_fin TIMESTAMP NOT NULL,
        mensaje TEXT,
        activa BOOLEAN DEFAULT TRUE,
        creada_en TIMESTAMP DEFAULT NOW()
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS notificaciones (
        id SERIAL PRIMARY KEY,
        usuario_id INTEGER REFERENCES usuarios(id),
        tipo TEXT,
        titulo TEXT,
        mensaje TEXT,
        leccion_id INTEGER REFERENCES lecciones(id),
        leida BOOLEAN DEFAULT FALSE,
        creada_en TIMESTAMP DEFAULT NOW()
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS estilos_curso (
        id SERIAL PRIMARY KEY,
        curso_id INTEGER REFERENCES cursos(id),
        color_principal TEXT,
        color_secundario TEXT,
        fuente TEXT,
        css_personalizado TEXT,
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
        stripe_session_id TEXT UNIQUE,
        fecha TIMESTAMP DEFAULT NOW()
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS foro_posts (
        id SERIAL PRIMARY KEY,
        curso_id INTEGER REFERENCES cursos(id),
        usuario_id INTEGER REFERENCES usuarios(id),
        titulo TEXT NOT NULL,
        contenido TEXT NOT NULL,
        creado_en TIMESTAMP DEFAULT NOW()
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS progreso_lecciones (
        id                  SERIAL PRIMARY KEY,
        usuario_id          INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        leccion_id          INTEGER REFERENCES lecciones(id) ON DELETE CASCADE,
        completada          BOOLEAN DEFAULT FALSE,
        fecha_completado    TIMESTAMP,
        progreso_porcentaje NUMERIC DEFAULT 0 CHECK (progreso_porcentaje >= 0 AND progreso_porcentaje <= 100),
        ultima_interaccion  TIMESTAMP DEFAULT NOW(),
        UNIQUE(usuario_id, leccion_id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS progreso_cursos (
        id                  SERIAL PRIMARY KEY,
        usuario_id          INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        curso_id            INTEGER REFERENCES cursos(id) ON DELETE CASCADE,
        porcentaje          NUMERIC DEFAULT 0 CHECK (porcentaje >= 0 AND porcentaje <= 100),
        ultima_actualizacion TIMESTAMP DEFAULT NOW(),
        completado          BOOLEAN DEFAULT FALSE,
        UNIQUE(usuario_id, curso_id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS resenas (
        id SERIAL PRIMARY KEY,
        curso_id INTEGER REFERENCES cursos(id) ON DELETE CASCADE,
        usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        puntaje INTEGER NOT NULL CHECK (puntaje >= 1 AND puntaje <= 5),
        comentario TEXT NOT NULL,
        creado_en TIMESTAMP DEFAULT NOW(),
        UNIQUE(usuario_id, curso_id)
    );
    """)

    # Datos iniciales
    cur.execute("SELECT COUNT(*) FROM metodos_pago;")
    if cur.fetchone()[0] == 0:
        cur.execute("""
            INSERT INTO metodos_pago(nombre, tipo, habilitado)
            VALUES
                ('Stripe (tarjeta)', 'tarjeta', TRUE),
                ('Transferencia Bancaria', 'transferencia', TRUE);
        """)

# Crear usuario profesor demo y cursos demo
    cur.execute("SELECT COUNT(*) FROM cursos;")
    if cur.fetchone()[0] == 0:
        cur.execute("SELECT id FROM usuarios WHERE correo = %s;", ("profesor@demo.test",))
        r = cur.fetchone()
        if not r:
            phash = generate_password_hash("profesor123")
            cur.execute("""
                INSERT INTO usuarios(nombre, correo, password_hash, rol)
                VALUES (%s, %s, %s, %s)
                RETURNING id;
            """, ("Profesor Demo", "profesor@demo.test", phash, "profesor"))
            profesor_id = cur.fetchone()[0]
        else:
            profesor_id = r[0]

    # ✅ AQUÍ VA EL CÓDIGO NUEVO
    cur.execute("SELECT id FROM cursos WHERE titulo = %s;", ("Marketing Digital para Emprendedores",))
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO cursos(titulo, descripcion, precio, imagen_url, profesor_id)
            VALUES (%s, %s, %s, %s, %s) RETURNING id;
        """, (
            "Marketing Digital para Emprendedores",
            "Aprende estrategias de marketing digital para hacer crecer tu negocio desde cero.",
            29.99,
            "styles/imagenes/mente_emprendedora.png",
            profesor_id
        ))
        curso_pago_id = cur.fetchone()[0]

        lecciones_demo = [
            ("Introducción al Marketing Digital", "https://www.youtube.com/embed/v17EXDu3t0E", "En esta lección verás los fundamentos del marketing digital y el ecosistema online actual."),
            ("Redes Sociales y Marca Personal", "https://www.youtube.com/embed/R5RU8Zng0rA", "Cómo construir tu presencia en redes sociales para atraer seguidores y clientes."),
            ("SEO y Posicionamiento Web", "https://www.youtube.com/embed/XwGSXcTEtks", "Aprende cómo funciona el algoritmo de Google y cómo aparecer en los primeros resultados."),
            ("Email Marketing Efectivo", "https://www.youtube.com/embed/9vIhgAr0BNA", "Estrategias para crear campañas de correo automatizadas y efectivas."),
            ("Publicidad en Google Ads", "https://www.youtube.com/embed/N-A28JFhRwI", "Crea y optimiza tus primeras campañas de publicidad pagada en el buscador de Google.")
        ]

        for titulo_lec, video_lec, contenido_lec in lecciones_demo:
            cur.execute("""
                INSERT INTO lecciones(curso_id, titulo, video_url, contenido)
                VALUES (%s, %s, %s, %s);
            """, (curso_pago_id, titulo_lec, video_lec, contenido_lec))
#
    cur.execute("SELECT id FROM cursos WHERE titulo = %s;", ("Desarrollo Web con Python",))
    resultado = cur.fetchone()

    if resultado:
        curso_id = resultado[0]
    else:
        cur.execute("""
            INSERT INTO cursos(titulo, descripcion, precio, imagen_url, profesor_id)
            VALUES (%s, %s, %s, %s, %s) RETURNING id;
        """, (
            "Desarrollo Web con Python",
            "Aprende a crear aplicaciones web desde cero usando Python y Flask.",
            39.99,
            "styles/imagenes/programacion.jpeg",
            profesor_id
        ))
        curso_id = cur.fetchone()[0]

        lecciones = [
            ("Introducción a Python Web", "https://www.youtube.com/embed/PtBHnMMRI0E", "Conceptos básicos de desarrollo web y por qué usar Python en 2026."),
            ("Primeros pasos con Flask", "https://www.youtube.com/embed/W-SfC_V7P6o", "Instalación del entorno y creación de tu primera aplicación 'Hola Mundo'."),
            ("Rutas y Templates", "https://www.youtube.com/embed/faJvSBNRXUY", "Uso de Jinja2 para crear páginas dinámicas y manejo de rutas en el servidor."),
            ("Bases de Datos", "https://www.youtube.com/embed/Zfpbnmdi-pE", "Integración de SQLAlchemy para crear, leer, actualizar y borrar datos (CRUD)."),
            ("Deploy de la App", "https://www.youtube.com/embed/ulkMLRqWWG0", "Cómo publicar tu aplicación gratis en internet usando Render o GitHub.")
        ]

        for t, v, c in lecciones:
            cur.execute("""
                INSERT INTO lecciones(curso_id, titulo, video_url, contenido)
                VALUES (%s, %s, %s, %s);
            """, (curso_id, t, v, c))
#
    cur.execute("SELECT id FROM cursos WHERE titulo = %s;", ("Diseño Gráfico para Principiantes",))
    resultado = cur.fetchone()

    if resultado:
        curso_id = resultado[0]
    else:
        cur.execute("""
            INSERT INTO cursos(titulo, descripcion, precio, imagen_url, profesor_id)
            VALUES (%s, %s, %s, %s, %s) RETURNING id;
        """, (
            "Diseño Gráfico para Principiantes",
            "Aprende los fundamentos del diseño gráfico y crea piezas visuales impactantes.",
            24.99,
            "styles/imagenes/diseño.jpg",
            profesor_id
        ))
        curso_id = cur.fetchone()[0]

        lecciones = [
            ("Fundamentos del Diseño", "https://www.youtube.com/embed/7N2v0bpNFKA", "Principios básicos del diseño visual."),
            ("Teoría del Color", "https://www.youtube.com/embed/MNKRUoKcWb0", "Uso adecuado de colores."),
            ("Tipografía", "https://www.youtube.com/embed/Z37lEQMfPtg", "Cómo elegir fuentes correctamente."),
            ("Diseño para Redes Sociales", "https://www.youtube.com/embed/HNQRqOisyj0", "Crea contenido visual atractivo."),
            ("Herramientas Digitales", "https://www.youtube.com/embed/ghQhms-ws7k", "Uso de software de diseño."),
        ]

        for t, v, c in lecciones:
            cur.execute("""
                INSERT INTO lecciones(curso_id, titulo, video_url, contenido)
                VALUES (%s, %s, %s, %s);
            """, (curso_id, t, v, c))
#
    cur.execute("SELECT id FROM cursos WHERE titulo = %s;", ("Finanzas Personales",))
    resultado = cur.fetchone()

    if resultado:
        curso_id = resultado[0]
    else:
        cur.execute("""
            INSERT INTO cursos(titulo, descripcion, precio, imagen_url, profesor_id)
            VALUES (%s, %s, %s, %s, %s) RETURNING id;
        """, (
            "Finanzas Personales",
            "Aprende a gestionar tu dinero, ahorrar e invertir inteligentemente.",
            19.99,
            "styles/imagenes/finanzas.jpg",
            profesor_id
        ))
        curso_id = cur.fetchone()[0]

        lecciones = [
            ("Introducción a las Finanzas", "https://www.youtube.com/embed/9sCVcWD1Svs", "Conceptos básicos financieros."),
            ("Presupuesto Personal", "https://www.youtube.com/embed/f2O4Q-T12FI", "Cómo organizar tus ingresos y gastos."),
            ("Ahorro Inteligente", "https://www.youtube.com/embed/U5wCPaNAjls", "Estrategias para ahorrar."),
            ("Inversiones Básicas", "https://www.youtube.com/embed/9xW0HK7IUo0", "Primeros pasos para invertir."),
            ("Libertad Financiera", "https://www.youtube.com/embed/ahLAhwPCO6I", "Planificación a largo plazo."),
        ]

        for t, v, c in lecciones:
            cur.execute("""
                INSERT INTO lecciones(curso_id, titulo, video_url, contenido)
                VALUES (%s, %s, %s, %s);
            """, (curso_id, t, v, c))

    #ADMINISTRADOR DEMO


    cur.execute("SELECT id FROM usuarios WHERE correo = %s;", ("admin@demo.test",))
    admin = cur.fetchone()

    if not admin:
        admin_hash = generate_password_hash("admin123")
        cur.execute("""
            INSERT INTO usuarios(
                nombre,
                apellido,
                username,
                correo,
                password_hash,
                rol
            )
            VALUES (%s, %s, %s, %s, %s, %s);
        """, (
            "Administrador",
            "Sistema",
            "admin",
            "admin@demo.test",
            admin_hash,
            "admin"
        ))



    conn.commit()
    cur.close()
    conn.close()
    print("Tablas creadas/verificadas y datos iniciales insertados.")


# --------------------------
# RUTAS DE FRONTEND (HTML)
# --------------------------

@app.route("/")
@app.route("/home")
def home():
    return render_template("Home.html")


@app.route('/servicios')
def servicios():
    return render_template('servicios.html')
    

@app.route('/politicas_privacidad')
def politicas_privacidad():
    return render_template("politicas_privacidad.html")


@app.route('/sobre-nosotros')
def sobre_nosotros():
    return render_template("sobre-nosotros.html")


@app.route('/Nuestros_valores')
def Nuestros_valores():
    return render_template("Nuestros_valores.html")


@app.route("/index")
def index():
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.titulo, c.descripcion, c.precio, c.imagen_url,
               COALESCE(e.color_principal, '#007bff') as cp,
               COALESCE(e.color_secundario, '#6c757d') as cs
        FROM cursos c
        LEFT JOIN estilos_curso e ON e.curso_id = c.id
        ORDER BY c.creado_en DESC;
    """)
    filas = cur.fetchall()
    cur.close()
    conn.close()

    cursos = [
        {
            "id": f[0],
            "titulo": f[1],
            "descripcion": f[2],
            "precio": float(f[3]) if f[3] else 0,
            "imagen_url": f[4],
            "color_principal": f[5],
            "color_secundario": f[6]
        }
        for f in filas
    ]
    return render_template("index.html", cursos=cursos, is_home=True)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    correo = request.form.get("correo")
    password = request.form.get("password")
    conn = conectar_bd()
    if not conn:
        flash("No se pudo conectar a la base de datos.", "error")
        return redirect(url_for("login"))

    cur = conn.cursor()
    cur.execute("SELECT id, nombre, password_hash, rol FROM usuarios WHERE correo = %s;", (correo,))
    r = cur.fetchone()
    cur.close()
    conn.close()

    if not r:
        flash("Usuario no encontrado.", "error")
        return redirect(url_for("login"))

    user_id, nombre, password_hash, rol = r
    if not check_password_hash(password_hash, password):
        flash("Contraseña incorrecta.", "error")
        return redirect(url_for("login"))

    session["user_id"] = user_id
    session["nombre"] = nombre
    session["rol"] = rol
    flash("Bienvenido/a " + nombre)

    # ← Redirigir según rol
    if rol == "admin":
        return redirect(url_for("admin_dashboard"))
    elif rol == "profesor":
        return redirect(url_for("profesor_dashboard"))
    else:
        return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada.", "success")
    return redirect(url_for("home"))


@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    if request.method == "GET":
        return render_template("registrar.html")

    nombre = request.form.get("nombre", "").strip()
    apellido = request.form.get("apellido", "").strip()
    username = request.form.get("username", "").strip()
    correo = request.form.get("correo", "").strip()
    password = request.form.get("password", "")
    rol = "alumno"  # ← SIEMPRE alumno, ignorar lo que venga del form

    if not nombre or not apellido or not username or not correo or not password:
        flash("Todos los campos son obligatorios.", "error")
        return redirect(url_for("/registrar"))

    if "@" not in correo or "." not in correo:
        flash("Correo electrónico inválido.", "error")
        return redirect(url_for("/registrar"))

    if len(password) < 6:
        flash("La contraseña debe tener al menos 6 caracteres.", "error")
        return redirect(url_for("/registrar"))

    password_hash = generate_password_hash(password)

    conn = conectar_bd()
    if not conn:
        flash("Error de conexión.", "error")
        return redirect(url_for("/registrar"))

    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM usuarios WHERE correo = %s;", (correo,))
        if cur.fetchone():
            flash(" El correo ya está registrado, por favor use otro correo para ingresar.", "error")
            return redirect(url_for("/registrar.html"))

        cur.execute("SELECT id FROM usuarios WHERE username = %s;", (username,))
        if cur.fetchone():
            flash("El nombre de usuario ya está en uso.", "error")
            return redirect(url_for("/registrar.html"))

        cur.execute(
            "INSERT INTO usuarios(nombre, apellido, username, correo, password_hash, rol) VALUES (%s,%s,%s,%s,%s,%s);",
            (nombre, apellido, username, correo, password_hash, rol)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        flash("Error al registrar: " + str(e))
        return redirect(url_for("/registrar.html"))
    
    
    finally:
        cur.close()
        conn.close()

        flash("Registrado correctamente.", "success")
        return redirect(url_for("registrar"))


# --------------------------
# API: Obtener cursos (JSON)
# --------------------------
@app.route("/cursos")
def api_cursos():
    conn = conectar_bd()
    if not conn:
        return jsonify({"error": "No hay conexión"}), 500
    cur = conn.cursor()
    cur.execute("SELECT id, titulo, descripcion, precio, imagen_url FROM cursos ORDER BY creado_en DESC;")
    filas = cur.fetchall()
    cur.close()
    conn.close()
    cursos = [
        {
            "id": f[0],
            "titulo": f[1],
            "descripcion": f[2],
            "precio": float(f[3]) if f[3] is not None else 0,
            "imagen_url": f[4] or ""
        }
        for f in filas
    ]
    return jsonify(cursos)


# --------------------------
# Panel profesor
# --------------------------
def requiere_profesor():
    return session.get("rol") == "profesor"


@app.route("/profesor/dashboard")
def profesor_dashboard():
    if not session.get("user_id"):
        flash("Debes iniciar sesión.", "warning")
        return redirect(url_for("login"))

    if not requiere_profesor():
        flash("Acceso solo para profesores.", "warning")
        return redirect(url_for("index"))

    profesor_id = session["user_id"]
    conn = conectar_bd()
    cur = conn.cursor()

    # Cursos con conteo de lecciones
    cur.execute(
        """
        SELECT c.id, c.titulo, c.descripcion, c.precio, c.imagen_url,
               COUNT(DISTINCT l.id) AS total_lecciones
        FROM cursos c
        LEFT JOIN lecciones l ON l.curso_id = c.id
        WHERE c.profesor_id = %s
        GROUP BY c.id, c.titulo, c.descripcion, c.precio, c.imagen_url
        ORDER BY c.id;
        """,
        (profesor_id,)
    )
    filas = cur.fetchall()

    # Total de compradores únicos en todos los cursos del profesor
    cur.execute(
        """
        SELECT COUNT(DISTINCT comp.usuario_id)
        FROM compras comp
        JOIN cursos c ON comp.curso_id = c.id
        WHERE c.profesor_id = %s AND comp.estado = 'completado';
        """,
        (profesor_id,)
    )
    total_compradores = cur.fetchone()[0] or 0

    cur.close()
    conn.close()

    cursos = [
        {
            "id": f[0], "titulo": f[1], "descripcion": f[2],
            "precio": float(f[3]) if f[3] else 0,
            "imagen_url": f[4], "total_lecciones": f[5],
        }
        for f in filas
    ]
    return render_template(
        "dashboard_profesor.html",
        cursos=cursos,
        nombre=session.get("nombre"),
        total_compradores=total_compradores,
    )


@app.route("/profesor/crear-curso", methods=["GET", "POST"])
def profesor_crear_curso():
    if not session.get("user_id"):
        flash("Debes iniciar sesión.", "warning")
        return redirect(url_for("login"))

    if not puede_agregar_contenido():
        flash("No tienes permiso para crear cursos.", "warning")
        return redirect(url_for("index"))

    if request.method == "POST":
        titulo = request.form.get("titulo")
        descripcion = request.form.get("descripcion")
        precio = request.form.get("precio")
        imagen = request.files.get("imagen")
        imagen_url = "imagenes/default-curso.png"
        profesor_id = session.get("user_id")

        if imagen and allowed_file(imagen.filename):
            filename = secure_filename(imagen.filename)
            ruta = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            imagen.save(ruta)
            imagen_url = "uploads/" + filename

        conn = conectar_bd()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO cursos (titulo, descripcion, precio, imagen_url, profesor_id)
                VALUES (%s, %s, %s, %s, %s) RETURNING id;
            """, (titulo, descripcion, precio, imagen_url, profesor_id))
            conn.commit()
            flash("Curso creado exitosamente", "success")
            return redirect(url_for("index"))
        except Exception as e:
            conn.rollback()
            flash("No se pudo crear el curso: probablemente ya existe un curso con el mismo título.", "error")
            return redirect(url_for("profesor_crear_curso"))
        finally:
            cur.close()
            conn.close()

    return render_template("crear_curso.html")


# --------------------------
# Añadir lección a curso
# --------------------------
@app.route("/profesor/curso/<int:curso_id>/anadir_leccion", methods=["GET", "POST"])
def profesor_anadir_leccion(curso_id):
    if not session.get("user_id"):
        flash("Debes iniciar sesión.", "warning")
        return redirect(url_for("login"))

    if not puede_agregar_contenido():
        flash("No tienes permiso para agregar lecciones.", "warning")
        return redirect(url_for("index"))

    # El profesor solo puede agregar lecciones a SUS cursos; el admin a cualquiera
    conn_chk = conectar_bd()
    cur_chk = conn_chk.cursor()
    autorizado = puede_gestionar_curso(cur_chk, curso_id)
    cur_chk.close()
    conn_chk.close()
    if not autorizado:
        flash("Solo puedes agregar lecciones a tus propios cursos.", "warning")
        return redirect(url_for("curso_detalle", curso_id=curso_id))

    if request.method == "GET":
        return render_template("anadir_leccion.html", curso_id=curso_id)

    titulo = request.form.get("titulo")
    video_url = request.form.get("video_url")
    contenido = request.form.get("contenido")
    fecha = request.form.get("fecha") or None
    video_url = convertir_youtube(video_url)

    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO lecciones(curso_id, titulo, video_url, contenido, fecha)
        VALUES (%s,%s,%s,%s,%s) RETURNING id;
    """, (curso_id, titulo, video_url, contenido, fecha))
    conn.commit()
    cur.close()
    conn.close()

    flash("Lección añadida.", "success")
    return redirect(url_for("curso_detalle", curso_id=curso_id))

#Panel Administrador

def requiere_admin():
 return session.get("rol") == "admin"


# ──────────────────────────────────────────────────────────
# Permisos por rol sobre CURSOS y LECCIONES
#   admin    → agregar, editar y eliminar (cualquier curso)
#   profesor → agregar y eliminar (solo SUS cursos)
#   alumno   → solo mirar
# ──────────────────────────────────────────────────────────
def puede_agregar_contenido():
    return session.get("rol") in ("admin", "profesor")


def puede_editar_contenido():
    return session.get("rol") == "admin"


def puede_eliminar_contenido():
    return session.get("rol") in ("admin", "profesor")


def es_dueno_curso(cur, curso_id):
    """True si el usuario en sesión es el profesor dueño del curso."""
    cur.execute("SELECT profesor_id FROM cursos WHERE id = %s;", (curso_id,))
    fila = cur.fetchone()
    return bool(fila) and fila[0] == session.get("user_id")


def puede_gestionar_curso(cur, curso_id):
    """El admin gestiona cualquier curso; el profesor solo el suyo."""
    rol = session.get("rol")
    if rol == "admin":
        return True
    if rol == "profesor":
        return es_dueno_curso(cur, curso_id)
    return False


def eliminar_leccion_completa(cur, leccion_id):
    """Borra una lección y todas sus referencias (meet, notificaciones)."""
    cur.execute("DELETE FROM reuniones_meet WHERE leccion_id = %s;", (leccion_id,))
    cur.execute("DELETE FROM notificaciones WHERE leccion_id = %s;", (leccion_id,))
    # progreso_lecciones se borra en cascada (ON DELETE CASCADE)
    cur.execute("DELETE FROM lecciones WHERE id = %s;", (leccion_id,))


def eliminar_curso_completo(cur, curso_id):
    """Borra un curso y todo lo que cuelga de él (lecciones, compras, foro...)."""
    cur.execute(
        "DELETE FROM reuniones_meet WHERE leccion_id IN "
        "(SELECT id FROM lecciones WHERE curso_id = %s);", (curso_id,))
    cur.execute(
        "DELETE FROM notificaciones WHERE leccion_id IN "
        "(SELECT id FROM lecciones WHERE curso_id = %s);", (curso_id,))
    cur.execute("DELETE FROM lecciones WHERE curso_id = %s;", (curso_id,))
    cur.execute("DELETE FROM estilos_curso WHERE curso_id = %s;", (curso_id,))
    cur.execute("DELETE FROM foro_posts WHERE curso_id = %s;", (curso_id,))
    cur.execute("DELETE FROM compras WHERE curso_id = %s;", (curso_id,))
    # progreso_cursos y resenas se borran en cascada (ON DELETE CASCADE)
    cur.execute("DELETE FROM cursos WHERE id = %s;", (curso_id,))


@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("user_id"):
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for("login"))
    if not requiere_admin():
        flash("Acceso solo para administradores", "warning")
        return redirect(url_for("index"))
    # Simplemente renderiza el template, los datos los carga el JS via API
    return render_template("admin/dashboard_admin.html")

# ══════════════════════════════════════════════════
# ADMIN — APIs JSON para el dashboard
# ══════════════════════════════════════════════════

@app.route("/admin/api/usuarios")
def admin_api_usuarios():
    if not requiere_admin():
        return jsonify({"error": "No autorizado"}), 403
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, nombre, apellido, username, correo, rol, creado_en
        FROM usuarios ORDER BY creado_en DESC;
    """)
    filas = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([
        {"id":f[0],"nombre":f[1],"apellido":f[2],"username":f[3],
         "correo":f[4],"rol":f[5],"creado_en":str(f[6])}
        for f in filas
    ])


@app.route("/admin/api/usuarios", methods=["POST"])
def admin_api_crear_usuario():
    if not requiere_admin():
        return jsonify({"error": "No autorizado"}), 403
    data = request.json
    nombre   = data.get("nombre","").strip()
    apellido = data.get("apellido","").strip()
    username = data.get("username","").strip()
    correo   = data.get("correo","").strip()
    password = data.get("password","")
    rol      = data.get("rol","alumno")

    if not nombre or not correo or not password:
        return jsonify({"error": "Nombre, correo y contraseña son requeridos"}), 400

    phash = generate_password_hash(password)
    conn = conectar_bd()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO usuarios(nombre, apellido, username, correo, password_hash, rol)
            VALUES (%s,%s,%s,%s,%s,%s);
        """, (nombre, apellido, username, correo, phash, rol))
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close(); conn.close()
        return jsonify({"error": str(e)}), 400
    cur.close(); conn.close()
    return jsonify({"ok": True}), 201


@app.route("/admin/api/usuarios/<int:uid>", methods=["PUT"])
def admin_api_editar_usuario(uid):
    if not requiere_admin():
        return jsonify({"error": "No autorizado"}), 403
    data = request.json
    conn = conectar_bd()
    cur = conn.cursor()
    try:
        if data.get("password"):
            phash = generate_password_hash(data["password"])
            cur.execute("""
                UPDATE usuarios SET nombre=%s, apellido=%s, username=%s,
                correo=%s, rol=%s, password_hash=%s WHERE id=%s;
            """, (data["nombre"], data.get("apellido",""), data.get("username",""),
                  data["correo"], data["rol"], phash, uid))
        else:
            cur.execute("""
                UPDATE usuarios SET nombre=%s, apellido=%s, username=%s,
                correo=%s, rol=%s WHERE id=%s;
            """, (data["nombre"], data.get("apellido",""), data.get("username",""),
                  data["correo"], data["rol"], uid))
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close(); conn.close()
        return jsonify({"error": str(e)}), 400
    cur.close(); conn.close()
    return jsonify({"ok": True})


@app.route("/admin/api/usuarios/<int:uid>", methods=["DELETE"])
def admin_api_eliminar_usuario(uid):
    if not requiere_admin():
        return jsonify({"error": "No autorizado"}), 403
    if uid == session.get("user_id"):
        return jsonify({"error": "No puedes eliminarte a ti mismo"}), 400
    conn = conectar_bd()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM usuarios WHERE id=%s;", (uid,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close(); conn.close()
        return jsonify({"error": str(e)}), 400
    cur.close(); conn.close()
    return jsonify({"ok": True})


@app.route("/admin/api/ventas")
def admin_api_ventas():
    if not requiere_admin():
        return jsonify({"error": "No autorizado"}), 403
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, u.nombre, cu.titulo, c.monto, c.estado, c.fecha
        FROM compras c
        JOIN usuarios u  ON c.usuario_id = u.id
        JOIN cursos   cu ON c.curso_id   = cu.id
        ORDER BY c.fecha DESC;
    """)
    filas = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([
        {"id":f[0],"usuario_nombre":f[1],"curso_titulo":f[2],
         "monto":float(f[3]) if f[3] else 0,"estado":f[4],"fecha":str(f[5])}
        for f in filas
    ])


@app.route("/admin/api/cursos")
def admin_api_cursos():
    if not requiere_admin():
        return jsonify({"error": "No autorizado"}), 403
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.titulo, c.precio, u.nombre, c.profesor_id
        FROM cursos c
        JOIN usuarios u ON c.profesor_id = u.id
        ORDER BY c.creado_en DESC;
    """)
    filas = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([
        {"id":f[0],"titulo":f[1],"precio":float(f[2]) if f[2] else 0,
         "profesor":f[3],"profesor_id":f[4]}
        for f in filas
    ])


@app.route("/admin/api/cursos/<int:cid>", methods=["DELETE"])
def admin_api_eliminar_curso(cid):
    if not requiere_admin():
        return jsonify({"error": "No autorizado"}), 403
    conn = conectar_bd()
    cur = conn.cursor()
    try:
        eliminar_curso_completo(cur, cid)
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close(); conn.close()
        return jsonify({"error": str(e)}), 400
    cur.close(); conn.close()
    return jsonify({"ok": True})


# ──────────────────────────────────────────────────────────
# CURSO — Eliminar (admin cualquiera, profesor solo el suyo)
# ──────────────────────────────────────────────────────────
@app.route("/curso/<int:curso_id>/eliminar", methods=["POST"])
def eliminar_curso(curso_id):
    if not session.get("user_id"):
        flash("Debes iniciar sesión.", "warning")
        return redirect(url_for("login"))

    conn = conectar_bd()
    cur = conn.cursor()

    if not puede_eliminar_contenido() or not puede_gestionar_curso(cur, curso_id):
        cur.close()
        conn.close()
        flash("No tienes permiso para eliminar este curso.", "error")
        return redirect(url_for("curso_detalle", curso_id=curso_id))

    try:
        eliminar_curso_completo(cur, curso_id)
        conn.commit()
        flash("Curso eliminado correctamente.", "success")
    except Exception as e:
        conn.rollback()
        flash("No se pudo eliminar el curso: " + str(e), "error")
    finally:
        cur.close()
        conn.close()

    if session.get("rol") == "admin":
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("profesor_dashboard"))


# ──────────────────────────────────────────────────────────
# CURSO — Editar (solo admin)
# ──────────────────────────────────────────────────────────
@app.route("/curso/<int:curso_id>/editar", methods=["GET", "POST"])
def editar_curso(curso_id):
    if not session.get("user_id"):
        flash("Debes iniciar sesión.", "warning")
        return redirect(url_for("login"))

    if not puede_editar_contenido():
        flash("Solo el administrador puede editar cursos.", "warning")
        return redirect(url_for("curso_detalle", curso_id=curso_id))

    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, titulo, descripcion, precio, imagen_url FROM cursos WHERE id = %s;",
        (curso_id,))
    fila = cur.fetchone()
    if not fila:
        cur.close()
        conn.close()
        return "Curso no encontrado", 404

    if request.method == "GET":
        curso = {
            "id": fila[0], "titulo": fila[1], "descripcion": fila[2],
            "precio": float(fila[3]) if fila[3] is not None else 0,
            "imagen_url": fila[4],
        }
        cur.close()
        conn.close()
        return render_template("editar_curso.html", curso=curso)

    # POST → actualizar
    titulo = request.form.get("titulo")
    descripcion = request.form.get("descripcion")
    precio = request.form.get("precio")
    imagen = request.files.get("imagen")
    imagen_url = fila[4]

    if imagen and allowed_file(imagen.filename):
        filename = secure_filename(imagen.filename)
        ruta = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        imagen.save(ruta)
        imagen_url = "uploads/" + filename

    try:
        cur.execute("""
            UPDATE cursos SET titulo=%s, descripcion=%s, precio=%s, imagen_url=%s
            WHERE id=%s;
        """, (titulo, descripcion, precio, imagen_url, curso_id))
        conn.commit()
        flash("Curso actualizado correctamente.", "success")
    except Exception as e:
        conn.rollback()
        flash("No se pudo actualizar el curso: " + str(e), "error")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("curso_detalle", curso_id=curso_id))


# ──────────────────────────────────────────────────────────
# LECCIÓN — Editar (solo admin)
# ──────────────────────────────────────────────────────────
@app.route("/leccion/<int:leccion_id>/editar", methods=["GET", "POST"])
def editar_leccion(leccion_id):
    if not session.get("user_id"):
        flash("Debes iniciar sesión.", "warning")
        return redirect(url_for("login"))

    if not puede_editar_contenido():
        flash("Solo el administrador puede editar lecciones.", "warning")
        return redirect(url_for("ver_leccion", leccion_id=leccion_id))

    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, curso_id, titulo, video_url, contenido FROM lecciones WHERE id = %s;",
        (leccion_id,))
    fila = cur.fetchone()
    if not fila:
        cur.close()
        conn.close()
        return "Lección no encontrada", 404

    curso_id = fila[1]

    if request.method == "GET":
        leccion = {
            "id": fila[0], "curso_id": fila[1], "titulo": fila[2],
            "video_url": fila[3], "contenido": fila[4],
        }
        cur.close()
        conn.close()
        return render_template("editar_leccion.html", leccion=leccion)

    # POST → actualizar
    titulo = request.form.get("titulo")
    video_url = convertir_youtube(request.form.get("video_url"))
    contenido = request.form.get("contenido")

    try:
        cur.execute("""
            UPDATE lecciones SET titulo=%s, video_url=%s, contenido=%s
            WHERE id=%s;
        """, (titulo, video_url, contenido, leccion_id))
        conn.commit()
        flash("Lección actualizada correctamente.", "success")
    except Exception as e:
        conn.rollback()
        flash("No se pudo actualizar la lección: " + str(e), "error")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("curso_detalle", curso_id=curso_id))


# --------------------------
# Página detalle curso (alumno)
# --------------------------
@app.route("/curso/<int:curso_id>")
def curso_detalle(curso_id):
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, titulo, descripcion, precio, imagen_url, profesor_id FROM cursos WHERE id = %s;",
        (curso_id,)
    )
    curso = cur.fetchone()
    if not curso:
        cur.close()
        conn.close()
        return "Curso no encontrado", 404

    cur.execute(
        "SELECT id, titulo, video_url, contenido, fecha FROM lecciones WHERE curso_id = %s ORDER BY creado_en;",
        (curso_id,)
    )
    lecciones = cur.fetchall()

    profesor_id = curso[5]
    cur.execute("SELECT nombre FROM usuarios WHERE id = %s;", (profesor_id,))
    profesor = cur.fetchone()
    cur.close()
    conn.close()

    datos_curso = {
        "id": curso[0],
        "titulo": curso[1],
        "descripcion": curso[2],
        "precio": float(curso[3]) if curso[3] else 0,
        "imagen_url": curso[4],
        "profesor_id": profesor[0] if profesor else "Desconocido",
        "usuario_logueado": session.get("user_id"),
        "es_profesor": session.get("rol") == "profesor" and session.get("user_id") == profesor_id
    }

    # ── Permisos de gestión sobre este curso ──
    _rol = session.get("rol")
    _es_dueno = (_rol == "profesor" and session.get("user_id") == profesor_id)
    datos_curso["es_admin"] = (_rol == "admin")
    datos_curso["puede_gestionar"] = (_rol == "admin") or _es_dueno   # agregar/eliminar lecciones
    datos_curso["puede_editar"] = (_rol == "admin")                   # editar (solo admin)
    datos_curso["puede_eliminar_curso"] = (_rol == "admin") or _es_dueno

    usuario = session.get("user_id")
    puede_acceder = False
    if usuario:
        conn = conectar_bd()
        cur = conn.cursor()
        cur.execute("SELECT rol FROM usuarios WHERE id = %s;", (usuario,))
        fila_rol = cur.fetchone()

        if not fila_rol:
            # El user_id en sesión no existe en la BD, limpiar sesión
            cur.close()
            conn.close()
            session.clear()
            flash("Tu sesión termino. Inicia sesión nuevamente.", "warning")
            return redirect(url_for("login"))

        rol = fila_rol[0]
        if rol in ('profesor', 'admin'):
            puede_acceder = True
        elif datos_curso["precio"] == 0:
            # Curso gratis: cualquier usuario logueado puede acceder y reseñar
            puede_acceder = True
        else:
            cur.execute("""
                SELECT 1 FROM compras
                WHERE usuario_id = %s AND curso_id = %s AND estado = 'completado' LIMIT 1;
            """, (usuario, datos_curso["id"]))
            if cur.fetchone():
                puede_acceder = True
        cur.close()
        conn.close()

    datos_curso["puede_acceder"] = puede_acceder

    lista_lecciones = [
        {"id": l[0], "titulo": l[1], "video_url": l[2], "contenido": l[3], "fecha": str(l[4]) if l[4] else None}
        for l in lecciones
    ]

    return render_template("curso_detalle.html", curso=datos_curso, lecciones=lista_lecciones)


# --------------------------
# Ver lección
# --------------------------
@app.route("/leccion/<int:leccion_id>")
def ver_leccion(leccion_id):
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT l.id, l.curso_id, l.titulo, l.video_url, l.contenido, l.fecha, c.titulo
        FROM lecciones l
        JOIN cursos c ON l.curso_id = c.id
        WHERE l.id = %s;
    """, (leccion_id,))
    l = cur.fetchone()
    if not l:
        cur.close()
        conn.close()
        return "Lección no encontrada", 404

    datos = {
        "id": l[0], "curso_id": l[1], "titulo": l[2],
        "video_url": l[3], "contenido": l[4],
        "fecha": str(l[5]) if l[5] else None,
        "curso_titulo": l[6]
    }

    puede_ver = False
    es_profesor = False
    usuario = session.get("user_id")
    if usuario:
        cur.execute("SELECT rol FROM usuarios WHERE id = %s;", (usuario,))
        rol = cur.fetchone()[0]
        if rol == 'admin':                    # ← admin ve todo
            puede_ver = True
        elif rol == 'profesor':
            cur.execute("SELECT profesor_id FROM cursos WHERE id = %s;", (datos["curso_id"],))
            profesor_curso = cur.fetchone()[0]
            if profesor_curso == usuario:
                es_profesor = True
            puede_ver = True
        elif datos["curso_titulo"] == "Mente Emprendedora":
            puede_ver = True
        else:
            cur.execute("""
                SELECT 1 FROM compras
                WHERE usuario_id = %s AND curso_id = %s AND estado = 'completado' LIMIT 1;
            """, (usuario, datos["curso_id"]))
            if cur.fetchone():
                puede_ver = True

    cur.close()
    conn.close()

    if not puede_ver:
        flash("Debes adquirir el curso o iniciar sesión con la cuenta del profesor para ver esta lección.", "warning")
        return redirect(url_for("curso_detalle", curso_id=datos["curso_id"]))

    # ... resto del código ...

    conn = conectar_bd()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM reuniones_meet WHERE hora_fin < NOW();")
        conn.commit()
    except Exception as e:
        print("Error al eliminar reuniones expiradas:", e)

    reuniones = []
    try:
        cur.execute("""
            SELECT id, url_meet, hora_inicio, hora_fin, mensaje
            FROM reuniones_meet
            WHERE leccion_id = %s AND activa = TRUE;
        """, (leccion_id,))
        zooms = cur.fetchall()
        reuniones = [{"id": z[0], "url": z[1], "inicio": z[2], "fin": z[3], "mensaje": z[4]} for z in zooms]
    except Exception as e:
        print("Error al consultar reuniones_meet:", e)

    cur.close()
    conn.close()

    rol_sesion = session.get("rol")
    puede_gestionar = (rol_sesion == "admin") or es_profesor   # eliminar lección
    puede_editar = (rol_sesion == "admin")                     # editar (solo admin)

    return render_template(
        "leccion.html", leccion=datos, reuniones=reuniones,
        es_profesor=es_profesor, puede_gestionar=puede_gestionar,
        puede_editar=puede_editar,
    )


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
    metodos = [{"id": f[0], "nombre": f[1], "tipo": f[2]} for f in filas]
    return jsonify(metodos)


# --------------------------
# PASARELA DE PAGO STRIPE
# --------------------------
@app.route("/crear-checkout-session", methods=["POST"])
def crear_checkout():
    if not session.get("user_id"):
        return jsonify({"error": "Debes iniciar sesión"}), 401

    data = request.json
    curso_id = data.get("curso_id")

    if not curso_id:
        return jsonify({"error": "curso_id es requerido"}), 400

    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("SELECT titulo, precio FROM cursos WHERE id = %s;", (curso_id,))
    curso = cur.fetchone()
    cur.close()
    conn.close()

    if not curso:
        return jsonify({"error": "Curso no encontrado"}), 404

    titulo_curso = curso[0]
    precio = float(curso[1]) if curso[1] else 0

    if precio == 0:
        return jsonify({"error": "Este curso es gratuito"}), 400

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": { "name": titulo_curso },
                    "unit_amount": int(precio * 100),
                },
                "quantity": 1,
            }],
            mode="payment",
            # ✅ Guardar datos del usuario en Stripe
            metadata={
                "usuario_id": str(session["user_id"]),
                "curso_id": str(curso_id)
            },
            success_url=f"{BASE_URL}/pago-exitoso?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/pago-cancelado",
        )
        return jsonify({"url": checkout_session.url})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --------------------------
# PAGO EXITOSO
# --------------------------
@app.route("/pago-exitoso")
def pago_exitoso():
    stripe_session_id = request.args.get("session_id")

    if not stripe_session_id:
        flash("Solicitud inválida.", "warning")
        return redirect(url_for("index"))

    # Verificar con Stripe
    try:
        checkout = stripe.checkout.Session.retrieve(stripe_session_id)
    except Exception as e:
        flash("No se pudo verificar el pago.", "error")
        return redirect(url_for("index"))

    if checkout.payment_status != "paid":
        flash("El pago no fue completado.", "error")
        return redirect(url_for("index"))

    # ✅ Recuperar datos desde los metadatos de Stripe
    usuario_id = None
    curso_id = None

    if checkout.metadata:
        if "usuario_id" in checkout.metadata:
            usuario_id = checkout.metadata["usuario_id"]
        if "curso_id" in checkout.metadata:
            curso_id = checkout.metadata["curso_id"]

    if not usuario_id or not curso_id:
        flash("Error al procesar la compra.", "error")
        return redirect(url_for("index"))

    monto = checkout.amount_total / 100

    conn = conectar_bd()
    cur = conn.cursor()

    cur.execute("SELECT id FROM metodos_pago WHERE nombre = %s;", ("Stripe (tarjeta)",))
    metodo = cur.fetchone()
    metodo_pago_id = metodo[0] if metodo else None

    cur.execute("""
        INSERT INTO compras(usuario_id, curso_id, metodo_pago_id, monto, estado, stripe_session_id)
        VALUES (%s, %s, %s, %s, 'completado', %s)
        ON CONFLICT (stripe_session_id) DO NOTHING;
    """, (usuario_id, curso_id, metodo_pago_id, monto, stripe_session_id))

    conn.commit()
    cur.close()
    conn.close()

    # ✅ Restaurar sesión si no está activa
    if not session.get("user_id"):
        session["user_id"] = int(usuario_id)
        conn = conectar_bd()
        cur = conn.cursor()
        cur.execute("SELECT nombre, rol FROM usuarios WHERE id = %s;", (usuario_id,))
        r = cur.fetchone()
        cur.close()
        conn.close()
        if r:
            session["nombre"] = r[0]
            session["rol"] = r[1]

    flash("¡Pago realizado correctamente! ✅", "success")
    return redirect(url_for("mis_compras"))


# --------------------------
# PAGO CANCELADO
# --------------------------
@app.route("/pago-cancelado")
def pago_cancelado():
    flash("El pago fue cancelado.", "warning")
    return redirect(url_for("index"))


# --------------------------
# Mis compras (alumno)
# --------------------------
@app.route("/mis_compras")
def mis_compras():
    if not session.get("user_id"):
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for("login"))

    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, cursos.titulo, c.monto, c.estado, c.fecha, c.curso_id
        FROM compras c JOIN cursos ON c.curso_id = cursos.id
        WHERE c.usuario_id = %s ORDER BY c.fecha DESC;
    """, (session["user_id"],))
    filas = cur.fetchall()

    cur.execute("""
        SELECT COUNT(*) FROM progreso_cursos
        WHERE usuario_id = %s AND completado = TRUE;
    """, (session["user_id"],))
    completados = cur.fetchone()[0]

    cur.close()
    conn.close()

    compras = [
        {"id": f[0], "titulo": f[1], "monto": float(f[2]), "estado": f[3], "fecha": f[4].strftime("%d/%m/%Y") if f[4] else "—", "curso_id": f[5]}
        for f in filas
    ]
    return render_template("mis_compras.html", compras=compras, completados=completados, is_home=True, barra_titulo="Mis Compras")

# --------------------------
# REUNIONES JITSI MEET
# --------------------------
@app.route("/profesor/leccion/<int:leccion_id>/crear-meet", methods=["POST"])
def crear_reunion_meet(leccion_id):
    if not requiere_profesor():
        return jsonify({"error": "No autorizado"}), 401

    profesor_actual = session.get("user_id")
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.profesor_id FROM cursos c
        JOIN lecciones l ON l.curso_id = c.id
        WHERE l.id = %s;
    """, (leccion_id,))
    res = cur.fetchone()
    if not res or res[0] != profesor_actual:
        cur.close()
        conn.close()
        return jsonify({"error": "No autorizado (no eres el profesor de este curso)"}), 403

    data = request.json
    hora_inicio = data.get("hora_inicio")
    hora_fin = data.get("hora_fin")
    mensaje = data.get("mensaje")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reuniones_meet (
            id SERIAL PRIMARY KEY,
            leccion_id INTEGER REFERENCES lecciones(id),
            url_meet TEXT NOT NULL,
            hora_inicio TIMESTAMP NOT NULL,
            hora_fin TIMESTAMP NOT NULL,
            mensaje TEXT,
            activa BOOLEAN DEFAULT TRUE,
            creada_en TIMESTAMP DEFAULT NOW()
        );
    """)

    sala = "emprende_" + str(uuid.uuid4())[:8]
    url_meet = f"https://meet.jit.si/{sala}"

    try:
        cur.execute("""
            INSERT INTO reuniones_meet (leccion_id, url_meet, hora_inicio, hora_fin, mensaje)
            VALUES (%s,%s,%s,%s,%s) RETURNING id;
        """, (leccion_id, url_meet, hora_inicio, hora_fin, mensaje))
        meet_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        cur.close()
        conn.close()
        return jsonify({"error": "Error al crear reunión: " + str(e)}), 500

    cur.close()
    conn.close()
    return jsonify({"mensaje": "Reunión creada", "url": url_meet, "id": meet_id})


@app.route("/meet/<int:meet_id>/eliminar", methods=["POST"])
def eliminar_meet(meet_id):
    if not requiere_profesor():
        return jsonify({"error": "No autorizado"}), 401

    profesor_actual = session.get("user_id")
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.profesor_id FROM cursos c
        JOIN lecciones l ON l.curso_id = c.id
        JOIN reuniones_meet m ON m.leccion_id = l.id
        WHERE m.id = %s;
    """, (meet_id,))
    res = cur.fetchone()
    if not res or res[0] != profesor_actual:
        cur.close()
        conn.close()
        return jsonify({"error": "No autorizado"}), 403

    cur.execute("DELETE FROM reuniones_meet WHERE id = %s;", (meet_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"mensaje": "Reunión eliminada correctamente"}), 200


@app.route("/leccion/<int:leccion_id>/meet")
def obtener_meet_leccion(leccion_id):
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, url_meet, hora_inicio, hora_fin, mensaje
        FROM reuniones_meet
        WHERE leccion_id = %s AND activa = TRUE;
    """, (leccion_id,))
    filas = cur.fetchall()
    cur.close()
    conn.close()

    zooms = [
        {"id": f[0], "url": f[1], "inicio": str(f[2]), "fin": str(f[3]), "mensaje": f[4]}
        for f in filas
    ]
    return jsonify(zooms)


# --------------------------
# NOTIFICACIONES
# --------------------------
@app.route("/notificaciones")
def obtener_notificaciones():
    if not session.get("user_id"):
        return jsonify({"error": "No autenticado"}), 401

    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, tipo, titulo, mensaje, leccion_id, leida, creada_en
        FROM notificaciones
        WHERE usuario_id = %s
        ORDER BY creada_en DESC
        LIMIT 20;
    """, (session["user_id"],))
    filas = cur.fetchall()
    cur.close()
    conn.close()

    notificaciones = [
        {
            "id": f[0], "tipo": f[1], "titulo": f[2], "mensaje": f[3],
            "leccion_id": f[4], "leida": f[5], "fecha": str(f[6])
        }
        for f in filas
    ]
    return jsonify(notificaciones)


@app.route("/notificacion/<int:notif_id>/marcar-leida", methods=["POST"])
def marcar_notificacion_leida(notif_id):
    if not session.get("user_id"):
        return jsonify({"error": "No autenticado"}), 401

    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("UPDATE notificaciones SET leida = TRUE WHERE id = %s;", (notif_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"mensaje": "Notificación marcada como leída"})


# --------------------------
# ESTILOS PERSONALIZADOS POR CURSO
# --------------------------
@app.route("/profesor/curso/<int:curso_id>/estilos", methods=["GET", "POST"])
def editar_estilos_curso(curso_id):
    if not requiere_profesor():
        return jsonify({"error": "No autorizado"}), 401

    if request.method == "POST":
        data = request.json
        color_principal = data.get("color_principal", "#007bff")
        color_secundario = data.get("color_secundario", "#6c757d")
        fuente = data.get("fuente", "Lato")
        css_personalizado = data.get("css_personalizado", "")

        conn = conectar_bd()
        cur = conn.cursor()
        cur.execute("SELECT id FROM estilos_curso WHERE curso_id = %s;", (curso_id,))
        existe = cur.fetchone()

        if existe:
            cur.execute("""
                UPDATE estilos_curso
                SET color_principal = %s, color_secundario = %s, fuente = %s, css_personalizado = %s
                WHERE curso_id = %s;
            """, (color_principal, color_secundario, fuente, css_personalizado, curso_id))
        else:
            cur.execute("""
                INSERT INTO estilos_curso (curso_id, color_principal, color_secundario, fuente, css_personalizado)
                VALUES (%s, %s, %s, %s, %s);
            """, (curso_id, color_principal, color_secundario, fuente, css_personalizado))

        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"mensaje": "Estilos actualizados"})

    else:
        conn = conectar_bd()
        cur = conn.cursor()
        cur.execute("""
            SELECT color_principal, color_secundario, fuente, css_personalizado
            FROM estilos_curso WHERE curso_id = %s;
        """, (curso_id,))
        resultado = cur.fetchone()
        cur.close()
        conn.close()

        if resultado:
            return jsonify({
                "color_principal": resultado[0], "color_secundario": resultado[1],
                "fuente": resultado[2], "css_personalizado": resultado[3]
            })
        return jsonify({"color_principal": "#007bff", "color_secundario": "#6c757d", "fuente": "Lato", "css_personalizado": ""})


@app.route("/curso/<int:curso_id>/estilos-datos")
def obtener_estilos_curso(curso_id):
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT color_principal, color_secundario, fuente, css_personalizado
        FROM estilos_curso WHERE curso_id = %s;
    """, (curso_id,))
    resultado = cur.fetchone()
    cur.close()
    conn.close()

    if resultado:
        return jsonify({
            "color_principal": resultado[0], "color_secundario": resultado[1],
            "fuente": resultado[2], "css_personalizado": resultado[3]
        })
    return jsonify({"color_principal": "#007bff", "color_secundario": "#6c757d", "fuente": "Lato", "css_personalizado": ""})


# --------------------------
# Perfiles
# --------------------------
@app.route("/perfil")
def perfil():
    if not session.get("user_id"):
        flash("Debes iniciar sesión.", "warning")
        return redirect(url_for("login"))

    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT nombre, apellido, username, correo, rol, creado_en, foto_perfil
        FROM usuarios WHERE id = %s;
    """, (session["user_id"],))
    usuario = cur.fetchone()
    cur.close()
    conn.close()

    if not usuario:
        flash("Usuario no encontrado.", "error")
        return redirect(url_for("index"))

    datos = {
        "nombre": usuario[0], "apellido": usuario[1], "username": usuario[2],
        "correo": usuario[3], "rol": usuario[4], "creado_en": usuario[5], "foto": usuario[6]
    }
    return render_template("perfil.html", usuario=datos)


@app.route("/perfil/editar", methods=["GET", "POST"])
def editar_perfil():
    if not session.get("user_id"):
        flash("Debes iniciar sesión.", "warning")
        return redirect(url_for("login"))

    conn = conectar_bd()
    cur = conn.cursor()

    if request.method == "POST":
        nombre = request.form.get("nombre")
        apellido = request.form.get("apellido")
        username = request.form.get("username")
        foto = request.files.get("foto")
        foto_path = None

        if foto and allowed_file(foto.filename):
            filename = secure_filename(f"user_{session['user_id']}_{foto.filename}")
            ruta = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            foto.save(ruta)
            foto_path = f"uploads/{filename}"
            cur.execute("""
                UPDATE usuarios SET nombre=%s, apellido=%s, username=%s, foto_perfil=%s
                WHERE id=%s;
            """, (nombre, apellido, username, foto_path, session["user_id"]))
        else:
            cur.execute("""
                UPDATE usuarios SET nombre=%s, apellido=%s, username=%s
                WHERE id=%s;
            """, (nombre, apellido, username, session["user_id"]))

        conn.commit()
        flash("Perfil actualizado correctamente.", "success")
        cur.close()
        conn.close()
        return redirect(url_for("perfil"))

    cur.execute("""
        SELECT nombre, apellido, username, foto_perfil
        FROM usuarios WHERE id=%s;
    """, (session["user_id"],))
    usuario = cur.fetchone()
    cur.close()
    conn.close()
    return render_template("editar_perfil.html", usuario=usuario)


@app.context_processor
def inject_user():
    if session.get("user_id"):
        conn = conectar_bd()
        cur = conn.cursor()
        cur.execute("SELECT foto_perfil FROM usuarios WHERE id=%s;", (session["user_id"],))
        r = cur.fetchone()
        cur.close()
        conn.close()
        return dict(usuario_sidebar={"foto": r[0] if r else None})
    return dict(usuario_sidebar=None)


# --------------------------
# FORO POR CURSO
# --------------------------
@app.route("/curso/<int:curso_id>/foro")
def foro_curso(curso_id):
    if not session.get("user_id"):
        flash("Debes iniciar sesión para acceder al foro.", "warning")
        return redirect(url_for("login"))

    usuario_id = session["user_id"]
    conn = conectar_bd()
    cur = conn.cursor()

    cur.execute("SELECT rol FROM usuarios WHERE id = %s;", (usuario_id,))
    rol = cur.fetchone()[0]

    if rol != 'profesor':
        cur.execute("""
            SELECT 1 FROM compras
            WHERE usuario_id = %s AND curso_id = %s AND estado = 'completado';
        """, (usuario_id, curso_id))
        if not cur.fetchone():
            cur.close()
            conn.close()
            flash("No estás inscrito en este curso.", "warning")
            return redirect(url_for("index"))

    cur.execute("""
        SELECT fp.id, fp.titulo, fp.contenido, fp.creado_en,
               u.nombre, u.apellido, u.foto_perfil
        FROM foro_posts fp
        JOIN usuarios u ON fp.usuario_id = u.id
        WHERE fp.curso_id = %s
        ORDER BY fp.creado_en DESC;
    """, (curso_id,))
    posts = cur.fetchall()
    cur.close()
    conn.close()

    foro_posts = [
        {
            "id": p[0], "titulo": p[1], "contenido": p[2], "creado_en": p[3],
            "autor": f"{p[4]} {p[5]}" if p[5] else p[4], "foto_autor": p[6]
        }
        for p in posts
    ]
    return render_template("foro.html", curso_id=curso_id, posts=foro_posts)


@app.route("/curso/<int:curso_id>/foro/post", methods=["POST"])
def crear_post_foro(curso_id):
    if not session.get("user_id"):
        return jsonify({"error": "No autenticado"}), 401

    usuario_id = session["user_id"]
    conn = conectar_bd()
    cur = conn.cursor()

    cur.execute("""
        SELECT 1 FROM compras
        WHERE usuario_id = %s AND curso_id = %s AND estado = 'completado';
    """, (usuario_id, curso_id))
    if not cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"error": "No inscrito"}), 403

    data = request.json
    titulo = data.get("titulo")
    contenido = data.get("contenido")

    if not titulo or not contenido:
        cur.close()
        conn.close()
        return jsonify({"error": "Título y contenido requeridos"}), 400

    cur.execute("""
        INSERT INTO foro_posts (curso_id, usuario_id, titulo, contenido)
        VALUES (%s, %s, %s, %s);
    """, (curso_id, usuario_id, titulo, contenido))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"mensaje": "Post creado"}), 201

@app.route("/notificaciones/no-leidas")
def notificaciones_no_leidas():

    if not session.get("user_id"):
        return jsonify({"cantidad": 0})
    
    conn = conectar_bd()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) FROM notificaciones
        WHERE usuario_id = %s AND leida = FALSE;
    """, (session["user_id"],))

    cantidad =cur.fetchone()[0]
    cur.close()
    conn.close()

    return jsonify({"cantidad": cantidad})
# --------------------------
# PROGRESO DE LECCIONES
# --------------------------
@app.route("/leccion/<int:leccion_id>/completar", methods=["POST"])
def completar_leccion(leccion_id):
    if not session.get("user_id"):
        return jsonify({"error": "No autenticado"}), 401

    usuario_id = session["user_id"]
    conn = conectar_bd()
    cur = conn.cursor()

    cur.execute("""
        SELECT l.curso_id, c.titulo, c.precio
        FROM lecciones l
        JOIN cursos c ON l.curso_id = c.id
        WHERE l.id = %s
    """, (leccion_id,))
    leccion = cur.fetchone()
    if not leccion:
        cur.close()
        conn.close()
        return jsonify({"error": "Lección no encontrada"}), 404

    curso_id = leccion[0]
    precio_leccion = float(leccion[2]) if leccion[2] else 0

    puede_ver = False
    cur.execute("SELECT rol FROM usuarios WHERE id = %s", (usuario_id,))
    rol = cur.fetchone()[0]
    if rol in ('profesor', 'admin'):
        puede_ver = True
    elif precio_leccion == 0:
        # Curso gratis: acceso libre
        puede_ver = True
    else:
        cur.execute("""
            SELECT 1 FROM compras
            WHERE usuario_id = %s AND curso_id = %s AND estado = 'completado'
        """, (usuario_id, curso_id))
        if cur.fetchone():
            puede_ver = True

    if not puede_ver:
        cur.close()
        conn.close()
        return jsonify({"error": "No autorizado"}), 403

    cur.execute("""
        INSERT INTO progreso_lecciones (usuario_id, leccion_id, completada, fecha_completado, ultima_interaccion)
        VALUES (%s, %s, TRUE, NOW(), NOW())
        ON CONFLICT (usuario_id, leccion_id)
        DO UPDATE SET completada = TRUE, fecha_completado = NOW(), ultima_interaccion = NOW()
    """, (usuario_id, leccion_id))

    cur.execute("SELECT COUNT(*) FROM lecciones WHERE curso_id = %s", (curso_id,))
    total_lecciones = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*)
        FROM progreso_lecciones pl
        JOIN lecciones l ON pl.leccion_id = l.id
        WHERE pl.usuario_id = %s AND l.curso_id = %s AND pl.completada = TRUE
    """, (usuario_id, curso_id))
    completadas = cur.fetchone()[0]

    porcentaje = round((completadas / total_lecciones * 100) if total_lecciones > 0 else 0, 1)

    # Crear notificación de progreso

    faltantes = total_lecciones - completadas

    mensaje = (
        f"Llevas {completadas} de {total_lecciones} lecciones completadas. "
        f"Tu progreso actual es del {porcentaje}%. "
        f"Te faltan {faltantes} lecciones para terminar el curso."
    )

    cur.execute("""
        INSERT INTO notificaciones
        (usuario_id, tipo, titulo, mensaje, leccion_id)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        usuario_id,
        "progreso",
        "Actualización de progreso",
        mensaje,
        leccion_id
    ))

    if porcentaje >= 100:
        cur.execute("""
                insert into notificaciones
                (usuario_id, tipo, titulo, mensaje)
                values (%s, %s, %s, %s)
            """, (
                usuario_id,
                "completado",
                "Curso completado",
                f"¡Felicidades! Has completado el curso '{leccion[1]}'  y ya puedes solicitar tu certificado."
            ))
        
    if porcentaje >= 25 and porcentaje < 50:
        cur.execute("""
                insert into notificaciones
                (usuario_id, tipo, titulo, mensaje)
                values (%s, %s, %s, %s)
            """, (
                usuario_id,
                "progreso",
                "¡Buen comienzo!",
                f"¡Genial! Has completado el {porcentaje}% del curso '{leccion[1]}'. Sigue así para alcanzar tus metas."
            ))
    
    elif porcentaje >= 50 and porcentaje < 75:
        cur.execute("""
                insert into notificaciones
                (usuario_id, tipo, titulo, mensaje)
                values (%s, %s, %s, %s)
            """, (
                usuario_id,
                "progreso",
                "¡Mitad del camino!",
                f"¡Excelente! Has completado el {porcentaje}% del curso '{leccion[1]}'. Estás a mitad de camino, ¡no te detengas ahora!"
            ))
    
        

    cur.execute("""
        INSERT INTO progreso_cursos (usuario_id, curso_id, porcentaje, ultima_actualizacion, completado)
        VALUES (%s, %s, %s, NOW(), %s)
        ON CONFLICT (usuario_id, curso_id)
        DO UPDATE SET porcentaje = %s, ultima_actualizacion = NOW(), completado = %s
    """, (usuario_id, curso_id, porcentaje, porcentaje >= 99.9, porcentaje, porcentaje >= 99.9))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "porcentaje_curso": porcentaje,
        "leccion_completada": leccion_id
    })


@app.route("/mis-cursos/progreso")
def mis_cursos_progreso():
    if not session.get("user_id"):
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for("login"))

    usuario_id = session["user_id"]
    conn = conectar_bd()
    cur = conn.cursor()

    # FIX: incluir todos los cursos comprados, aunque no haya progreso aún
    cur.execute("""
        SELECT
            c.id AS curso_id,
            c.titulo,
            c.imagen_url,
            COALESCE(pc.porcentaje, 0) AS porcentaje,
            COALESCE(pc.completado, FALSE) AS completado,
            COALESCE(pc.ultima_actualizacion, comp.fecha) AS ultima_actualizacion,
            COUNT(l.id) AS total_lecciones,
            COUNT(pl.id) FILTER (WHERE pl.completada = TRUE) AS lecciones_completadas
        FROM compras comp
        JOIN cursos c ON comp.curso_id = c.id
        LEFT JOIN progreso_cursos pc ON pc.curso_id = c.id AND pc.usuario_id = comp.usuario_id
        LEFT JOIN lecciones l ON l.curso_id = c.id
        LEFT JOIN progreso_lecciones pl ON pl.leccion_id = l.id AND pl.usuario_id = comp.usuario_id
        WHERE comp.usuario_id = %s AND comp.estado = 'completado'
        GROUP BY c.id, c.titulo, c.imagen_url, pc.porcentaje, pc.completado, pc.ultima_actualizacion, comp.fecha
        ORDER BY ultima_actualizacion DESC
    """, (usuario_id,))

    filas = cur.fetchall()
    cur.close()
    conn.close()

    cursos = [
        {
            "curso_id": row[0], "titulo": row[1], "imagen_url": row[2],
            "porcentaje": float(row[3]), "completado": row[4],
            "ultima_actualizacion": str(row[5]),
            "total_lecciones": row[6] or 0,
            "lecciones_completadas": row[7] or 0
        }
        for row in filas
    ]
    return render_template("mis_cursos.html", cursos=cursos)

# --------------------------
# BÚSQUEDA
# --------------------------

@app.route("/certificado/<int:curso_id>")
def ver_certificado(curso_id):
    if not session.get("user_id"):
        flash("Debes iniciar sesión", "warning")
        return redirect(url_for("login"))

    usuario_id = session["user_id"]
    conn = conectar_bd()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            c.titulo,
            u_est.nombre,
            COALESCE(u_est.apellido, ''),
            u_prof.nombre,
            COALESCE(u_prof.apellido, ''),
            pc.completado,
            pc.ultima_actualizacion
        FROM cursos c
        JOIN usuarios u_est ON u_est.id = %s
        JOIN usuarios u_prof ON u_prof.id = c.profesor_id
        LEFT JOIN progreso_cursos pc ON pc.curso_id = c.id AND pc.usuario_id = %s
        WHERE c.id = %s
    """, (usuario_id, usuario_id, curso_id))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row or not row[5]:
        flash("Debes completar el curso para ver el certificado.", "warning")
        return redirect(url_for("mis_cursos_progreso"))

    curso_nombre      = row[0]
    nombre_estudiante = f"{row[1]} {row[2]}".strip()
    nombre_instructor = f"{row[3]} {row[4]}".strip()
    fecha_emision     = row[6].strftime("%d de %B de %Y") if row[6] else datetime.now().strftime("%d de %B de %Y")
    folio             = f"IYE-{curso_id}-{usuario_id:04d}"

    return render_template("certificados.html",
        curso_nombre=curso_nombre,
        nombre_estudiante=nombre_estudiante,
        nombre_instructor=nombre_instructor,
        fecha_emision=fecha_emision,
        folio=folio
    )


@app.route("/buscar")
def buscar():
    query = request.args.get("q")
    if not query:
        return redirect(url_for("index"))

    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, titulo, descripcion, precio, imagen_url
        FROM cursos
        WHERE LOWER(titulo) LIKE LOWER(%s)
        OR LOWER(descripcion) LIKE LOWER(%s)
        ORDER BY creado_en DESC;
    """, (f"%{query}%", f"%{query}%"))
    filas = cur.fetchall()
    cur.close()
    conn.close()

    resultados = [
        {
            "id": f[0], "titulo": f[1], "descripcion": f[2],
            "precio": float(f[3]) if f[3] else 0, "imagen_url": f[4]
        }
        for f in filas
    ]
    return render_template("resultados.html", query=query, resultados=resultados)



 

# --------------------------
# Eliminar lección (solo profesor)
# --------------------------
@app.route("/profesor/leccion/<int:leccion_id>/eliminar", methods=["POST"])
def profesor_eliminar_leccion(leccion_id):
    if not session.get("user_id"):
        flash("Debes iniciar sesión.", "warning")
        return redirect(url_for("login"))

    if not puede_eliminar_contenido():
        flash("No tienes permiso para eliminar lecciones.", "warning")
        return redirect(url_for("index"))

    conn = conectar_bd()
    cur = conn.cursor()

    # Obtener el curso de la lección
    cur.execute("SELECT curso_id FROM lecciones WHERE id = %s;", (leccion_id,))
    fila = cur.fetchone()
    if not fila:
        cur.close()
        conn.close()
        flash("La lección no existe.", "error")
        return redirect(url_for("index"))

    curso_id = fila[0]

    # Admin elimina cualquiera; el profesor solo en sus cursos
    if not puede_gestionar_curso(cur, curso_id):
        cur.close()
        conn.close()
        flash("No tienes permiso para eliminar esta lección.", "error")
        return redirect(url_for("curso_detalle", curso_id=curso_id))

    eliminar_leccion_completa(cur, leccion_id)
    conn.commit()
    cur.close()
    conn.close()

    flash("Lección eliminada correctamente.", "success")
    return redirect(url_for("curso_detalle", curso_id=curso_id))


# --------------------------
# REPORTES (solo profesor)
# --------------------------
@app.route("/profesor/reportes")
def profesor_reportes():
    if not session.get("user_id"):
        flash("Debes iniciar sesión.", "warning")
        return redirect(url_for("login"))
    if not requiere_profesor():
        flash("Acceso solo para profesores.", "warning")
        return redirect(url_for("index"))

    profesor_id = session["user_id"]
    conn = conectar_bd()
    cur = conn.cursor()

    # Alumnos inscritos y total recaudado por curso (todos los cursos)
    cur.execute("""
        SELECT
            c.id,
            c.titulo,
            COUNT(DISTINCT comp.usuario_id)   AS total_alumnos,
            COALESCE(SUM(comp.monto), 0)       AS ingresos_totales,
            c.precio
        FROM cursos c
        LEFT JOIN compras comp
               ON comp.curso_id = c.id AND comp.estado = 'completado'
        GROUP BY c.id, c.titulo, c.precio
        ORDER BY ingresos_totales DESC;
    """)
    filas_cursos = cur.fetchall()

    # Últimas 10 ventas (todas)
    cur.execute("""
        SELECT
            u.nombre || ' ' || COALESCE(u.apellido, '') AS alumno,
            c.titulo AS curso,
            comp.monto,
            comp.fecha
        FROM compras comp
        JOIN cursos   c ON comp.curso_id  = c.id
        JOIN usuarios u ON comp.usuario_id = u.id
        WHERE comp.estado = 'completado'
        ORDER BY comp.fecha DESC
        LIMIT 10;
    """)
    ultimas_ventas = cur.fetchall()

    # Todos los usuarios registrados
    cur.execute("""
        SELECT nombre, COALESCE(apellido, ''), correo, rol, creado_en
        FROM usuarios
        ORDER BY creado_en DESC;
    """)
    filas_usuarios = cur.fetchall()

    cur.close()
    conn.close()

    resumen_cursos = [
        {
            "id": f[0],
            "titulo": f[1],
            "total_alumnos": f[2],
            "ingresos_totales": float(f[3]),
            "precio": float(f[4]) if f[4] else 0,
        }
        for f in filas_cursos
    ]

    ventas = [
        {
            "alumno": v[0].strip(),
            "curso": v[1],
            "monto": float(v[2]),
            "fecha": v[3].strftime("%d/%m/%Y %H:%M") if v[3] else "-",
        }
        for v in ultimas_ventas
    ]

    usuarios = [
        {
            "nombre": u[0] + (" " + u[1] if u[1] else ""),
            "correo": u[2],
            "rol": u[3],
            "creado_en": u[4].strftime("%d/%m/%Y") if u[4] else "-",
        }
        for u in filas_usuarios
    ]

    total_ingresos = sum(r["ingresos_totales"] for r in resumen_cursos)
    total_alumnos  = sum(r["total_alumnos"]   for r in resumen_cursos)

    return render_template(
        "reportes_profesor.html",
        resumen_cursos=resumen_cursos,
        ventas=ventas,
        usuarios=usuarios,
        total_ingresos=total_ingresos,
        total_alumnos=total_alumnos,
        now=datetime.now(),
    )

@app.route("/curso/<int:curso_id>/resenas")
def obtener_resenas(curso_id):
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute("""
        SELECT r.id, r.puntaje, r.comentario, r.creado_en,
               u.nombre, u.apellido, u.foto_perfil
        FROM resenas r
        JOIN usuarios u ON r.usuario_id = u.id
        WHERE r.curso_id = %s
        ORDER BY r.creado_en DESC;
    """, (curso_id,))
    filas = cur.fetchall()

    cur.execute("SELECT AVG(puntaje), COUNT(*) FROM resenas WHERE curso_id = %s;", (curso_id,))
    stats = cur.fetchone()
    cur.close()
    conn.close()

    resenas = [
        {
            "id": f[0],
            "puntaje": f[1],
            "comentario": f[2],
            "fecha": f[3].strftime("%d/%m/%Y") if f[3] else "",
            "autor": f"{f[4]} {f[5]}" if f[5] else f[4],
            "foto": f[6]
        }
        for f in filas
    ]
    return jsonify({
        "resenas": resenas,
        "promedio": round(float(stats[0]), 1) if stats[0] else 0,
        "total": stats[1]
    })


@app.route("/curso/<int:curso_id>/resena", methods=["POST"])
def crear_resena(curso_id):
    if not session.get("user_id"):
        return jsonify({"error": "Debes iniciar sesión"}), 401

    usuario_id = session["user_id"]
    conn = conectar_bd()
    cur = conn.cursor()

    cur.execute("SELECT rol FROM usuarios WHERE id = %s;", (usuario_id,))
    rol = cur.fetchone()[0]

    if rol != 'profesor':
        # Verificar que el usuario pueda acceder al curso:
        # 1) Curso gratis (precio = 0 o NULL)
        # 2) Tiene compra completada
        cur.execute("SELECT precio FROM cursos WHERE id = %s;", (curso_id,))
        fila_precio = cur.fetchone()
        precio_curso = float(fila_precio[0]) if fila_precio and fila_precio[0] else 0

        if precio_curso > 0:
            cur.execute("""
                SELECT 1 FROM compras
                WHERE usuario_id = %s AND curso_id = %s AND estado = 'completado';
            """, (usuario_id, curso_id))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({"error": "Solo puedes reseñar cursos que hayas comprado"}), 403

    data = request.json
    puntaje = data.get("puntaje")
    comentario = data.get("comentario", "").strip()

    if not puntaje or not (1 <= int(puntaje) <= 5):
        cur.close()
        conn.close()
        return jsonify({"error": "Puntaje inválido (1-5)"}), 400

    if not comentario:
        cur.close()
        conn.close()
        return jsonify({"error": "El comentario no puede estar vacío"}), 400

    try:
        cur.execute("""
            INSERT INTO resenas (curso_id, usuario_id, puntaje, comentario)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (usuario_id, curso_id)
            DO UPDATE SET puntaje = %s, comentario = %s, creado_en = NOW();
        """, (curso_id, usuario_id, puntaje, comentario, puntaje, comentario))
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({"error": str(e)}), 500

    cur.close()
    conn.close()
    return jsonify({"mensaje": "Reseña guardada correctamente"}), 201
# --------------------------
# Ejecutar app
# --------------------------
if __name__ == "__main__":
    crear_tablas()
    app.run(host="0.0.0.0", port=5000, debug=True)