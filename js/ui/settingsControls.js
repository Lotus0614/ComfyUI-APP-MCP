import { createTemplateWidget } from './templateWidget.js';
import { apiFetch } from '../core/http.js';
import { t } from '../core/i18n.js';

export function createTemplateSetting() {
    return createTemplateWidget();
}

export function createUploadCacheSetting() {
    const container = document.createElement('div');
    container.style.cssText =
        'display:flex;flex-direction:column;gap:6px;max-width:520px;';

    const tip = document.createElement('div');
    tip.textContent = t('uploadCacheTooltip');
    tip.style.cssText = 'color:#999;font-size:12px;line-height:1.4;';

    const button = document.createElement('button');
    button.textContent = t('clearUploadCache');
    button.style.cssText =
        'align-self:flex-start;padding:5px 10px;cursor:pointer;';

    const status = document.createElement('div');
    status.style.cssText = 'color:#999;font-size:12px;line-height:1.4;';

    button.addEventListener('click', async () => {
        if (!confirm(t('clearUploadCacheConfirm'))) return;
        button.disabled = true;
        status.textContent = t('clearingUploadCache');
        try {
            const result = await apiFetch('/upload-cache/clear', { method: 'POST' });
            status.textContent = t('clearUploadCacheComplete', {
                deleted: result.deleted || 0,
                directory: result.cache_dir || 'mcp_cache',
            });
            if (result.failed?.length) {
                status.textContent += ` ${t('clearUploadCacheFailed', {
                    count: result.failed.length,
                })}`;
            }
        } catch (e) {
            status.textContent = t('clearUploadCacheError', { message: e.message });
        } finally {
            button.disabled = false;
        }
    });

    container.append(tip, button, status);
    return container;
}
