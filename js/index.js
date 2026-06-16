/**
 * ComfyUI MCP Server — Frontend Settings Panel
 *
 * Settings panel with:
 * - MCP Server status
 * - Template management (create, delete)
 */

import { app } from '../../../scripts/app.js';
import { api } from '../../../scripts/api.js';

const I18N = {
    en: {
        refresh: 'Refresh',
        createFromWorkflow: 'Create from Workflow',
        autoExtractTemplates: 'Auto Extract Templates',
        batchRefreshTemplates: 'Batch Refresh Templates',
        exportTemplates: 'Export Templates',
        details: 'Details',
        enable: 'Enable',
        disable: 'Disable',
        delete: 'Delete',
        close: 'Close',
        cancel: 'Cancel',
        createTemplate: 'Create Template',
        working: 'Working...',
        exporting: 'Exporting...',
        loading: 'Loading...',
        noTemplates:
            'No templates yet. Click "Create from Workflow" to create one.',
        templateCounts: '{inputs} in / {outputs} out',
        disabled: 'disabled',
        updateFailed: 'Update failed: {message}',
        refreshFailed: 'Refresh failed: {message}',
        deleteConfirm: 'Delete template "{name}"?',
        error: 'Error: {message}',
        scanningWorkflows:
            'Scanning workflows and creating missing templates...',
        generatingApiPrompts: 'Generating API prompts for {count} templates...',
        autoExtractComplete:
            'Auto extract complete: {created} created, {skipped} skipped, {failed} failed.',
        generatedApiPrompts: ' Generated API prompts for {count} templates.',
        autoExtractFailed: 'Auto extract failed: {message}',
        refreshingTemplates:
            'Refreshing all existing templates from workflows...',
        batchRefreshComplete:
            'Batch refresh complete: {refreshed} refreshed, {skipped} skipped, {failed} failed.',
        batchRefreshFailed: 'Batch refresh failed: {message}',
        exportFailed: 'Export failed: {message}',
        inputsParameters: 'Inputs (parameters):',
        noInputsConfigured: 'No inputs configured',
        outputs: 'Outputs:',
        noOutputsConfigured: 'No outputs configured',
        createTemplateFromWorkflow: 'Create Template from Workflow',
        workflow: 'Workflow:',
        searchWorkflows: 'Search workflows...',
        noMatchingWorkflows: 'No matching workflows',
        noWorkflowsFound: 'No workflows found',
        errorLoadingWorkflows: 'Error loading workflows',
        analyzingWorkflow: 'Analyzing workflow...',
        description: 'Description:',
        autoDetectedInputs: 'Auto-detected inputs ({count}):',
        autoDetectedOutputs: 'Auto-detected outputs',
        none: 'none',
        failedCreateTemplate: 'Failed to create template: {message}',
        mcpEndpoint: 'MCP endpoint: {url}',
        mcpNotReachable: 'MCP server not reachable',
        statusSetting: 'MCP Server Status',
        templatesSetting: 'Templates',
        statusCategory: 'Status',
        templatesCategory: 'Templates',
        templatesTooltip: 'Create and manage MCP templates from workflows',
        nodeLabel: 'node',
        defaultLabel: 'default',
        creating: 'Creating...',
    },
    zh: {
        refresh: '刷新',
        createFromWorkflow: '从工作流创建',
        autoExtractTemplates: '自动提取模板',
        batchRefreshTemplates: '批量刷新模板',
        exportTemplates: '导出模板',
        details: '详情',
        enable: '启用',
        disable: '禁用',
        delete: '删除',
        close: '关闭',
        cancel: '取消',
        createTemplate: '创建模板',
        working: '处理中...',
        exporting: '导出中...',
        loading: '加载中...',
        noTemplates: '暂无模板。点击“从工作流创建”来创建模板。',
        templateCounts: '{inputs} 输入 / {outputs} 输出',
        disabled: '已禁用',
        updateFailed: '更新失败：{message}',
        refreshFailed: '刷新失败：{message}',
        deleteConfirm: '删除模板“{name}”？',
        error: '错误：{message}',
        scanningWorkflows: '正在扫描工作流并创建缺失模板...',
        generatingApiPrompts: '正在为 {count} 个模板生成 API Prompt...',
        autoExtractComplete:
            '自动提取完成：创建 {created} 个，跳过 {skipped} 个，失败 {failed} 个。',
        generatedApiPrompts: ' 已为 {count} 个模板生成 API Prompt。',
        autoExtractFailed: '自动提取失败：{message}',
        refreshingTemplates: '正在从工作流批量刷新已有模板...',
        batchRefreshComplete:
            '批量刷新完成：刷新 {refreshed} 个，跳过 {skipped} 个，失败 {failed} 个。',
        batchRefreshFailed: '批量刷新失败：{message}',
        exportFailed: '导出失败：{message}',
        inputsParameters: '输入（参数）：',
        noInputsConfigured: '未配置输入',
        outputs: '输出：',
        noOutputsConfigured: '未配置输出',
        createTemplateFromWorkflow: '从工作流创建模板',
        workflow: '工作流：',
        searchWorkflows: '搜索工作流...',
        noMatchingWorkflows: '没有匹配的工作流',
        noWorkflowsFound: '未找到工作流',
        errorLoadingWorkflows: '加载工作流失败',
        analyzingWorkflow: '正在分析工作流...',
        description: '描述：',
        autoDetectedInputs: '自动检测到的输入（{count}）：',
        autoDetectedOutputs: '自动检测到的输出',
        none: '无',
        failedCreateTemplate: '创建模板失败：{message}',
        mcpEndpoint: 'MCP 端点：{url}',
        mcpNotReachable: '无法连接 MCP 服务',
        statusSetting: 'MCP 服务状态',
        templatesSetting: '模板',
        statusCategory: '状态',
        templatesCategory: '模板',
        templatesTooltip: '从工作流创建和管理 MCP 模板',
        nodeLabel: '节点',
        defaultLabel: '默认值',
        creating: '创建中...',
    },
};

