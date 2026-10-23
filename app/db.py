"""Stockage (PostgreSQL) des tâches, groupes et partages : schéma `tasks` + comptes `core.accounts`.

REMPLACANT DIRECT de l'ancien fichier : mêmes fonctions, mêmes paramètres, mêmes retours, même init_app(app).
Fichier autonome (aucune autre dépendance que psycopg, psycopg_pool et Flask).

Les identifiants « user_id » sont les anciens users.id : la migration les a conservés (core.accounts.id).

Nouveautés côté .env (toutes optionnelles) :
  DB_USER          : rôle PROPRE à ce service (svc_tasks, voir sql/003_login_roles.sql), plus le propriétaire des tables
  DB_SSLMODE       : « require » par défaut ; mettre « verify-full » + DB_SSLROOTCERT=/chemin/ca.pem en production
  DB_LINK_LEGACY   : « true » seulement pendant la bascule, pour rattacher un compte Keycloak à l'ancien
                     utilisateur de même nom ; à retirer ensuite (voir 002_migrate_legacy.sql)
Plus de DB_AUTO_CREATE : les tables sont créées par sql/001_schema.sql, avec le propriétaire.

Les droits d'accès (propriétaire / éditeur / lecteur) sont appliqués par la base elle-même (RLS) : une
ressource inaccessible est simplement invisible (None / False), même si une requête oubliait un WHERE.
"""
import atexit
from contextlib import contextmanager

import psycopg
from flask import current_app
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

PERSONAL_GROUP = "Personnel"

_EXT_KEY = "hub_db_pool"
_REQUIRED = ("tasks.groups", "tasks.group_members", "tasks.tasks", "core.accounts")
_BAD_INPUT = (psycopg.errors.UniqueViolation, psycopg.errors.InvalidTextRepresentation,
              psycopg.errors.InvalidParameterValue)


# ── Connexion / pool ─────────────────────────────────────────────────────────

