import { app } from '../../../scripts/app.js';

import { t } from './core/i18n.js';
import { RUNTIME_SETTINGS } from './core/constants.js';
import { syncRuntimeSetting } from './core/runtimeSettings.js';
import {
    createStatusSetting,
    createTemplateSetting,
} from './ui/settingsControls.js';

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
        {
            id: 'MCPServer.status.server',
            name: t('statusSetting'),
            type: () => createStatusSetting(),
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
});
