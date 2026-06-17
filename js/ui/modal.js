export function createModalShell({ width = 'min(720px,100%)' } = {}) {
    const overlay = document.createElement('div');
    overlay.style.cssText =
        'position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:9999;display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box;';

    const modal = document.createElement('div');
    modal.style.cssText =
        `background:#1e1e1e;border:1px solid #444;border-radius:8px;padding:18px;width:${width};max-height:calc(100vh - 48px);overflow-y:auto;color:#ddd;box-sizing:border-box;`;

    overlay.addEventListener('click', (event) => {
        if (event.target === overlay) overlay.remove();
    });

    overlay.appendChild(modal);

    return {
        overlay,
        modal,
        open() {
            document.body.appendChild(overlay);
        },
        close() {
            overlay.remove();
        },
    };
}
