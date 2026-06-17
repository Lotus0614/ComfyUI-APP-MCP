import { api } from '../../../scripts/api.js';

import {
    DEFAULT_RUN_TEMPLATE_TIMEOUT,
    RUN_TEMPLATE_TIMEOUT_SETTING_ID,
    RUN_TEMPLATE_TIMEOUT_STORAGE_KEY,
} from './constants.js';
import { apiFetch } from './http.js';

export async function persistLocalSetting(settingId, storageKey, value) {
    if (typeof api.storeSetting === 'function') {
        await api.storeSetting(settingId, value);
        return;
    }
    localStorage.setItem(storageKey, String(value));
}

export async function loadLocalSetting(settingId, storageKey) {
    if (typeof api.getSetting === 'function') {
        const settingValue = await api.getSetting(settingId);
        if (settingValue !== null && settingValue !== undefined) {
            return Number(settingValue);
        }
    }

    const storedValue = localStorage.getItem(storageKey);
    if (storedValue !== null) {
        return Number(storedValue);
    }

    return null;
}

export async function loadRunTemplateTimeout() {
    const value = await loadLocalSetting(
        RUN_TEMPLATE_TIMEOUT_SETTING_ID,
        RUN_TEMPLATE_TIMEOUT_STORAGE_KEY,
    );
    return value ?? null;
}

export async function persistRunTemplateTimeout(value) {
    await persistLocalSetting(
        RUN_TEMPLATE_TIMEOUT_SETTING_ID,
        RUN_TEMPLATE_TIMEOUT_STORAGE_KEY,
        value,
    );
}

export async function getRuntimeSetting(apiKey, fallbackValue) {
    const response = await apiFetch(`/settings/${apiKey}`);
    const value = Number(response.value);
    if (!Number.isFinite(value)) return fallbackValue;
    return value;
}

export async function syncRuntimeSetting(apiKey, value) {
    return apiFetch(`/settings/${apiKey}`, {
        method: 'POST',
        body: JSON.stringify({ value }),
    });
}

export async function resolveRunTemplateTimeout(apiKey) {
    const localValue = await loadRunTemplateTimeout();
    if (Number.isFinite(localValue) && localValue > 0) {
        return localValue;
    }

    try {
        return await getRuntimeSetting(apiKey, DEFAULT_RUN_TEMPLATE_TIMEOUT);
    } catch {
        return DEFAULT_RUN_TEMPLATE_TIMEOUT;
    }
}
