// ── Utils.js ──
// Helpers partagés par les composants de la page.

// Racine de l'application, lue dans <meta name="app-base"> (URL_PREFIX côté serveur).
// Ex. "/tasks" derrière le reverse proxy, "" en local.
const base = (document.querySelector('meta[name="app-base"]')?.content || '').replace(/\/+$/, '');

/** URL d'une route d'API : apiUrl('/tasks') -> "/tasks/api/tasks". */
export function apiUrl(path) {
  return `${base}/api${path}`;
}

/**
 * Charge une feuille de style de static/css/ une seule fois, même si plusieurs composants
 * (ou plusieurs instances d'un composant) la demandent.
 *   injectCSS('task-card', 'task.css', import.meta.url)
 */
export function injectCSS(id, file, moduleUrl) {
  const href = new URL(`../css/${file}`, moduleUrl).href;
  if (document.head.querySelector(`link[rel="stylesheet"][href="${href}"]`)) return;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = href;
  link.dataset.component = id;
  document.head.appendChild(link);
}
