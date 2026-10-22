import { apiUrl } from './Utils.js';

// ── tasks.js ──
// Gestion de la page de tâches.
// Chargement, filtrage, ajout via fetch + <task-card>.

(async () => {
  /* ── Références DOM ── */
  const taskList       = document.getElementById('task-list');
  const taskCount      = document.getElementById('task-count');
  const filterBtns     = document.querySelectorAll('.filter-btn');
  const filterGroup    = document.getElementById('filter-group');
  const addForm        = document.getElementById('add-task-form');
  const titleInput     = document.getElementById('task-title-input');
  const groupSelect    = document.getElementById('task-group-select');
  const groupManager   = document.getElementById('group-manager');

  /* ── État local ── */
  let allTasks    = [];   // cache brut des tâches retournées par /api/tasks
  let allGroups   = [];   // cache des groupes (propres + partagés)
  let filter      = 'all';  // 'all' | 'todo' | 'done'
  let filterGrp   = '';     // '' = tous les groupes

  /* ────────────────────────────────
     1. Chargement initial
  ──────────────────────────────── */
  async function loadTasks() {
    try {
      const res = await fetch(apiUrl('/tasks'));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      allTasks  = data.tasks  || [];
      allGroups = data.groups || [];
      populateGroupSelects(allGroups);
      renderTasks();
    } catch (err) {
      taskList.innerHTML = `<p class="task-list-empty">Impossible de charger les tâches.</p>`;
      console.error(err);
    }
  }

  /* ────────────────────────────────
     2. Remplir les <select> de groupes
     – Le select d'ajout n'a PAS d'option vide.
     – Il est présélectionné sur le groupe "Personnel"
       (premier de la liste = celui créé à l'inscription).
  ──────────────────────────────── */
  function populateGroupSelects(groups) {
    // ── Select du formulaire d'ajout ──
    groupSelect.innerHTML = '';
    groups.forEach(g => {
      const opt = document.createElement('option');
      opt.value       = g.id;
      opt.textContent = g.name;
      groupSelect.appendChild(opt);
    });

    // Présélectionne "Personnel" si présent, sinon le premier groupe
    const perso = groups.find(g => g.name.toLowerCase() === 'personnel');
    groupSelect.value = perso ? perso.id : (groups[0]?.id ?? '');

    // ── Select du filtre ──
    filterGroup.innerHTML = `<option value="">Tous les groupes</option>`;
    groups.forEach(g => {
      filterGroup.innerHTML += `<option value="${g.id}">${g.name}</option>`;
    });
  }

  /* ────────────────────────────────
     3. Rendu de la liste
  ──────────────────────────────── */
  function renderTasks() {
    let tasks = allTasks;

    if (filter === 'todo') tasks = tasks.filter(t => !t.is_done);
    if (filter === 'done') tasks = tasks.filter(t =>  t.is_done);
    if (filterGrp) tasks = tasks.filter(t => String(t.group_id) === filterGrp);

    updateCount(tasks.length);

    if (tasks.length === 0) {
      taskList.innerHTML = `<p class="task-list-empty">Aucune tâche à afficher.</p>`;
      return;
    }

    taskList.innerHTML = '';
    tasks.forEach(t => {
      const el = document.createElement('task-card');
      el.setAttribute('task-id',    t.id);
      el.setAttribute('name',       t.title);
      el.setAttribute('is_done',    String(t.is_done));
      el.setAttribute('is_shared',  String(t.is_shared  ?? false));
      el.setAttribute('group_name', t.group_name ?? '');
      taskList.appendChild(el);
    });
  }

  function updateCount(n) {
    if (taskCount) taskCount.textContent = `${n} tâche${n !== 1 ? 's' : ''}`;
  }

  /* ────────────────────────────────
     4. Filtres
  ──────────────────────────────── */
  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      filterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      filter = btn.dataset.filter;
      renderTasks();
    });
  });

  filterGroup.addEventListener('change', () => {
    filterGrp = filterGroup.value;
    renderTasks();
  });

  /* ────────────────────────────────
     5. Ajout d'une tâche
     – group_id est toujours défini grâce au select sans option vide.
  ──────────────────────────────── */
  addForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const title   = titleInput.value.trim();
    const groupId = groupSelect.value;   // toujours une valeur
    if (!title) return;

    try {
      const res  = await fetch(apiUrl('/tasks'), {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ title, group_id: groupId }),
      });
      if (!res.ok) throw new Error();
      const newTask = await res.json();

      allTasks.unshift(newTask);
      titleInput.value = '';
      // On ne remet PAS groupSelect.value = '' : on garde la sélection courante
      renderTasks();
    } catch {
      alert('Erreur lors de l\'ajout de la tâche.');
    }
  });

  /* ────────────────────────────────
     6. Écoute des events des <task-card>
  ──────────────────────────────── */
  taskList.addEventListener('task-toggled', (e) => {
    const { taskId, done } = e.detail;
    const task = allTasks.find(t => String(t.id) === String(taskId));
    if (task) task.is_done = done;
    updateCount(taskList.querySelectorAll('task-card').length);
  });

  taskList.addEventListener('task-deleted', (e) => {
    const { taskId } = e.detail;
    allTasks = allTasks.filter(t => String(t.id) !== String(taskId));
    updateCount(taskList.querySelectorAll('task-card').length);
  });

  taskList.addEventListener('task-request-groups', (e) => {
    const groups = [...groupSelect.options].map(o => ({ id: o.value, name: o.text }));
    e.detail.callback(groups);
  });

  /* ────────────────────────────────
     8. Événements du group-manager
  ──────────────────────────────── */
  groupManager.addEventListener('group-created', () => {
    // Recharge tout pour avoir l'id réel retourné par l'API
    loadTasks();
  });

  groupManager.addEventListener('group-left', () => {
    loadTasks();
  });

  /* ── Init ── */
  await loadTasks();
})();