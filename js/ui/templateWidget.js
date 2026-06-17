import { apiFetch, downloadFile } from '../core/http.js';
import { t, updateLocale } from '../core/i18n.js';
import { generateApiPrompt } from '../core/prompt.js';
import { showCreateTemplateDialog } from './createTemplateDialog.js';
import { showTemplateDetail } from './templateDetailDialog.js';
import { S } from './styles.js';

function buildTemplateListMessage(message, color = '#888') {
    return `<div style="color:${color};font-size:12px;padding:8px 2px;">${message}</div>`;
}

async function syncApiPrompts(templateNames, setActionInfo) {
    let generatedCount = 0;
    if (!templateNames.length) return generatedCount;

    setActionInfo(
        t('generatingApiPrompts', {
            count: templateNames.length,
        }),
    );

    for (const name of templateNames) {
        try {
            const workflowContent = await apiFetch(`/workflows/${name}`);
            const apiPrompt = await generateApiPrompt(workflowContent);
            await apiFetch(`/templates/${name}`, {
                method: 'PUT',
                body: JSON.stringify({ api_prompt: apiPrompt }),
            });
            generatedCount++;
        } catch (e) {
            console.warn(
                `[MCP] Failed to generate api_prompt for ${name}:`,
                e,
            );
        }
    }

    return generatedCount;
}

function createTemplateRow(template, reloadTemplates) {
    const row = document.createElement('div');
    row.style.cssText = S.row;

    const body = document.createElement('div');
    body.style.cssText =
        'display:flex;flex-direction:column;gap:3px;flex:1;min-width:0;';

    const name = document.createElement('span');
    name.textContent = template.name;
    name.title = template.name;
    name.style.cssText = `font-size:13px;font-weight:bold;line-height:1.35;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;${template.disabled ? 'color:#888;text-decoration:line-through;' : ''}`;

    const meta = document.createElement('div');
    meta.style.cssText = 'display:flex;align-items:center;gap:8px;min-width:0;';

    const info = document.createElement('span');
    info.textContent = `${t('templateCounts', {
        inputs: template.input_count,
        outputs: template.output_count,
    })}${template.disabled ? ` | ${t('disabled')}` : ''}`;
    info.style.cssText = `font-size:11px;color:${template.disabled ? '#b66' : '#888'};`;

    const description = document.createElement('span');
    description.textContent = template.description || '';
    description.title = template.description || '';
    description.style.cssText =
        'font-size:11px;color:#666;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';

    meta.append(info, description);
    body.append(name, meta);

    const actions = document.createElement('div');
    actions.style.cssText =
        'display:flex;align-items:center;justify-content:flex-end;gap:4px;flex-wrap:wrap;margin-left:auto;';

    const detailsButton = document.createElement('button');
    detailsButton.textContent = t('details');
    detailsButton.style.cssText = S.smallBtn;
    detailsButton.addEventListener('click', () =>
        showTemplateDetail(template.name),
    );

    const refreshButton = document.createElement('button');
    refreshButton.textContent = t('refresh');
    refreshButton.style.cssText = S.smallBtn;
    refreshButton.addEventListener('click', async () => {
        refreshButton.textContent = '...';
        refreshButton.disabled = true;
        try {
            const workflowContent = await apiFetch(`/workflows/${template.name}`);

            let apiPrompt = null;
            try {
                apiPrompt = await generateApiPrompt(workflowContent);
            } catch (e) {
                console.warn(
                    '[MCP] Failed to generate API prompt during refresh:',
                    e,
                );
            }

            const infoData = await apiFetch('/templates/extract', {
                method: 'POST',
                body: JSON.stringify({ workflow: workflowContent }),
            });

            await apiFetch(`/templates/${template.name}`, {
                method: 'PUT',
                body: JSON.stringify({
                    workflow: workflowContent,
                    api_prompt: apiPrompt,
                    inputs: infoData.inputs,
                    outputs: infoData.outputs,
                    description: infoData.description,
                }),
            });
            await reloadTemplates();
        } catch (e) {
            alert(t('refreshFailed', { message: e.message }));
            refreshButton.textContent = t('refresh');
            refreshButton.disabled = false;
        }
    });

    const toggleButton = document.createElement('button');
    toggleButton.textContent = template.disabled ? t('enable') : t('disable');
    toggleButton.style.cssText = `${S.smallBtn}${template.disabled ? 'color:#6d6;' : 'color:#fb6;'}`;
    toggleButton.addEventListener('click', async () => {
        toggleButton.textContent = '...';
        toggleButton.disabled = true;
        try {
            await apiFetch(`/templates/${template.name}`, {
                method: 'PUT',
                body: JSON.stringify({ disabled: !template.disabled }),
            });
            await reloadTemplates();
        } catch (e) {
            alert(t('updateFailed', { message: e.message }));
            toggleButton.textContent = template.disabled
                ? t('enable')
                : t('disable');
            toggleButton.disabled = false;
        }
    });

    const deleteButton = document.createElement('button');
    deleteButton.textContent = t('delete');
    deleteButton.style.cssText = `${S.smallBtn}color:#f66;`;
    deleteButton.addEventListener('click', async () => {
        if (!confirm(t('deleteConfirm', { name: template.name }))) return;
        await apiFetch(`/templates/${template.name}`, {
            method: 'DELETE',
        });
        await reloadTemplates();
    });

    actions.append(detailsButton, refreshButton, toggleButton, deleteButton);
    row.append(body, actions);
    return row;
}

