import { apiFetch } from '../core/http.js';
import { t } from '../core/i18n.js';
import { generateApiPrompt } from '../core/prompt.js';
import { createModalShell } from './modal.js';
import { S } from './styles.js';

function renderWorkflowPreview(info) {
    let html = '';
    if (info.description) {
        html += `<div style="margin-bottom:4px;"><b>${t('description')}</b> ${info.description}</div>`;
    }

    const inputKeys = Object.keys(info.inputs || {});
    html += `<div><b>${t('autoDetectedInputs', { count: inputKeys.length })}</b> ${inputKeys.join(', ') || t('none')}</div>`;

    const outputEntries = Object.entries(info.outputs || {});
    if (outputEntries.length) {
        html += `<div><b>${t('autoDetectedOutputs')} (${outputEntries.length}):</b></div>`;
        for (const [outputName, definition] of outputEntries) {
            html += `<div style="padding-left:12px;color:#8f8;">${outputName} <span style="color:#888;">(${definition.comfy_type || definition.type})</span></div>`;
        }
    } else {
        html += `<div><b>${t('autoDetectedOutputs')}:</b> ${t('none')}</div>`;
    }

    return html;
}

function positionDropdown(input, dropdown) {
    const rect = input.getBoundingClientRect();
    dropdown.style.top = `${rect.bottom + 2}px`;
    dropdown.style.left = `${rect.left}px`;
    dropdown.style.width = `${rect.width}px`;
    dropdown.style.display = 'block';
}

export async function showCreateTemplateDialog(onDone) {
    const shell = createModalShell({ width: 'min(680px,100%)' });
    const { overlay, modal, open, close } = shell;

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

    const searchInput = modal.querySelector('#mcp-wf-search');
    const dropdown = modal.querySelector('#mcp-wf-dropdown');
    const preview = modal.querySelector('#mcp-preview');
    const saveBtn = modal.querySelector('#mcp-save');
    const cancelBtn = modal.querySelector('#mcp-cancel');
    const refreshBtn = modal.querySelector('#mcp-wf-refresh');

    let selectedWorkflow = '';
    let allWorkflows = [];
    let removeDocumentClickListener = null;

    function closeDropdown() {
        dropdown.style.display = 'none';
    }

    function closeDialog() {
        if (removeDocumentClickListener) {
            document.removeEventListener('click', removeDocumentClickListener);
            removeDocumentClickListener = null;
        }
        close();
    }

    function renderDropdown(filter = '') {
        dropdown.innerHTML = '';
        const lower = filter.toLowerCase();
        const matched = lower
            ? allWorkflows.filter((workflow) =>
                  workflow.name.toLowerCase().includes(lower),
              )
            : allWorkflows;

        if (!matched.length) {
            dropdown.innerHTML = `<div style="padding:6px 8px;color:#888;font-size:12px;">${t('noMatchingWorkflows')}</div>`;
            dropdown.style.display = 'block';
            return;
        }

        for (const workflow of matched) {
            const item = document.createElement('div');
            item.textContent = workflow.name;
            item.title = workflow.name;
            item.style.cssText =
                'padding:7px 9px;cursor:pointer;font-size:12px;color:#ddd;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
            if (workflow.name === selectedWorkflow) {
                item.style.background = '#3a5a3a';
            }
            item.addEventListener('mouseenter', () => {
                item.style.background = '#3a3a5a';
            });
            item.addEventListener('mouseleave', () => {
                item.style.background =
                    workflow.name === selectedWorkflow ? '#3a5a3a' : '';
            });
            item.addEventListener('click', () => {
                selectedWorkflow = workflow.name;
                searchInput.value = workflow.name;
                closeDropdown();
                void onWorkflowSelected(workflow.name);
            });
            dropdown.appendChild(item);
        }

        positionDropdown(searchInput, dropdown);
    }

    async function loadWorkflows() {
        searchInput.value = '';
        searchInput.placeholder = t('loading');
        searchInput.disabled = true;
        selectedWorkflow = '';
        saveBtn.disabled = true;

        try {
            const workflowData = await apiFetch('/workflows');
            allWorkflows = workflowData.workflows || [];
            searchInput.placeholder = allWorkflows.length
                ? t('searchWorkflows')
                : t('noWorkflowsFound');
        } catch {
            allWorkflows = [];
            searchInput.placeholder = t('errorLoadingWorkflows');
        }

        searchInput.disabled = false;
    }

    async function onWorkflowSelected(name) {
        if (!name) {
            preview.innerHTML = '';
            saveBtn.disabled = true;
            return;
        }

        preview.innerHTML = t('analyzingWorkflow');
        try {
            const workflowContent = await apiFetch(`/workflows/${name}`);
            const info = await apiFetch('/templates/extract', {
                method: 'POST',
                body: JSON.stringify({ workflow: workflowContent }),
            });
            preview.innerHTML = renderWorkflowPreview(info);
            saveBtn.disabled = false;
        } catch (e) {
            preview.innerHTML = `<span style="color:#f66;">${t('error', { message: e.message })}</span>`;
        }
    }

    searchInput.addEventListener('input', () => {
        selectedWorkflow = '';
        saveBtn.disabled = true;
        renderDropdown(searchInput.value);
    });
    searchInput.addEventListener('focus', () => {
        renderDropdown(searchInput.value);
    });
    removeDocumentClickListener = (event) => {
        if (
            !searchInput.contains(event.target) &&
            !dropdown.contains(event.target)
        ) {
            closeDropdown();
        }
    };
    document.addEventListener('click', removeDocumentClickListener);

    refreshBtn.addEventListener('click', () => void loadWorkflows());
    cancelBtn.addEventListener('click', closeDialog);
    saveBtn.addEventListener('click', async () => {
        if (!selectedWorkflow) return;

        saveBtn.disabled = true;
        saveBtn.textContent = t('creating');

        try {
            const workflowContent = await apiFetch(`/workflows/${selectedWorkflow}`);

            let apiPrompt = null;
            try {
                apiPrompt = await generateApiPrompt(workflowContent);
            } catch (e) {
                console.warn(
                    '[MCP] Failed to generate API prompt, template will use backend conversion:',
                    e,
                );
            }

            await apiFetch('/templates', {
                method: 'POST',
                body: JSON.stringify({
                    name: selectedWorkflow,
                    workflow: workflowContent,
                    api_prompt: apiPrompt,
                }),
            });

            closeDialog();
            if (onDone) onDone();
        } catch (e) {
            alert(t('failedCreateTemplate', { message: e.message }));
            saveBtn.disabled = false;
            saveBtn.textContent = t('createTemplate');
        }
    });

    open();
    await loadWorkflows();
    overlay.addEventListener('click', (event) => {
        if (event.target === overlay) {
            closeDialog();
        }
    });
}
