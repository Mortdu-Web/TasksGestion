import { injectCSS } from './Utils.js';
import './taskUser.js';

// ─────────────────────────────────────────────
//  <task-user-manager></task-user-manager>
//
//  Attributs :
//      group-name  : str   — nom du groupe affiché dans le header
//
//  Propriété JS (setter) :
//      usersInfo   : Array<{ id, username, is_shared: boolean }>
//                    Setter à appeler pour peupler la liste.
//
//  Événements émis (bubbles) :
//      tum-back         — clic sur Retour          (pas de detail)
//      tum-close        — clic sur ✕ Fermer        (pas de detail)
//      tum-search       — frappe dans la recherche  { query: str }
//      task-user-share  — remonté depuis task-user  { userId, username }
//      task-user-revoke — remonté depuis task-user  { userId, username }
// ─────────────────────────────────────────────
class TaskUserManager extends HTMLElement {

  static get observedAttributes() {
    return ['group-name'];
  }

  attributeChangedCallback() {
    if (this.isConnected) this._renderHeader();
  }

  connectedCallback() {
    injectCSS('task-user-manager', 'groupManager.css', import.meta.url);
    this._usersInfo = [];
    this._render();
  }

  /* ── Setter public : reçoit la liste filtrée depuis GroupManager ── */
  set usersInfo(list) {
    this._usersInfo = list || [];
    if (this.isConnected) this._renderList();
  }

  /* ── Squelette complet ── */
  _render() {
    const groupName = this.getAttribute('group-name') || '';

    this.innerHTML = `
      <div class="gm-header">
        <div class="gm-header-text">
          <span class="gm-title">Partager le groupe</span>
          <span class="gm-subtitle">${this._esc(groupName)}</span>
        </div>
        <button class="tum-close-btn gm-close-btn" aria-label="Fermer">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
          </svg>
        </button>
      </div>

      <div class="gm-divider"></div>

      <div class="gm-share-search-wrap">
        <input class="tum-search gm-share-search" type="text" placeholder="Rechercher un utilisateur..." />
      </div>

      <div class="tum-list gm-share-list"></div>

      <div class="gm-divider"></div>

      <div class="gm-share-footer">
        <button class="tum-back-btn gm-back-btn">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M9 2L4 7l5 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          Retour
        </button>
      </div>
    `;

    this.querySelector('.tum-close-btn').addEventListener('click', () =>
      this._emit('tum-close')
    );
    this.querySelector('.tum-back-btn').addEventListener('click', () =>
      this._emit('tum-back')
    );
    this.querySelector('.tum-search').addEventListener('input', (e) => {
      this._emit('tum-search', { query: e.target.value });
    });

    this._renderList();
  }

  /* ── Met à jour uniquement la liste des utilisateurs ── */
  _renderList() {
    const list = this.querySelector('.tum-list');
    if (!list) return;
    const sharedUsers    = this._usersInfo.filter(u => u.is_shared);
    const availableUsers = this._usersInfo.filter(u => !u.is_shared);

    if (sharedUsers.length === 0 && availableUsers.length === 0) {
      list.innerHTML = `<p class="gm-empty">Aucun utilisateur disponible.</p>`;
      return;
    }

    list.innerHTML = '';

    if (sharedUsers.length > 0) {
      const label = document.createElement('div');
      label.className = 'gm-share-section-label';
      label.textContent = 'Accès actif';
      list.appendChild(label);

      sharedUsers.forEach(u => {
        const el = document.createElement('task-user');
        el.setAttribute('data-id', u.id);
        el.setAttribute('name', u.username);
        el.setAttribute('is_shared', 'true');
        list.appendChild(el);
      });

      const div = document.createElement('div');
      div.className = 'gm-divider';
      list.appendChild(div);
    }

    if (availableUsers.length > 0) {
      if (sharedUsers.length > 0) {
        const label = document.createElement('div');
        label.className = 'gm-share-section-label';
        label.textContent = 'Ajouter';
        list.appendChild(label);
      }

      availableUsers.forEach(u => {
        const el = document.createElement('task-user');
        el.setAttribute('data-id', u.id);
        el.setAttribute('name', u.username);
        list.appendChild(el);
      });
    }
  }

  /* ── Met à jour le header sans recréer tout le DOM ── */
  _renderHeader() {
    const subtitle = this.querySelector('.gm-subtitle');
    if (subtitle) subtitle.textContent = this.getAttribute('group-name') || '';
  }

  /* ── Focus automatique sur la recherche ── */
  focusSearch() {
    const input = this.querySelector('.tum-search');
    if (input) input.focus();
  }

  _emit(type, detail = {}) {
    this.dispatchEvent(new CustomEvent(type, { bubbles: true, composed: true, detail }));
  }

  _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
}

customElements.define('task-user-manager', TaskUserManager);