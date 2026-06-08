// ================================================================
// Hilfsfunktionen
// ================================================================

// HTML-Escaping gegen XSS: alle dynamischen Werte (Labels, Zustände,
// Entitätsnamen) werden vor dem Einfügen ins DOM maskiert.
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function chip(t, c) { return `<span class="chip chip-${c}">${esc(t)}</span>`; }
function tile(v, l, vc = '') { return `<div class="metric"><div class="val ${vc}">${esc(v)}</div><div class="lbl">${esc(l)}</div></div>`; }
function row(k, v, c = '') { return `<div class="row"><span class="k">${esc(k)}</span><span class="v ${c}">${esc(v)}</span></div>`; }
function fmt(v) { return v == null ? '–' : Math.round(v).toLocaleString('de-DE'); }
function fmtDur(s) { return s >= 60 ? Math.floor(s / 60) + 'm ' + Math.round(s % 60) + 's' : Math.round(s) + 's'; }
function showError(msg) {
  const el = document.getElementById('error-banner');
  el.style.display = msg ? 'block' : 'none';
  if (msg) el.textContent = '⚠ ' + msg;
}

// ================================================================
// TAB-NAVIGATION
// ================================================================
function switchTab(name) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  const btn = document.querySelector(`.tab-btn[data-tab="${name}"]`);
  if (btn) btn.classList.add('active');
  if (name === 'steuerung') fetchControls();
}

// ================================================================
// MONITOR
// ================================================================
// Gecachter Snapshot + Empfangszeit, damit Timer zwischen den Zyklen live
// herunterzählen. Der Regelzyklus läuft nur alle interval_s (Standard 30 s),
// sonst blieben die serverseitigen Restzeiten zwischen den Polls eingefroren.
let _lastData = null;
let _statusAt = 0;   // Date.now() beim Eintreffen des letzten Snapshots
let _elapsed  = 0;   // Sekunden seit diesem Snapshot (je Render gesetzt)

async function pollStatus() {
  try {
    const r = await fetch('api/status');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    _lastData = await r.json();
    _statusAt = Date.now();
    render(_lastData);
    document.getElementById('live-dot').className = 'dot';
  } catch (e) {
    document.getElementById('live-dot').className = 'dot error';
    showError('Verbindungsfehler: ' + e.message);
  }
}

function render(data) {
  const s = data.status || {};
  _elapsed = _statusAt ? (Date.now() - _statusAt) / 1000 : 0;
  showError(data.error || '');

  const chips = [
    chip(s.ems_enabled ? 'EMS Aktiv' : 'EMS Inaktiv', s.ems_enabled ? 'green' : 'grey'),
    chip('Modus: ' + (s.global_mode || '–'), 'blue'),
  ];
  if (s.hard_lockout)         chips.push(chip('⚠ LOCKOUT', 'red'));
  if (s.binary_immediate_off) chips.push(chip('Notabschaltung', 'red'));
  document.getElementById('chips').innerHTML = chips.join('');

  const tiles = [
    tile(fmt(s.residual_w) + ' W', 'Überschuss', s.residual_w < 0 ? 'warn' : 'ok'),
    tile(fmt(s.pool_w)     + ' W', 'EMS Pool'),
  ];
  if (s.current_deficit_w > 0) tiles.push(tile(fmt(s.current_deficit_w) + ' W', 'Defizit', 'warn'));
  tiles.push(tile(fmt(s.binary_total_w) + ' W', 'Binär gesamt'));
  document.getElementById('metrics').innerHTML = tiles.join('');

  const devices = s.devices || [];
  document.getElementById('controllable').innerHTML =
    devices.filter(d => d.type === 'controllable').map(renderControllable).join('');
  document.getElementById('binary').innerHTML =
    devices.filter(d => d.type === 'binary').map(renderBinary).join('');

  document.getElementById('footer').innerHTML =
    `<span>Letzter Zyklus: ${esc(data.last_cycle_at || '–')}</span>` +
    `<span>Zyklen: ${esc(data.cycle_count || 0)}</span>` +
    `<span>Intervall: ${esc(data.interval_s)}s</span>`;
}

