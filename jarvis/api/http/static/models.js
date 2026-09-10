"use strict";
const $ = id => document.getElementById(id);
let token = "", current = null, reset = false, busy = false;
const titles = {answer: "回答", reflection: "反思评分", agent_dispatch: "Agent 分派"};
const message = (text, error = false) => { $("status").textContent = text; $("status").className = error ? "error" : ""; };
function setBusy(value) {
  busy = value;
  document.querySelectorAll("button, input, select").forEach(el => { el.disabled = value; });
  if (!value) changed();
}
async function api(path, options = {}) {
  const response = await fetch(path, {...options, cache: "no-store", headers: {
    Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...options.headers
  }});
  const data = await response.json();
  if (!response.ok) {
    const errors = {401: "管理员 Token 无效，请重新登录。", 409: "配置已被更新，请重新加载后再保存。",
      503: "服务不可用，请检查管理员配置或配置数据库。", 502: "模型列表获取失败，可手动填写模型 ID。"};
    throw new Error(errors[response.status] || (typeof data.detail === "string" ? data.detail : "配置格式有误，请检查输入。"));
  }
  return data;
}
function selected() {
  return Object.fromEntries([...document.querySelectorAll(".profile")].map(row => [row.dataset.profile,
    `${row.querySelector("select").value}/${row.querySelector("input").value.trim()}`]));
}
function changed() {
  if (!current || busy) return;
  const values = selected();
  const dirty = reset || Object.entries(values).some(([key, value]) => value !== current.profiles[key].model);
  $("dirty").textContent = dirty ? "有未保存的修改" : "";
  $("save").disabled = !dirty;
}
function element(tag, text, className) {
  const el = document.createElement(tag);
  if (text) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function render() {
  $("profiles").replaceChildren();
  Object.entries(current.profiles).forEach(([name, profile], index) => {
    const row = element("section", null, "profile"); row.dataset.profile = name;
    const info = element("div"); info.append(element("h3", titles[name] || name), element("code", name));
    const badges = element("div", null, "badges");
    badges.append(element("span", profile.thinking === "enabled" ? "深度思考" : "非思考模式", "badge"));
    if (profile.tools === "enabled") badges.append(element("span", "工具调用", "badge"));
    info.append(badges);
    const fields = element("div", null, "fields");
    const providerField = element("div"), modelField = element("div");
    const provider = element("select"); provider.id = `provider-${index}`;
    for (const [id, capability] of Object.entries(current.providers)) {
      const option = element("option", id); option.value = id;
      option.disabled = (profile.tools === "enabled" && !capability.tools) || (profile.thinking === "enabled" && !capability.thinking);
      provider.append(option);
    }
    const slash = profile.model.indexOf("/"); provider.value = profile.model.slice(0, slash);
    const model = element("input"); model.id = `model-${index}`; model.value = profile.model.slice(slash + 1);
    model.required = true; model.maxLength = 160; model.pattern = "[A-Za-z0-9_.:/\\-]+";
    const choices = element("datalist"); choices.id = `choices-${index}`; model.setAttribute("list", choices.id);
    const pLabel = element("label", "供应商"); pLabel.htmlFor = provider.id;
    const mLabel = element("label", "模型 ID"); mLabel.htmlFor = model.id;
    providerField.append(pLabel, provider);
    const actions = element("div", null, "model-actions");
    const fetchButton = element("button", "获取模型列表"); fetchButton.type = "button";
    const note = element("div", null, "catalog-status"); note.setAttribute("role", "status");
    actions.append(element("span", `默认：${profile.default_model}`, "default"), fetchButton);
    fetchButton.addEventListener("click", async () => {
      const id = provider.value; fetchButton.disabled = true; note.textContent = "正在获取…"; note.classList.remove("error");
      try {
        const result = await api(`/admin/api/providers/${encodeURIComponent(id)}/models`);
        if (id !== provider.value) return;
        choices.replaceChildren(...result.models.map(value => { const o = element("option"); o.value = value; return o; }));
        note.textContent = result.models.length ? `可用模型：${result.models.length}` : "未返回模型，可手动填写。";
      } catch (error) { note.textContent = error.message; note.classList.add("error"); }
      finally { fetchButton.disabled = busy; }
    });
    provider.addEventListener("change", () => { model.value = ""; choices.replaceChildren(); note.textContent = ""; reset = false; changed(); });
    model.addEventListener("input", () => { reset = false; changed(); });
    modelField.append(mLabel, model, choices, actions, note); fields.append(providerField, modelField);
    row.append(info, fields); $("profiles").append(row);
  });
  $("version").textContent = `配置版本 ${current.revision}`;
  $("login").hidden = true; $("editor").hidden = false; $("logout").hidden = false;
  changed();
}
async function load() {
  setBusy(true); message("正在读取配置…");
  try { current = await api("/admin/api/models"); reset = false; render(); message("配置已加载"); }
  catch (error) { message(error.message, true); }
  finally { setBusy(false); }
}
$("login-form").addEventListener("submit", event => { event.preventDefault(); token = $("token").value; $("token").value = ""; load(); });
$("logout").addEventListener("click", () => { token = ""; current = null; $("profiles").replaceChildren(); $("editor").hidden = true; $("logout").hidden = true; $("login").hidden = false; $("version").textContent = "未连接"; message(""); });
$("reload").addEventListener("click", () => { if (!$("save").disabled && !confirm("放弃未保存的修改？")) return; load(); });
$("defaults").addEventListener("click", () => {
  document.querySelectorAll(".profile").forEach(row => {
    const spec = current.profiles[row.dataset.profile].default_model, slash = spec.indexOf("/");
    row.querySelector("select").value = spec.slice(0, slash); row.querySelector("input").value = spec.slice(slash + 1);
  }); reset = true; changed(); message("默认值已填入，保存后生效。");
});
$("editor").addEventListener("submit", async event => {
  event.preventDefault(); const models = reset ? {} : selected(); setBusy(true); message("正在保存…");
  try {
    current = await api("/admin/api/models", {method: "PUT", body: JSON.stringify({revision: current.revision, config_version: current.config_version, models})});
    reset = false; render(); message("已保存，新对话使用新配置。");
  } catch (error) { message(error.message, true); }
  finally { setBusy(false); }
});
window.addEventListener("beforeunload", event => { if (current && !$("save").disabled) { event.preventDefault(); event.returnValue = ""; } });
