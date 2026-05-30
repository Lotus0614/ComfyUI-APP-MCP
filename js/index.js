/**
 * ComfyUI MCP Server — Frontend Settings Panel
 *
 * Settings panel with:
 * - MCP Server status
 * - Template management (create, delete)
 */

import { app } from "../../../scripts/app.js";

function getApiBase() {
    const scriptUrl = import.meta.url;
    const url = new URL(scriptUrl);
    const pathParts = url.pathname.split("/");
    const jsIdx = pathParts.indexOf("js");
    if (jsIdx > 0) return `/${pathParts[jsIdx - 1]}/api`;
    return "/mcp-server/api";
}

const API = getApiBase();

async function apiFetch(path, options = {}) {
    const resp = await fetch(`${API}${path}`, {
        headers: { "Content-Type": "application/json" },
        ...options,
    });
    return resp.json();
}

// ── Styles ────────────────────────────────────────────────

const S = {
    row: "display:flex;align-items:center;gap:8px;padding:4px 8px;border:1px solid #333;border-radius:4px;",
    btn: "padding:4px 12px;cursor:pointer;",
    btnRow: "display:flex;gap:8px;margin-top:4px;",
    label: "flex:1;font-size:13px;",
    section: "font-size:12px;color:#aaa;margin:8px 0 4px;font-weight:bold;",
};

// ── Template management widget ────────────────────────────

function createTemplateWidget() {
    const container = document.createElement("div");
    container.style.cssText = "display:flex;flex-direction:column;gap:8px;max-height:500px;overflow-y:auto;padding:4px 0;";

    const listEl = document.createElement("div");
    listEl.style.cssText = "display:flex;flex-direction:column;gap:4px;";
    container.appendChild(listEl);

    const btnRow = document.createElement("div");
    btnRow.style.cssText = S.btnRow;

    const refreshBtn = document.createElement("button");
    refreshBtn.textContent = "Refresh";
    refreshBtn.style.cssText = S.btn;

    const createBtn = document.createElement("button");
    createBtn.textContent = "Create from Workflow";
    createBtn.style.cssText = S.btn;

    btnRow.append(refreshBtn, createBtn);
    container.appendChild(btnRow);

    async function loadTemplates() {
        listEl.innerHTML = "Loading...";
        try {
            const data = await apiFetch("/templates");
            listEl.innerHTML = "";
            if (!data.templates?.length) {
                listEl.innerHTML = '<div style="color:#888;font-size:12px;">No templates yet. Click "Create from Workflow" to create one.</div>';
                return;
            }
            for (const t of data.templates) {
                const row = document.createElement("div");
                row.style.cssText = S.row;

                const nameEl = document.createElement("span");
                nameEl.textContent = t.name;
                nameEl.style.cssText = "font-size:13px;font-weight:bold;";

                const infoEl = document.createElement("span");
                infoEl.textContent = `${t.input_count} in / ${t.output_count} out`;
                infoEl.style.cssText = "font-size:11px;color:#888;";

                const descEl = document.createElement("span");
                descEl.textContent = t.description || "";
                descEl.style.cssText = "font-size:11px;color:#666;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;";
                descEl.title = t.description || "";

                const viewBtn = document.createElement("button");
                viewBtn.textContent = "Details";
                viewBtn.style.cssText = "padding:2px 8px;cursor:pointer;font-size:11px;";
                viewBtn.addEventListener("click", () => showTemplateDetail(t.name));

                const refreshBtn = document.createElement("button");
                refreshBtn.textContent = "Refresh";
                refreshBtn.style.cssText = "padding:2px 8px;cursor:pointer;font-size:11px;";
                refreshBtn.addEventListener("click", async () => {
                    refreshBtn.textContent = "...";
                    refreshBtn.disabled = true;
                    try {
                        const wfContent = await apiFetch(`/workflows/${t.name}`);
                        const info = await apiFetch("/templates/extract", {
                            method: "POST",
                            body: JSON.stringify({ workflow: wfContent }),
                        });
                        await apiFetch(`/templates/${t.name}`, {
                            method: "PUT",
                            body: JSON.stringify({
                                workflow: wfContent,
                                inputs: info.inputs,
                                outputs: info.outputs,
                                description: info.description,
                            }),
                        });
                        loadTemplates();
                    } catch (e) {
                        alert(`Refresh failed: ${e.message}`);
                        refreshBtn.textContent = "Refresh";
                        refreshBtn.disabled = false;
                    }
                });

                const delBtn = document.createElement("button");
                delBtn.textContent = "Delete";
                delBtn.style.cssText = "padding:2px 8px;cursor:pointer;font-size:11px;color:#f66;";
                delBtn.addEventListener("click", async () => {
                    if (confirm(`Delete template "${t.name}"?`)) {
                        await apiFetch(`/templates/${t.name}`, { method: "DELETE" });
                        loadTemplates();
                    }
                });

                row.append(nameEl, infoEl, descEl, viewBtn, refreshBtn, delBtn);
                listEl.appendChild(row);
            }
        } catch (e) {
            listEl.innerHTML = `<div style="color:#f66;font-size:12px;">Error: ${e.message}</div>`;
        }
    }

    refreshBtn.addEventListener("click", loadTemplates);
    createBtn.addEventListener("click", () => showCreateTemplateDialog(loadTemplates));

    loadTemplates();
    return container;
}

