"""Stockage (PostgreSQL, sur une machine distante) des tâches, groupes et partages.

Connexion configurée via le .env : DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD.
Les routes n'appellent que les fonctions ci-dessous : c'est le seul fichier à adapter pour une autre base.

Schéma (identique à l'ancien site, voir migrations/) :
  users(id, username, password, keycloak_id)
  tasks(id, name, is_done, group_id)
  tasks_groups(id, name, owner_id)
  shared_groups(group_id, allowed_for, allowed_by)      -- unique (group_id, allowed_for)

Les identifiants utilisateur restent les `users.id` entiers de l'ancien site (les tâches et groupes
existants sont conservés). Un utilisateur Keycloak y est rattaché via `users.keycloak_id`.
"""
import psycopg
from flask import current_app, g
from psycopg.rows import dict_row

PERSONAL_GROUP = "Personnel"

# Mot de passe inutilisable pour les comptes créés depuis Keycloak (pas un hash bcrypt valide :
# ils ne peuvent pas se connecter à l'ancien site).
_NO_PASSWORD = "!keycloak"

SCHEMA = """
SELECT pg_advisory_xact_lock(727002);  -- evite les courses entre workers gunicorn au demarrage

CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(100) NOT NULL UNIQUE,
    password    TEXT NOT NULL DEFAULT '',
    keycloak_id TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS tasks_groups (
    id       SERIAL PRIMARY KEY,
    name     VARCHAR(100) NOT NULL,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS tasks (
    id       SERIAL PRIMARY KEY,
    name     TEXT NOT NULL,
    is_done  BOOLEAN NOT NULL DEFAULT FALSE,
    group_id INTEGER NOT NULL REFERENCES tasks_groups(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS shared_groups (
    group_id    INTEGER NOT NULL REFERENCES tasks_groups(id) ON DELETE CASCADE,
    allowed_for INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    allowed_by  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (group_id, allowed_for)
);
"""

# Condition « l'utilisateur :uid a accès au groupe tg » : propriétaire OU groupe partagé avec lui.
_ACCESSIBLE = """(
    tg.owner_id = %(uid)s
    OR EXISTS (
        SELECT 1 FROM shared_groups sg
        WHERE sg.group_id = tg.id AND sg.allowed_for = %(uid)s
    )
)"""


def _connect() -> psycopg.Connection:
    cfg = current_app.config
    return psycopg.connect(
        host=cfg["DB_HOST"],
        port=cfg["DB_PORT"],
        dbname=cfg["DB_NAME"],
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        row_factory=dict_row,
        connect_timeout=10,
        client_encoding="UTF8",
    )


def get_db() -> psycopg.Connection:
    if "db" not in g:
        g.db = _connect()
    return g.db


