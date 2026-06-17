import { app } from '../../../scripts/app.js';

async function waitForGraphNodes(timeoutMs = 1000) {
    const waitFrame = () =>
        new Promise((resolve) => requestAnimationFrame(resolve));

    const start = performance.now();
    while (performance.now() - start < timeoutMs) {
        if (app.graph._nodes?.length) return;
        await waitFrame();
    }
    throw new Error('Failed to load workflow into graph');
}

export async function generateApiPrompt(workflow) {
    const originalGraph = app.graph.serialize();

    try {
        app.graph.configure(workflow);
        await waitForGraphNodes();

        const { output } = await app.graphToPrompt();
        if (!output || Object.keys(output).length === 0) {
            throw new Error('graphToPrompt returned empty output');
        }
        return output;
    } finally {
        app.graph.configure(JSON.parse(JSON.stringify(originalGraph)));
    }
}
