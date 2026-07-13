import { apiFetch } from '../core/http.js';
import { t } from '../core/i18n.js';
import { createModalShell } from './modal.js';
import { escapeHtml, S } from './styles.js';

function formatDefaultValue(value) {
    if (value === undefined) return '';
    return `${t('defaultLabel')}: ${JSON.stringify(value)}`;
}

function renderDetailRows(entries, formatter, emptyText) {
    if (!entries.length) {
        return `<div style="${S.empty};text-align:left;">${escapeHtml(emptyText)}</div>`;
    }
    return `<div style="${S.detailGrid}">${entries.map(formatter).join('')}</div>`;
}

export async function showTemplateDetail(name) {
    const template = await apiFetch(`/templates/${name}?include_disabled=1`);
    if (template.error) {
        alert(template.error);
        return;
    }

    const shell = createModalShell({ width: 'min(720px,100%)' });
    const { modal, open, close } = shell;

    const inputs = Object.entries(template.inputs || {});
    const outputs = Object.entries(template.outputs || {});

    let html = `
        <div style="${S.modalHeader}">
            <div style="min-width:0;">
                <h3 style="${S.modalTitle}">${escapeHtml(template.name)}</h3>
                <div style="${S.meta}">
                    <span style="${S.badge}">${t('templateCounts', {
                        inputs: inputs.length,
                        outputs: outputs.length,
                    })}</span>
                    ${
                        template.disabled
                            ? `<span style="${S.badge}${S.badgeOff}">${t('disabled')}</span>`
                            : ''
                    }
                </div>
            </div>
        </div>
    `;

    if (template.description) {
        html += `<div style="${S.descriptionBox};margin-bottom:12px;">${escapeHtml(template.description)}</div>`;
    }

    html += `<div style="${S.section}">${t('inputsParameters')}</div>`;
    html += renderDetailRows(
        inputs,
        ([inputName, definition]) => {
            const details = [
                definition.type,
                formatDefaultValue(definition.default),
            ].filter(Boolean);
            return `
                <div style="${S.detailRow}">
                    <span style="${S.key}">${escapeHtml(inputName)}</span>
                    <span style="${S.value}">${escapeHtml(details.join(' | '))}</span>
                </div>
            `;
        },
        t('noInputsConfigured'),
    );

    html += `<div style="${S.section}">${t('outputs')}</div>`;
    html += renderDetailRows(
        outputs,
        ([outputName, definition]) => {
            const details = [
                definition.comfy_type || definition.type,
            ].filter(Boolean);
            return `
                <div style="${S.detailRow}">
                    <span style="${S.key}">${escapeHtml(outputName)}</span>
                    <span style="${S.value}">${escapeHtml(details.join(' | '))}</span>
                </div>
            `;
        },
        t('noOutputsConfigured'),
    );

    html += `<div style="${S.footer}"><button id="mcp-close" style="${S.btn}">${t('close')}</button></div>`;

    modal.innerHTML = html;
    modal.querySelector('#mcp-close').addEventListener('click', close);
    open();
}