const I18N_NAMESPACE = 'comfyuiMcpServer';
let comfyI18n = null;

try {
    const i18nModule = await import('../../../scripts/i18n.js');
    if (i18nModule.i18n?.global?.mergeLocaleMessage) {
        const comfyMessages = {
            en: I18N.en,
            'en-US': I18N.en,
            zh: I18N.zh,
            'zh-CN': I18N.zh,
        };
        for (const [language, messages] of Object.entries(comfyMessages)) {
            i18nModule.i18n.global.mergeLocaleMessage(language, {
                [I18N_NAMESPACE]: messages,
            });
        }
        comfyI18n = i18nModule;
    }
} catch {
    // Older ComfyUI builds do not expose the native i18n module to extensions.
}

function normalizeLocale(locale) {
    return String(locale || '')
        .toLowerCase()
        .startsWith('zh')
        ? 'zh'
        : 'en';
}

let locale = normalizeLocale(navigator.language);

try {
    locale = normalizeLocale(await api.getSetting('Comfy.Locale'));
} catch (e) {
    console.warn('[MCP] Failed to read Comfy.Locale, using browser locale:', e);
}

function formatMessage(value, params = {}) {
    return value.replace(/\{(\w+)\}/g, (_, name) =>
        params[name] === undefined ? `{${name}}` : String(params[name]),
    );
}

function t(key, params = {}) {
    const value = I18N[locale]?.[key] ?? I18N.en[key] ?? key;
    const comfyKey = `${I18N_NAMESPACE}.${key}`;
    if (comfyI18n?.te?.(comfyKey)) {
        return String(comfyI18n.t(comfyKey, params));
    }
    return formatMessage(value, params);
}

async function updateLocale() {
    try {
        const nextLocale = normalizeLocale(
            await api.getSetting('Comfy.Locale'),
        );
        if (nextLocale !== locale) {
            locale = nextLocale;
            return true;
        }
    } catch (e) {
        console.warn('[MCP] Failed to refresh Comfy.Locale:', e);
    }
    return false;
}

function getApiBase() {
    const scriptUrl = import.meta.url;
    const url = new URL(scriptUrl);
    const pathParts = url.pathname.split('/');
    const jsIdx = pathParts.indexOf('js');
    if (jsIdx > 0) return `/${pathParts[jsIdx - 1]}/api`;
    return '/mcp-server/api';
}
const API = getApiBase();

