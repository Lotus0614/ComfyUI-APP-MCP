// reka-ui (used by ComfyUI's settings dialog) treats a pointer-down/focus outside
// its layer as a request to close. Our modal is normally hosted inside that layer,
// but if the host structure changes, cancelling these custom events keeps the
// settings dialog open while the modal is in use.
const HOST_DISMISS_EVENTS = [
    'dismissableLayer.pointerDownOutside',
    'dismissableLayer.focusOutside',
];

/**
 * Host the modal inside the same container as `anchor`.
 *
 * ComfyUI's settings dialog sets `pointer-events: none` on <body> while open, so
 * anchoring next to the widget (the outermost ancestor that still accepts pointer
 * events) keeps the modal clickable and keeps the host dialog from treating
 * clicks in the modal as "outside" interactions.
 */
function findHost(anchor) {
    let node = anchor instanceof Element ? anchor : null;
    let host = document.body;
    while (node && node !== document.body) {
        if (getComputedStyle(node).pointerEvents !== 'none') host = node;
        node = node.parentElement;
    }
    return host;
}

export function createModalShell({ width = 'min(720px,100%)', anchor = null } = {}) {
    const overlay = document.createElement('div');
    // pointer-events:auto is required: the settings dialog sets
    // `document.body { pointer-events: none }`, and the overlay would otherwise
    // inherit it and let clicks fall through to the panel underneath.
    overlay.style.cssText =
        'position:fixed;inset:0;background:rgba(0,0,0,0.62);z-index:9999;display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box;backdrop-filter:blur(2px);pointer-events:auto;';

    const modal = document.createElement('div');
    modal.style.cssText =
        `background:#1f1f1f;border:1px solid #3d3d3d;border-radius:10px;padding:18px;width:${width};max-height:calc(100vh - 48px);overflow-y:auto;color:#ddd;box-sizing:border-box;box-shadow:0 18px 46px rgba(0,0,0,.45);`;

    const blockHostDismiss = (event) => event.preventDefault();
    for (const name of HOST_DISMISS_EVENTS) {
        overlay.addEventListener(name, blockHostDismiss, true);
    }

    overlay.addEventListener('click', (event) => {
        if (event.target === overlay) overlay.remove();
    });

    overlay.appendChild(modal);

    return {
        overlay,
        modal,
        open() {
            findHost(anchor).appendChild(overlay);
        },
        close() {
            overlay.remove();
        },
    };
}
