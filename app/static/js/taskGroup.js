import { injectCSS } from './Utils.js';

// ─────────────────────────────────────────────
//  <task-group></task-group>
//
//  Attributs :
//      name      : str
//      color     : str  (hex, défaut #b89a6a)
//      is_shared : boolean  — groupe reçu (badge PARTAGÉ + bouton Quitter)
//      has_share : boolean  — groupe owned déjà partagé (badge PARTAGÉ)
//
//  Événements émis (bubbles) :
//      task-group-share   — clic sur l'icône partager   { id, name }
//      task-group-delete  — clic sur supprimer           { id, name }
//      task-group-leave   — clic sur quitter             { id, name }
// ─────────────────────────────────────────────
class TaskGroup extends HTMLElement {

  /* Attributs observés pour re-render automatique */
  static get observedAttributes() {
    return ['name', 'color', 'is_shared', 'has_share'];
  }

  attributeChangedCallback() {
    if (this.isConnected) this._render();
  }

  connectedCallback() {
    injectCSS('task-group', 'groupManager.css', import.meta.url);
    this._render();
  }

  _render() {
    const id        = this.getAttribute('data-id') || '';
    const name      = this.getAttribute('name')      || '';
    const color     = this.getAttribute('color')     || '#b89a6a';
    const isShared  = this.hasAttribute('is_shared') && this.getAttribute('is_shared') !== 'false';
    const hasShare  = this.hasAttribute('has_share') && this.getAttribute('has_share') !== 'false';

    if (isShared) {
      // Groupe reçu d'un autre utilisateur
      this.innerHTML = `
        <div class="gm-group-row">
          <span class="gm-group-dot" style="background:${this._esc(color)}"></span>
          <span class="gm-group-name">${this._esc(name)}</span>
          <span class="gm-badge-shared">PARTAGÉ</span>
          <button class="gm-leave-btn" title="Quitter ce groupe partagé">
            <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
              <path d="M9 2L4 7l5 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M4 7h9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
            </svg>
            Quitter
          </button>
        </div>
      `;
      this.querySelector('.gm-leave-btn').addEventListener('click', () =>
        this._emit('task-group-leave', { id, name })
      );
    } else {
      // Groupe owned
      const isPersonnel = name.toLowerCase() === 'personnel';
      this.innerHTML = `
        <div class="gm-group-row">
          <span class="gm-group-dot" style="background:${this._esc(color)}"></span>
          <span class="gm-group-name">${this._esc(name)}</span>
          ${hasShare ? `<span class="gm-badge-shared">PARTAGÉ</span>` : ''}
          ${!isPersonnel ? `
            <button class="gm-share-icon-btn" title="Partager">
              <svg width="14" height="14" viewBox="0 0 13 13" fill="none">
                <circle cx="10.5" cy="2.5" r="1.5" stroke="currentColor" stroke-width="1.4"/>
                <circle cx="10.5" cy="10.5" r="1.5" stroke="currentColor" stroke-width="1.4"/>
                <circle cx="2.5" cy="6.5" r="1.5" stroke="currentColor" stroke-width="1.4"/>
                <path d="M4 6.5h4.5m-4-2.5 4-1.5M4 9l4.5 1.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
              </svg>
            </button>
            <button class="gm-remove-btn" title="Supprimer">
              <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
              </svg>
            </button>
          ` : ''}
        </div>
      `;
      if (!isPersonnel) {
        this.querySelector('.gm-share-icon-btn').addEventListener('click', () =>
          this._emit('task-group-share', { id, name })
        );
        this.querySelector('.gm-remove-btn').addEventListener('click', () =>
          this._emit('task-group-delete', { id, name })
        );
      }
    }
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

customElements.define('task-group', TaskGroup);