async function apiFetch(path, options = {}) {
    const resp = await fetch(`${API}${path}`, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    const text = await resp.text();
    if (!resp.ok) throw new Error(`API error (${resp.status}): ${text}`);
    try {
        return JSON.parse(text);
    } catch (e) {
        throw new Error(`Invalid JSON response: ${text.slice(0, 200)}`);
    }
}

const waitForGraphNodes = async (timeoutMs = 1000) => {
    const waitFrame = () =>
        new Promise((resolve) => requestAnimationFrame(resolve));

    const start = performance.now();
    while (performance.now() - start < timeoutMs) {
        if (app.graph._nodes?.length) return;
        await waitFrame();
    }
    throw new Error('Failed to load workflow into graph');
};

/**
 * Generate API prompt from workflow using frontend's graphToPrompt.
 * Uses app.graph.configure() to avoid opening a new tab.
 */
async function generateApiPrompt(workflow) {
    // Save current graph state
    const originalGraph = app.graph.serialize();

    try {
        // Configure graph directly (no tab opening)
        app.graph.configure(workflow);

        await waitForGraphNodes();

        // Use frontend's graphToPrompt to generate API format
        const { output } = await app.graphToPrompt();
        if (!output || Object.keys(output).length === 0) {
            throw new Error('graphToPrompt returned empty output');
        }
        return output;
    } finally {
        // Restore original graph
        app.graph.configure(JSON.parse(JSON.stringify(originalGraph)));
    }
}

async function downloadFile(path, filename) {
    const resp = await fetch(`${API}${path}`);
    const text = resp.ok ? null : await resp.text();
    if (!resp.ok) throw new Error(`API error (${resp.status}): ${text}`);
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

// ── Styles ────────────────────────────────────────────────

const S = {
    row: 'display:flex;align-items:center;gap:12px;padding:8px 10px;border:1px solid #333;border-radius:6px;background:#202020;min-width:0;flex-wrap:wrap;',
    detailRow:
        'display:flex;align-items:flex-start;gap:10px;padding:6px 8px;border:1px solid #333;border-radius:6px;background:#202020;margin:4px 0;',
    btn: 'padding:5px 12px;min-height:28px;cursor:pointer;border-radius:4px;',
    smallBtn:
        'padding:3px 8px;min-height:24px;cursor:pointer;font-size:11px;border-radius:4px;white-space:nowrap;',
    btnRow: 'display:flex;flex-wrap:wrap;gap:6px;margin-top:2px;',
    label: 'flex:1;min-width:0;font-size:13px;line-height:1.35;overflow-wrap:anywhere;',
    section: 'font-size:12px;color:#aaa;margin:14px 0 6px;font-weight:bold;',
};

// ── Template management widget ────────────────────────────

function createTemplateWidget() {
    updateLocale().then((changed) => {
        if (changed) refreshTexts();
    });

    const container = document.createElement('div');
    container.style.cssText =
        'display:flex;flex-direction:column;gap:10px;max-height:520px;overflow-y:auto;padding:6px 2px;';

    const listEl = document.createElement('div');
    listEl.style.cssText = 'display:flex;flex-direction:column;gap:6px;';
    container.appendChild(listEl);

    const actionInfoEl = document.createElement('div');
    actionInfoEl.style.cssText =
        'font-size:12px;color:#888;min-height:18px;line-height:1.4;';
    container.appendChild(actionInfoEl);

    const btnRow = document.createElement('div');
    btnRow.style.cssText = S.btnRow;

    const refreshBtn = document.createElement('button');
    refreshBtn.textContent = t('refresh');
    refreshBtn.style.cssText = S.btn;

    const createBtn = document.createElement('button');
    createBtn.textContent = t('createFromWorkflow');
    createBtn.style.cssText = S.btn;

    const autoCreateBtn = document.createElement('button');
    autoCreateBtn.textContent = t('autoExtractTemplates');
    autoCreateBtn.style.cssText = S.btn;

    const batchRefreshBtn = document.createElement('button');
    batchRefreshBtn.textContent = t('batchRefreshTemplates');
    batchRefreshBtn.style.cssText = S.btn;

    const exportBtn = document.createElement('button');
    exportBtn.textContent = t('exportTemplates');
    exportBtn.style.cssText = S.btn;

    btnRow.append(
        refreshBtn,
        createBtn,
        autoCreateBtn,
        batchRefreshBtn,
        exportBtn,
    );
    container.appendChild(btnRow);

    function refreshTexts() {
        refreshBtn.textContent = t('refresh');
        createBtn.textContent = t('createFromWorkflow');
        autoCreateBtn.textContent = t('autoExtractTemplates');
        batchRefreshBtn.textContent = t('batchRefreshTemplates');
        exportBtn.textContent = t('exportTemplates');
        loadTemplates();
    }

    function setActionInfo(text, isError = false) {
        actionInfoEl.textContent = text;
        actionInfoEl.style.color = isError ? '#f66' : '#888';
    }

    async function loadTemplates() {
        listEl.innerHTML = t('loading');
        try {
            const data = await apiFetch('/templates?include_disabled=1');
            listEl.innerHTML = '';
            if (!data.templates?.length) {
                listEl.innerHTML = `<div style="color:#888;font-size:12px;padding:8px 2px;">${t('noTemplates')}</div>`;
                return;
            }
            for (const template of data.templates) {
                const row = document.createElement('div');
                row.style.cssText = S.row;

                const bodyEl = document.createElement('div');
                bodyEl.style.cssText =
                    'display:flex;flex-direction:column;gap:3px;flex:1;min-width:0;';

                const nameEl = document.createElement('span');
                nameEl.textContent = template.name;
                nameEl.style.cssText = `font-size:13px;font-weight:bold;line-height:1.35;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;${template.disabled ? 'color:#888;text-decoration:line-through;' : ''}`;
                nameEl.title = template.name;

                const metaEl = document.createElement('div');
                metaEl.style.cssText =
                    'display:flex;align-items:center;gap:8px;min-width:0;';

                const infoEl = document.createElement('span');
                infoEl.textContent = `${t('templateCounts', { inputs: template.input_count, outputs: template.output_count })}${template.disabled ? ` | ${t('disabled')}` : ''}`;
                infoEl.style.cssText = `font-size:11px;color:${template.disabled ? '#b66' : '#888'};`;

                const descEl = document.createElement('span');
                descEl.textContent = template.description || '';
                descEl.style.cssText =
                    'font-size:11px;color:#666;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
                descEl.title = template.description || '';

                metaEl.append(infoEl, descEl);
                bodyEl.append(nameEl, metaEl);

                const actionEl = document.createElement('div');
                actionEl.style.cssText =
                    'display:flex;align-items:center;justify-content:flex-end;gap:4px;flex-wrap:wrap;margin-left:auto;';

                const viewBtn = document.createElement('button');
                viewBtn.textContent = t('details');
                viewBtn.style.cssText = S.smallBtn;
                viewBtn.addEventListener('click', () =>
                    showTemplateDetail(template.name),
                );

                const toggleBtn = document.createElement('button');
                toggleBtn.textContent = template.disabled
                    ? t('enable')
                    : t('disable');
                toggleBtn.style.cssText = `${S.smallBtn}${template.disabled ? 'color:#6d6;' : 'color:#fb6;'}`;
                toggleBtn.addEventListener('click', async () => {
                    toggleBtn.textContent = '...';
                    toggleBtn.disabled = true;
                    try {
                        await apiFetch(`/templates/${template.name}`, {
                            method: 'PUT',
                            body: JSON.stringify({
                                disabled: !template.disabled,
                            }),
                        });
                        loadTemplates();
                    } catch (e) {
                        alert(t('updateFailed', { message: e.message }));
                        toggleBtn.textContent = template.disabled
                            ? t('enable')
                            : t('disable');
                        toggleBtn.disabled = false;
                    }
                });

                const refreshBtn = document.createElement('button');
                refreshBtn.textContent = t('refresh');
                refreshBtn.style.cssText = S.smallBtn;
                refreshBtn.addEventListener('click', async () => {
                    refreshBtn.textContent = '...';
                    refreshBtn.disabled = true;
                    try {
                        const wfContent = await apiFetch(
                            `/workflows/${template.name}`,
                        );

                        // Generate API prompt
                        let apiPrompt = null;
                        try {
                            apiPrompt = await generateApiPrompt(wfContent);
                        } catch (e) {
                            console.warn(
                                '[MCP] Failed to generate API prompt during refresh:',
                                e,
                            );
                        }

                        const info = await apiFetch('/templates/extract', {
                            method: 'POST',
                            body: JSON.stringify({ workflow: wfContent }),
                        });
                        await apiFetch(`/templates/${template.name}`, {
                            method: 'PUT',
                            body: JSON.stringify({
                                workflow: wfContent,
                                api_prompt: apiPrompt,
                                inputs: info.inputs,
                                outputs: info.outputs,
                                description: info.description,
                            }),
                        });
                        loadTemplates();
                    } catch (e) {
                        alert(t('refreshFailed', { message: e.message }));
                        refreshBtn.textContent = t('refresh');
                        refreshBtn.disabled = false;
                    }
                });

                const delBtn = document.createElement('button');
                delBtn.textContent = t('delete');
                delBtn.style.cssText = `${S.smallBtn}color:#f66;`;
                delBtn.addEventListener('click', async () => {
                    if (confirm(t('deleteConfirm', { name: template.name }))) {
                        await apiFetch(`/templates/${template.name}`, {
                            method: 'DELETE',
                        });
                        loadTemplates();
                    }
                });

                actionEl.append(viewBtn, refreshBtn, toggleBtn, delBtn);
                row.append(bodyEl, actionEl);
                listEl.appendChild(row);
            }
        } catch (e) {
            listEl.innerHTML = `<div style="color:#f66;font-size:12px;">${t('error', { message: e.message })}</div>`;
        }
    }

    refreshBtn.addEventListener('click', loadTemplates);
    createBtn.addEventListener('click', () =>
        showCreateTemplateDialog(loadTemplates),
    );
    autoCreateBtn.addEventListener('click', async () => {
        autoCreateBtn.disabled = true;
        autoCreateBtn.textContent = t('working');
        setActionInfo(t('scanningWorkflows'));
        try {
            const result = await apiFetch('/templates/auto-create', {
                method: 'POST',
            });
            const created = result.created?.length || 0;
            const skipped = result.skipped?.length || 0;
            const failed = result.failed?.length || 0;
            const needsApiPrompt = result.needs_api_prompt || [];

            // Generate api_prompt for newly created templates
            let apiPromptGenerated = 0;
            if (needsApiPrompt.length > 0) {
                setActionInfo(
                    t('generatingApiPrompts', {
                        count: needsApiPrompt.length,
                    }),
                );
                for (const name of needsApiPrompt) {
                    try {
                        const wfContent = await apiFetch(`/workflows/${name}`);
                        const apiPrompt = await generateApiPrompt(wfContent);
                        await apiFetch(`/templates/${name}`, {
                            method: 'PUT',
                            body: JSON.stringify({ api_prompt: apiPrompt }),
                        });
                        apiPromptGenerated++;
                    } catch (e) {
                        console.warn(
                            `[MCP] Failed to generate api_prompt for ${name}:`,
                            e,
                        );
                    }
                }
            }

            const msg =
                t('autoExtractComplete', { created, skipped, failed }) +
                (apiPromptGenerated > 0
                    ? t('generatedApiPrompts', {
                          count: apiPromptGenerated,
                      })
                    : '');
            setActionInfo(msg, failed > 0);
            await loadTemplates();
        } catch (e) {
            setActionInfo(t('autoExtractFailed', { message: e.message }), true);
        } finally {
            autoCreateBtn.disabled = false;
            autoCreateBtn.textContent = t('autoExtractTemplates');
        }
    });
    batchRefreshBtn.addEventListener('click', async () => {
        batchRefreshBtn.disabled = true;
        batchRefreshBtn.textContent = t('working');
        setActionInfo(t('refreshingTemplates'));
        try {
            const result = await apiFetch('/templates/batch-refresh', {
                method: 'POST',
            });
            const refreshed = result.refreshed?.length || 0;
            const skipped = result.skipped?.length || 0;
            const failed = result.failed?.length || 0;
            const needsApiPrompt = result.needs_api_prompt || [];

            // Generate api_prompt for templates that need it
            let apiPromptGenerated = 0;
            if (needsApiPrompt.length > 0) {
                setActionInfo(
                    t('generatingApiPrompts', {
                        count: needsApiPrompt.length,
                    }),
                );
                for (const name of needsApiPrompt) {
                    try {
                        const wfContent = await apiFetch(`/workflows/${name}`);
                        const apiPrompt = await generateApiPrompt(wfContent);
                        await apiFetch(`/templates/${name}`, {
                            method: 'PUT',
                            body: JSON.stringify({ api_prompt: apiPrompt }),
                        });
                        apiPromptGenerated++;
                    } catch (e) {
                        console.warn(
                            `[MCP] Failed to generate api_prompt for ${name}:`,
                            e,
                        );
                    }
                }
            }

            const msg =
                t('batchRefreshComplete', { refreshed, skipped, failed }) +
                (apiPromptGenerated > 0
                    ? t('generatedApiPrompts', {
                          count: apiPromptGenerated,
                      })
                    : '');
            setActionInfo(msg, failed > 0);
            await loadTemplates();
        } catch (e) {
            setActionInfo(
                t('batchRefreshFailed', { message: e.message }),
                true,
            );
        } finally {
            batchRefreshBtn.disabled = false;
            batchRefreshBtn.textContent = t('batchRefreshTemplates');
        }
    });
    exportBtn.addEventListener('click', async () => {
        exportBtn.textContent = t('exporting');
        exportBtn.disabled = true;
        try {
            await downloadFile('/templates/export', 'mcp-templates.zip');
        } catch (e) {
            alert(t('exportFailed', { message: e.message }));
        } finally {
            exportBtn.textContent = t('exportTemplates');
            exportBtn.disabled = false;
        }
    });

    loadTemplates();
    return container;
}

// ── Template detail dialog ────────────────────────────────

async function showTemplateDetail(name) {
    const template = await apiFetch(`/templates/${name}?include_disabled=1`);
    if (template.error) return alert(template.error);

    const overlay = document.createElement('div');
    overlay.style.cssText =
        'position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:9999;display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box;';

    const modal = document.createElement('div');
    modal.style.cssText =
        'background:#1e1e1e;border:1px solid #444;border-radius:8px;padding:18px;width:min(720px,100%);max-height:calc(100vh - 48px);overflow-y:auto;color:#ddd;box-sizing:border-box;';

    let html = `<h3 style="margin:0 0 8px;font-size:16px;line-height:1.35;overflow-wrap:anywhere;">${template.name}</h3>`;
    if (template.description)
        html += `<p style="color:#aaa;font-size:12px;line-height:1.45;margin:0 0 14px;overflow-wrap:anywhere;">${template.description}</p>`;

    html += `<div style="${S.section}">${t('inputsParameters')}</div>`;
    const inputs = template.inputs || {};
    if (Object.keys(inputs).length) {
        for (const [k, v] of Object.entries(inputs)) {
            const def =
                v.default !== undefined
                    ? ` | ${t('defaultLabel')}: ${JSON.stringify(v.default)}`
                    : '';
            html += `<div style="${S.detailRow}"><span style="${S.label}">${k}</span><span style="font-size:11px;color:#888;line-height:1.4;text-align:right;overflow-wrap:anywhere;">${v.type} | ${t('nodeLabel')} ${v.node_id} → ${v.widget}${def}</span></div>`;
        }
    } else {
        html += `<div style="color:#888;font-size:12px;">${t('noInputsConfigured')}</div>`;
    }

    html += `<div style="${S.section}">${t('outputs')}</div>`;
    const outputs = template.outputs || {};
    if (Object.keys(outputs).length) {
        for (const [k, v] of Object.entries(outputs)) {
            html += `<div style="${S.detailRow}"><span style="${S.label}">${k}</span><span style="font-size:11px;color:#888;line-height:1.4;text-align:right;overflow-wrap:anywhere;">${v.comfy_type || v.type} | ${t('nodeLabel')} ${v.node_id}</span></div>`;
        }
    } else {
        html += `<div style="color:#888;font-size:12px;">${t('noOutputsConfigured')}</div>`;
    }

    html += `<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px;"><button id="mcp-close" style="${S.btn}">${t('close')}</button></div>`;

    modal.innerHTML = html;
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.remove();
    });
    modal
        .querySelector('#mcp-close')
        .addEventListener('click', () => overlay.remove());
}

