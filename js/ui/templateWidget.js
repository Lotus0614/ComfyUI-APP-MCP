import { apiFetch, downloadFile } from '../core/http.js';
import { t, updateLocale } from '../core/i18n.js';
import { generateApiPrompt } from '../core/prompt.js';
import { showCreateTemplateDialog } from './createTemplateDialog.js';
import { showTemplateDetail } from './templateDetailDialog.js';
import { escapeHtml, S } from './styles.js';

function buildTemplateListMessage(message, color = '#888') {
    return `<div style="${S.empty}color:${color};">${escapeHtml(message)}</div>`;
}

function buildButton(label, style = S.btn) {
    const button = document.createElement('button');
    button.textContent = label;
    button.style.cssText = style;
    return button;
}

async function syncApiPrompts(templateNames, setActionInfo) {
    let generatedCount = 0;
    if (!templateNames.length) return generatedCount;

    setActionInfo(t('generatingApiPrompts', { count: templateNames.length }));

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
            console.warn(`[MCP] Failed to generate api_prompt for ${name}:`, e);
        }
    }

    return generatedCount;
}

function createTemplateRow(template, reloadTemplates) {
    const row = document.createElement('div');
    row.style.cssText = `${S.row}${template.disabled ? S.rowDisabled : ''}`;

    const body = document.createElement('div');
    body.style.cssText =
        'display:flex;flex-direction:column;gap:4px;min-width:0;';

    const name = document.createElement('div');
    name.textContent = template.name;
    name.title = template.name;
    name.style.cssText = `${S.title}${template.disabled ? 'text-decoration:line-through;color:#999;' : ''}`;

    const description = document.createElement('div');
    description.textContent = template.description || template.title || '';
    description.title = template.description || template.title || '';
    description.style.cssText = S.description;

    const meta = document.createElement('div');
    meta.style.cssText = S.meta;

    const counts = document.createElement('span');
    counts.textContent = t('templateCounts', {
        inputs: template.input_count,
        outputs: template.output_count,
    });
    counts.style.cssText = S.badge;
    meta.appendChild(counts);

    if (template.disabled) {
        const disabled = document.createElement('span');
        disabled.textContent = t('disabled');
        disabled.style.cssText = `${S.badge}${S.badgeOff}`;
        meta.appendChild(disabled);
    }

    body.append(name, description, meta);

    const actions = document.createElement('div');
    actions.style.cssText = S.actions;

    const detailsButton = buildButton(t('details'), S.smallBtn);
    detailsButton.addEventListener('click', () => showTemplateDetail(template.name));

    const refreshButton = buildButton(t('refresh'), S.smallBtn);
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

    const toggleButton = buildButton(
        template.disabled ? t('enable') : t('disable'),
        `${S.smallBtn}${template.disabled ? S.primaryBtn : S.warnBtn}`,
    );
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
            toggleButton.textContent = template.disabled ? t('enable') : t('disable');
            toggleButton.disabled = false;
        }
    });

    const deleteButton = buildButton(t('delete'), `${S.smallBtn}${S.dangerBtn}`);
    deleteButton.addEventListener('click', async () => {
        if (!confirm(t('deleteConfirm', { name: template.name }))) return;
        await apiFetch(`/templates/${template.name}`, { method: 'DELETE' });
        await reloadTemplates();
    });

    actions.append(detailsButton, refreshButton, toggleButton, deleteButton);
    row.append(body, actions);
    return row;
}

export function createTemplateWidget() {
    const container = document.createElement('div');
    container.style.cssText = S.panel;

    const toolbar = document.createElement('div');
    toolbar.style.cssText = S.toolbar;

    const searchInput = document.createElement('input');
    searchInput.type = 'search';
    searchInput.style.cssText = S.search;
    searchInput.autocomplete = 'off';

    const buttonRow = document.createElement('div');
    buttonRow.style.cssText = S.toolbarGroup;

    const refreshButton = buildButton(t('refresh'));
    const createButton = buildButton(t('createFromWorkflow'), `${S.btn}${S.primaryBtn}`);
    const autoCreateButton = buildButton(t('autoExtractTemplates'));
    const batchRefreshButton = buildButton(t('batchRefreshTemplates'));
    const exportButton = buildButton(t('exportTemplates'));

    buttonRow.append(
        refreshButton,
        createButton,
        autoCreateButton,
        batchRefreshButton,
        exportButton,
    );
    toolbar.append(searchInput, buttonRow);

    const actionInfo = document.createElement('div');
    actionInfo.style.cssText = S.status;

    const list = document.createElement('div');
    list.style.cssText = S.list;

    container.append(toolbar, actionInfo, list);

    let allTemplates = [];

    function setActionInfo(text, isError = false) {
        actionInfo.textContent = text;
        actionInfo.style.color = isError ? '#f66' : '#8f8f8f';
    }

    function getVisibleTemplates() {
        const query = searchInput.value.trim().toLowerCase();
        if (!query) return allTemplates;
        return allTemplates.filter((template) =>
            [
                template.name,
                template.title,
                template.description,
                template.disabled ? t('disabled') : '',
            ]
                .filter(Boolean)
                .some((value) => String(value).toLowerCase().includes(query)),
        );
    }

    function renderTemplates() {
        const visibleTemplates = getVisibleTemplates();
        list.innerHTML = '';

        if (!allTemplates.length) {
            list.innerHTML = buildTemplateListMessage(t('noTemplates'));
            setActionInfo('');
            return;
        }

        if (!visibleTemplates.length) {
            list.innerHTML = buildTemplateListMessage(t('noMatchingWorkflows'));
        } else {
            for (const template of visibleTemplates) {
                list.appendChild(createTemplateRow(template, loadTemplates));
            }
        }

        setActionInfo(
            t('templateSummary', {
                shown: visibleTemplates.length,
                total: allTemplates.length,
            }),
        );
    }

    async function loadTemplates() {
        list.innerHTML = buildTemplateListMessage(t('loading'));
        try {
            const data = await apiFetch('/templates?include_disabled=1');
            allTemplates = data.templates || [];
            renderTemplates();
        } catch (e) {
            allTemplates = [];
            list.innerHTML = buildTemplateListMessage(
                t('error', { message: e.message }),
                '#f66',
            );
            setActionInfo('', true);
        }
    }

    refreshButton.addEventListener('click', () => void loadTemplates());
    createButton.addEventListener('click', () =>
        showCreateTemplateDialog(loadTemplates),
    );
    searchInput.addEventListener('input', renderTemplates);

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
        searchInput.placeholder = t('searchTemplates');
        refreshButton.textContent = t('refresh');
        createButton.textContent = t('createFromWorkflow');
        autoCreateButton.textContent = t('autoExtractTemplates');
        batchRefreshButton.textContent = t('batchRefreshTemplates');
        exportButton.textContent = t('exportTemplates');
        renderTemplates();
    }

    void updateLocale().then((changed) => {
        if (changed) refreshTexts();
    });
    refreshTexts();
    void loadTemplates();

    return container;
}
