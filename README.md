# tasks — gestion de tâches par personne

Tâches regroupées en groupes (« Personnel » par défaut), partageables avec d'autres utilisateurs.
Extrait de l'ancien site : même structure que `game-hub` (Flask + gunicorn + docker-compose, auth via `auth_client`).

## Lancer en local (sans authentification)
```bash
pip install -r requirements.txt      # sans auth-client
cp .env.example .env                 # AUTH_ENABLED=false, URL_PREFIX= (vide), renseigner DB_*
flask --app wsgi run --debug --port 5000
```
Accueil : `http://localhost:5000/` (ou `http://localhost:5000<URL_PREFIX>/` si un préfixe est défini).
Sans auth, l'utilisateur est simulé (`DEV_USERNAME`, « dev » par défaut) ; la liste de partage propose les
autres utilisateurs de la table `users`.

## Production (avec authentification)
```bash
pip install -r requirements-auth.txt   # ajoute auth-client
# .env : AUTH_ENABLED=true + variables AUTH_* + URL_PREFIX=/tasks + PUBLIC_URL=https://mon-domaine.fr/tasks
```
`REQUIRED_ROLE` : rôle Keycloak exigé (remplace l'ancienne permission `tasks`). Vide = tout utilisateur connecté.

## Structure
```
wsgi.py                  point d'entrée (gunicorn / flask)
app/
  __init__.py            create_app : préfixe d'URL, proxy, base de données
  config.py              lecture du .env
  helpers.py             tasks_auth() : require_auth (auth_client si AUTH_ENABLED) + rôle optionnel
  db.py                  PostgreSQL : tâches, groupes, partages, lien Keycloak <-> users (seul fichier SQL)
  users.py               utilisateur courant + liste des utilisateurs partageables (Keycloak)
  routes.py              blueprint « tasks » : page + API
  templates/             base.html, tasks.html
  static/css/            site.css (variables, topbar), tasks.css, task.css, groupManager.css
  static/js/             Utils.js (apiUrl, injectCSS), tasks.js (page), task.js (<task-card>),
                         GroupManager.js (<group-manager>), taskGroup.js, taskUserManager.js, taskUser.js
migrations/              001_keycloak_id.sql
```
Les composants JS n'ont aucun chemin en dur : `base.html` expose la racine de l'app (`<meta name="app-base">`)
et `Utils.js` en déduit les URL de l'API, donc tout suit `URL_PREFIX`.

## Routes (toutes sous `<URL_PREFIX>`)
- `/` : page
- `GET /api/tasks` : `{tasks, groups}` · `POST /api/tasks` `{title, group_id?}`
- `POST /api/tasks/<id>/toggle` `{is_done}` · `POST /api/tasks/<id>/move` `{group_id}` · `DELETE /api/tasks/<id>`
- `GET /api/groups` · `POST /api/groups` `{name}` → `{group}` · `DELETE /api/groups/<id>`
- `POST /api/groups/<id>/share` `{user_id}` · `DELETE /api/groups/<id>/share/<user_id>` · `DELETE /api/groups/<id>/leave`
- `GET /api/users` : utilisateurs avec qui partager (tous sauf soi-même)

## Données
Base PostgreSQL **de l'ancien site** (hébergée sur une autre machine) : `users`, `tasks`, `tasks_groups`,
`shared_groups`. Les tâches et groupes existants sont conservés. Renseigner `DB_HOST`, `DB_PORT`, `DB_NAME`,
`DB_USER`, `DB_PASSWORD` dans le `.env` ; le serveur PostgreSQL doit accepter les connexions depuis la machine
qui héberge le conteneur (`listen_addresses`, `pg_hba.conf`, pare-feu).

**Migration (une fois)** : `migrations/001_keycloak_id.sql` ajoute `users.keycloak_id`.

### Lien Keycloak ↔ utilisateurs existants
Les tâches restent rattachées aux `users.id` entiers. À la première connexion, un compte Keycloak est rattaché à
l'utilisateur existant **de même nom d'utilisateur** (sans tenir compte de la casse) : il retrouve ses tâches et
ses groupes. Sans correspondance, un utilisateur est créé (avec son groupe « Personnel »).
Les comptes créés ainsi ont un mot de passe inutilisable : ils ne peuvent pas se connecter à l'ancien site.
Penser à vérifier que les noms d'utilisateur Keycloak correspondent à ceux de l'ancien site.

## Docker
```bash
cp .env.example .env                 # renseigner PORT, SECRET_KEY et DB_*
docker network create web            # une seule fois (réseau partagé avec le reverse proxy / l'auth)
docker compose up -d --build
```
En production (auth activée) : `WITH_AUTH=true docker compose up -d --build` avec `AUTH_ENABLED=true` dans le `.env`.

### Reverse proxy (nginx)
Le préfixe est géré par Flask : nginx transmet le chemin tel quel (pas de `/` final dans `proxy_pass`).
```nginx
location /tasks/ {
    proxy_pass http://192.168.1.207:PORT;          # PORT = celui du .env
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```
Avec `BEHIND_PROXY=true`, `SESSION_COOKIE_SECURE=true` en HTTPS.
