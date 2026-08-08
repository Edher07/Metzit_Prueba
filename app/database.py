"""Conexión SQLite + esquema + datos semilla para Metzit — Agua y Pueblo.

Reemplaza las constantes SEED_USERS / SEED_TURNOS / SEED_AVISOS / SEED_ACTIVIDADES /
CULTIVOS que en el prototipo original vivían en memoria del navegador: ahora se
guardan en una base de datos SQLite real (`metzit.sqlite3`, junto a este archivo)
la primera vez que se levanta el servidor.
"""
import sqlite3

from flask import current_app, g
from werkzeug.security import generate_password_hash

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS usuarios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario         TEXT NOT NULL UNIQUE,   -- nombre de acceso (login)
    password_hash   TEXT NOT NULL,
    nombre          TEXT NOT NULL,
    direccion       TEXT,
    telefono        TEXT,
    parcela         TEXT,
    rol             TEXT NOT NULL CHECK (rol IN ('comisariado', 'usuario')),
    activo          INTEGER NOT NULL DEFAULT 1,
    fecha_registro  TEXT
);

-- Nota: los usuarios ya no se eliminan físicamente (solo se activan/desactivan),
-- por eso turnos, multas y demás registros siempre conservan una referencia
-- válida a un usuario real y nunca deben mostrar "(usuario eliminado)".
CREATE TABLE IF NOT EXISTS turnos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
    fecha           TEXT NOT NULL,
    hora_inicio     TEXT NOT NULL,
    hora_fin        TEXT NOT NULL,
    sector          TEXT NOT NULL,
    estado          TEXT NOT NULL DEFAULT 'programado'
                    CHECK (estado IN ('programado','en_curso','completado','cancelado'))
);

-- alcance='general': visible para toda la comunidad.
-- alcance='personal': visible solo para el comisariado y los usuarios listados
-- en aviso_destinatarios.
CREATE TABLE IF NOT EXISTS avisos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo          TEXT NOT NULL,
    contenido       TEXT NOT NULL,
    tipo            TEXT NOT NULL DEFAULT 'informativo'
                    CHECK (tipo IN ('informativo','urgente','mantenimiento','incidencia')),
    alcance         TEXT NOT NULL DEFAULT 'general' CHECK (alcance IN ('general','personal')),
    fecha           TEXT NOT NULL,
    autor           TEXT NOT NULL,
    activo          INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS aviso_destinatarios (
    aviso_id        INTEGER NOT NULL REFERENCES avisos(id) ON DELETE CASCADE,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
    PRIMARY KEY (aviso_id, usuario_id)
);

CREATE TABLE IF NOT EXISTS actividades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo            TEXT NOT NULL DEFAULT 'faena' CHECK (tipo IN ('faena','junta')),
    titulo          TEXT NOT NULL,
    descripcion     TEXT,
    fecha           TEXT NOT NULL,
    hora            TEXT NOT NULL,
    lugar           TEXT,
    multa           INTEGER
);

CREATE TABLE IF NOT EXISTS actividad_participantes (
    actividad_id    INTEGER NOT NULL REFERENCES actividades(id) ON DELETE CASCADE,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    PRIMARY KEY (actividad_id, usuario_id)
);

-- Multas: solo el comisariado ve todas; un usuario normal solo ve las suyas.
-- El saldo pendiente (monto_total - monto_pagado) se actualiza mediante abonos
-- registrados en multa_pagos, y el estado se recalcula automáticamente.
CREATE TABLE IF NOT EXISTS multas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
    concepto        TEXT NOT NULL,
    descripcion     TEXT,
    monto_total     REAL NOT NULL,
    monto_pagado    REAL NOT NULL DEFAULT 0,
    estado          TEXT NOT NULL DEFAULT 'pendiente'
                    CHECK (estado IN ('pendiente','parcial','pagada')),
    fecha           TEXT NOT NULL,
    actividad_id    INTEGER REFERENCES actividades(id) ON DELETE SET NULL,
    creado_por      TEXT
);

CREATE TABLE IF NOT EXISTS multa_pagos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    multa_id        INTEGER NOT NULL REFERENCES multas(id) ON DELETE CASCADE,
    monto           REAL NOT NULL,
    fecha           TEXT NOT NULL,
    registrado_por  TEXT
);

