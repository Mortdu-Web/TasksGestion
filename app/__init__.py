from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from . import db
from .config import Config
from .routes import bp as tasks_bp


def create_app() -> Flask:
    # static_folder=None : les fichiers statiques sont servis par le blueprint « tasks »,
    # sous URL_PREFIX (ex. /tasks/static/...).
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)

    if Config.BEHIND_PROXY:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    app.register_blueprint(tasks_bp, url_prefix=Config.URL_PREFIX or None)
    return app
