import { injectCSS, apiUrl } from './Utils.js';
import './taskGroup.js';
import './taskUserManager.js';

// ─────────────────────────────────────────────
//  <group-manager></group-manager>
//
//  Orchestre :
//    • <task-group>        — une ligne de groupe
//    • <task-user-manager> — la vue de partage
//
//  API publique :
//    • setGroups(groups)   — injecte la liste depuis l'extérieur
// ─────────────────────────────────────────────
class GroupManager extends HTMLElement {
  connectedCallback() {
    injectCSS('group-manager', 'groupManager.css', import.meta.url);
    this._groups      = [];
    this._users       = [];
    this._view        = 'list';   // 'list' | 'share'
    this._shareTarget = null;     // { id, name }
    this._searchQuery = '';
    this._render();
    this._load();
  }

  /* ── Chargement initial ── */
  async _load() {
    try {
      const [rGroups, rUsers] = await Promise.all([
        fetch(apiUrl('/groups')),
        fetch(apiUrl('/users')),
      ]);
      this._groups = (await rGroups.json()).groups || [];
      this._users  = (await rUsers.json()).users   || [];
      this._renderContent();
      
    } catch (err) {
      console.error('GroupManager load error', err);
    }
  }

  /* ── Squelette HTML (bouton + overlay) ── */
  _render() {
    this.innerHTML = `
      <button class="gm-open-btn" aria-label="Gérer les groupes">
        <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
          <path d="M1 3.5A1.5 1.5 0 0 1 2.5 2h10A1.5 1.5 0 0 1 14 3.5v1A1.5 1.5 0 0 1 12.5 6h-10A1.5 1.5 0 0 1 1 4.5v-1ZM1 9.5A1.5 1.5 0 0 1 2.5 8h6A1.5 1.5 0 0 1 10 9.5v1A1.5 1.5 0 0 1 8.5 12h-6A1.5 1.5 0 0 1 1 10.5v-1Z"
            stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        Groupes
      </button>

      <div class="gm-overlay" aria-hidden="true">
        <div class="gm-modal" role="dialog" aria-modal="true">
          <div class="gm-modal-inner"></div>
        </div>
      </div>
    `;

    this.querySelector('.gm-open-btn').addEventListener('click', () => this._open());
    this.querySelector('.gm-overlay').addEventListener('click', (e) => {
      if (e.target === e.currentTarget) this._close();
    });
  }

  /* ── Dispatch vers la bonne vue ── */
  _renderContent() {
    // Détache tous les listeners de la vue précédente avant d'en monter une nouvelle
    if (this._viewAbort) this._viewAbort.abort();
    this._viewAbort = new AbortController();
    if (this._view === 'list')  this._renderListView();
    else                        this._renderShareView();
  }