CREATE TABLE IF NOT EXISTS cultivos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT NOT NULL,
    temporada       TEXT,
    frecuencia_riego TEXT,
    consumo_agua    TEXT,
    descripcion     TEXT,
    accent          TEXT NOT NULL DEFAULT '#16A34A'
);


CREATE TABLE IF NOT EXISTS historial_actividades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    tipo_accion TEXT NOT NULL,        -- 'crear_turno', 'cancelar_turno', 'editar_turno', 'login', etc.
    modulo TEXT NOT NULL,             -- 'turnos', 'avisos', 'usuarios', etc.
    descripcion TEXT,                 -- texto legible: "Canceló turno de riego Sector Oriente"
    entidad_id INTEGER,               -- id del turno/aviso/etc afectado (opcional)
    fecha_hora TEXT NOT NULL,         -- ISO 8601: '2026-08-06T12:40:04'
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);
"""

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE_PATH"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)


def init_db(app):
    """Crea las tablas (si no existen) y siembra los datos iniciales una sola vez."""
    with app.app_context():
        db = sqlite3.connect(app.config["DATABASE_PATH"])
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(SCHEMA_SQL)
        db.commit()
        _seed_if_empty(db)
        db.close()


def _seed_if_empty(db):
    if db.execute("SELECT COUNT(*) AS c FROM usuarios").fetchone()["c"] == 0:
        _seed_usuarios(db)
    if db.execute("SELECT COUNT(*) AS c FROM turnos").fetchone()["c"] == 0:
        _seed_turnos(db)
    if db.execute("SELECT COUNT(*) AS c FROM avisos").fetchone()["c"] == 0:
        _seed_avisos(db)
    if db.execute("SELECT COUNT(*) AS c FROM actividades").fetchone()["c"] == 0:
        _seed_actividades(db)
    if db.execute("SELECT COUNT(*) AS c FROM multas").fetchone()["c"] == 0:
        _seed_multas(db)
    if db.execute("SELECT COUNT(*) AS c FROM cultivos").fetchone()["c"] == 0:
        _seed_cultivos(db)
    db.commit()


def _seed_usuarios(db):
    usuarios = [
        # usuario(login), password demo, nombre, direccion, telefono, parcela, rol, activo, fecha_registro
        ("comisariado", "1234", "Manuel Ramiro Soto", "Calle Principal s/n", "775-101-2030", "Administrador", "comisariado", 1, "1 ene. 2026"),
        ("usuario", "1234", "José Hernández Reyes", "Calle del Río 12", "775-201-4050", "1.5 ha — Sector Norte", "usuario", 1, "5 ene. 2026"),
        ("maria.gonzalez", "1234", "María González Pérez", "Calle Morelos 8", "775-202-4060", "0.8 ha — Sector Sur", "usuario", 1, "6 ene. 2026"),
        ("pedro.soto", "1234", "Pedro Soto Ramírez", "Camino a la Cañada 3", "775-203-4070", "2.0 ha — Sector Oriente", "usuario", 1, "8 ene. 2026"),
        ("guadalupe.torres", "1234", "Guadalupe Torres Méndez", "Calle Hidalgo 15", "775-204-4080", "1.2 ha — Sector Norte", "usuario", 1, "10 ene. 2026"),
        ("antonio.flores", "1234", "Antonio Flores Cruz", "Calle Reforma 22", "775-205-4090", "0.5 ha — Sector Sur", "usuario", 0, "12 ene. 2026"),
    ]
    for u, pw, nombre, direccion, telefono, parcela, rol, activo, fecha in usuarios:
        db.execute(
            """INSERT INTO usuarios (usuario, password_hash, nombre, direccion, telefono, parcela, rol, activo, fecha_registro)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (u, generate_password_hash(pw), nombre, direccion, telefono, parcela, rol, activo, fecha),
        )


