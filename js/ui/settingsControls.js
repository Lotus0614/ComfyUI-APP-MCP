import { t } from '../core/i18n.js';
import { apiFetch } from '../core/http.js';
import {
    DEFAULT_RUN_TEMPLATE_TIMEOUT,
    RUN_TEMPLATE_TIMEOUT_API_KEY,
} from '../core/constants.js';
import {
    getRuntimeSetting,
    persistRunTemplateTimeout,
    resolveRunTemplateTimeout,
    syncRuntimeSetting,
} from '../core/runtimeSettings.js';
import { createTemplateWidget } from './templateWidget.js';

function createNumberInput() {
    const input = document.createElement('input');
    input.type = 'number';
    input.min = '1';
    input.step = '1';
    input.style.cssText =
        'width:100px;min-height:28px;padding:4px 8px;background:#2a2a2a;color:#ddd;border:1px solid #444;border-radius:4px;box-sizing:border-box;';
    return input;
}

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

export async function createRunTemplateTimeoutSetting() {
    const input = createNumberInput();
    let currentValue = DEFAULT_RUN_TEMPLATE_TIMEOUT;

    try {
        currentValue = await resolveRunTemplateTimeout(RUN_TEMPLATE_TIMEOUT_API_KEY);
    } catch {
        currentValue = DEFAULT_RUN_TEMPLATE_TIMEOUT;
    }

    if (!Number.isFinite(currentValue) || currentValue <= 0) {
        currentValue = await getRuntimeSetting(
            RUN_TEMPLATE_TIMEOUT_API_KEY,
            DEFAULT_RUN_TEMPLATE_TIMEOUT,
        );
    }

    input.value = String(currentValue);
    await syncRuntimeSetting(RUN_TEMPLATE_TIMEOUT_API_KEY, currentValue);

    input.addEventListener('change', async () => {
        const nextValue = Number(input.value);
        if (!Number.isFinite(nextValue) || nextValue <= 0) {
            input.value = String(currentValue);
            return;
        }

        input.disabled = true;
        try {
            await persistRunTemplateTimeout(nextValue);
            await syncRuntimeSetting(RUN_TEMPLATE_TIMEOUT_API_KEY, nextValue);
            currentValue = nextValue;
        } catch (e) {
            input.value = String(currentValue);
            alert(t('timeoutSaveFailed', { message: e.message }));
        } finally {
            input.disabled = false;
        }
    });

    return input;
}
