import { injectCSS, apiUrl } from './Utils.js';

class Task extends HTMLElement {
  connectedCallback() {
    injectCSS('task-card', 'task.css', import.meta.url);

    const taskId    = this.getAttribute('task-id')    || null;
    const name      = this.getAttribute('name')       || '—';
    const isDone    = this.getAttribute('is_done')    === 'true';
    const isShared  = this.getAttribute('is_shared')  === 'true';
    const groupName = this.getAttribute('group_name') || null;

    this.innerHTML = `
      <div class="task-card ${isDone ? 'is-done' : ''}">
        <input
          type="checkbox"
          class="task-checkbox"
          ${isDone ? 'checked' : ''}
          title="Marquer comme ${isDone ? 'à faire' : 'terminée'}"
        >
        <span class="task-name">${this._escape(name)}</span>
        ${groupName ? `<span class="task-group-badge">${this._escape(groupName)}</span>` : ''}
        ${isShared  ? `<span class="task-shared-badge">partagée</span>` : ''}

        <div class="task-move" style="display:none;">
          <select class="task-move-select"></select>
          <button class="task-move-confirm" title="Confirmer">✓</button>
          <button class="task-move-cancel"  title="Annuler">✕</button>
        </div>

        ${isShared ? `` : `
        <button class="task-move-btn" title="Changer de groupe">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M1 7h12M8 3l4 4-4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>`}
        
        <button class="task-delete" title="Supprimer" aria-label="Supprimer la tâche">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M2 2l10 10M12 2L2 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
          </svg>
        </button>
      </div>
    `;

    const checkbox  = this.querySelector('.task-checkbox');
    const card      = this.querySelector('.task-card');
    const moveBtn   = this.querySelector('.task-move-btn');
    const movePanel = this.querySelector('.task-move');
    const moveSelect  = this.querySelector('.task-move-select');
    const moveConfirm = this.querySelector('.task-move-confirm');
    const moveCancel  = this.querySelector('.task-move-cancel');
    const groupBadge  = this.querySelector('.task-group-badge');

    // ── Checkbox : toggle done ──
    checkbox.addEventListener('change', async () => {
      const done = checkbox.checked;
      try {
        const res = await fetch(apiUrl(`/tasks/${taskId}/toggle`), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ is_done: done }),
        });
        if (!res.ok) throw new Error();
        card.classList.toggle('is-done', done);
        this.setAttribute('is_done', String(done));
        this.dispatchEvent(new CustomEvent('task-toggled', { bubbles: true, detail: { taskId, done } }));
      } catch {
        checkbox.checked = !done;
      }
    });

    // ── Bouton changer de groupe ──
    if (!isShared) {

      moveBtn.addEventListener('click', () => {
        // Demande les groupes disponibles à la page parente via un event
        const ev = new CustomEvent('task-request-groups', {
          bubbles: true,
          detail: { callback: (groups) => {
            moveSelect.innerHTML = groups
              .map(g => `<option value="${g.id}">${this._escape(g.name)}</option>`)
              .join('');
            movePanel.style.display = 'flex';
            moveBtn.style.display   = 'none';
          }}
        });
        this.dispatchEvent(ev);
      });

      moveCancel.addEventListener('click', () => {
        movePanel.style.display = 'none';
        moveBtn.style.display   = '';
      });

      moveConfirm.addEventListener('click', async () => {
        const newGroupId   = moveSelect.value;
        const newGroupName = moveSelect.options[moveSelect.selectedIndex].text;
        try {
          const res = await fetch(apiUrl(`/tasks/${taskId}/move`), {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ group_id: parseInt(newGroupId) }),
          });
          if (!res.ok) throw new Error();

          // Met à jour le badge groupe
          if (groupBadge) groupBadge.textContent = newGroupName;
          this.setAttribute('group_name', newGroupName);

          movePanel.style.display = 'none';
          moveBtn.style.display   = '';

          this.dispatchEvent(new CustomEvent('task-moved', {
            bubbles: true,
            detail: { taskId, newGroupId, newGroupName }
          }));
        } catch {
          alert('Erreur lors du déplacement.');
        }
      });
    }

    // ── Bouton supprimer ──
    const deleteBtn = this.querySelector('.task-delete');
    deleteBtn.addEventListener('click', async () => {
      if (!confirm(`Supprimer « ${name} » ?`)) return;
      try {
        const res = await fetch(apiUrl(`/tasks/${taskId}`), { method: 'DELETE' });
        if (!res.ok) throw new Error();
        this.dispatchEvent(new CustomEvent('task-deleted', { bubbles: true, detail: { taskId } }));
        card.style.transition = 'opacity 0.2s, transform 0.2s';
        card.style.opacity    = '0';
        card.style.transform  = 'translateX(16px)';
        setTimeout(() => this.remove(), 220);
      } catch {
        alert('Erreur lors de la suppression.');
      }
    });
  }

  _escape(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
}

customElements.define('task-card', Task);