function renderControllable(d) {
  const cls = !d.eligible ? 'off' : d.new_w > 0 ? 'active' : 'idle';
  const changed = Math.round(d.new_w) !== Math.round(d.anforderung_current_w);
  const isAmpere = d.output_unit === 'ampere';
  const ph = isAmpere ? (d.current_phases || 1) : 1;
  const vl1 = d.voltage_l1 || 230;
  const vl2 = d.voltage_l2 || 230;
  const vl3 = d.voltage_l3 || 230;
  const eff = isAmpere ? (ph === 1 ? vl1 : vl1 + vl2 + vl3) : 1;
  // Aktueller Sollwert zur Anzeige in A umgerechnet (anforderung_current_w ist immer in W)
  const anfA = isAmpere ? Math.floor(d.anforderung_current_w / eff) : null;
  const anfDisplay = isAmpere
    ? (anfA + ' A  (' + fmt(d.anforderung_current_w) + ' W)')
    : fmt(d.anforderung_current_w) + ' W';
  const neuDisplay = isAmpere
    ? (d.new_a != null ? d.new_a + ' A  (' + fmt(d.new_w) + ' W)' : '–')
    : fmt(d.new_w) + ' W';
  const multiPhase = isAmpere && d.allowed_phases && d.allowed_phases.length > 1;
  const phaseLockRem = multiPhase ? Math.max(0, (d.phase_lock_remaining_s || 0) - _elapsed) : 0;
  const phaseLock  = phaseLockRem > 0
    ? ' (Lock: ' + fmtDur(phaseLockRem) + ')' : '';
  return `<div class="card ${cls}">
    <div class="card-title"><span class="card-name">${esc(d.label || d.id)}</span><span class="prio-badge">Prio ${esc(d.priority)}</span></div>
    ${row('Freigabe',     d.eligible ? '✓ ja' : '✗ nein', d.eligible ? 'on' : 'off-val')}
    ${row('Ist',          fmt(d.actual_w) + ' W')}
    ${row('Anforderung',  anfDisplay)}
    ${row('Ziel (alloc)', fmt(d.alloc_w) + ' W')}
    ${row('Schutz',       fmt(d.schutz_w) + ' W', 'dim')}
    ${isAmpere ? row('Spannung', ph === 1 ? `L1: ${vl1} V` : `L1/L2/L3: ${vl1}/${vl2}/${vl3} V`, 'dim') : ''}
    ${multiPhase ? row('Phasen', ph + '-phasig' + phaseLock, phaseLock ? 'dim' : '') : ''}
    ${row('Neu → HA',     neuDisplay, changed ? 'changed' : '')}
  </div>`;
}

function renderBinary(d) {
  const cls = !d.eligible ? 'off' : d.final_on ? 'active' : 'idle';
  const changed = d.actual_on !== d.final_on;

  let timingRow = '';
  if (d.actual_on && d.min_runtime_s > 0) {
    const rem = Math.max(0, d.min_runtime_s - d.switch_age_s - _elapsed);
    timingRow = rem > 0
      ? row('Mindestlaufzeit', 'noch ' + fmtDur(rem), 'dim')
      : row('Mindestlaufzeit', '✓ erfüllt', 'on');
  } else if (!d.actual_on && d.min_offtime_s > 0) {
    const rem = Math.max(0, d.min_offtime_s - d.switch_age_s - _elapsed);
    timingRow = rem > 0
      ? row('Mindestauszeit', 'noch ' + fmtDur(rem), 'dim')
      : row('Mindestauszeit', '✓ erfüllt', 'on');
  }

  let offDelayRow = '';
  if (d.off_delay_remaining_s != null) {
    const rem = Math.max(0, d.off_delay_remaining_s - _elapsed);
    offDelayRow = rem > 0
      ? row('Abschaltverzögerung', 'noch ' + fmtDur(rem), 'dim')
      : row('Abschaltverzögerung', '↓ abschalten', 'changed');
  }

  return `<div class="card ${cls}">
    <div class="card-title"><span class="card-name">${esc(d.label || d.id)}</span><span class="prio-badge">Prio ${esc(d.priority)}</span></div>
    ${row('Freigabe',   d.eligible  ? '✓ ja' : '✗ nein', d.eligible  ? 'on' : 'off-val')}
    ${row('Leistung',   fmt(d.power_w) + ' W')}
    ${row('Ist',        d.actual_on  ? '● AN' : '○ AUS', d.actual_on  ? 'on' : 'off-val')}
    ${row('Gewünscht',  d.desired_on ? '● AN' : '○ AUS', d.desired_on ? 'on' : 'dim')}
    ${row('Kandidat',   d.candidate_on ? '● AN' : '○ AUS', d.candidate_on ? 'on' : 'dim')}
    ${row('Final → HA', d.final_on ? '● AN' : '○ AUS', changed ? 'changed' : d.final_on ? 'on' : 'off-val')}
    ${timingRow}
    ${offDelayRow}
  </div>`;
}

