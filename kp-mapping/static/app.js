const API = "";

let allMappings = [];
let allKps = [];
let facets = { topics: [], content_types: [] };
let selectedId = null;

const FILTER_IDS = [
  "searchList",
  "filterReview",
  "filterType",
  "filterTopic",
  "filterKp",
  "filterConfidence",
  "filterTags",
];

async function fetchJson(url, options) {
  const res = await fetch(API + url, options);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function confidenceClass(c) {
  return `conf-${c || "uncertain"}`;
}

function renderStats(stats) {
  document.getElementById("stats").innerHTML = `
    <span class="stat-pill">Total: ${stats.total}</span>
    <span class="stat-pill">Flagged: ${stats.flagged_for_human}</span>
    <span class="stat-pill">Pending: ${stats.pending_review}</span>
    <span class="stat-pill">Approved: ${stats.approved}</span>
  `;
}

function effectiveTags(mapping) {
  return mapping.human_tags.length
    ? mapping.human_tags
    : mapping.ai_result.proposed_tags;
}

function getFilterParams() {
  const review = document.getElementById("filterReview").value;
  const params = new URLSearchParams();
  params.set("limit", "2000");

  if (review === "flagged") {
    params.set("needs_human_review", "true");
  } else if (review) {
    params.set("review_status", review);
  }

  const type = document.getElementById("filterType").value;
  if (type) params.set("content_type", type);

  const topic = document.getElementById("filterTopic").value;
  if (topic) params.set("topic_name", topic);

  const kp = document.getElementById("filterKp").value;
  if (kp) params.set("kp_id", kp);

  const confidence = document.getElementById("filterConfidence").value;
  if (confidence) params.set("confidence", confidence);

  const tags = document.getElementById("filterTags").value;
  if (tags === "has") params.set("has_tags", "true");
  if (tags === "none") params.set("has_tags", "false");

  const q = document.getElementById("searchList").value.trim();
  if (q) params.set("q", q);

  return params;
}

function updateFilterSummary(shown, total) {
  const el = document.getElementById("filterSummary");
  const active = FILTER_IDS.some((id) => {
    const node = document.getElementById(id);
    return node && node.value && node.value.trim() !== "";
  });
  if (!active) {
    el.textContent = `Showing ${shown} item${shown === 1 ? "" : "s"}`;
    return;
  }
  el.textContent = `Showing ${shown} of ${total} (filtered)`;
}

function populateSelect(id, values, labelFn) {
  const select = document.getElementById(id);
  const current = select.value;
  const first = select.options[0];
  select.innerHTML = "";
  select.appendChild(first);
  values.forEach((value) => {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = labelFn ? labelFn(value) : value;
    select.appendChild(opt);
  });
  if ([...select.options].some((o) => o.value === current)) {
    select.value = current;
  }
}

function populateFilterDropdowns() {
  populateSelect("filterType", facets.content_types);
  populateSelect("filterTopic", facets.topics);
  populateSelect(
    "filterKp",
    allKps.map((kp) => kp.source_kp_id),
    (id) => {
      const kp = allKps.find((k) => k.source_kp_id === id);
      return kp ? `${id} — ${kp.label}` : id;
    }
  );
}

function clearFilters() {
  FILTER_IDS.forEach((id) => {
    document.getElementById(id).value = "";
  });
  loadMappings();
}

function renderList() {
  const list = document.getElementById("contentList");
  const items = allMappings;
  updateFilterSummary(items.length, items.length);

  if (!items.length) {
    list.innerHTML = `<li class="empty-state">No items match the current filters.</li>`;
    return;
  }

  list.innerHTML = items
    .map((m) => {
      const flagged = m.ai_result.needs_human_review;
      const status = m.review_status;
      const tagCount = effectiveTags(m).length;
      return `
        <li data-id="${m.content_id}" class="${m.content_id === selectedId ? "active" : ""}">
          <div class="title">${escapeHtml(m.title)}</div>
          <div class="meta">
            ${flagged ? '<span class="badge flagged">review</span>' : ""}
            <span class="badge ${status}">${status}</span>
            ${m.content_type} · ${tagCount} tag${tagCount === 1 ? "" : "s"}
          </div>
          ${m.topic_name ? `<div class="topic-line">${escapeHtml(m.topic_name)}</div>` : ""}
        </li>
      `;
    })
    .join("");

  list.querySelectorAll("li[data-id]").forEach((li) => {
    li.addEventListener("click", () => selectItem(li.dataset.id));
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function tagRowHtml(tag, index) {
  return `
    <div class="tag-row" data-index="${index}">
      <div class="kp-picker">
        <input type="text" class="kp-search" placeholder="KP id or label" value="${escapeHtml(tag.source_kp_id)} - ${escapeHtml(tag.label || "")}" data-kp-id="${escapeHtml(tag.source_kp_id)}" data-label="${escapeHtml(tag.label || "")}" />
        <div class="kp-suggestions"></div>
      </div>
      <select class="tag-role">
        ${["explain","practice","example","assessment","project","syntax","prerequisite"].map((r) => `<option value="${r}" ${tag.tag_role === r ? "selected" : ""}>${r}</option>`).join("")}
      </select>
      <select class="tag-confidence">
        ${["high","medium","low","uncertain"].map((c) => `<option value="${c}" ${tag.confidence === c ? "selected" : ""}>${c}</option>`).join("")}
      </select>
      <button type="button" class="danger remove-tag">Remove</button>
      <textarea class="rationale" placeholder="Rationale">${escapeHtml(tag.rationale || "")}</textarea>
    </div>
  `;
}

async function selectItem(contentId) {
  selectedId = contentId;
  renderList();
  const data = await fetchJson(`/api/mappings/${contentId}`);
  renderDetail(data);
}

function renderDetail(mapping) {
  const panel = document.getElementById("detailPanel");
  const tags = effectiveTags(mapping);
  const ai = mapping.ai_result;

  panel.innerHTML = `
    <h2>${escapeHtml(mapping.title)}</h2>
    <div class="meta-grid">
      <div><span>Content ID</span>${escapeHtml(mapping.content_id)}</div>
      <div><span>Type</span>${escapeHtml(mapping.content_type)}</div>
      <div><span>Topic</span>${escapeHtml(mapping.topic_name || "—")}</div>
      <div><span>Course</span>${escapeHtml(mapping.course_title || "—")}</div>
      <div><span>AI confidence</span><span class="${confidenceClass(ai.overall_confidence)}">${ai.overall_confidence}</span></div>
      <div><span>Model</span>${escapeHtml(ai.model || "—")}</div>
      <div><span>File</span><code style="font-size:0.75rem">${escapeHtml(mapping.file_path)}</code></div>
    </div>

    ${
      ai.review_reasons?.length
        ? `<div class="reasons"><strong>Review reasons</strong><ul>${ai.review_reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul></div>`
        : ""
    }

    <div class="tag-section">
      <h3>Knowledge point tags</h3>
      <div id="tagRows">${tags.map((t, i) => tagRowHtml(t, i)).join("")}</div>
      <button type="button" class="secondary" id="addTag">+ Add KP</button>
    </div>

    <label>Review status
      <select id="reviewStatus">
        <option value="pending" ${mapping.review_status === "pending" ? "selected" : ""}>pending</option>
        <option value="needs_review" ${mapping.review_status === "needs_review" ? "selected" : ""}>needs_review</option>
        <option value="approved" ${mapping.review_status === "approved" ? "selected" : ""}>approved</option>
        <option value="rejected" ${mapping.review_status === "rejected" ? "selected" : ""}>rejected</option>
      </select>
    </label>

    <label style="display:block;margin-top:0.75rem">Reviewer notes
      <textarea id="reviewerNotes" rows="3" style="width:100%;margin-top:0.25rem;padding:0.5rem;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text)">${escapeHtml(mapping.reviewer_notes || "")}</textarea>
    </label>

    <div class="actions">
      <button type="button" class="primary" id="saveReview">Save review</button>
      <button type="button" class="secondary" id="useAiTags">Reset to AI suggestions</button>
    </div>
  `;

  wireTagRows(panel);
  document.getElementById("addTag").onclick = () => {
    const rows = document.getElementById("tagRows");
    const empty = {
      source_kp_id: "",
      label: "",
      tag_role: "practice",
      confidence: "medium",
      rationale: "",
    };
    rows.insertAdjacentHTML("beforeend", tagRowHtml(empty, rows.children.length));
    wireTagRows(panel);
  };

  document.getElementById("useAiTags").onclick = () => {
    document.getElementById("tagRows").innerHTML = ai.proposed_tags
      .map((t, i) => tagRowHtml(t, i))
      .join("");
    wireTagRows(panel);
  };

  document.getElementById("saveReview").onclick = () => saveReview(mapping.content_id);
}

function wireTagRows(panel) {
  panel.querySelectorAll(".remove-tag").forEach((btn) => {
    btn.onclick = () => btn.closest(".tag-row").remove();
  });

  panel.querySelectorAll(".kp-search").forEach((input) => {
    const box = input.nextElementSibling;
    input.addEventListener("input", () => {
      const q = input.value.toLowerCase();
      const matches = allKps
        .filter(
          (kp) =>
            kp.source_kp_id.toLowerCase().includes(q) ||
            kp.label.toLowerCase().includes(q)
        )
        .slice(0, 12);
      box.innerHTML = matches
        .map(
          (kp) =>
            `<div data-id="${kp.source_kp_id}" data-label="${escapeHtml(kp.label)}">${kp.source_kp_id} — ${escapeHtml(kp.label)}</div>`
        )
        .join("");
      box.classList.add("open");
      box.querySelectorAll("div").forEach((div) => {
        div.onclick = () => {
          input.value = `${div.dataset.id} - ${div.dataset.label}`;
          input.dataset.kpId = div.dataset.id;
          input.dataset.label = div.dataset.label;
          box.classList.remove("open");
        };
      });
    });
    input.addEventListener("blur", () => setTimeout(() => box.classList.remove("open"), 200));
  });
}

function collectTags() {
  return [...document.querySelectorAll(".tag-row")].map((row) => {
    const input = row.querySelector(".kp-search");
    let kpId = input.dataset.kpId;
    let label = input.dataset.label;
    if (!kpId && input.value.includes(" - ")) {
      [kpId, label] = input.value.split(" - ", 2);
    } else if (!kpId) {
      kpId = input.value.trim();
    }
    return {
      source_kp_id: kpId.trim(),
      label: (label || "").trim(),
      tag_role: row.querySelector(".tag-role").value,
      confidence: row.querySelector(".tag-confidence").value,
      rationale: row.querySelector(".rationale").value,
    };
  }).filter((t) => t.source_kp_id);
}

async function saveReview(contentId) {
  const payload = {
    human_tags: collectTags(),
    review_status: document.getElementById("reviewStatus").value,
    reviewer_notes: document.getElementById("reviewerNotes").value,
  };
  await fetchJson(`/api/mappings/${contentId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await loadMappings();
  await selectItem(contentId);
}

let searchDebounce = null;

async function loadMappings() {
  const params = getFilterParams();
  const data = await fetchJson(`/api/mappings?${params.toString()}`);
  allMappings = data.items;
  renderStats(data.stats);
  renderList();

  if (selectedId && !allMappings.some((m) => m.content_id === selectedId)) {
    selectedId = null;
    document.getElementById("detailPanel").innerHTML =
      '<p class="placeholder">Selected item is hidden by filters. Clear filters or pick another item.</p>';
  }
}

async function loadKps() {
  const data = await fetchJson("/api/kps?limit=500");
  allKps = data.knowledge_points;
}

async function loadFacets() {
  try {
    facets = await fetchJson("/api/mappings/facets");
  } catch {
    facets = { topics: [], content_types: [] };
  }
  populateFilterDropdowns();
}

async function init() {
  FILTER_IDS.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("change", () => loadMappings());
    if (el.type === "search" || el.tagName === "INPUT") {
      el.addEventListener("input", () => {
        clearTimeout(searchDebounce);
        searchDebounce = setTimeout(() => loadMappings(), 300);
      });
    }
  });

  document.getElementById("clearFilters").addEventListener("click", clearFilters);

  await loadKps();
  await loadFacets();
  await loadMappings();
}

init().catch((err) => {
  document.getElementById("detailPanel").innerHTML = `<p class="placeholder">Error: ${escapeHtml(err.message)}</p>`;
});