def _seed_turnos(db):
    # usuario_id corresponde al orden de inserción de _seed_usuarios (1=comisariado ... 6=antonio.flores)
    turnos = [
        (2, "2026-07-14", "06:00", "09:00", "Sector Norte", "completado"),
        (3, "2026-07-15", "06:00", "08:00", "Sector Sur", "en_curso"),
        (4, "2026-07-16", "06:00", "10:00", "Sector Oriente", "programado"),
        (5, "2026-07-17", "06:30", "09:00", "Sector Norte", "programado"),
        (6, "2026-07-18", "06:00", "07:30", "Sector Sur", "cancelado"),
        (2, "2026-07-21", "06:00", "09:00", "Sector Norte", "programado"),
        (3, "2026-07-22", "06:00", "08:00", "Sector Sur", "programado"),
    ]
    for usuario_id, fecha, hi, hf, sector, estado in turnos:
        db.execute(
            "INSERT INTO turnos (usuario_id, fecha, hora_inicio, hora_fin, sector, estado) VALUES (?,?,?,?,?,?)",
            (usuario_id, fecha, hi, hf, sector, estado),
        )


def _seed_avisos(db):
    avisos_generales = [
        ("Mantenimiento de la tubería principal",
         "El viernes 18 de julio se realizará mantenimiento preventivo en la tubería principal. El suministro estará suspendido de 08:00 a 14:00 hrs. Se pide a los usuarios programar sus actividades con anticipación.",
         "mantenimiento", "2026-07-13", "Manuel Ramiro Soto", 1),
        ("Junta comunitaria — domingo 20 de julio",
         "Se convoca a todos los usuarios a la asamblea comunitaria del domingo 20 de julio a las 10:00 AM en el salón ejidal. Orden del día: asignación de turnos para agosto, informe de gastos y acuerdos generales.",
         "informativo", "2026-07-12", "Manuel Ramiro Soto", 1),
        ("Fuga reparada en el sector norte",
         "Se informa a la comunidad que la fuga menor detectada el 10 de julio en el sector norte fue atendida y reparada el mismo día. El suministro opera con normalidad.",
         "incidencia", "2026-07-11", "Manuel Ramiro Soto", 1),
        ("Alerta: uso fuera de horario asignado",
         "Se hace un llamado respetuoso a los usuarios a respetar los horarios asignados. El uso fuera de turno afecta a todos los beneficiarios. En caso de reincidencia se procederá conforme al reglamento comunitario.",
         "urgente", "2026-07-09", "Manuel Ramiro Soto", 1),
    ]
    for titulo, contenido, tipo, fecha, autor, activo in avisos_generales:
        db.execute(
            "INSERT INTO avisos (titulo, contenido, tipo, alcance, fecha, autor, activo) VALUES (?,?,?,'general',?,?,?)",
            (titulo, contenido, tipo, fecha, autor, activo),
        )

    # Un aviso personal de ejemplo, dirigido únicamente al usuario con id=2.
    cur = db.execute(
        "INSERT INTO avisos (titulo, contenido, tipo, alcance, fecha, autor, activo) VALUES (?,?,?,'personal',?,?,1)",
        ("Recordatorio de pago pendiente",
         "Tienes una multa pendiente por inasistencia a la faena comunitaria del 19 de julio. Favor de acudir con el comisariado para regularizar tu adeudo.",
         "incidencia", "2026-07-20", "Manuel Ramiro Soto"),
    )
    db.execute("INSERT INTO aviso_destinatarios (aviso_id, usuario_id) VALUES (?,2)", (cur.lastrowid,))


def _seed_actividades(db):
    actividades = [
        ("faena", "Limpieza del canal de riego",
         "Limpieza general del canal principal y sus ramificaciones. Se solicita la participación de un representante por familia. Quien no pueda asistir deberá enviar representante o cubrir la cuota correspondiente.",
         "2026-07-19", "07:00", "Canal principal — entrada norte", 150, [2, 3, 4]),
        ("junta", "Asamblea general — organización agosto",
         "Reunión para planificación de turnos del mes de agosto, revisión de incidencias del mes y asuntos generales.",
         "2026-07-20", "10:00", "Salón ejidal", None, [3, 5]),
        ("faena", "Reparación del pozo comunitario",
         "Trabajo comunitario para revisar y reparar el sistema de bombeo del pozo. Se necesitan al menos 8 personas con herramientas básicas.",
         "2026-07-26", "07:30", "Pozo comunitario — sector oriente", 200, []),
    ]
    for tipo, titulo, descripcion, fecha, hora, lugar, multa, participantes in actividades:
        cur = db.execute(
            "INSERT INTO actividades (tipo, titulo, descripcion, fecha, hora, lugar, multa) VALUES (?,?,?,?,?,?,?)",
            (tipo, titulo, descripcion, fecha, hora, lugar, multa),
        )
        actividad_id = cur.lastrowid
        for usuario_id in participantes:
            db.execute("INSERT INTO actividad_participantes (actividad_id, usuario_id) VALUES (?,?)",
                       (actividad_id, usuario_id))