// ================================================================
// STEUERUNG
// ================================================================
let _saveTimers = {};
let _ctrlOpen   = {};      // Aufklappzustand je Gruppen-Index
let _ctrlSchema = null;    // einmalig aus /api/device_controls_schema geladen

async function fetchControls() {
  try {
    if (!_ctrlSchema) {
      const rs = await fetch('api/device_controls_schema');
      _ctrlSchema = await rs.json();
    }
    const r = await fetch('api/controls');
    const states = await r.json();
    renderControls(_ctrlSchema, states);
    document.getElementById('ctrl-refresh').textContent =
      'Aktualisiert: ' + new Date().toLocaleTimeString('de');
  } catch (e) {
    document.getElementById('ctrl-refresh').textContent = 'Fehler: ' + e.message;
  }
}

function renderControls(schema, states) {
  // Gruppen werden über ihren Index referenziert (stabil & frei von Sonderzeichen),
  // damit Labels mit Leerzeichen/Anführungszeichen weder IDs noch Handler aufbrechen.
  document.getElementById('ctrl-grid').innerHTML = schema.map((group, idx) => {
    const open = _ctrlOpen[idx] !== false;    // Standard: offen
    const rows = group.items.map(item => renderCtrlRow(item, states[item.entity])).join('');
    return `<div class="ctrl-card">
      <div class="ctrl-card-header" data-key="${idx}">
        <span class="ctrl-card-title">${esc(group.label)}</span>
        <span class="ctrl-card-arrow ${open ? 'open' : ''}">▼</span>
      </div>
      <div class="ctrl-card-body ${open ? '' : 'collapsed'}" id="ctrlbody-${idx}">
        ${rows}
      </div>
    </div>`;
  }).join('');
}

function toggleCard(key, header) {
  const body  = document.getElementById('ctrlbody-' + key);
  const arrow = header.querySelector('.ctrl-card-arrow');
  const isOpen = !body.classList.contains('collapsed');
  body.classList.toggle('collapsed', isOpen);
  arrow.classList.toggle('open', !isOpen);
  _ctrlOpen[key] = !isOpen;
}

function renderCtrlRow(item, state) {
  const siId = 'si-' + item.entity.replace(/\./g, '-');
  let input;

  if (!state) {
    input = `<span class="ctrl-not-found">nicht gefunden</span>`;
  } else {
    const domain = item.entity.split('.')[0];
    const attrs  = state.attributes || {};

    if (domain === 'input_boolean') {
      const on = state.state === 'on';
      input = `<button class="toggle-btn ${on ? 'on' : ''}"
        data-entity="${esc(item.entity)}"
        data-role="toggle">${on ? 'AN' : 'AUS'}</button>`;

    } else if (domain === 'input_number') {
      const val  = parseFloat(state.state) || 0;
      const unit = attrs.unit_of_measurement || '';
      const min  = attrs.min  != null ? `min="${esc(attrs.min)}"`  : '';
      const max  = attrs.max  != null ? `max="${esc(attrs.max)}"`  : '';
      const step = attrs.step != null ? `step="${esc(attrs.step)}"` : 'step="1"';
      input = `<div class="num-wrap">
        <input type="number" class="num-input"
          value="${esc(val)}" ${min} ${max} ${step}
          data-entity="${esc(item.entity)}"
          data-role="number">
        ${unit ? `<span class="unit">${esc(unit)}</span>` : ''}
      </div>`;

    } else if (domain === 'input_select') {
      const opts = (attrs.options || []).map(o =>
        `<option value="${esc(o)}" ${o === state.state ? 'selected' : ''}>${esc(o)}</option>`
      ).join('');
      input = `<select class="sel-input" data-entity="${esc(item.entity)}" data-role="select">
        ${opts}
      </select>`;
    } else {
      input = `<span class="ctrl-not-found">${esc(state.state)}</span>`;
    }
  }

  return `<div class="ctrl-row">
    <span class="k">${esc(item.label)}</span>
    <div class="ctrl-right">${input}<span class="save-indicator" id="${siId}"></span></div>
  </div>`;
}

