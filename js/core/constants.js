/**
 * Runtime settings synced between frontend and backend.
 * Each entry maps a ComfyUI setting to a backend /settings/{apiKey} endpoint.
 */
export const RUNTIME_SETTINGS = [
    {
        id: 'MCPServer.execution.runTemplateTimeout',
        i18nName: 'runTemplateTimeoutSetting',
        i18nTooltip: 'runTemplateTimeoutTooltip',
        type: 'number',
        defaultValue: 120,
        attrs: { min: 1, step: 1, showButtons: true },
        apiKey: 'run_template_timeout',
        validate: (v) => {
            const n = Number(v);
            return Number.isFinite(n) && n > 0 ? n : null;
        },
    },
    {
        id: 'MCPServer.execution.updateDocEnabled',
        i18nName: 'updateDocEnabledSetting',
        i18nTooltip: 'updateDocEnabledTooltip',
        type: 'boolean',
        defaultValue: true,
        apiKey: 'update_doc_enabled',
    },
];
