"""Blueprint « tasks » : page, API des tâches, des groupes et du partage.

Toutes les routes sont relatives à URL_PREFIX (ex. /tasks) ; le front calcule ses URL d'API à partir de
la page (voir static/js/Utils.js), il n'y a donc aucun chemin en dur côté navigateur.
"""
from flask import Blueprint, jsonify, render_template, request

from . import db, users
from .helpers import tasks_auth

bp = Blueprint("tasks", __name__, static_folder="static", static_url_path="/static")


@bp.route("/")
@tasks_auth()
def page():
    return render_template("tasks.html")


# ── Tâches ───────────────────────────────────────────────────────────────────

@bp.route("/api/tasks", methods=["GET"])
@tasks_auth()
def get_tasks():
    """{tasks: [{id, title, is_done, is_shared, group_id, group_name}], groups: [{id, name}]}"""
    return jsonify(db.get_tasks_and_groups(users.current_user_id())), 200


@bp.route("/api/tasks", methods=["POST"])
@tasks_auth()
def create_task():
    """Corps : {title, group_id?}. Sans group_id, la tâche va dans le premier groupe de l'utilisateur."""
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    group_id = body.get("group_id")
    user_id = users.current_user_id()

    if not title:
        return jsonify({"error": "Le titre est obligatoire."}), 400

    if not group_id:
        default = db.get_default_group(user_id)
        if default is None:
            return jsonify({"error": "Aucun groupe disponible."}), 400
        group_id = default["id"]

    try:
        group_id = int(group_id)
    except (TypeError, ValueError):
        return jsonify({"error": "group_id invalide."}), 400

    task = db.create_task(title=title, group_id=group_id, user_id=user_id)
    if task is None:
        return jsonify({"error": "Groupe invalide ou accès refusé."}), 403
    return jsonify(task), 201


@bp.route("/api/tasks/<int:task_id>/toggle", methods=["POST"])
@tasks_auth()
def toggle_task(task_id):
    """Corps : {is_done: bool}"""
    body = request.get_json(silent=True) or {}
    is_done = body.get("is_done")
    if not isinstance(is_done, bool):
        return jsonify({"error": "is_done (boolean) est obligatoire."}), 400

    if not db.toggle_task(task_id, is_done, users.current_user_id()):
        return jsonify({"error": "Tâche introuvable ou accès refusé."}), 403
    return jsonify({"success": True}), 200


@bp.route("/api/tasks/<int:task_id>", methods=["DELETE"])
@tasks_auth()
def delete_task(task_id):
    if not db.delete_task(task_id, users.current_user_id()):
        return jsonify({"error": "Tâche introuvable ou accès refusé."}), 403
    return jsonify({"success": True}), 200


@bp.route("/api/tasks/<int:task_id>/move", methods=["POST"])
@tasks_auth()
def move_task(task_id):
    """Corps : {group_id}"""
    body = request.get_json(silent=True) or {}
    try:
        new_group_id = int(body.get("group_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "group_id est obligatoire."}), 400

    if not db.move_task(task_id, new_group_id, users.current_user_id()):
        return jsonify({"error": "Tâche ou groupe invalide."}), 403
    return jsonify({"success": True}), 200


# ── Groupes ──────────────────────────────────────────────────────────────────

@bp.route("/api/groups", methods=["GET"])
@tasks_auth()
def get_groups():
    """{groups: [{id, name, is_received_share, shared_users: [{id, username}]}]}"""
    return jsonify({"groups": db.get_all_accessible_groups(users.current_user_id())}), 200


@bp.route("/api/groups", methods=["POST"])
@tasks_auth()
def create_group():
    """Corps : {name, color?}. Réponse : {group: {...}} (même forme que GET /api/groups)."""
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Le nom est obligatoire."}), 400

    group = db.create_group(name=name, owner_id=users.current_user_id())
    group.update({"is_received_share": False, "shared_users": []})
    return jsonify({"group": group}), 201


@bp.route("/api/groups/<int:group_id>", methods=["DELETE"])
@tasks_auth()
def delete_group(group_id):
    if not db.delete_group(group_id, users.current_user_id()):
        return jsonify({"error": "Groupe introuvable ou accès refusé."}), 403
    return jsonify({"success": True}), 200


@bp.route("/api/groups/<int:group_id>/share", methods=["POST"])
@tasks_auth()
def share_group(group_id):
    """Corps : {user_id}"""
    body = request.get_json(silent=True) or {}
    try:
        target = int(body.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "user_id est obligatoire."}), 400

    if not db.share_group(group_id, target, users.current_user_id()):
        return jsonify({"error": "Groupe invalide ou accès refusé."}), 403
    return jsonify({"success": True}), 201


@bp.route("/api/groups/<int:group_id>/share/<int:user_id>", methods=["DELETE"])
@tasks_auth()
def revoke_share(group_id, user_id):
    if not db.revoke_share(group_id, user_id, users.current_user_id()):
        return jsonify({"error": "Accès refusé."}), 403
    return jsonify({"success": True}), 200


@bp.route("/api/groups/<int:group_id>/leave", methods=["DELETE"])
@tasks_auth()
def leave_shared_group(group_id):
    if not db.leave_shared_group(group_id, users.current_user_id()):
        return jsonify({"error": "Partage introuvable."}), 404
    return jsonify({"success": True}), 200


# ── Utilisateurs ─────────────────────────────────────────────────────────────

@bp.route("/api/users", methods=["GET"])
@tasks_auth()
def get_users():
    """{users: [{id, username}]} : utilisateurs avec qui partager un groupe."""
    return jsonify({"users": users.list_shareable_users()}), 200
