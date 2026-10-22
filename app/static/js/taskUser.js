import { injectCSS } from './Utils.js';

// ─────────────────────────────────────────────
//  <task-user></task-user>
//
//  Attributs :
//      name      : str
//      is_shared : boolean  — utilisateur qui a déjà accès (section "Accès actif")
//
//  Événements émis (bubbles) :
//      task-user-share   — clic sur PARTAGER  { userId, username }
//      task-user-revoke  — clic sur RETIRER   { userId, username }
// ─────────────────────────────────────────────
class TaskUser extends HTMLElement {

  static get observedAttributes() {
    return ['name', 'is_shared'];
  }

  attributeChangedCallback() {
    if (this.isConnected) this._render();
  }

  connectedCallback() {
    injectCSS('task-user', 'groupManager.css', import.meta.url);
    this._render();
  }

  _render() {
    const userId   = this.getAttribute('data-id') || '';
    const name     = this.getAttribute('name')    || '';
    const isShared = this.hasAttribute('is_shared') && this.getAttribute('is_shared') !== 'false';
    const initials = String(name).slice(0, 2).toUpperCase();

    if (isShared) {
      // Utilisateur qui a déjà accès — section "Accès actif"
      this.innerHTML = `
        <div class="gm-user-row gm-user-row--shared">
          <span class="gm-user-avatar gm-user-avatar--shared">${this._esc(initials)}</span>
          <span class="gm-user-name">${this._esc(name)}</span>
          <button class="gm-revoke-btn" title="Retirer l'accès">
            <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
              <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
            </svg>
            Retirer
          </button>
        </div>
      `;
      this.querySelector('.gm-revoke-btn').addEventListener('click', (e) => {
        e.currentTarget.disabled = true;
        this._emit('task-user-revoke', { userId, username: name });
      });
    } else {
      // Utilisateur disponible — section "Ajouter"
      this.innerHTML = `
        <div class="gm-user-row">
          <span class="gm-user-avatar">${this._esc(initials)}</span>
          <span class="gm-user-name">${this._esc(name)}</span>
          <button class="gm-share-user-btn">PARTAGER</button>
        </div>
      `;
      this.querySelector('.gm-share-user-btn').addEventListener('click', (e) => {
        const btn = e.currentTarget;
        btn.disabled = true;
        btn.textContent = '…';
        this._emit('task-user-share', { userId, username: name });
      });
    }
  }

  /* Remet le bouton PARTAGER en état normal (appelé par le parent en cas d'erreur) */
  resetShareBtn() {
    const btn = this.querySelector('.gm-share-user-btn');
    if (btn) { btn.disabled = false; btn.textContent = 'PARTAGER'; }
  }

  _emit(type, detail) {
    this.dispatchEvent(new CustomEvent(type, { bubbles: true, composed: true, detail }));
  }

  _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
}

customElements.define('task-user', TaskUser);