def _seed_multas(db):
    # (usuario_id, concepto, descripcion, monto_total, fecha, actividad_id, pagos=[(monto,fecha), ...])
    multas = [
        (2, "Inasistencia a faena comunitaria",
         "No se presentó ni envió representante a la limpieza del canal de riego del 19 de julio.",
         150.0, "2026-07-19", 1, [(50.0, "2026-07-25")]),
        (5, "Uso de agua fuera de turno",
         "Uso del canal fuera del horario asignado en el Sector Norte.",
         100.0, "2026-07-17", None, []),
        (3, "Inasistencia a junta comunitaria",
         "No asistió a la asamblea general de organización de agosto.",
         80.0, "2026-07-20", 2, [(80.0, "2026-07-28")]),
    ]
    for usuario_id, concepto, descripcion, monto_total, fecha, actividad_id, pagos in multas:
        cur = db.execute(
            """INSERT INTO multas (usuario_id, concepto, descripcion, monto_total, monto_pagado, estado, fecha, actividad_id, creado_por)
               VALUES (?,?,?,?,0,'pendiente',?,?,?)""",
            (usuario_id, concepto, descripcion, monto_total, fecha, actividad_id, "Manuel Ramiro Soto"),
        )
        multa_id = cur.lastrowid
        pagado = 0.0
        for monto, fecha_pago in pagos:
            db.execute(
                "INSERT INTO multa_pagos (multa_id, monto, fecha, registrado_por) VALUES (?,?,?,?)",
                (multa_id, monto, fecha_pago, "Manuel Ramiro Soto"),
            )
            pagado += monto
        estado = "pagada" if pagado >= monto_total else ("parcial" if pagado > 0 else "pendiente")
        db.execute("UPDATE multas SET monto_pagado = ?, estado = ? WHERE id = ?", (pagado, estado, multa_id))


def _seed_cultivos(db):
    cultivos = [
        ("Maíz (Milpa)", "Mayo – Octubre", "Cada 7 días", "5–8 L/m²",
         "Cultivo principal de la comunidad. Requiere riego regular en germinación y floración. Reducir en periodo de lluvias.", "#CA8A04"),
        ("Frijol", "Junio – Noviembre", "Cada 5 días", "4–6 L/m²",
         "Se siembra intercalado con el maíz en la milpa. Sensible al exceso de humedad. Reducir riego en la etapa de llenado del grano.", "#EA580C"),
        ("Nopal", "Todo el año", "Cada 14 días", "2–3 L/m²",
         "Muy resistente a la sequía. Riego mínimo en temporada de lluvias. Ideal para sectores con escasa disponibilidad hídrica.", "#16A34A"),
        ("Chile Serrano", "Marzo – Agosto", "Cada 4 días", "5–7 L/m²",
         "Requiere riego frecuente y constante. Muy sensible al estrés hídrico en floración. Evitar encharcamiento.", "#DC2626"),
        ("Quelite / Verdolaga", "Junio – Septiembre", "Cada 6 días", "3–4 L/m²",
         "Planta comestible silvestre de alto valor nutritivo. Poco exigente en riego. Crece espontáneamente en las parcelas.", "#0D9488"),
        ("Calabaza", "Abril – Septiembre", "Cada 6 días", "5–7 L/m²",
         "Parte del sistema milpa junto al maíz y el frijol. Cubre el suelo reduciendo la evaporación. Riego moderado y constante.", "#D97706"),
    ]
    for nombre, temporada, freq, consumo, desc, accent in cultivos:
        db.execute(
            "INSERT INTO cultivos (nombre, temporada, frecuencia_riego, consumo_agua, descripcion, accent) VALUES (?,?,?,?,?,?)",
            (nombre, temporada, freq, consumo, desc, accent),
        )
