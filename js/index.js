import { app } from '../../../scripts/app.js';

import { t } from './core/i18n.js';
import {
    createRunTemplateTimeoutSetting,
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
            id: 'MCPServer.RunTemplateTimeout',
            name: t('runTemplateTimeoutSetting'),
            category: ['MCP Server', t('timeoutCategory')],
            tooltip: t('runTemplateTimeoutTooltip'),
            type: () => createRunTemplateTimeoutSetting(),
        },
    ],
});
