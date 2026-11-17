import { apiFetch } from '../core/http.js';
import { t } from '../core/i18n.js';
import { generateApiPrompt } from '../core/prompt.js';
import { createModalShell } from './modal.js';
import { escapeHtml, mutedText, S } from './styles.js';

function renderWorkflowPreview(info) {
    let html = '';
    if (info.description) {
        html += `<div style="${S.previewCard}">`;
        html += `<div style="${S.key};margin-bottom:6px;">${t('description')}</div>`;
        html += `<div style="${S.descriptionBox}">${escapeHtml(info.description)}</div>`;
        html += '</div>';
    }

    const inputKeys = Object.keys(info.inputs || {});
    html += `<div style="${S.previewGrid}">`;
    html += `<div style="${S.previewCard}"><div style="${S.key}">${t('autoDetectedInputs', {
        count: inputKeys.length,
    })}</div><div style="${S.mutedText};margin-top:6px;">${escapeHtml(inputKeys.join(', ') || t('none'))}</div></div>`;

    const outputEntries = Object.entries(info.outputs || {});
    let outputHtml = '';
    if (outputEntries.length) {
        for (const [outputName, definition] of outputEntries) {
            outputHtml += `<div style="margin-top:5px;">${escapeHtml(outputName)} ${mutedText(definition.comfy_type || definition.type)}</div>`;
        }
    } else {
        outputHtml = mutedText(t('none'));
    }
    html += `<div style="${S.previewCard}"><div style="${S.key}">${t('autoDetectedOutputs')} (${outputEntries.length})</div><div style="${S.mutedText};margin-top:6px;">${outputHtml}</div></div>`;
    html += '</div>';

    return html;
}

/**
 * Place the workflow list under the search field.
 *
 * The list is a native popover, so it renders in the top layer: the settings
 * dialog's transformed/overflow-clipped ancestors no longer shift or cut it,
 * and `getBoundingClientRect()` matches the fixed coordinates it uses.
 */
function positionDropdown(input, dropdown) {
    const rect = input.getBoundingClientRect();
    dropdown.style.top = `${rect.bottom + 2}px`;
    dropdown.style.left = `${rect.left}px`;
    dropdown.style.width = `${rect.width}px`;
}

function showDropdown(input, dropdown) {
    positionDropdown(input, dropdown);
    dropdown.style.display = 'block';
    try {
        dropdown.showPopover?.();
    } catch {
        /* browser without popover support: fall back to a plain overlay */
    }
}

function hideDropdown(dropdown) {
    try {
        dropdown.hidePopover?.();
    } catch {
        /* not open */
    }
    dropdown.style.display = 'none';
}

export async function showCreateTemplateDialog(onDone, anchor = null) {
    const shell = createModalShell({ width: 'min(680px,100%)', anchor });
    const { overlay, modal, open, close } = shell;

    modal.innerHTML = `
        <div style="${S.modalHeader}">
            <div>
                <h3 style="${S.modalTitle}">${t('createTemplateFromWorkflow')}</h3>
                <p style="${S.modalSubtitle}">${t('templatesTooltip')}</p>
            </div>
        </div>
        <div>
            <label style="${S.label}">${t('workflow')}</label>
            <div style="display:flex;gap:8px;align-items:center;position:relative;">
                <div style="flex:1;position:relative;">
                    <input id="mcp-wf-search" type="text" placeholder="${t('searchWorkflows')}" style="${S.input}" autocomplete="off" />
                    <div id="mcp-wf-dropdown" style="${S.dropdown}"></div>
                </div>
                <button id="mcp-wf-refresh" style="${S.btn}">${t('refresh')}</button>
            </div>
        </div>
        <div id="mcp-preview" style="${S.preview}"></div>
        <div style="${S.footer}">
            <button id="mcp-save" style="${S.btn}${S.primaryBtn}" disabled>${t('createTemplate')}</button>
            <button id="mcp-cancel" style="${S.btn}">${t('cancel')}</button>
        </div>
    `;

    const searchInput = modal.querySelector('#mcp-wf-search');
    const dropdown = modal.querySelector('#mcp-wf-dropdown');
    const preview = modal.querySelector('#mcp-preview');
    const saveBtn = modal.querySelector('#mcp-save');
    const cancelBtn = modal.querySelector('#mcp-cancel');
    const refreshBtn = modal.querySelector('#mcp-wf-refresh');

    // Render the list in the top layer so the modal's scroll box cannot clip it.
    dropdown.popover = 'manual';

    let selectedWorkflow = '';
    let allWorkflows = [];
    let removeDocumentClickListener = null;

    function closeDropdown() {
        hideDropdown(dropdown);
    }

    function closeDialog() {
        if (removeDocumentClickListener) {
            document.removeEventListener('click', removeDocumentClickListener);
            removeDocumentClickListener = null;
        }
        window.removeEventListener('resize', keepDropdownAligned);
        hideDropdown(dropdown);
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
            dropdown.innerHTML = `<div style="${S.dropdownItem};color:#888;">${t('noMatchingWorkflows')}</div>`;
            showDropdown(searchInput, dropdown);
            return;
        }

        for (const workflow of matched) {
            const item = document.createElement('div');
            item.textContent = workflow.name;
            item.title = workflow.name;
            item.style.cssText = S.dropdownItem;
            if (workflow.name === selectedWorkflow) {
                item.style.background = '#263a2b';
            }
            item.addEventListener('mouseenter', () => {
                item.style.background = '#2a2a2a';
            });
            item.addEventListener('mouseleave', () => {
                item.style.background =
                    workflow.name === selectedWorkflow ? '#263a2b' : '';
            });
            item.addEventListener('click', () => {
                selectedWorkflow = workflow.name;
                searchInput.value = workflow.name;
                closeDropdown();
                void onWorkflowSelected(workflow.name);
            });
            dropdown.appendChild(item);
        }

        showDropdown(searchInput, dropdown);
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

        preview.innerHTML = mutedText(t('analyzingWorkflow'));
        try {
            const workflowContent = await apiFetch(`/workflows/${encodeURIComponent(name)}`);
            const info = await apiFetch('/templates/extract', {
                method: 'POST',
                body: JSON.stringify({ workflow: workflowContent }),
            });
            preview.innerHTML = renderWorkflowPreview(info);
            saveBtn.disabled = false;
        } catch (e) {
            preview.innerHTML = `<span style="color:#f66;">${escapeHtml(t('error', { message: e.message }))}</span>`;
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
    const keepDropdownAligned = () => {
        if (dropdown.style.display === 'none') return;
        positionDropdown(searchInput, dropdown);
    };
    modal.addEventListener('scroll', keepDropdownAligned, { passive: true });
    window.addEventListener('resize', keepDropdownAligned);

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
            const workflowContent = await apiFetch(`/workflows/${encodeURIComponent(selectedWorkflow)}`);

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
