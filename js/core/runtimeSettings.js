import { apiFetch } from './http.js';

/**
 * Sync a runtime setting value to the backend.
 */
export async function syncRuntimeSetting(apiKey, value) {
    return apiFetch(`/settings/${apiKey}`, {
        method: 'POST',
        body: JSON.stringify({ value }),
    });
}
