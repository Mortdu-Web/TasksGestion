from .config import Config

# Remplace l'ancien `require_permission("tasks")` du site principal.
if Config.AUTH_ENABLED:
    from auth_client import require_auth
else:

    def require_auth(*roles: str, mode: str = "any"):
        """Auth desactivee (dev local) : ne controle rien."""

        def decorator(view):
            return view

        return decorator


def tasks_auth():
    """Décorateur commun à toutes les routes : connexion + rôle Keycloak optionnel (REQUIRED_ROLE).

    Usage : @tasks_auth()
    """
    return require_auth(Config.REQUIRED_ROLE) if Config.REQUIRED_ROLE else require_auth()
