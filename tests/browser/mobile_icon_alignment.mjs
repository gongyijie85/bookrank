import assert from 'node:assert/strict';

// Run with a CUA tab bound to the actual mobile homepage. This uses rendered
// geometry and real keyboard scrolling, not a DOM stub or inferred CSS layout.
export async function measureMobileIconAlignment(tab) {
    return tab.playwright.evaluate(() => {
        const ids = ['m-search-toggle', 'm-theme-toggle', 'm-lang-globe'];
        const buttons = ids.map(id => {
            const button = document.getElementById(id);
            if (!button) throw new Error(`Missing mobile control: ${id}`);
            const rect = button.getBoundingClientRect();
            const icon = button.querySelector('svg').getBoundingClientRect();
            const center = { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
            const hit = document.elementFromPoint(center.x, center.y);
            return {
                id, x: rect.x, y: rect.y, width: rect.width, height: rect.height,
                iconOffsetX: icon.x + icon.width / 2 - center.x,
                iconOffsetY: icon.y + icon.height / 2 - center.y,
                hitTarget: hit === button || button.contains(hit),
            };
        });
        const tops = buttons.map(button => button.y);
        return {
            viewport: { width: innerWidth, height: innerHeight }, scrollY, buttons,
            topSpread: Math.max(...tops) - Math.min(...tops),
        };
    });
}

export function assertMobileIconAlignment(sample) {
    assert.ok(sample.topSpread <= 1, `mobile icons differ vertically by ${sample.topSpread}px at scrollY=${sample.scrollY}`);
    for (const button of sample.buttons) {
        assert.ok(button.width >= 44 && button.height >= 44, `${button.id}: touch target`);
        assert.ok(button.x >= 0 && button.x + button.width <= sample.viewport.width, `${button.id}: viewport bounds`);
        assert.ok(button.y >= 0 && button.y + button.height <= sample.viewport.height, `${button.id}: vertical bounds`);
        assert.ok(Math.abs(button.iconOffsetX) <= 1 && Math.abs(button.iconOffsetY) <= 1, `${button.id}: icon center`);
        assert.ok(button.hitTarget, `${button.id}: blocked center`);
    }
    for (let index = 1; index < sample.buttons.length; index++) {
        const gap = sample.buttons[index].x - sample.buttons[index - 1].x - sample.buttons[index - 1].width;
        assert.ok(gap >= 7 && gap <= 9, `mobile action gap is ${gap}px`);
    }
}

export async function checkMobileIconAlignment(tab) {
    await tab.pressKey(null, 'Control+Home');
    await tab.getAXState({ emit: false });
    const top = await measureMobileIconAlignment(tab);
    assertMobileIconAlignment(top);
    await tab.pressKey(null, 'ArrowDown');
    await tab.getAXState({ emit: false });
    const scrolled = await measureMobileIconAlignment(tab);
    assert.ok(scrolled.scrollY > top.scrollY, 'fixture must actually scroll to exercise the defect');
    assertMobileIconAlignment(scrolled);
    return { top, scrolled };
}
