export function createModalShell({ width = 'min(720px,100%)' } = {}) {
    const overlay = document.createElement('div');
    overlay.style.cssText =
        'position:fixed;inset:0;background:rgba(0,0,0,0.62);z-index:9999;display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box;backdrop-filter:blur(2px);';

    const modal = document.createElement('div');
    modal.style.cssText =
        `background:#1f1f1f;border:1px solid #3d3d3d;border-radius:10px;padding:18px;width:${width};max-height:calc(100vh - 48px);overflow-y:auto;color:#ddd;box-sizing:border-box;box-shadow:0 18px 46px rgba(0,0,0,.45);`;

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
