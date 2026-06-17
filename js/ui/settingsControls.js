import { t } from '../core/i18n.js';
import { apiFetch } from '../core/http.js';
import { createTemplateWidget } from './templateWidget.js';

export function createStatusSetting() {
    const element = document.createElement('div');
    element.style.cssText = 'font-size:12px;color:#aaa;padding:4px 0;';

    apiFetch('/status')
        .then((status) => {
            element.textContent = t('mcpEndpoint', { url: status.mcp_url });
        })
        .catch(() => {
            element.textContent = t('mcpNotReachable');
        });

    return element;
}

export function createTemplateSetting() {
    return createTemplateWidget();
}
