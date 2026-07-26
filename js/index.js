import { app } from '../../../scripts/app.js';

import { t } from './core/i18n.js';
import { RUNTIME_SETTINGS } from './core/constants.js';
import { syncRuntimeSetting } from './core/runtimeSettings.js';
import { createTemplateSetting } from './ui/settingsControls.js';

app.registerExtension({
    name: 'ComfyUI.MCPServer',
    settings: [
        // Custom widget settings
        {
            id: 'MCPServer.templates.manager',
            name: t('templatesSetting'),
            tooltip: t('templatesTooltip'),
            type: () => createTemplateSetting(),
        },
        // Runtime settings (auto-synced to backend via onChange)
        ...RUNTIME_SETTINGS.map((s) => ({
            id: s.id,
            name: t(s.i18nName),
            type: s.type,
            defaultValue: s.defaultValue,
            ...(s.attrs && { attrs: s.attrs }),
            ...(s.i18nTooltip && { tooltip: t(s.i18nTooltip) }),
            onChange: (newVal) => {
                const value = s.validate ? s.validate(newVal) : newVal;
                if (value === null) return;
                syncRuntimeSetting(s.apiKey, value).catch((e) =>
                    console.error(`[MCP] Failed to sync ${s.apiKey}:`, e)
                );
            },
        })),
    ],
    async setup() {
        // Push stored setting values to the backend once at startup.
        // onChange alone only fires on user edits, so after a ComfyUI restart
        // the backend would otherwise fall back to its defaults until the
        // user touched each setting again.
        for (const s of RUNTIME_SETTINGS) {
            try {
                let value;
                try {
                    value = app.ui?.settings?.getSettingValue?.(s.id);
                } catch {
                    /* older frontend without getSettingValue */
                }
                if (value === undefined || value === null) {
                    value = s.defaultValue;
                }
                const validated = s.validate ? s.validate(value) : value;
                if (validated === null) continue;
                await syncRuntimeSetting(s.apiKey, validated);
            } catch (e) {
                console.warn(`[MCP] Initial sync failed for ${s.apiKey}:`, e);
            }
        }
    },
});
