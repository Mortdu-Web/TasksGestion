import os

try:  # chargement optionnel du .env en local (en Docker, c'est compose qui injecte les variables)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")

    # Route racine derrière le reverse proxy (ex. /tasks). Vide = à la racine.
    URL_PREFIX = os.getenv("URL_PREFIX", "").rstrip("/")
    PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:5000").rstrip("/")
    BEHIND_PROXY = _bool("BEHIND_PROXY", False)

    # Base PostgreSQL hébergée sur une autre machine (voir .env). Même base que l'ancien site :
    # tables `users`, `tasks`, `tasks_groups`, `shared_groups`.
    DB_HOST = os.getenv("DB_HOST", "")
    DB_PORT = int(os.getenv("DB_PORT") or 5432)
    DB_NAME = os.getenv("DB_NAME", "")
    DB_USER = os.getenv("DB_USER", "")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    # true = cree les tables au demarrage (base vide ; exige le droit CREATE sur le schema public)
    DB_AUTO_CREATE = _bool("DB_AUTO_CREATE", False)

    # Authentification via le paquet auth_client (service d'auth séparé).
    # Désactivée par défaut pour pouvoir développer en local sans le service.
    AUTH_ENABLED = _bool("AUTH_ENABLED", False)
    AUTH_INTERNAL_URL = os.getenv("AUTH_INTERNAL_URL", "")
    AUTH_PUBLIC_URL = os.getenv("AUTH_PUBLIC_URL", "")
    # Rôle Keycloak exigé pour utiliser l'application (remplace l'ancienne permission "tasks").
    # Vide = tout utilisateur connecté.
    REQUIRED_ROLE = os.getenv("REQUIRED_ROLE", "").strip()
    # Utilisateur simulé quand AUTH_ENABLED=false (dev local)
    DEV_USERNAME = os.getenv("DEV_USERNAME", "dev").strip()

    SESSION_COOKIE_NAME = "site_session"
    SESSION_COOKIE_DOMAIN = os.getenv("SESSION_COOKIE_DOMAIN") or None
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = int(os.getenv("SESSION_LIFETIME_MINUTES", "480")) * 60
