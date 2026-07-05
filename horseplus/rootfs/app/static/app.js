/* HorsePlus Booking — frontend app logic.
 * All fetch URLs are relative (no leading slash) so they work correctly
 * behind Home Assistant's Ingress reverse proxy path prefixing.
 */

const state = {
  facilities: [],
  horses: [],
  calYear: new Date().getFullYear(),
  calMonth: new Date().getMonth() + 1,
};

// ── Utilities ────────────────────────────────────────────────────────────────

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* no body */ }
  if (!res.ok) {
    const msg = (data && (data.error || data.description)) || res.statusText;
    throw new Error(msg);
  }
  return data;
}

function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

// ── Tabs ─────────────────────────────────────────────────────────────────────

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "schedules") loadSchedules();
    if (btn.dataset.tab === "calendar") loadCalendar();
  });
});

// ── Status ───────────────────────────────────────────────────────────────────

async function loadStatus() {
  const badge = document.getElementById("status-badge");
  try {
    const data = await api("api/status");
    if (data.connected) {
      badge.textContent = `✅ ${data.user} @ ${data.farm}`;
      badge.className = "badge badge-connected";
    } else {
      badge.textContent = "⚠️ Not connected — check Configuration";
      badge.className = "badge badge-disconnected";
    }
    return data.connected;
  } catch (e) {
    badge.textContent = "⚠️ Connection error";
    badge.className = "badge badge-disconnected";
    return false;
  }
}

// ── Reference data (facilities / horses / activities) ───────────────────────

async function loadReferenceData() {
  try {
    const [facilities, horses] = await Promise.all([
      api("api/facilities"),
      api("api/horses"),
    ]);
    state.facilities = facilities;
    state.horses = horses;
    fillSelect("bf-facility", facilities, "facilityId", "name");
    fillSelect("bf-horse", horses, "horseId", "name");
    fillSelect("sf-facility", facilities, "facilityId", "name");
    fillSelect("sf-horse", horses, "horseId", "name");
  } catch (e) {
    console.error("Failed to load reference data:", e);
  }
}

function fillSelect(id, items, valueKey, labelKey) {
  const select = document.getElementById(id);
  select.innerHTML = "";
  items.forEach((item) => {
    const opt = document.createElement("option");
    opt.value = item[valueKey];
    opt.textContent = item[labelKey] + (item.nickName ? ` (${item.nickName})` : "");
    select.appendChild(opt);
  });
}

async function loadActivitiesFor(facilitySelectId, activitySelectId, facilityId) {
  const activitySelect = document.getElementById(activitySelectId);
  activitySelect.innerHTML = '<option value="">Auto</option>';
  if (!facilityId) return;
  try {
    const activities = await api(`api/activities?facility_id=${encodeURIComponent(facilityId)}`);
    activities.forEach((a) => {
      const opt = document.createElement("option");
      opt.value = a.facilityReservationActivityId;
      opt.textContent = a.name || "Activity";
      activitySelect.appendChild(opt);
    });
  } catch (e) { /* ignore, "Auto" remains selected */ }
}

document.getElementById("bf-facility").addEventListener("change", (e) =>
  loadActivitiesFor("bf-facility", "bf-activity", e.target.value));
document.getElementById("sf-facility").addEventListener("change", (e) =>
  loadActivitiesFor("sf-facility", "sf-activity", e.target.value));

// ── Book Now ─────────────────────────────────────────────────────────────────

document.getElementById("book-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const resultDiv = document.getElementById("book-result");
  resultDiv.textContent = "Booking…";
  resultDiv.className = "result";

  const facilitySelect = document.getElementById("bf-facility");
  const horseSelect = document.getElementById("bf-horse");

  const payload = {
    facility_id: facilitySelect.value,
    facility_name: facilitySelect.options[facilitySelect.selectedIndex]?.textContent,
    horse_id: horseSelect.value,
    horse_name: horseSelect.options[horseSelect.selectedIndex]?.textContent,
    activity_id: document.getElementById("bf-activity").value || null,
    date: document.getElementById("bf-date").value,
    time: document.getElementById("bf-time").value,
    duration_hours: parseFloat(document.getElementById("bf-duration").value),
  };

  try {
    const result = await api("api/book", { method: "POST", body: JSON.stringify(payload) });
    if (result.success) {
      resultDiv.textContent = "✅ Booked successfully!";
      resultDiv.className = "result success";
      loadBookings();
    } else {
      resultDiv.textContent = `❌ ${result.error}${result.conflicts ? ": " + result.conflicts.join(", ") : ""}`;
      resultDiv.className = "result error";
    }
  } catch (err) {
    resultDiv.textContent = `❌ ${err.message}`;
    resultDiv.className = "result error";
  }
});

