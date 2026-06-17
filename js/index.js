import { app } from '../../../scripts/app.js';

import { t } from './core/i18n.js';
import {
    DEFAULT_RUN_TEMPLATE_TIMEOUT,
    RUN_TEMPLATE_TIMEOUT_API_KEY,
    RUN_TEMPLATE_TIMEOUT_SETTING_ID,
} from './core/constants.js';
import {
    persistRunTemplateTimeout,
    syncRuntimeSetting,
    resolveRunTemplateTimeout,
} from './core/runtimeSettings.js';
import {
    createStatusSetting,
    createTemplateSetting,
} from './ui/settingsControls.js';

app.registerExtension({
    name: 'ComfyUI.MCPServer',
    settings: [
        {
            id: 'MCPServer.Status',
            name: t('statusSetting'),
            category: ['MCP Server', t('statusCategory')],
            type: () => createStatusSetting(),
        },
        {
            id: 'MCPServer.Templates',
            name: t('templatesSetting'),
            category: ['MCP Server', t('templatesCategory')],
            tooltip: t('templatesTooltip'),
            type: () => createTemplateSetting(),
        },
        {
            id: RUN_TEMPLATE_TIMEOUT_SETTING_ID,
            name: t('runTemplateTimeoutSetting'),
            category: ['MCP Server', t('timeoutCategory')],
            tooltip: t('runTemplateTimeoutTooltip'),
            type: 'number',
            defaultValue: DEFAULT_RUN_TEMPLATE_TIMEOUT,
            attrs: {
                min: 1,
                step: 1,
                showButtons: true,
            },
            onChange: async (newVal) => {
                const value = Number(newVal);
                if (!Number.isFinite(value) || value <= 0) return;
                try {
                    await persistRunTemplateTimeout(value);
                    await syncRuntimeSetting(RUN_TEMPLATE_TIMEOUT_API_KEY, value);
                } catch (e) {
                    console.error('[MCP] Failed to save run template timeout:', e);
                }
            },
        },
    ],
    async init() {
        // Sync persisted timeout value to backend on startup
        try {
            const value = await resolveRunTemplateTimeout(RUN_TEMPLATE_TIMEOUT_API_KEY);
            await syncRuntimeSetting(RUN_TEMPLATE_TIMEOUT_API_KEY, value);
        } catch (e) {
            console.warn('[MCP] Failed to sync run template timeout to backend:', e);
        }
    },
});