export function createTemplateWidget() {
    const container = document.createElement('div');
    container.style.cssText =
        'display:flex;flex-direction:column;gap:10px;max-height:520px;overflow-y:auto;padding:6px 2px;';

    const list = document.createElement('div');
    list.style.cssText = 'display:flex;flex-direction:column;gap:6px;';
    container.appendChild(list);

    const actionInfo = document.createElement('div');
    actionInfo.style.cssText =
        'font-size:12px;color:#888;min-height:18px;line-height:1.4;';
    container.appendChild(actionInfo);

    const buttonRow = document.createElement('div');
    buttonRow.style.cssText = S.btnRow;
    container.appendChild(buttonRow);

    function setActionInfo(text, isError = false) {
        actionInfo.textContent = text;
        actionInfo.style.color = isError ? '#f66' : '#888';
    }

    async function loadTemplates() {
        list.innerHTML = t('loading');
        try {
            const data = await apiFetch('/templates?include_disabled=1');
            list.innerHTML = '';

            if (!data.templates?.length) {
                list.innerHTML = buildTemplateListMessage(t('noTemplates'));
                return;
            }

            for (const template of data.templates) {
                list.appendChild(createTemplateRow(template, loadTemplates));
            }
        } catch (e) {
            list.innerHTML = buildTemplateListMessage(
                t('error', { message: e.message }),
                '#f66',
            );
        }
    }

    const refreshButton = document.createElement('button');
    refreshButton.style.cssText = S.btn;
    refreshButton.addEventListener('click', () => void loadTemplates());

    const createButton = document.createElement('button');
    createButton.style.cssText = S.btn;
    createButton.addEventListener('click', () =>
        showCreateTemplateDialog(loadTemplates),
    );

    const autoCreateButton = document.createElement('button');
    autoCreateButton.style.cssText = S.btn;
    autoCreateButton.addEventListener('click', async () => {
        autoCreateButton.disabled = true;
        autoCreateButton.textContent = t('working');
        setActionInfo(t('scanningWorkflows'));

        try {
            const result = await apiFetch('/templates/auto-create', {
                method: 'POST',
            });
            const created = result.created?.length || 0;
            const skipped = result.skipped?.length || 0;
            const failed = result.failed?.length || 0;
            const generated = await syncApiPrompts(
                result.needs_api_prompt || [],
                setActionInfo,
            );

            setActionInfo(
                t('autoExtractComplete', { created, skipped, failed }) +
                    (generated > 0
                        ? t('generatedApiPrompts', { count: generated })
                        : ''),
                failed > 0,
            );
            await loadTemplates();
        } catch (e) {
            setActionInfo(t('autoExtractFailed', { message: e.message }), true);
        } finally {
            autoCreateButton.disabled = false;
            autoCreateButton.textContent = t('autoExtractTemplates');
        }
    });

    const batchRefreshButton = document.createElement('button');
    batchRefreshButton.style.cssText = S.btn;
    batchRefreshButton.addEventListener('click', async () => {
        batchRefreshButton.disabled = true;
        batchRefreshButton.textContent = t('working');
        setActionInfo(t('refreshingTemplates'));

        try {
            const result = await apiFetch('/templates/batch-refresh', {
                method: 'POST',
            });
            const refreshed = result.refreshed?.length || 0;
            const skipped = result.skipped?.length || 0;
            const failed = result.failed?.length || 0;
            const generated = await syncApiPrompts(
                result.needs_api_prompt || [],
                setActionInfo,
            );

            setActionInfo(
                t('batchRefreshComplete', { refreshed, skipped, failed }) +
                    (generated > 0
                        ? t('generatedApiPrompts', { count: generated })
                        : ''),
                failed > 0,
            );
            await loadTemplates();
        } catch (e) {
            setActionInfo(
                t('batchRefreshFailed', { message: e.message }),
                true,
            );
        } finally {
            batchRefreshButton.disabled = false;
            batchRefreshButton.textContent = t('batchRefreshTemplates');
        }
    });

    const exportButton = document.createElement('button');
    exportButton.style.cssText = S.btn;
    exportButton.addEventListener('click', async () => {
        exportButton.textContent = t('exporting');
        exportButton.disabled = true;
        try {
            await downloadFile('/templates/export', 'mcp-templates.zip');
        } catch (e) {
            alert(t('exportFailed', { message: e.message }));
        } finally {
            exportButton.textContent = t('exportTemplates');
            exportButton.disabled = false;
        }
    });

    function refreshTexts() {
        refreshButton.textContent = t('refresh');
        createButton.textContent = t('createFromWorkflow');
        autoCreateButton.textContent = t('autoExtractTemplates');
        batchRefreshButton.textContent = t('batchRefreshTemplates');
        exportButton.textContent = t('exportTemplates');
    }

    buttonRow.append(
        refreshButton,
        createButton,
        autoCreateButton,
        batchRefreshButton,
        exportButton,
    );

    void updateLocale().then((changed) => {
        if (changed) refreshTexts();
    });
    refreshTexts();
    void loadTemplates();

    return container;
}