def _close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app) -> None:
    missing = [k for k in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD") if not app.config.get(k)]
    if missing:
        raise RuntimeError(f"Variables manquantes dans le .env : {', '.join(missing)}")

    app.teardown_appcontext(_close_db)

    # Les tables existent deja sur le serveur : on ne les cree que si DB_AUTO_CREATE=true
    # (base vide). Cette operation exige les droits CREATE sur le schema public.
    if app.config.get("DB_AUTO_CREATE"):
        with app.app_context():
            db = get_db()
            db.execute(SCHEMA)
            db.commit()


# ── Utilisateurs (rattachement Keycloak) ─────────────────────────────────────

def get_user_id_by_keycloak_id(keycloak_id: str) -> int | None:
    row = get_db().execute("SELECT id FROM users WHERE keycloak_id = %s", (keycloak_id,)).fetchone()
    return row["id"] if row else None


def link_or_create_user(keycloak_id: str, username: str) -> int | None:
    """Retourne users.id pour un compte Keycloak.

    Un compte Keycloak inconnu est rattaché à l'utilisateur existant de même nom (sans compte lié) :
    il retrouve ainsi ses tâches et ses groupes. Sinon, un utilisateur est créé.
    """
    db = get_db()
    try:
        row = db.execute(
            """UPDATE users SET keycloak_id = %s
               WHERE id = (SELECT id FROM users
                           WHERE keycloak_id IS NULL AND LOWER(username) = LOWER(%s)
                           ORDER BY id LIMIT 1)
               RETURNING id""",
            (keycloak_id, username),
        ).fetchone()
        if row is None:
            row = db.execute(
                """INSERT INTO users (username, password, keycloak_id) VALUES (%s, %s, %s)
                   ON CONFLICT DO NOTHING RETURNING id""",
                (username, _NO_PASSWORD, keycloak_id),
            ).fetchone()
        db.commit()
    except psycopg.Error:
        db.rollback()
        raise
    if row is not None:
        return row["id"]
    return get_user_id_by_keycloak_id(keycloak_id)  # course entre deux requêtes : déjà créé


def sync_keycloak_users(users: list[dict]) -> list[dict]:
    """users = [{"keycloak_id", "username"}] -> [{"id", "username"}] (id = users.id)."""
    result = []
    for u in users:
        if not u.get("keycloak_id") or not u.get("username"):
            continue
        uid = get_user_id_by_keycloak_id(u["keycloak_id"]) or link_or_create_user(u["keycloak_id"], u["username"])
        if uid is not None:
            result.append({"id": uid, "username": u["username"]})
    return sorted(result, key=lambda x: x["username"].lower())


def list_users(keycloak_only: bool = False) -> list[dict]:
    sql = "SELECT id, username FROM users"
    if keycloak_only:
        sql += " WHERE keycloak_id IS NOT NULL"
    return get_db().execute(sql + " ORDER BY username").fetchall()


def ensure_personal_group(user_id: int) -> None:
    """Crée le groupe « Personnel » s'il manque (avant : créé à l'inscription)."""
    db = get_db()
    db.execute(
        """INSERT INTO tasks_groups (name, owner_id)
           SELECT CAST(%(name)s AS VARCHAR), CAST(%(uid)s AS INTEGER)
           WHERE NOT EXISTS (
               SELECT 1 FROM tasks_groups WHERE owner_id = %(uid)s AND name = %(name)s
           )""",
        {"name": PERSONAL_GROUP, "uid": user_id},
    )
    db.commit()


# ── Tâches ───────────────────────────────────────────────────────────────────

def get_tasks_and_groups(user_id: int) -> dict:
    """Tâches des groupes propres + partagés, et liste de ces groupes (pour les <select>)."""
    db = get_db()
    tasks = db.execute(
        f"""SELECT t.id,
                   t.name                   AS title,
                   t.is_done,
                   (tg.owner_id != %(uid)s) AS is_shared,
                   tg.id                    AS group_id,
                   tg.name                  AS group_name
            FROM tasks t
            JOIN tasks_groups tg ON tg.id = t.group_id
            WHERE {_ACCESSIBLE}
            ORDER BY t.id DESC""",
        {"uid": user_id},
    ).fetchall()
    groups = db.execute(
        f"""SELECT tg.id, tg.name FROM tasks_groups tg
            WHERE {_ACCESSIBLE}
            ORDER BY tg.name""",
        {"uid": user_id},
    ).fetchall()
    for t in tasks:
        t["is_shared"] = bool(t["is_shared"])
    return {"tasks": tasks, "groups": groups}


def create_task(title: str, group_id: int, user_id: int) -> dict | None:
    """Crée une tâche dans `group_id` (propriétaire OU groupe partagé). None si accès refusé."""
    db = get_db()
    group = db.execute(
        f"""SELECT tg.id, tg.name, (tg.owner_id != %(uid)s) AS is_shared
            FROM tasks_groups tg
            WHERE tg.id = %(gid)s AND {_ACCESSIBLE}""",
        {"uid": user_id, "gid": group_id},
    ).fetchone()
    if group is None:
        return None
    row = db.execute(
        "INSERT INTO tasks (name, is_done, group_id) VALUES (%s, FALSE, %s) RETURNING id",
        (title, group["id"]),
    ).fetchone()
    db.commit()
    return {
        "id": row["id"],
        "title": title,
        "is_done": False,
        "is_shared": bool(group["is_shared"]),
        "group_id": group["id"],
        "group_name": group["name"],
    }


def toggle_task(task_id: int, is_done: bool, user_id: int) -> bool:
    db = get_db()
    cur = db.execute(
        f"""UPDATE tasks SET is_done = %(done)s
            WHERE id = %(tid)s
              AND group_id IN (SELECT tg.id FROM tasks_groups tg WHERE {_ACCESSIBLE})""",
        {"done": is_done, "tid": task_id, "uid": user_id},
    )
    db.commit()
    return cur.rowcount > 0


def delete_task(task_id: int, user_id: int) -> bool:
    """Suppression autorisée si l'utilisateur a accès au groupe (propriétaire OU partagé)."""
    db = get_db()
    cur = db.execute(
        f"""DELETE FROM tasks
            WHERE id = %(tid)s
              AND group_id IN (SELECT tg.id FROM tasks_groups tg WHERE {_ACCESSIBLE})""",
        {"tid": task_id, "uid": user_id},
    )
    db.commit()
    return cur.rowcount > 0


def move_task(task_id: int, new_group_id: int, user_id: int) -> bool:
    """Déplace une tâche d'un groupe accessible vers un autre groupe accessible."""
    db = get_db()
    dest = db.execute(
        f"SELECT tg.id FROM tasks_groups tg WHERE tg.id = %(gid)s AND {_ACCESSIBLE}",
        {"gid": new_group_id, "uid": user_id},
    ).fetchone()
    if dest is None:
        return False
    cur = db.execute(
        f"""UPDATE tasks SET group_id = %(gid)s
            WHERE id = %(tid)s
              AND group_id IN (SELECT tg.id FROM tasks_groups tg WHERE {_ACCESSIBLE})""",
        {"gid": new_group_id, "tid": task_id, "uid": user_id},
    )
    db.commit()
    return cur.rowcount > 0


# ── Groupes ──────────────────────────────────────────────────────────────────

def get_default_group(user_id: int) -> dict | None:
    """Premier groupe appartenant à l'utilisateur (« Personnel », créé à la volée si besoin)."""
    return get_db().execute(
        "SELECT id, name FROM tasks_groups WHERE owner_id = %s ORDER BY id ASC LIMIT 1", (user_id,)
    ).fetchone()


def create_group(name: str, owner_id: int) -> dict:
    db = get_db()
    row = db.execute(
        "INSERT INTO tasks_groups (name, owner_id) VALUES (%s, %s) RETURNING id", (name, owner_id)
    ).fetchone()
    db.commit()
    return {"id": row["id"], "name": name}


def get_all_accessible_groups(user_id: int) -> list[dict]:
    """Groupes propres (avec les utilisateurs de partage) + groupes reçus (is_received_share)."""
    rows = get_db().execute(
        """SELECT tg.id, tg.name, FALSE AS is_received_share,
                  u.id AS shared_user_id, u.username AS shared_username
           FROM tasks_groups tg
           LEFT JOIN shared_groups sg ON sg.group_id = tg.id
           LEFT JOIN users u          ON u.id = sg.allowed_for
           WHERE tg.owner_id = %(uid)s
           UNION
           SELECT tg.id, tg.name, TRUE AS is_received_share,
                  NULL AS shared_user_id, NULL AS shared_username
           FROM tasks_groups tg
           JOIN shared_groups sg ON sg.group_id = tg.id
           WHERE sg.allowed_for = %(uid)s
           ORDER BY name""",
        {"uid": user_id},
    ).fetchall()

    groups: dict[int, dict] = {}
    for r in rows:
        gid = r["id"]
        if gid not in groups:
            groups[gid] = {
                "id": gid,
                "name": r["name"],
                "is_received_share": bool(r["is_received_share"]),
                "shared_users": [],
            }
        if r["shared_user_id"]:
            groups[gid]["shared_users"].append({"id": r["shared_user_id"], "username": r["shared_username"]})
    return list(groups.values())


def _owned_group(group_id: int, owner_id: int) -> dict | None:
    return get_db().execute(
        "SELECT id, name FROM tasks_groups WHERE id = %s AND owner_id = %s", (group_id, owner_id)
    ).fetchone()


def share_group(group_id: int, target_user_id: int, owner_id: int) -> bool:
    """Partage un groupe avec un utilisateur. owner_id doit être le propriétaire ; « Personnel » n'est pas partageable."""
    group = _owned_group(group_id, owner_id)
    if group is None or group["name"] == PERSONAL_GROUP or target_user_id == owner_id:
        return False
    db = get_db()
    try:
        db.execute(
            """INSERT INTO shared_groups (group_id, allowed_for, allowed_by)
               VALUES (%s, %s, %s)
               ON CONFLICT (group_id, allowed_for) DO NOTHING""",
            (group_id, target_user_id, owner_id),
        )
        db.commit()
    except psycopg.errors.ForeignKeyViolation:  # utilisateur cible inexistant
        db.rollback()
        return False
    return True


def revoke_share(group_id: int, target_user_id: int, owner_id: int) -> bool:
    """Retire l'accès d'un utilisateur à un groupe dont owner_id est propriétaire."""
    if _owned_group(group_id, owner_id) is None:
        return False
    db = get_db()
    db.execute(
        "DELETE FROM shared_groups WHERE group_id = %s AND allowed_for = %s", (group_id, target_user_id)
    )
    db.commit()
    return True


def delete_group(group_id: int, owner_id: int) -> bool:
    """Supprime un groupe et ses tâches (« Personnel » n'est pas supprimable)."""
    group = _owned_group(group_id, owner_id)
    if group is None or group["name"] == PERSONAL_GROUP:
        return False
    db = get_db()
    db.execute("DELETE FROM shared_groups WHERE group_id = %s", (group_id,))
    db.execute("DELETE FROM tasks WHERE group_id = %s", (group_id,))
    db.execute("DELETE FROM tasks_groups WHERE id = %s AND owner_id = %s", (group_id, owner_id))
    db.commit()
    return True


def leave_shared_group(group_id: int, user_id: int) -> bool:
    """L'utilisateur quitte un groupe qui lui a été partagé."""
    db = get_db()
    cur = db.execute(
        "DELETE FROM shared_groups WHERE group_id = %s AND allowed_for = %s", (group_id, user_id)
    )
    db.commit()
    return cur.rowcount > 0