// ── Create template dialog ────────────────────────────────

async function showCreateTemplateDialog(onDone) {
    const overlay = document.createElement('div');
    overlay.style.cssText =
        'position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:9999;display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box;';

    const modal = document.createElement('div');
    modal.style.cssText =
        'background:#1e1e1e;border:1px solid #444;border-radius:8px;padding:18px;width:min(680px,100%);max-height:calc(100vh - 48px);overflow-y:auto;color:#ddd;box-sizing:border-box;';

    modal.innerHTML = `
        <h3 style="margin:0 0 14px;font-size:16px;line-height:1.35;">${t('createTemplateFromWorkflow')}</h3>
        <div style="margin-bottom:10px;">
            <label style="display:block;font-size:12px;color:#aaa;margin-bottom:5px;">${t('workflow')}</label>
            <div style="display:flex;gap:8px;align-items:center;position:relative;">
                <div style="flex:1;position:relative;">
                    <input id="mcp-wf-search" type="text" placeholder="${t('searchWorkflows')}" style="width:100%;min-height:30px;padding:5px 9px;background:#2a2a2a;color:#ddd;border:1px solid #444;border-radius:4px;box-sizing:border-box;" autocomplete="off" />
                    <div id="mcp-wf-dropdown" style="display:none;position:fixed;max-height:240px;overflow-y:auto;background:#2a2a2a;border:1px solid #444;border-radius:4px;z-index:10001;margin-top:2px;"></div>
                </div>
                <button id="mcp-wf-refresh" style="${S.btn}font-size:11px;">${t('refresh')}</button>
            </div>
        </div>
        <div id="mcp-preview" style="margin:10px 0 0;font-size:12px;color:#aaa;line-height:1.45;min-height:36px;padding:8px;border:1px solid #333;border-radius:6px;background:#202020;box-sizing:border-box;"></div>
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px;">
            <button id="mcp-save" style="${S.btn}background:#2d5a2d;color:#8f8;" disabled>${t('createTemplate')}</button>
            <button id="mcp-cancel" style="${S.btn}">${t('cancel')}</button>
        </div>
    `;

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    const searchInput = modal.querySelector('#mcp-wf-search');
    const dropdown = modal.querySelector('#mcp-wf-dropdown');
    const preview = modal.querySelector('#mcp-preview');
    const saveBtn = modal.querySelector('#mcp-save');
    const cancelBtn = modal.querySelector('#mcp-cancel');
    const refreshBtn = modal.querySelector('#mcp-wf-refresh');

    let extractedInfo = null;
    let allWorkflows = [];
    let selectedWorkflow = '';

    function renderDropdown(filter = '') {
        dropdown.innerHTML = '';
        const lower = filter.toLowerCase();
        const matched = lower
            ? allWorkflows.filter((w) => w.name.toLowerCase().includes(lower))
            : allWorkflows;

        if (!matched.length) {
            dropdown.innerHTML = `<div style="padding:6px 8px;color:#888;font-size:12px;">${t('noMatchingWorkflows')}</div>`;
            dropdown.style.display = 'block';
            return;
        }

        for (const w of matched) {
            const item = document.createElement('div');
            item.textContent = w.name;
            item.style.cssText =
                'padding:7px 9px;cursor:pointer;font-size:12px;color:#ddd;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
            item.title = w.name;
            if (w.name === selectedWorkflow) {
                item.style.background = '#3a5a3a';
            }
            item.addEventListener('mouseenter', () => {
                item.style.background = '#3a3a5a';
            });
            item.addEventListener('mouseleave', () => {
                item.style.background =
                    w.name === selectedWorkflow ? '#3a5a3a' : '';
            });
            item.addEventListener('click', () => {
                selectedWorkflow = w.name;
                searchInput.value = w.name;
                dropdown.style.display = 'none';
                onWorkflowSelected(w.name);
            });
            dropdown.appendChild(item);
        }
        // Position dropdown below the search input
        const rect = searchInput.getBoundingClientRect();
        dropdown.style.top = rect.bottom + 2 + 'px';
        dropdown.style.left = rect.left + 'px';
        dropdown.style.width = rect.width + 'px';
        dropdown.style.display = 'block';
    }

    searchInput.addEventListener('input', () => {
        selectedWorkflow = '';
        saveBtn.disabled = true;
        renderDropdown(searchInput.value);
    });

    searchInput.addEventListener('focus', () => {
        renderDropdown(searchInput.value);
    });

    document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.style.display = 'none';
        }
    });

    async function loadWorkflows() {
        searchInput.value = '';
        searchInput.placeholder = t('loading');
        searchInput.disabled = true;
        selectedWorkflow = '';
        try {
            const wfData = await apiFetch('/workflows');
            allWorkflows = wfData.workflows || [];
            searchInput.placeholder = allWorkflows.length
                ? t('searchWorkflows')
                : t('noWorkflowsFound');
        } catch (e) {
            allWorkflows = [];
            searchInput.placeholder = t('errorLoadingWorkflows');
        }
        searchInput.disabled = false;
    }

    refreshBtn.addEventListener('click', loadWorkflows);

    async function onWorkflowSelected(name) {
        if (!name) {
            preview.innerHTML = '';
            saveBtn.disabled = true;
            return;
        }
        preview.innerHTML = t('analyzingWorkflow');
        try {
            const wfContent = await apiFetch(`/workflows/${name}`);
            const info = await apiFetch('/templates/extract', {
                method: 'POST',
                body: JSON.stringify({ workflow: wfContent }),
            });
            extractedInfo = info;

            let html = '';
            if (info.description)
                html += `<div style="margin-bottom:4px;"><b>${t('description')}</b> ${info.description}</div>`;
            const inputKeys = Object.keys(info.inputs || {});
            html += `<div><b>${t('autoDetectedInputs', { count: inputKeys.length })}</b> ${inputKeys.join(', ') || t('none')}</div>`;
            const outputEntries = Object.entries(info.outputs || {});
            if (outputEntries.length) {
                html += `<div><b>${t('autoDetectedOutputs')} (${outputEntries.length}):</b></div>`;
                for (const [oname, def] of outputEntries) {
                    html += `<div style="padding-left:12px;color:#8f8;">${oname} <span style="color:#888;">(${def.comfy_type || def.type})</span></div>`;
                }
            } else {
                html += `<div><b>${t('autoDetectedOutputs')}:</b> ${t('none')}</div>`;
            }
            preview.innerHTML = html;

            saveBtn.disabled = false;
        } catch (e) {
            preview.innerHTML = `<span style="color:#f66;">${t('error', { message: e.message })}</span>`;
        }
    }

    saveBtn.addEventListener('click', async () => {
        const wfName = selectedWorkflow;
        if (!wfName) return;

        saveBtn.disabled = true;
        saveBtn.textContent = t('creating');

        try {
            const wfContent = await apiFetch(`/workflows/${wfName}`);

            // Generate API prompt using frontend's graphToPrompt
            let apiPrompt = null;
            try {
                apiPrompt = await generateApiPrompt(wfContent);
            } catch (e) {
                console.warn(
                    '[MCP] Failed to generate API prompt, template will use backend conversion:',
                    e,
                );
            }

            await apiFetch('/templates', {
                method: 'POST',
                body: JSON.stringify({
                    name: wfName,
                    workflow: wfContent,
                    api_prompt: apiPrompt,
                }),
            });

            overlay.remove();
            if (onDone) onDone();
        } catch (e) {
            alert(t('failedCreateTemplate', { message: e.message }));
            saveBtn.disabled = false;
            saveBtn.textContent = t('createTemplate');
        }
    });

    cancelBtn.addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.remove();
    });

    // Load workflows on open
    loadWorkflows();
}

// ── Register extension ────────────────────────────────────

app.registerExtension({
    name: 'ComfyUI.MCPServer',

    settings: [
        {
            id: 'MCPServer.Status',
            name: t('statusSetting'),
            category: ['MCP Server', t('statusCategory')],
            type: () => {
                const el = document.createElement('div');
                el.style.cssText = 'font-size:12px;color:#aaa;padding:4px 0;';
                apiFetch('/status')
                    .then((d) => {
                        el.textContent = t('mcpEndpoint', {
                            url: d.mcp_url,
                        });
                    })
                    .catch(() => {
                        el.textContent = t('mcpNotReachable');
                    });
                return el;
            },
        },
        {
            id: 'MCPServer.Templates',
            name: t('templatesSetting'),
            category: ['MCP Server', t('templatesCategory')],
            tooltip: t('templatesTooltip'),
            type: () => createTemplateWidget(),
        },
    ],
});
