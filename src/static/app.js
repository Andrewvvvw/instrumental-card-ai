"use strict";

const $ = (id) => document.getElementById(id);
const form = $("product-form");
const specsList = $("specs-list");
let currentCard = null;
let currentFormat = "preview";
let busy = false;
let toastTimer;

function addSpec(key = "", value = "") {
  const row = document.createElement("div");
  row.className = "spec-row";
  const keyInput = document.createElement("input");
  keyInput.className = "spec-key";
  keyInput.placeholder = "Параметр";
  keyInput.value = key;
  keyInput.setAttribute("aria-label", "Название характеристики");
  const valueInput = document.createElement("input");
  valueInput.className = "spec-value";
  valueInput.placeholder = "Значение";
  valueInput.value = value;
  valueInput.setAttribute("aria-label", "Значение характеристики");
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "remove-spec";
  remove.setAttribute("aria-label", "Удалить характеристику");
  remove.textContent = "×";
  remove.addEventListener("click", () => {
    row.remove();
    if (!specsList.children.length) addSpec();
    markChanged();
  });
  row.append(keyInput, valueInput, remove);
  specsList.append(row);
  return keyInput;
}

function clearForm() {
  form.reset();
  specsList.replaceChildren();
  addSpec();
}

function readProduct() {
  const name = $("product-name").value.trim();
  if (!name) {
    $("product-name").focus();
    throw new Error("Укажите название прибора.");
  }
  const specs = Object.create(null);
  for (const row of specsList.children) {
    const key = row.querySelector(".spec-key").value.trim();
    const value = row.querySelector(".spec-value").value.trim();
    if (!key && !value) continue;
    if (!key) {
      row.querySelector(".spec-key").focus();
      throw new Error("Укажите название характеристики рядом со значением.");
    }
    if (Object.hasOwn(specs, key)) {
      row.querySelector(".spec-key").focus();
      throw new Error(`Характеристика "${key}" указана дважды.`);
    }
    specs[key] = value;
  }
  return {
    name,
    manufacturer: $("manufacturer").value.trim() || null,
    specs,
    description: $("description").value.trim() || null,
  };
}

function setError(message = "") {
  $("form-error").textContent = message;
  $("form-error").hidden = !message;
}

function setBusy(value) {
  busy = value;
  $("form-fields").disabled = value;
  $("clear-button").disabled = value;
  $("copy-button").disabled = value || !currentCard;
  $("result-panel").setAttribute("aria-busy", String(value));
  $("loading-overlay").hidden = !value;
  $("generate-button").querySelector(".button-label").textContent = value ? "Создаём карточку…" : "Создать карточку";
  $("generate-button").querySelector(".spinner").hidden = !value;
  $("generate-button").querySelector(".arrow-icon").hidden = value;
}

function markChanged() {
  setError();
  if (!currentCard || busy) return;
  $("result-badge").textContent = "Данные изменены";
  $("result-badge").classList.add("stale");
}

function fieldName(path) {
  const names = { name: "Название", manufacturer: "Производитель", description: "Описание", specs: "Характеристики" };
  return path.startsWith("specs.") ? path.slice(6) : names[path] || path;
}

function renderCard(card) {
  currentCard = card;
  $("empty-state").hidden = true;
  $("card-content").hidden = false;
  $("seo-title").textContent = card.seo_title;
  $("title-count").textContent = `${Array.from(card.seo_title).length} / 70`;
  $("seo-description").textContent = card.seo_description;
  $("description-count").textContent = `${Array.from(card.seo_description).length} символов`;
  $("commercial-block").textContent = card.commercial_block;
  $("json-output").textContent = JSON.stringify(card, null, 2);
  $("result-badge").textContent = "Готово";
  $("result-badge").hidden = false;
  $("result-badge").classList.remove("stale");
  $("json-tab").disabled = false;
  $("characteristics").replaceChildren();
  const entries = Object.entries(card.key_characteristics);
  for (const [key, value] of entries) {
    const row = document.createElement("div");
    row.className = "characteristic";
    const name = document.createElement("dt");
    name.textContent = key;
    const content = document.createElement("dd");
    content.textContent = value;
    row.append(name, content);
    $("characteristics").append(row);
  }
  if (!entries.length) {
    const message = document.createElement("div");
    message.className = "no-specs";
    message.textContent = "Данных нет";
    $("characteristics").append(message);
  }
  $("search-queries").replaceChildren();
  for (const query of card.search_queries) {
    const item = document.createElement("li");
    item.textContent = query;
    $("search-queries").append(item);
  }
  $("missing-fields").replaceChildren();
  for (const field of card.missing_fields) {
    const item = document.createElement("li");
    item.textContent = `${fieldName(field)} — данных нет`;
    $("missing-fields").append(item);
  }
  $("missing-section").hidden = !card.missing_fields.length;
  $("copy-button").disabled = busy;
}