// ── Upcoming Bookings ────────────────────────────────────────────────────────

async function loadBookings() {
  const list = document.getElementById("bookings-list");
  list.textContent = "Loading…";
  try {
    const bookings = await api("api/bookings");
    if (!bookings.length) {
      list.innerHTML = '<div class="empty-msg">No upcoming bookings.</div>';
      return;
    }
    list.innerHTML = "";
    bookings.forEach((b) => {
      const item = el(`
        <div class="list-item">
          <div class="info">
            <div class="title">${b.facility} — ${b.horse || ""}</div>
            <div class="subtitle">${b.start_display} – ${b.end_display}</div>
          </div>
          <div class="actions">
            <button class="icon-btn danger" data-id="${b.id}">Cancel</button>
          </div>
        </div>
      `);
      item.querySelector("button").addEventListener("click", async () => {
        if (!confirm("Cancel this booking?")) return;
        try {
          await api(`api/bookings/${encodeURIComponent(b.id)}`, { method: "DELETE" });
          loadBookings();
        } catch (err) {
          alert(`Failed to cancel: ${err.message}`);
        }
      });
      list.appendChild(item);
    });
  } catch (e) {
    list.innerHTML = `<div class="empty-msg">Could not load bookings: ${e.message}</div>`;
  }
}

// ── Schedules ────────────────────────────────────────────────────────────────

const WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

async function loadSchedules() {
  const list = document.getElementById("schedules-list");
  list.textContent = "Loading…";
  try {
    const schedules = await api("api/schedules");
    if (!schedules.length) {
      list.innerHTML = '<div class="empty-msg">No schedules yet. Click "+ Add Schedule" to create one.</div>';
      return;
    }
    list.innerHTML = "";
    schedules.forEach((s) => {
      const statusClass = s.last_status === "success" ? "last-success" : s.last_status === "error" ? "last-error" : "";
      const item = el(`
        <div class="list-item">
          <div class="info">
            <div class="title">${s.name}
              <span class="status-pill ${s.enabled ? "enabled" : "disabled"}">${s.enabled ? "ENABLED" : "DISABLED"}</span>
              ${s.last_status ? `<span class="status-pill ${statusClass}">${s.last_status.toUpperCase()}</span>` : ""}
            </div>
            <div class="subtitle">
              ${s.facility_name || s.facility_id} · ${s.horse_name || s.horse_id}<br>
              Runs: ${WEEKDAY_NAMES[s.trigger_weekday]} ${s.trigger_time} → books ${s.booking_time} (+${s.booking_date_offset}d, ${s.duration_hours}h)
              ${s.next_run ? `<br>Next run: ${new Date(s.next_run).toLocaleString()}` : ""}
            </div>
          </div>
          <div class="actions">
            <button class="icon-btn" data-action="run">Run now</button>
            <button class="icon-btn" data-action="toggle">${s.enabled ? "Disable" : "Enable"}</button>
            <button class="icon-btn" data-action="edit">Edit</button>
            <button class="icon-btn danger" data-action="delete">Delete</button>
          </div>
        </div>
      `);
      item.querySelector('[data-action="run"]').addEventListener("click", async () => {
        await api(`api/schedules/${s.id}/run`, { method: "POST" });
        alert("Schedule triggered — check upcoming bookings shortly.");
      });
      item.querySelector('[data-action="toggle"]').addEventListener("click", async () => {
        await api(`api/schedules/${s.id}/toggle`, { method: "POST" });
        loadSchedules();
      });
      item.querySelector('[data-action="edit"]').addEventListener("click", () => openScheduleModal(s));
      item.querySelector('[data-action="delete"]').addEventListener("click", async () => {
        if (!confirm(`Delete schedule "${s.name}"?`)) return;
        await api(`api/schedules/${s.id}`, { method: "DELETE" });
        loadSchedules();
      });
      list.appendChild(item);
    });
  } catch (e) {
    list.innerHTML = `<div class="empty-msg">Could not load schedules: ${e.message}</div>`;
  }
}

