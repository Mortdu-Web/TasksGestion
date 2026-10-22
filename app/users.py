"""Utilisateur courant et liste des utilisateurs partageables.

L'identité vient de Keycloak (via le service d'auth, g.user posé par require_auth) ; les tâches restent
rattachées aux `users.id` entiers de la base (voir db.py : link_or_create_user).
"""
import requests
from flask import current_app, g, request

from . import db
from .config import Config


def current_user_id() -> int:
    """users.id de l'utilisateur connecté (créé / rattaché à Keycloak à la première connexion)."""
    cached = g.get("_tasks_user_id")
    if cached:
        return cached

    if Config.AUTH_ENABLED:
        user = getattr(g, "user", None) or {}
        keycloak_id = user.get("sub")
        username = user.get("username") or user.get("preferred_username") or keycloak_id
    else:  # dev local : utilisateur simulé
        keycloak_id, username = f"dev:{Config.DEV_USERNAME}", Config.DEV_USERNAME

    if not keycloak_id:
        raise PermissionError("Utilisateur non authentifié.")

    uid = db.get_user_id_by_keycloak_id(keycloak_id) or db.link_or_create_user(keycloak_id, username)
    if uid is None:
        raise RuntimeError(f"Impossible de rattacher l'utilisateur {username!r} à la base.")
    db.ensure_personal_group(uid)
    g._tasks_user_id = uid
    return uid


def _fetch_keycloak_users() -> list[dict]:
    """Interroge GET <AUTH_INTERNAL_URL>/api/users en transmettant la session de l'utilisateur."""
    headers = {h: request.headers[h] for h in ("Cookie", "Authorization") if request.headers.get(h)}
    resp = requests.get(f"{Config.AUTH_INTERNAL_URL}/api/users", headers=headers, timeout=5)
    resp.raise_for_status()
    return resp.json()["users"]


def list_shareable_users() -> list[dict]:
    """[{id, username}] : utilisateurs avec qui partager un groupe (tous sauf soi-même).

    Avec auth : utilisateurs Keycloak (rattachés à la base au passage). Sans auth (dev local) ou si
    Keycloak est injoignable : utilisateurs déjà présents en base.
    """
    me = current_user_id()
    users: list[dict] | None = None

    if Config.AUTH_ENABLED:
        try:
            users = db.sync_keycloak_users(
                [{"keycloak_id": u.get("id"), "username": u.get("username")} for u in _fetch_keycloak_users()]
            )
        except (requests.RequestException, ValueError, KeyError):
            current_app.logger.exception("Liste Keycloak indisponible : repli sur les comptes connus en base")

    if users is None:
        users = db.list_users(keycloak_only=Config.AUTH_ENABLED)
    return [u for u in users if u["id"] != me]
