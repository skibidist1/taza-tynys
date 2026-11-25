import sys,os
from playwright.sync_api import sync_playwright
sub,out=sys.argv[1],sys.argv[2]
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1920,'height':1080})
    pg.goto('file://'+os.path.join(sub,'slides.html')); pg.wait_for_timeout(1000)
    n=pg.locator('.slide').count(); print('slides',n)
    # overflow check
    print(pg.evaluate('''[...document.querySelectorAll('.slide')].map((s,i)=>{let r=s.getBoundingClientRect();let bad=[...s.querySelectorAll('*')].filter(e=>{let q=e.getBoundingClientRect();return q.bottom>r.bottom-30||q.right>r.right+1}).map(e=>e.tagName+':'+(e.className||'')+':'+(e.innerText||'').slice(0,20));return i+1+' '+bad.slice(0,4).join('|')})'''))
    for i in range(n):
        pg.locator('.slide').nth(i).screenshot(path=f'{out}/slide_{i+1:02d}.png')
    pg.pdf(path=os.path.join(sub,'slides.pdf'),width='1920px',height='1080px',print_background=True,prefer_css_page_size=True)
    b.close()