def init_app(app) -> None:
    """Ouvre le pool et vérifie la base. Lève RuntimeError (message lisible) au moindre problème.

    Un pool par worker gunicorn, créé ici : ne pas lancer gunicorn avec --preload.
    """
    cfg = app.config
    missing = [k for k in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD") if not cfg.get(k)]
    if missing:
        raise RuntimeError(f"Variables manquantes dans le .env : {', '.join(missing)}")

    conninfo = make_conninfo(
        host=cfg["DB_HOST"],
        port=cfg.get("DB_PORT") or 5432,
        dbname=cfg["DB_NAME"],
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        connect_timeout=10,
        client_encoding="UTF8",
        sslmode=cfg.get("DB_SSLMODE") or "require",
        sslrootcert=cfg.get("DB_SSLROOTCERT") or None,
        options="-c statement_timeout=10000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=15000",
    )
    try:
        psycopg.connect(conninfo).close()  # le pool masque la vraie cause (mot de passe, hôte...) derrière un « timeout »
    except psycopg.Error as exc:
        raise RuntimeError(
            f"[DB] Connexion impossible à {cfg['DB_HOST']}:{cfg.get('DB_PORT') or 5432} "
            f"(base « {cfg['DB_NAME']} », utilisateur « {cfg['DB_USER']} ») : {exc}"
        ) from exc

    pool = ConnectionPool(
        conninfo,
        min_size=cfg.get("DB_POOL_MIN") or 1,
        max_size=cfg.get("DB_POOL_MAX") or 5,
        kwargs={"row_factory": dict_row},
        check=ConnectionPool.check_connection,
        timeout=10,
        name="hub-tasks",
        open=True,
    )
    try:
        problems = []
        with pool.connection() as conn:
            for t in _REQUIRED:
                row = conn.execute(
                    "SELECT to_regclass(%s) IS NOT NULL AS ok, "
                    "COALESCE(has_any_column_privilege(to_regclass(%s), 'SELECT'), false) AS can_read", (t, t)
                ).fetchone()
                if not row["ok"]:
                    problems.append(f"table {t} introuvable (sql/001_schema.sql appliqué ?)")
                elif not row["can_read"]:
                    problems.append(f"pas de droit SELECT sur {t} (DB_USER rattaché à app_tasks ?)")
        if problems:
            raise RuntimeError("[DB] Base non prête : " + " ; ".join(problems))
    except Exception:
        pool.close()
        raise
    app.extensions[_EXT_KEY] = pool
    atexit.register(pool.close)


@contextmanager
def _session(account_id: int | None = None, *, readonly: bool = False):
    """Curseur dans une transaction (commit / rollback / retour au pool automatiques).

    `account_id` est posé pour la durée de la transaction : c'est lui que la RLS utilise pour filtrer.
    """
    with current_app.extensions[_EXT_KEY].connection() as conn:
        with conn.cursor() as cur:
            if readonly:
                cur.execute("SET TRANSACTION READ ONLY")  # doit être la première instruction
            cur.execute("SELECT set_config('app.account_id', %s, true)",
                        ("" if account_id is None else str(int(account_id)),))
            yield cur


def _audit(cur, action: str, entity_id, details: dict | None = None) -> None:
    from psycopg.types.json import Jsonb
    cur.execute("INSERT INTO core.audit_log (service, action, entity, entity_id, details) "
                "VALUES ('tasks', %s, 'group', %s, %s)",
                (action, str(entity_id), Jsonb(details) if details else None))


# ── Utilisateurs (rattachement Keycloak) ─────────────────────────────────────

def get_user_id_by_keycloak_id(keycloak_id: str) -> int | None:
    try:
        with _session(readonly=True) as cur:
            cur.execute("SELECT core.account_id_by_sub(%s::uuid) AS id", (keycloak_id,))
            return cur.fetchone()["id"]
    except psycopg.errors.InvalidTextRepresentation:  # pas un UUID
        return None


def link_or_create_user(keycloak_id: str, username: str) -> int | None:
    """Retourne users.id pour un compte Keycloak (créé à la première connexion).

    Un compte désactivé, un `sub` invalide ou un nom déjà pris par un autre compte Keycloak donnent None.
    Le rattachement à un ancien utilisateur de même nom n'a lieu que si DB_LINK_LEGACY=true.
    """
    try:
        with _session() as cur:
            cur.execute("SELECT core.sync_account(%s::uuid, %s, NULL, NULL, %s) AS id",
                        (keycloak_id, username, bool(current_app.config.get("DB_LINK_LEGACY"))))
            return cur.fetchone()["id"]
    except _BAD_INPUT:
        return None


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
    sql = "SELECT id, username FROM core.accounts WHERE is_active AND kind = 'personal'"
    if keycloak_only:
        sql += " AND is_linked"
    with _session(readonly=True) as cur:
        cur.execute(sql + " ORDER BY lower(username), id")
        return cur.fetchall()


def ensure_personal_group(user_id: int) -> None:
    """Crée le groupe « Personnel » s'il manque (sans doublon, même en cas de concurrence)."""
    with _session(user_id) as cur:
        cur.execute("INSERT INTO tasks.groups (owner_id, name, is_personal) VALUES (%s, %s, true) "
                    "ON CONFLICT (owner_id) WHERE is_personal DO NOTHING", (user_id, PERSONAL_GROUP))


# ── Tâches ───────────────────────────────────────────────────────────────────

def get_tasks_and_groups(user_id: int) -> dict:
    """Tâches des groupes propres + partagés, et liste de ces groupes (pour les <select>).

    Chaque tâche porte en plus `can_edit` (False pour un groupe partagé en lecture seule).
    """
    with _session(user_id, readonly=True) as cur:
        cur.execute(
            """SELECT t.id, t.title, t.is_done,
                      (g.owner_id <> %(uid)s) AS is_shared,
                      (g.owner_id = %(uid)s OR m.role = 'editor') AS can_edit,
                      g.id AS group_id, g.name AS group_name
               FROM tasks.tasks t
               JOIN tasks.groups g ON g.id = t.group_id
               LEFT JOIN tasks.group_members m ON m.group_id = g.id AND m.account_id = %(uid)s
               ORDER BY t.id DESC""",
            {"uid": user_id},
        )
        tasks = cur.fetchall()
        cur.execute("SELECT id, name FROM tasks.groups ORDER BY name, id")
        groups = cur.fetchall()
    return {"tasks": tasks, "groups": groups}


def create_task(title: str, group_id: int, user_id: int) -> dict | None:
    """Crée une tâche dans `group_id` (propriétaire OU éditeur). None si accès refusé."""
    title = (title or "").strip()
    if not title or len(title) > 1000:
        raise ValueError("Titre de tâche invalide (1 à 1000 caractères).")
    try:
        with _session(user_id) as cur:
            cur.execute("SELECT id, name, (owner_id <> %s) AS is_shared FROM tasks.groups WHERE id = %s",
                        (user_id, group_id))
            group = cur.fetchone()
            if group is None:
                return None
            cur.execute("INSERT INTO tasks.tasks (group_id, title, created_by) VALUES (%s, %s, %s) RETURNING id",
                        (group["id"], title, user_id))
            task_id = cur.fetchone()["id"]
    except psycopg.errors.InsufficientPrivilege:  # groupe visible mais en lecture seule
        return None
    return {"id": task_id, "title": title, "is_done": False, "is_shared": bool(group["is_shared"]),
            "group_id": group["id"], "group_name": group["name"]}


def toggle_task(task_id: int, is_done: bool, user_id: int) -> bool:
    with _session(user_id) as cur:
        cur.execute("UPDATE tasks.tasks SET is_done = %s WHERE id = %s", (is_done, task_id))
        return cur.rowcount > 0


def delete_task(task_id: int, user_id: int) -> bool:
    """Suppression autorisée si l'utilisateur peut écrire dans le groupe (propriétaire OU éditeur)."""
    with _session(user_id) as cur:
        cur.execute("DELETE FROM tasks.tasks WHERE id = %s", (task_id,))
        return cur.rowcount > 0


def move_task(task_id: int, new_group_id: int, user_id: int) -> bool:
    """Déplace une tâche d'un groupe modifiable vers un autre groupe modifiable."""
    try:
        with _session(user_id) as cur:
            cur.execute("UPDATE tasks.tasks SET group_id = %s WHERE id = %s", (new_group_id, task_id))
            return cur.rowcount > 0
    except psycopg.errors.InsufficientPrivilege:  # groupe de destination interdit
        return False


# ── Groupes ──────────────────────────────────────────────────────────────────

def get_default_group(user_id: int) -> dict | None:
    """Premier groupe appartenant à l'utilisateur (« Personnel » en priorité)."""
    with _session(user_id, readonly=True) as cur:
        cur.execute("SELECT id, name FROM tasks.groups WHERE owner_id = %s ORDER BY is_personal DESC, id LIMIT 1",
                    (user_id,))
        return cur.fetchone()


def create_group(name: str, owner_id: int) -> dict:
    name = (name or "").strip()
    if not name or len(name) > 100:
        raise ValueError("Nom de groupe invalide (1 à 100 caractères).")
    with _session(owner_id) as cur:
        cur.execute("INSERT INTO tasks.groups (owner_id, name) VALUES (%s, %s) RETURNING id", (owner_id, name))
        return {"id": cur.fetchone()["id"], "name": name}


def get_all_accessible_groups(user_id: int) -> list[dict]:
    """Groupes propres (avec les utilisateurs de partage) + groupes reçus (is_received_share)."""
    with _session(user_id, readonly=True) as cur:
        cur.execute(
            """SELECT g.id, g.name, (g.owner_id <> %s) AS is_received_share,
                      a.id AS shared_user_id, a.username AS shared_username, m.role AS shared_role
               FROM tasks.groups g
               LEFT JOIN tasks.group_members m ON m.group_id = g.id
               LEFT JOIN core.accounts a ON a.id = m.account_id
               ORDER BY g.name, g.id, lower(a.username)""",
            (user_id,),
        )
        rows = cur.fetchall()
    groups: dict[int, dict] = {}
    for r in rows:
        grp = groups.setdefault(r["id"], {"id": r["id"], "name": r["name"],
                                          "is_received_share": bool(r["is_received_share"]), "shared_users": []})
        if r["shared_user_id"] and not r["is_received_share"]:  # un destinataire ne voit que sa propre ligne
            grp["shared_users"].append({"id": r["shared_user_id"], "username": r["shared_username"],
                                        "role": r["shared_role"]})
    return list(groups.values())


def share_group(group_id: int, target_user_id: int, owner_id: int, role: str = "editor") -> bool:
    """Partage un groupe. owner_id doit être le propriétaire ; « Personnel » n'est pas partageable.

    role = « editor » (comportement historique) ou « viewer » (lecture seule).
    """
    if role not in ("viewer", "editor"):
        raise ValueError("Rôle de partage invalide.")
    try:
        with _session(owner_id) as cur:
            cur.execute(
                """INSERT INTO tasks.group_members (group_id, account_id, role, added_by) VALUES (%s, %s, %s, %s)
                   ON CONFLICT (group_id, account_id) DO UPDATE SET role = EXCLUDED.role""",
                (group_id, target_user_id, role, owner_id),
            )
            _audit(cur, "share_group", group_id, {"with": target_user_id, "role": role})
    except (psycopg.errors.InsufficientPrivilege, psycopg.errors.IntegrityError):
        return False  # pas propriétaire / utilisateur inconnu / groupe personnel / partage avec soi-même
    return True


def revoke_share(group_id: int, target_user_id: int, owner_id: int) -> bool:
    """Retire l'accès d'un utilisateur à un groupe dont owner_id est propriétaire."""
    with _session(owner_id) as cur:
        cur.execute("SELECT 1 FROM tasks.groups WHERE id = %s AND owner_id = %s", (group_id, owner_id))
        if cur.fetchone() is None:
            return False
        cur.execute("DELETE FROM tasks.group_members WHERE group_id = %s AND account_id = %s",
                    (group_id, target_user_id))
        if cur.rowcount:
            _audit(cur, "revoke_share", group_id, {"account": target_user_id})
        return True


def delete_group(group_id: int, owner_id: int) -> bool:
    """Supprime un groupe, ses tâches et ses partages (« Personnel » n'est pas supprimable)."""
    with _session(owner_id) as cur:
        cur.execute("DELETE FROM tasks.groups WHERE id = %s AND owner_id = %s", (group_id, owner_id))
        if cur.rowcount:
            _audit(cur, "delete_group", group_id)
        return cur.rowcount > 0


def leave_shared_group(group_id: int, user_id: int) -> bool:
    """L'utilisateur quitte un groupe qui lui a été partagé."""
    with _session(user_id) as cur:
        cur.execute("DELETE FROM tasks.group_members WHERE group_id = %s AND account_id = %s", (group_id, user_id))
        return cur.rowcount > 0