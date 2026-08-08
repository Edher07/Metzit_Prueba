from functools import wraps
from flask import session, redirect, url_for, flash, g

from datos import usuario_por_id


def iniciar_sesion(usuario):
    session.clear()
    session["usuario_id"] = usuario.id
    session.permanent = True


def cerrar_sesion():
    session.clear()


def usuario_actual():
    if "usuario_id" not in session:
        return None
    if not hasattr(g, "_usuario_actual"):
        g._usuario_actual = usuario_por_id(session["usuario_id"])
    return g._usuario_actual


def login_required(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if usuario_actual() is None:
            flash("Inicia sesión para continuar.", "error")
            return redirect(url_for("auth.login"))
        return vista(*args, **kwargs)
    return envoltura


def admin_required(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        u = usuario_actual()
        if u is None:
            flash("Inicia sesión para continuar.", "error")
            return redirect(url_for("auth.login"))
        if u.rol != "comisariado":
            flash("No tienes permisos para acceder a esta sección.", "error")
            return redirect(url_for("dashboard.ver"))
        return vista(*args, **kwargs)
    return envoltura
