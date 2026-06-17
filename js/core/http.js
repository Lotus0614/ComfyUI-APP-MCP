function getApiBase() {
    const scriptUrl = import.meta.url;
    const url = new URL(scriptUrl);
    const pathParts = url.pathname.split('/');
    const jsIdx = pathParts.indexOf('js');
    if (jsIdx > 0) return `/${pathParts[jsIdx - 1]}/api`;
    return '/mcp-server/api';
}

export const API = getApiBase();

export async function apiFetch(path, options = {}) {
    const resp = await fetch(`${API}${path}`, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    const text = await resp.text();
    if (!resp.ok) throw new Error(`API error (${resp.status}): ${text}`);
    try {
        return JSON.parse(text);
    } catch (e) {
        throw new Error(`Invalid JSON response: ${text.slice(0, 200)}`);
    }
}

export async function downloadFile(path, filename) {
    const resp = await fetch(`${API}${path}`);
    const text = resp.ok ? null : await resp.text();
    if (!resp.ok) throw new Error(`API error (${resp.status}): ${text}`);
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}