function switchFormat(format) {
  currentFormat = format;
  for (const name of ["preview", "json"]) {
    const active = name === format;
    $(name + "-tab").classList.toggle("active", active);
    $(name + "-tab").setAttribute("aria-selected", String(active));
    $(name + "-tab").tabIndex = active ? 0 : -1;
    $(name + "-content").hidden = !active;
  }
}

function errorMessage(data) {
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((item) => `${item.loc.slice(1).map(String).join(" → ")}: ${item.msg}`).join("; ");
  }
  return data.detail?.message || "Не удалось создать карточку. Попробуйте позже.";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  let product;
  try { product = readProduct(); } catch (error) { setError(error.message); return; }
  setError();
  setBusy(true);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 75000);
  try {
    const response = await fetch("/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(product),
      signal: controller.signal,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(errorMessage(data));
    renderCard(data);
    if (window.matchMedia("(max-width: 760px)").matches) {
      $("result-panel").scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
    }
  } catch (error) {
    setError(error.name === "AbortError"
      ? "Время ожидания истекло. Проверьте доступность модели перед повторной попыткой."
      : error instanceof TypeError ? "Нет связи с сервером. Проверьте, что приложение запущено." : error.message);
  } finally {
    clearTimeout(timeout);
    setBusy(false);
  }
});

function markdown(card) {
  const specs = Object.entries(card.key_characteristics).map(([key, value]) => `- ${key}: ${value}`).join("\n") || "Данных нет";
  const missing = card.missing_fields.length ? `\n\n## Нужно уточнить\n${card.missing_fields.map((field) => `- ${fieldName(field)}: данных нет`).join("\n")}` : "";
  return `# ${card.seo_title}\n\n${card.seo_description}\n\n## Характеристики\n${specs}\n\n## Поисковые запросы\n${card.search_queries.map((query) => `- ${query}`).join("\n")}\n\n## Для менеджера\n${card.commercial_block}${missing}`;
}

async function copyText(text) {
  try {
    if (!navigator.clipboard) throw new Error("Clipboard unavailable");
    await navigator.clipboard.writeText(text);
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.append(textarea);
    textarea.select();
    try {
      if (!document.execCommand("copy")) throw new Error("Copy failed");
    } finally { textarea.remove(); $("copy-button").focus(); }
  }
}

$("copy-button").addEventListener("click", async () => {
  if (!currentCard || busy) return;
  try {
    await copyText(currentFormat === "json" ? JSON.stringify(currentCard, null, 2) : markdown(currentCard));
    $("toast").textContent = currentFormat === "json" ? "JSON скопирован" : "Карточка скопирована в Markdown";
  } catch { $("toast").textContent = "Не удалось скопировать. Откройте JSON и скопируйте текст вручную."; }
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 3500);
});

$("add-spec").addEventListener("click", () => { addSpec().focus(); markChanged(); });
form.addEventListener("input", markChanged);
$("clear-button").addEventListener("click", () => {
  if (busy) return;
  clearForm();
  markChanged();
  $("product-name").focus();
});
for (const name of ["preview", "json"]) {
  const tab = $(name + "-tab");
  tab.addEventListener("click", () => switchFormat(name));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? "preview" : event.key === "End" ? "json" : currentFormat === "preview" ? "json" : "preview";
    if ($(next + "-tab").disabled) return;
    switchFormat(next);
    $(next + "-tab").focus();
  });
}
addSpec();
