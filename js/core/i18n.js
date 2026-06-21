import { api } from '../../../scripts/api.js';

const I18N_NAMESPACE = 'comfyuiMcpServer';

const I18N = {
    en: {
        refresh: 'Refresh',
        createFromWorkflow: 'Create from Workflow',
        autoExtractTemplates: 'Auto Extract Templates',
        batchRefreshTemplates: 'Batch Refresh Templates',
        exportTemplates: 'Export Templates',
        details: 'Details',
        enable: 'Enable',
        disable: 'Disable',
        delete: 'Delete',
        close: 'Close',
        cancel: 'Cancel',
        createTemplate: 'Create Template',
        working: 'Working...',
        exporting: 'Exporting...',
        loading: 'Loading...',
        noTemplates:
            'No templates yet. Click "Create from Workflow" to create one.',
        templateCounts: '{inputs} in / {outputs} out',
        disabled: 'disabled',
        updateFailed: 'Update failed: {message}',
        refreshFailed: 'Refresh failed: {message}',
        deleteConfirm: 'Delete template "{name}"?',
        error: 'Error: {message}',
        scanningWorkflows:
            'Scanning workflows and creating missing templates...',
        generatingApiPrompts: 'Generating API prompts for {count} templates...',
        autoExtractComplete:
            'Auto extract complete: {created} created, {skipped} skipped, {failed} failed.',
        generatedApiPrompts: ' Generated API prompts for {count} templates.',
        autoExtractFailed: 'Auto extract failed: {message}',
        refreshingTemplates:
            'Refreshing all existing templates from workflows...',
        batchRefreshComplete:
            'Batch refresh complete: {refreshed} refreshed, {skipped} skipped, {failed} failed.',
        batchRefreshFailed: 'Batch refresh failed: {message}',
        exportFailed: 'Export failed: {message}',
        inputsParameters: 'Inputs (parameters):',
        noInputsConfigured: 'No inputs configured',
        outputs: 'Outputs:',
        noOutputsConfigured: 'No outputs configured',
        createTemplateFromWorkflow: 'Create Template from Workflow',
        workflow: 'Workflow:',
        searchWorkflows: 'Search workflows...',
        noMatchingWorkflows: 'No matching workflows',
        noWorkflowsFound: 'No workflows found',
        errorLoadingWorkflows: 'Error loading workflows',
        analyzingWorkflow: 'Analyzing workflow...',
        description: 'Description:',
        autoDetectedInputs: 'Auto-detected inputs ({count}):',
        autoDetectedOutputs: 'Auto-detected outputs',
        none: 'none',
        failedCreateTemplate: 'Failed to create template: {message}',
        mcpEndpoint: 'MCP endpoint: {url}',
        mcpNotReachable: 'MCP server not reachable',
        statusSetting: 'MCP Server Status',
        templatesSetting: 'Templates',
        templatesTooltip: 'Create and manage MCP templates from workflows',
        nodeLabel: 'node',
        defaultLabel: 'default',
        creating: 'Creating...',
        runTemplateTimeoutSetting: 'Run Template Timeout',
        runTemplateTimeoutTooltip:
            'Default wait timeout in seconds when wait=true (applies to run_template and get_template_result)',
        updateDocEnabledSetting: 'Enable Update Template Doc',
        updateDocEnabledTooltip:
            'Allow the update_template_doc MCP tool to modify template documentation',
    },
    zh: {
        refresh: '刷新',
        createFromWorkflow: '从工作流创建',
        autoExtractTemplates: '自动提取模板',
        batchRefreshTemplates: '批量刷新模板',
        exportTemplates: '导出模板',
        details: '详情',
        enable: '启用',
        disable: '禁用',
        delete: '删除',
        close: '关闭',
        cancel: '取消',
        createTemplate: '创建模板',
        working: '处理中...',
        exporting: '导出中...',
        loading: '加载中...',
        noTemplates: '暂无模板。点击“从工作流创建”来创建模板。',
        templateCounts: '{inputs} 输入 / {outputs} 输出',
        disabled: '已禁用',
        updateFailed: '更新失败：{message}',
        refreshFailed: '刷新失败：{message}',
        deleteConfirm: '删除模板“{name}”？',
        error: '错误：{message}',
        scanningWorkflows: '正在扫描工作流并创建缺失模板...',
        generatingApiPrompts: '正在为 {count} 个模板生成 API Prompt...',
        autoExtractComplete:
            '自动提取完成：创建 {created} 个，跳过 {skipped} 个，失败 {failed} 个。',
        generatedApiPrompts: ' 已为 {count} 个模板生成 API Prompt。',
        autoExtractFailed: '自动提取失败：{message}',
        refreshingTemplates: '正在从工作流批量刷新已有模板...',
        batchRefreshComplete:
            '批量刷新完成：刷新 {refreshed} 个，跳过 {skipped} 个，失败 {failed} 个。',
        batchRefreshFailed: '批量刷新失败：{message}',
        exportFailed: '导出失败：{message}',
        inputsParameters: '输入（参数）：',
        noInputsConfigured: '未配置输入',
        outputs: '输出：',
        noOutputsConfigured: '未配置输出',
        createTemplateFromWorkflow: '从工作流创建模板',
        workflow: '工作流：',
        searchWorkflows: '搜索工作流...',
        noMatchingWorkflows: '没有匹配的工作流',
        noWorkflowsFound: '未找到工作流',
        errorLoadingWorkflows: '加载工作流失败',
        analyzingWorkflow: '正在分析工作流...',
        description: '描述：',
        autoDetectedInputs: '自动检测到的输入（{count}）：',
        autoDetectedOutputs: '自动检测到的输出',
        none: '无',
        failedCreateTemplate: '创建模板失败：{message}',
        mcpEndpoint: 'MCP 端点：{url}',
        mcpNotReachable: '无法连接 MCP 服务',
        statusSetting: 'MCP 服务状态',
        templatesSetting: '模板',
        templatesTooltip: '从工作流创建和管理 MCP 模板',
        nodeLabel: '节点',
        defaultLabel: '默认值',
        creating: '创建中...',
        runTemplateTimeoutSetting: '模板运行超时',
        runTemplateTimeoutTooltip:
            'wait=true 时的默认等待超时秒数（适用于 run_template 和 get_template_result）',
        updateDocEnabledSetting: '启用更新模板文档',
        updateDocEnabledTooltip:
            '允许 update_template_doc MCP 工具修改模板文档',
    },
};