// ---- Steuerungs-Event-Handler ----

function ctrlToggle(btn) {
  const isOn = btn.classList.contains('on');
  btn.classList.toggle('on', !isOn);
  btn.textContent = !isOn ? 'AN' : 'AUS';
  saveEntity(btn.dataset.entity, !isOn);
}

function scheduleSet(input) {
  const id = input.dataset.entity;
  clearTimeout(_saveTimers[id]);
  _saveTimers[id] = setTimeout(() => immediateSet(input), 700);
}

function immediateSet(input) {
  clearTimeout(_saveTimers[input.dataset.entity]);
  saveEntity(input.dataset.entity, parseFloat(input.value));
}

function ctrlSelect(sel) {
  saveEntity(sel.dataset.entity, sel.value);
}

async function saveEntity(entityId, value) {
  const siId = 'si-' + entityId.replace(/\./g, '-');
  const si   = document.getElementById(siId);
  if (si) { si.textContent = '↑'; si.className = 'save-indicator saving'; }

  try {
    const r = await fetch('api/set', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entity_id: entityId, value }),
    });
    const ok = (await r.json()).ok === true;
    if (si) {
      si.textContent = ok ? '✓' : '✗';
      si.className   = 'save-indicator ' + (ok ? 'saved' : 'err');
      setTimeout(() => { if (si) { si.textContent = ''; si.className = 'save-indicator'; } }, 2500);
    }
  } catch (e) {
    if (si) { si.textContent = '✗'; si.className = 'save-indicator err'; }
  }
}

// ================================================================
// EVENT-DELEGATION & INITIALISIERUNG
// ================================================================
document.addEventListener('DOMContentLoaded', () => {
  // Tab-Buttons
  document.querySelector('.tabs').addEventListener('click', (e) => {
    const btn = e.target.closest('.tab-btn');
    if (btn) switchTab(btn.dataset.tab);
  });

  const grid = document.getElementById('ctrl-grid');

  // Klicks: Karten auf-/zuklappen + Toggle-Buttons
  grid.addEventListener('click', (e) => {
    const header = e.target.closest('.ctrl-card-header');
    if (header) { toggleCard(header.dataset.key, header); return; }
    const toggle = e.target.closest('.toggle-btn[data-role="toggle"]');
    if (toggle) ctrlToggle(toggle);
  });

  // Änderungen: Zahlenfeld (debounced) + Select
  grid.addEventListener('input', (e) => {
    const num = e.target.closest('.num-input[data-role="number"]');
    if (num) scheduleSet(num);
  });
  grid.addEventListener('change', (e) => {
    const sel = e.target.closest('.sel-input[data-role="select"]');
    if (sel) ctrlSelect(sel);
  });
  // Sofortiges Speichern beim Verlassen des Zahlenfelds
  grid.addEventListener('focusout', (e) => {
    const num = e.target.closest('.num-input[data-role="number"]');
    if (num) immediateSet(num);
  });

  // Initialer Abruf + periodische Aktualisierung
  pollStatus();
  setInterval(pollStatus, 5000);
  // Sekündlich aus dem gecachten Snapshot neu rendern, damit Countdowns
  // (Abschaltverzögerung, Mindestlauf-/auszeit, Phasen-Lock) live ticken,
  // statt bis zum nächsten Regelzyklus eingefroren zu bleiben.
  setInterval(() => { if (_lastData) render(_lastData); }, 1000);

  // Steuerungs-Tab alle 15 s aktualisieren, wenn aktiv
  setInterval(() => {
    if (document.getElementById('tab-steuerung').classList.contains('active'))
      fetchControls();
  }, 15000);
});
