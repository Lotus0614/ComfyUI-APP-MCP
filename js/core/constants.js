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
        id: 'MCPServer.execution.templateTokenEnabled',
        i18nName: 'templateTokenEnabledSetting',
        i18nTooltip: 'templateTokenEnabledTooltip',
        type: 'boolean',
        defaultValue: false,
        apiKey: 'template_token_enabled',
    },
    {
        id: 'MCPServer.execution.templateTokenMaxUses',
        i18nName: 'templateTokenMaxUsesSetting',
        i18nTooltip: 'templateTokenMaxUsesTooltip',
        type: 'number',
        defaultValue: 50,
        attrs: { min: 1, step: 1, showButtons: true },
        apiKey: 'template_token_max_uses',
        validate: (v) => {
            const n = Math.floor(Number(v));
            return Number.isFinite(n) && n > 0 ? n : null;
        },
    },
    {
        id: 'MCPServer.execution.templateTokenTtlHours',
        i18nName: 'templateTokenTtlHoursSetting',
        i18nTooltip: 'templateTokenTtlHoursTooltip',
        type: 'number',
        defaultValue: 12,
        attrs: { min: 0.1, step: 0.5, showButtons: true },
        apiKey: 'template_token_ttl_hours',
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
    {
        id: 'MCPServer.execution.embedWorkflowMetadata',
        i18nName: 'embedWorkflowMetadataSetting',
        i18nTooltip: 'embedWorkflowMetadataTooltip',
        type: 'boolean',
        defaultValue: true,
        apiKey: 'embed_workflow_metadata',
    },
    {
        id: 'MCPServer.execution.maxConcurrency',
        i18nName: 'maxConcurrencySetting',
        i18nTooltip: 'maxConcurrencyTooltip',
        type: 'number',
        defaultValue: -1,
        attrs: { step: 1, showButtons: true }, // no min: allow -1
        apiKey: 'max_concurrency',
        validate: (v) => {
            const n = Math.floor(Number(v));
            if (!Number.isFinite(n)) return null;
            if (n === -1) return -1; // -1 = unlimited
            return n > 0 ? n : null; // only -1 or positive ints are valid
        },
    },
];