// ── Template detail dialog ────────────────────────────────

async function showTemplateDetail(name) {
    const template = await apiFetch(`/templates/${name}`);
    if (template.error) return alert(template.error);

    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;";

    const modal = document.createElement("div");
    modal.style.cssText = "background:#1e1e1e;border:1px solid #444;border-radius:8px;padding:16px;min-width:500px;max-width:700px;max-height:80vh;overflow-y:auto;color:#ddd;";

    let html = `<h3 style="margin:0 0 8px;">${template.name}</h3>`;
    if (template.description) html += `<p style="color:#aaa;font-size:12px;margin:0 0 12px;">${template.description}</p>`;

    html += `<div style="${S.section}">Inputs (parameters):</div>`;
    const inputs = template.inputs || {};
    if (Object.keys(inputs).length) {
        for (const [k, v] of Object.entries(inputs)) {
            html += `<div style="${S.row}margin:2px 0;"><span style="${S.label}">${k}</span><span style="font-size:11px;color:#888;">${v.type} | node ${v.node_id} → ${v.widget}</span></div>`;
        }
    } else {
        html += '<div style="color:#888;font-size:12px;">No inputs configured</div>';
    }

    html += `<div style="${S.section}">Outputs:</div>`;
    const outputs = template.outputs || {};
    if (Object.keys(outputs).length) {
        for (const [k, v] of Object.entries(outputs)) {
            html += `<div style="${S.row}margin:2px 0;"><span style="${S.label}">${k}</span><span style="font-size:11px;color:#888;">${v.comfy_type || v.type} | node ${v.node_id}</span></div>`;
        }
    } else {
        html += '<div style="color:#888;font-size:12px;">No outputs configured</div>';
    }

    html += `<div style="display:flex;gap:8px;margin-top:12px;"><button id="mcp-close" style="${S.btn}">Close</button></div>`;

    modal.innerHTML = html;
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
    modal.querySelector("#mcp-close").addEventListener("click", () => overlay.remove());
}

// ── Create template dialog ────────────────────────────────

