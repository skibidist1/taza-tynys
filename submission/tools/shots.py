import sys
from playwright.sync_api import sync_playwright
out=sys.argv[1]
U='https://taza-tynys.vercel.app/'
with sync_playwright() as p:
    b=p.chromium.launch()
    ctx=b.new_context(viewport={'width':390,'height':844},device_scale_factor=2,color_scheme='light')
    pg=ctx.new_page()
    pg.goto(U+'?demo=winter',wait_until='networkidle'); pg.wait_for_timeout(3500); pg.add_style_tag(content='nav.tabs,.tabs{position:static!important}')
    pg.screenshot(path=f'{out}/phone_winter_top.png')
    pg.locator('#hero').screenshot(path=f'{out}/hero_winter.png')
    pg.locator('.scale-card').screenshot(path=f'{out}/strip_winter.png')
    pg.locator('#actions').screenshot(path=f'{out}/actions_winter.png')
    pg.click('[data-tab=why]'); pg.wait_for_timeout(800)
    pg.click('text=Худший час прогноза'); pg.wait_for_timeout(800)
    pg.locator('#view-why .card').nth(0).screenshot(path=f'{out}/why_gauge.png')
    pg.locator('#view-why .card').nth(1).screenshot(path=f'{out}/why_factors.png')
    pg.click('[data-tab=school]'); pg.wait_for_timeout(800)
    pg.locator('#view-school .card').nth(0).screenshot(path=f'{out}/school_lessons.png')
    pg.locator('#view-school .card').nth(1).screenshot(path=f'{out}/school_announce.png')
    pg.click('[data-tab=honest]'); pg.wait_for_timeout(800)
    pg.locator('#view-honest .card').nth(2).screenshot(path=f'{out}/honest_tables.png')
    # live
    pg2=ctx.new_page(); pg2.goto(U,wait_until='networkidle'); pg2.wait_for_timeout(8000); pg2.add_style_tag(content='nav.tabs,.tabs{position:static!important}')
    pg2.screenshot(path=f'{out}/phone_live_top.png')
    pg2.locator('#place').screenshot(path=f'{out}/map_live.png')
    pg2.locator('#hero').screenshot(path=f'{out}/hero_live.png')
    print('LIVE', pg2.inner_text('#hero')[:400])
    # desktop
    d=b.new_context(viewport={'width':1440,'height':900},device_scale_factor=1,color_scheme='light').new_page()
    d.goto(U+'?demo=winter',wait_until='networkidle'); d.wait_for_timeout(3500)
    d.screenshot(path=f'{out}/desktop_winter.png')
    d.click('[data-tab=school]'); d.wait_for_timeout(800); d.screenshot(path=f'{out}/desktop_school.png')
    b.close()
