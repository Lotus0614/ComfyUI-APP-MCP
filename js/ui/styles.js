export function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
    })[char]);
}

export function mutedText(value) {
    return `<span style="${S.mutedText}">${escapeHtml(value)}</span>`;
}

export const S = {
    panel:
        'display:flex;flex-direction:column;gap:8px;max-height:480px;overflow:hidden;padding:2px 0 4px;',
    toolbar:
        'display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;',
    toolbarGroup:
        'display:flex;align-items:center;gap:6px;flex-wrap:wrap;min-width:0;',
    search:
        'width:160px;min-height:28px;padding:4px 8px;background:#181818;color:#ddd;border:1px solid #3a3a3a;border-radius:6px;box-sizing:border-box;outline:none;',
    list:
        'display:flex;flex-direction:column;gap:6px;overflow-y:auto;padding:1px 2px 2px;',
    row:
        'display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:start;padding:8px 9px;border:1px solid #333;border-radius:7px;background:#202020;min-width:0;',
    rowDisabled:
        'opacity:.64;background:#1b1b1b;',
    title:
        'font-size:12px;font-weight:650;line-height:1.35;color:#e6e6e6;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;',
    description:
        'font-size:11px;color:#858585;line-height:1.35;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere;',
    meta:
        'display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:7px;',
    badge:
        'display:inline-flex;align-items:center;gap:4px;min-height:18px;padding:1px 6px;border:1px solid #3b3b3b;border-radius:999px;background:#191919;color:#aaa;font-size:10px;line-height:1.2;white-space:nowrap;',
    badgeWarn:
        'border-color:#5b4630;background:#2a2118;color:#e0ad6a;',
    badgeOff:
        'border-color:#5a3434;background:#2a1b1b;color:#e28282;',
    actions:
        'display:flex;align-items:flex-start;justify-content:flex-end;gap:5px;flex-wrap:wrap;',
    btn:
        'padding:4px 9px;min-height:28px;cursor:pointer;border-radius:6px;border:1px solid #444;background:#2a2a2a;color:#ddd;font-size:11px;line-height:1.2;',
    primaryBtn:
        'border-color:#3f6547;background:#263a2b;color:#9ee5a8;',
    warnBtn:
        'border-color:#614a2c;background:#312414;color:#e4b272;',
    dangerBtn:
        'border-color:#663b3b;background:#351e1e;color:#f09999;',
    smallBtn:
        'padding:3px 7px;min-height:23px;cursor:pointer;font-size:10px;border-radius:5px;border:1px solid #3e3e3e;background:#242424;color:#d0d0d0;white-space:nowrap;',
    btnRow:
        'display:flex;flex-wrap:wrap;gap:6px;',
    status:
        'font-size:12px;color:#8f8f8f;min-height:18px;line-height:1.4;padding:0 2px;',
    empty:
        'color:#8b8b8b;font-size:12px;line-height:1.5;padding:16px;border:1px dashed #3a3a3a;border-radius:8px;background:#1b1b1b;text-align:center;',
    modalTitle:
        'margin:0;font-size:16px;line-height:1.35;color:#f0f0f0;overflow-wrap:anywhere;',
    modalSubtitle:
        'margin:5px 0 0;color:#a0a0a0;font-size:12px;line-height:1.5;overflow-wrap:anywhere;',
    descriptionBox:
        'height:88px;overflow-y:auto;padding:8px 9px;border:1px solid #333;border-radius:7px;background:#1a1a1a;color:#a0a0a0;font-size:11px;line-height:1.45;white-space:pre-wrap;overflow-wrap:anywhere;box-sizing:border-box;',
    modalHeader:
        'display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:14px;',
    footer:
        'display:flex;justify-content:flex-end;gap:8px;margin-top:16px;flex-wrap:wrap;',
    input:
        'width:100%;min-height:30px;padding:5px 9px;background:#181818;color:#ddd;border:1px solid #3a3a3a;border-radius:6px;box-sizing:border-box;outline:none;',
    label:
        'display:block;font-size:12px;color:#aaa;margin-bottom:6px;',
    dropdown:
        'display:none;position:fixed;max-height:260px;overflow-y:auto;background:#202020;border:1px solid #444;border-radius:8px;z-index:10001;box-shadow:0 12px 28px rgba(0,0,0,.4);',
    dropdownItem:
        'padding:8px 10px;cursor:pointer;font-size:12px;color:#ddd;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;',
    preview:
        'margin:10px 0 0;font-size:12px;color:#aaa;line-height:1.4;min-height:42px;padding:8px;border:1px solid #333;border-radius:7px;background:#1a1a1a;box-sizing:border-box;',
    previewGrid:
        'display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;margin-top:8px;',
    previewCard:
        'border:1px solid #333;border-radius:8px;background:#202020;padding:9px;min-width:0;',
    section:
        'font-size:12px;color:#bdbdbd;margin:14px 0 7px;font-weight:650;letter-spacing:.01em;',
    detailGrid:
        'display:flex;flex-direction:column;gap:6px;',
    detailRow:
        'display:flex;align-items:flex-start;justify-content:space-between;gap:10px;padding:7px 8px;border:1px solid #333;border-radius:7px;background:#202020;margin:0;min-width:0;',
    key:
        'min-width:0;font-size:12px;line-height:1.4;color:#e3e3e3;overflow-wrap:anywhere;',
    value:
        'font-size:11px;color:#929292;line-height:1.4;text-align:right;overflow-wrap:anywhere;max-width:60%;',
    mutedText:
        'color:#8f8f8f;font-size:11px;line-height:1.45;',
};