function openScheduleModal(schedule = null) {
  document.getElementById("schedule-modal-title").textContent = schedule ? "Edit Schedule" : "New Schedule";
  document.getElementById("sf-id").value = schedule?.id || "";
  document.getElementById("sf-name").value = schedule?.name || "";
  document.getElementById("sf-trigger-weekday").value = schedule?.trigger_weekday ?? 0;
  document.getElementById("sf-trigger-time").value = schedule?.trigger_time || "08:00";
  document.getElementById("sf-date-offset").value = schedule?.booking_date_offset ?? 7;
  document.getElementById("sf-booking-time").value = schedule?.booking_time || "16:30";
  document.getElementById("sf-duration").value = schedule?.duration_hours ?? 1.5;
  document.getElementById("sf-retry-count").value = schedule?.retry_count ?? 3;
  document.getElementById("sf-retry-delay").value = schedule?.retry_delay_seconds ?? 2;

  if (schedule?.facility_id) {
    document.getElementById("sf-facility").value = schedule.facility_id;
    loadActivitiesFor("sf-facility", "sf-activity", schedule.facility_id).then(() => {
      if (schedule.activity_id) document.getElementById("sf-activity").value = schedule.activity_id;
    });
  }
  if (schedule?.horse_id) document.getElementById("sf-horse").value = schedule.horse_id;

  document.getElementById("schedule-modal").classList.remove("hidden");
}

function closeScheduleModal() {
  document.getElementById("schedule-modal").classList.add("hidden");
  document.getElementById("schedule-form").reset();
}

document.getElementById("add-schedule-btn").addEventListener("click", () => openScheduleModal());
document.getElementById("schedule-cancel-btn").addEventListener("click", closeScheduleModal);

document.getElementById("schedule-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const facilitySelect = document.getElementById("sf-facility");
  const horseSelect = document.getElementById("sf-horse");
  const id = document.getElementById("sf-id").value;

  const payload = {
    name: document.getElementById("sf-name").value,
    facility_id: facilitySelect.value,
    facility_name: facilitySelect.options[facilitySelect.selectedIndex]?.textContent,
    horse_id: horseSelect.value,
    horse_name: horseSelect.options[horseSelect.selectedIndex]?.textContent,
    activity_id: document.getElementById("sf-activity").value || null,
    trigger_weekday: parseInt(document.getElementById("sf-trigger-weekday").value, 10),
    trigger_time: document.getElementById("sf-trigger-time").value,
    booking_date_offset: parseInt(document.getElementById("sf-date-offset").value, 10),
    booking_time: document.getElementById("sf-booking-time").value,
    duration_hours: parseFloat(document.getElementById("sf-duration").value),
    retry_count: parseInt(document.getElementById("sf-retry-count").value, 10),
    retry_delay_seconds: parseInt(document.getElementById("sf-retry-delay").value, 10),
    enabled: true,
  };

  try {
    if (id) {
      await api(`api/schedules/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      await api("api/schedules", { method: "POST", body: JSON.stringify(payload) });
    }
    closeScheduleModal();
    loadSchedules();
  } catch (err) {
    alert(`Failed to save schedule: ${err.message}`);
  }
});

// ── Calendar ─────────────────────────────────────────────────────────────────

async function loadCalendar() {
  const grid = document.getElementById("calendar-grid");
  const title = document.getElementById("cal-title");
  const monthNames = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  title.textContent = `${monthNames[state.calMonth - 1]} ${state.calYear}`;
  grid.textContent = "Loading…";

  try {
    const data = await api(`api/calendar?year=${state.calYear}&month=${state.calMonth}`);
    const daysInMonth = new Date(state.calYear, state.calMonth, 0).getDate();
    const eventsByDay = {};
    (data.events || []).forEach((ev) => {
      (eventsByDay[ev.day] ||= []).push(ev);
    });

    grid.innerHTML = "";
    for (let d = 1; d <= daysInMonth; d++) {
      const dayEvents = eventsByDay[d] || [];
      const dayDiv = el(`<div class="cal-day"><div class="day-num">${d}</div></div>`);
      dayEvents.forEach((ev) => {
        dayDiv.appendChild(el(`<div class="cal-event">${ev.start_time} ${ev.facility} (${ev.horse})</div>`));
      });
      grid.appendChild(dayDiv);
    }
  } catch (e) {
    grid.innerHTML = `<div class="empty-msg">Could not load calendar: ${e.message}</div>`;
  }
}

document.getElementById("cal-prev").addEventListener("click", () => {
  state.calMonth--;
  if (state.calMonth < 1) { state.calMonth = 12; state.calYear--; }
  loadCalendar();
});
document.getElementById("cal-next").addEventListener("click", () => {
  state.calMonth++;
  if (state.calMonth > 12) { state.calMonth = 1; state.calYear++; }
  loadCalendar();
});

// ── Init ─────────────────────────────────────────────────────────────────────

(async function init() {
  const today = new Date();
  document.getElementById("bf-date").value = today.toISOString().slice(0, 10);
  document.getElementById("bf-time").value = "16:30";

  const connected = await loadStatus();
  if (connected) {
    await loadReferenceData();
    await loadBookings();
  }
  // Poll connection status periodically
  setInterval(loadStatus, 30000);
})();