  /* ── Vue liste ── */
  _renderListView() {
    const inner = this.querySelector('.gm-modal-inner');
    if (!inner) return;

    inner.innerHTML = `
      <div class="gm-header">
        <div class="gm-header-text">
          <span class="gm-title">Mes groupes</span>
          <span class="gm-subtitle">Créez et organisez vos groupes de tâches</span>
        </div>
        <button class="gm-close-btn" aria-label="Fermer">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
          </svg>
        </button>
      </div>

      <div class="gm-divider"></div>

      <div class="gm-list">
        ${this._groups.length === 0
          ? `<p class="gm-empty">Aucun groupe.</p>`
          : this._groups.map(g => `
              <task-group
                data-id="${g.id}"
                name="${this._esc(g.name)}"
                color="${this._esc(g.color || '#b89a6a')}"
                ${g.is_received_share ? 'is_shared' : ''}
                ${!g.is_received_share && g.shared_users?.length > 0 ? 'has_share' : ''}
              ></task-group>
            `).join('')
        }
      </div>

      <div class="gm-divider"></div>

      <div class="gm-footer">
        <input class="gm-new-input" type="text" placeholder="Nouveau groupe..." maxlength="60" />
        <input class="gm-color-picker" type="color" value="#b89a6a" title="Couleur du groupe" />
        <button class="gm-create-btn">CRÉER</button>
      </div>
    `;

    const sig = this._viewAbort.signal;

    /* Événements header / footer */
    inner.querySelector('.gm-close-btn').addEventListener('click', () => this._close(), { signal: sig });

    const newInput  = inner.querySelector('.gm-new-input');
    const createBtn = inner.querySelector('.gm-create-btn');
    createBtn.addEventListener('click', () =>
      this._doCreate(newInput, inner.querySelector('.gm-color-picker')), { signal: sig }
    );
    newInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this._doCreate(newInput, inner.querySelector('.gm-color-picker'));
    }, { signal: sig });

    /* Événements remontés depuis <task-group> */
    inner.addEventListener('task-group-share', (e) => {
      this._shareTarget = { id: e.detail.id, name: e.detail.name };
      this._view = 'share';
      this._searchQuery = '';
      this._renderContent();
    }, { signal: sig });

    inner.addEventListener('task-group-delete', (e) =>
      this._doDelete(e.detail.id, e.detail.name), { signal: sig }
    );

    inner.addEventListener('task-group-leave', (e) =>
      this._doLeave(e.detail.id, e.detail.name), { signal: sig }
    );
  }

  /* ── Vue partage ── */
  _renderShareView() {
    const inner = this.querySelector('.gm-modal-inner');
    if (!inner) return;

    // Crée (ou réutilise) le composant <task-user-manager>
    inner.innerHTML = `<task-user-manager group-name="${this._esc(this._shareTarget.name)}"></task-user-manager>`;
    const tum = inner.querySelector('task-user-manager');

    // Injecte la liste filtrée initiale
    tum.usersInfo = this._filteredUsers();
    tum.focusSearch();

    /* Événements remontés depuis <task-user-manager> */
    inner.addEventListener('tum-close',  () => this._close());
    inner.addEventListener('tum-back',   () => {
      this._view = 'list';
      this._shareTarget = null;

      this._renderContent();
    });
    inner.addEventListener('tum-search', (e) => {
      this._searchQuery = e.detail.query;
      tum.usersInfo = this._filteredUsers();
    });

    /* Événements remontés depuis <task-user> (via <task-user-manager>) */
    inner.addEventListener('task-user-share',  (e) =>
      this._doShare(this._shareTarget.id, e.detail.userId, e.detail.username,
        e.target  /* l'élément <task-user> lui-même */)
    );
    inner.addEventListener('task-user-revoke', (e) =>
      this._doRevoke(this._shareTarget.id, e.detail.userId, e.detail.username,
        e.target)
    );
  }

  /* ── Calcule la liste d'utilisateurs filtrée pour la vue partage ── */
  _filteredUsers() {
    const group     = this._groups.find(g => String(g.id) === String(this._shareTarget.id));
    const sharedIds = new Set((group?.shared_users || []).map(u => String(u.id)));
    const query     = this._searchQuery.toLowerCase();

    return this._users
      .filter(u => u.username.toLowerCase().includes(query))
      .map(u => ({ ...u, is_shared: sharedIds.has(String(u.id)) }));
  }

  /* ── Actions API ── */
  async _doCreate(input, colorPicker) {
    const name  = input.value.trim();
    const color = colorPicker?.value || '#b89a6a';
    if (!name) { input.focus(); return; }

    try {
      const res  = await fetch(apiUrl('/groups'), {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ name, color }),
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      this._groups.push(data.group);
      input.value = '';

      this._renderContent();
      this.dispatchEvent(new CustomEvent('group-created', { bubbles: true, detail: { name, color } }));
    } catch {
      alert('Erreur lors de la création du groupe.');
    }
  }

  async _doShare(groupId, userId, username, taskUserEl) {
    try {
      const res = await fetch(apiUrl(`/groups/${groupId}/share`), {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ user_id: parseInt(userId) }),
      });
      if (!res.ok) throw new Error();

      const g = this._groups.find(g => String(g.id) === String(groupId));
      if (g) {
        if (!g.shared_users) g.shared_users = [];
        if (!g.shared_users.find(u => String(u.id) === String(userId))) {
          g.shared_users.push({ id: userId, username });
        }
      }
      // Mise à jour douce : on repousse la liste sans recréer tout le DOM
      const tum = this.querySelector('task-user-manager');
      if (tum) tum.usersInfo = this._filteredUsers();

      this.dispatchEvent(new CustomEvent('group-shared', { bubbles: true, detail: { groupId, userId } }));
    } catch {
      if (taskUserEl?.resetShareBtn) taskUserEl.resetShareBtn();
      alert('Erreur lors du partage.');
    }
  }

  async _doDelete(groupId, groupName) {
    if (!confirm(`Supprimer le groupe « ${groupName} » et toutes ses tâches ?`)) return;
    try {
      const res = await fetch(apiUrl(`/groups/${groupId}`), { method: 'DELETE' });
      if (!res.ok) throw new Error();
      this._groups = this._groups.filter(g => String(g.id) !== String(groupId));

      this._renderContent();
      this.dispatchEvent(new CustomEvent('group-deleted', { bubbles: true, detail: { groupId } }));
    } catch {
      alert('Erreur lors de la suppression du groupe.');
    }
  }

  async _doLeave(groupId, groupName) {
    if (!confirm(`Quitter le groupe partagé « ${groupName} » ?`)) return;
    try {
      const res = await fetch(apiUrl(`/groups/${groupId}/leave`), { method: 'DELETE' });
      if (!res.ok) throw new Error();
      this._groups = this._groups.filter(g => String(g.id) !== String(groupId));

      this._renderContent();
      this.dispatchEvent(new CustomEvent('group-left', { bubbles: true, detail: { groupId } }));
    } catch {
      alert('Erreur lors de la sortie du groupe.');
    }
  }

  async _doRevoke(groupId, userId, username, taskUserEl) {
    try {
      const res = await fetch(apiUrl(`/groups/${groupId}/share/${userId}`), { method: 'DELETE' });
      if (!res.ok) throw new Error();

      const g = this._groups.find(g => String(g.id) === String(groupId));
      if (g) g.shared_users = g.shared_users.filter(u => String(u.id) !== String(userId));

      const tum = this.querySelector('task-user-manager');
      if (tum) tum.usersInfo = this._filteredUsers();

      this.dispatchEvent(new CustomEvent('group-unshared', { bubbles: true, detail: { groupId, userId } }));
    } catch {
      if (taskUserEl) {
        const btn = taskUserEl.querySelector('.gm-revoke-btn');
        if (btn) btn.disabled = false;
      }
      alert('Erreur lors de la révocation du partage.');
    }
  }

  /* ── Ouverture / fermeture ── */
  _open() {
    this._view = 'list';
    this._shareTarget = null;

    this._renderContent();
    const overlay = this.querySelector('.gm-overlay');
    overlay.removeAttribute('aria-hidden');
    overlay.classList.add('gm-overlay--visible');
    document.body.style.overflow = 'hidden';
  }

  _close() {
    const overlay = this.querySelector('.gm-overlay');
    overlay.setAttribute('aria-hidden', 'true');
    overlay.classList.remove('gm-overlay--visible');
    document.body.style.overflow = '';
  }

  /* ── API publique ── */
  setGroups(groups) {
    this._groups = groups.map(g => ({
      ...g,
      shared_users: g.shared_users ?? [],
    }));

    this._renderContent();
  }

  /* ── Helpers ── */
  _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
}

customElements.define('group-manager', GroupManager);