let comfyI18n = null;
let locale = normalizeLocale(navigator.language);

try {
    const i18nModule = await import('../../../scripts/i18n.js');
    if (i18nModule.i18n?.global?.mergeLocaleMessage) {
        const comfyMessages = {
            en: I18N.en,
            'en-US': I18N.en,
            zh: I18N.zh,
            'zh-CN': I18N.zh,
        };
        for (const [language, messages] of Object.entries(comfyMessages)) {
            i18nModule.i18n.global.mergeLocaleMessage(language, {
                [I18N_NAMESPACE]: messages,
            });
        }
        comfyI18n = i18nModule;
    }
} catch {
    // Older ComfyUI builds do not expose the native i18n module to extensions.
}

try {
    locale = normalizeLocale(await api.getSetting('Comfy.Locale'));
} catch (e) {
    console.warn('[MCP] Failed to read Comfy.Locale, using browser locale:', e);
}

function normalizeLocale(nextLocale) {
    return String(nextLocale || '')
        .toLowerCase()
        .startsWith('zh')
        ? 'zh'
        : 'en';
}

function formatMessage(value, params = {}) {
    return value.replace(/\{(\w+)\}/g, (_, name) =>
        params[name] === undefined ? `{${name}}` : String(params[name]),
    );
}

export function t(key, params = {}) {
    const value = I18N[locale]?.[key] ?? I18N.en[key] ?? key;
    const comfyKey = `${I18N_NAMESPACE}.${key}`;
    if (comfyI18n?.te?.(comfyKey)) {
        return String(comfyI18n.t(comfyKey, params));
    }
    return formatMessage(value, params);
}

export async function updateLocale() {
    try {
        const nextLocale = normalizeLocale(await api.getSetting('Comfy.Locale'));
        if (nextLocale !== locale) {
            locale = nextLocale;
            return true;
        }
    } catch (e) {
        console.warn('[MCP] Failed to refresh Comfy.Locale:', e);
    }
    return false;
}