async function showCreateTemplateDialog(onDone) {
    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;";

    const modal = document.createElement("div");
    modal.style.cssText = "background:#1e1e1e;border:1px solid #444;border-radius:8px;padding:16px;min-width:500px;max-width:700px;max-height:80vh;overflow-y:auto;color:#ddd;";

    modal.innerHTML = `
        <h3 style="margin:0 0 12px;">Create Template from Workflow</h3>
        <div style="margin-bottom:8px;">
            <label style="font-size:12px;color:#aaa;">Workflow:</label>
            <div style="display:flex;gap:8px;margin-top:4px;">
                <select id="mcp-wf-select" style="flex:1;padding:4px;background:#2a2a2a;color:#ddd;border:1px solid #444;border-radius:4px;">
                    <option value="">-- Select a workflow --</option>
                </select>
                <button id="mcp-wf-refresh" style="${S.btn}font-size:11px;">Refresh</button>
            </div>
        </div>
        <div id="mcp-preview" style="margin:8px 0;font-size:12px;color:#aaa;"></div>
        <div style="display:flex;gap:8px;margin-top:12px;">
            <button id="mcp-save" style="${S.btn}background:#2d5a2d;color:#8f8;" disabled>Create Template</button>
            <button id="mcp-cancel" style="${S.btn}">Cancel</button>
        </div>
    `;

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    const select = modal.querySelector("#mcp-wf-select");
    const preview = modal.querySelector("#mcp-preview");
    const saveBtn = modal.querySelector("#mcp-save");
    const cancelBtn = modal.querySelector("#mcp-cancel");
    const refreshBtn = modal.querySelector("#mcp-wf-refresh");

    let extractedInfo = null;

    async function loadWorkflows() {
        const prev = select.value;
        select.innerHTML = '<option value="">-- Loading... --</option>';
        try {
            const wfData = await apiFetch("/workflows");
            const workflows = wfData.workflows || [];
            select.innerHTML = '<option value="">-- Select a workflow --</option>';
            for (const w of workflows) {
                const opt = document.createElement("option");
                opt.value = w.name;
                opt.textContent = w.name;
                select.appendChild(opt);
            }
            if (prev) select.value = prev;
        } catch (e) {
            select.innerHTML = '<option value="">-- Error loading workflows --</option>';
        }
    }

    refreshBtn.addEventListener("click", loadWorkflows);

    select.addEventListener("change", async () => {
        const name = select.value;
        if (!name) {
            preview.innerHTML = "";
            saveBtn.disabled = true;
            return;
        }
        preview.innerHTML = "Analyzing workflow...";
        try {
            const wfContent = await apiFetch(`/workflows/${name}`);
            const info = await apiFetch("/templates/extract", {
                method: "POST",
                body: JSON.stringify({ workflow: wfContent }),
            });
            extractedInfo = info;

            let html = "";
            if (info.description) html += `<div style="margin-bottom:4px;"><b>Description:</b> ${info.description}</div>`;
            const inputKeys = Object.keys(info.inputs || {});
            html += `<div><b>Auto-detected inputs (${inputKeys.length}):</b> ${inputKeys.join(", ") || "none"}</div>`;
            const outputEntries = Object.entries(info.outputs || {});
            if (outputEntries.length) {
                html += `<div><b>Auto-detected outputs (${outputEntries.length}):</b></div>`;
                for (const [oname, def] of outputEntries) {
                    html += `<div style="padding-left:12px;color:#8f8;">${oname} <span style="color:#888;">(${def.comfy_type || def.type})</span></div>`;
                }
            } else {
                html += `<div><b>Auto-detected outputs:</b> none</div>`;
            }
            preview.innerHTML = html;

            saveBtn.disabled = false;
        } catch (e) {
            preview.innerHTML = `<span style="color:#f66;">Error: ${e.message}</span>`;
        }
    });

    saveBtn.addEventListener("click", async () => {
        const wfName = select.value;
        if (!wfName) return;

        saveBtn.disabled = true;
        saveBtn.textContent = "Creating...";

        try {
            const wfContent = await apiFetch(`/workflows/${wfName}`);
            await apiFetch("/templates", {
                method: "POST",
                body: JSON.stringify({
                    name: wfName,
                    workflow: wfContent,
                }),
            });

            overlay.remove();
            if (onDone) onDone();
        } catch (e) {
            alert(`Failed to create template: ${e.message}`);
            saveBtn.disabled = false;
            saveBtn.textContent = "Create Template";
        }
    });

    cancelBtn.addEventListener("click", () => overlay.remove());
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });

    // Load workflows on open
    loadWorkflows();
}

// ── Register extension ────────────────────────────────────

app.registerExtension({
    name: "ComfyUI.MCPServer",

    settings: [
        {
            id: "MCPServer.Status",
            name: "MCP Server Status",
            category: ["MCP Server", "Status"],
            type: () => {
                const el = document.createElement("div");
                el.style.cssText = "font-size:12px;color:#aaa;padding:4px 0;";
                apiFetch("/status").then((d) => {
                    el.textContent = `MCP endpoint: ${d.mcp_url}`;
                }).catch(() => { el.textContent = "MCP server not reachable"; });
                return el;
            },
        },
        {
            id: "MCPServer.Templates",
            name: "Templates",
            category: ["MCP Server", "Templates"],
            tooltip: "Create and manage MCP templates from workflows",
            type: () => createTemplateWidget(),
        },
    ],
});
