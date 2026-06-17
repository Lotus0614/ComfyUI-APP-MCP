import { apiFetch } from '../core/http.js';
import { t } from '../core/i18n.js';
import { createModalShell } from './modal.js';
import { S } from './styles.js';

function renderEntries(entries, formatter) {
    if (!entries.length) return '';
    return entries.map(formatter).join('');
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

    let html = `<h3 style="margin:0 0 8px;font-size:16px;line-height:1.35;overflow-wrap:anywhere;">${template.name}</h3>`;
    if (template.description) {
        html += `<p style="color:#aaa;font-size:12px;line-height:1.45;margin:0 0 14px;overflow-wrap:anywhere;">${template.description}</p>`;
    }

    html += `<div style="${S.section}">${t('inputsParameters')}</div>`;
    html += inputs.length
        ? renderEntries(inputs, ([inputName, definition]) => {
              const defaultValue =
                  definition.default !== undefined
                      ? ` | ${t('defaultLabel')}: ${JSON.stringify(definition.default)}`
                      : '';
              return `<div style="${S.detailRow}"><span style="${S.label}">${inputName}</span><span style="font-size:11px;color:#888;line-height:1.4;text-align:right;overflow-wrap:anywhere;">${definition.type} | ${t('nodeLabel')} ${definition.node_id} → ${definition.widget}${defaultValue}</span></div>`;
          })
        : `<div style="color:#888;font-size:12px;">${t('noInputsConfigured')}</div>`;

    html += `<div style="${S.section}">${t('outputs')}</div>`;
    html += outputs.length
        ? renderEntries(outputs, ([outputName, definition]) => {
              return `<div style="${S.detailRow}"><span style="${S.label}">${outputName}</span><span style="font-size:11px;color:#888;line-height:1.4;text-align:right;overflow-wrap:anywhere;">${definition.comfy_type || definition.type} | ${t('nodeLabel')} ${definition.node_id}</span></div>`;
          })
        : `<div style="color:#888;font-size:12px;">${t('noOutputsConfigured')}</div>`;

    html += `<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px;"><button id="mcp-close" style="${S.btn}">${t('close')}</button></div>`;

    modal.innerHTML = html;
    modal.querySelector('#mcp-close').addEventListener('click', close);
    open();
}
