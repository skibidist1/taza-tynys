# Demo capture as a stream of real screenshots (Playwright screencast tears on scroll).
import time, json, subprocess, os, glob, shutil
from playwright.sync_api import sync_playwright
U='https://taza-tynys.vercel.app/?demo=winter'
FF='/Users/zhumat/.local/bin/ffmpeg'
def dur(n):
    return float(subprocess.run(['/Users/zhumat/.local/bin/ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',n+'.aiff'],capture_output=True,text=True).stdout)
CSS='nav.tabs,.tabs{position:static!important} html{scroll-behavior:auto!important}'
class R:
    def __init__(s,pg,d):
        s.pg=pg; s.d=d; s.fr=[]; s.t0=time.monotonic()
        shutil.rmtree(d,ignore_errors=True); os.makedirs(d)
    def snap(s):
        p=f'{s.d}/f{len(s.fr):04d}.png'; s.pg.screenshot(path=p); s.fr.append((p,time.monotonic()-s.t0))
    def hold(s,sec):
        s.snap(); end=time.monotonic()+sec
        while time.monotonic()<end: time.sleep(0.02)
    def scroll(s,y,sec=1.2):
        y0=s.pg.evaluate('window.scrollY'); n=max(1,int(sec/0.09))
        for i in range(1,n+1):
            k=i/n; e=k*k*(3-2*k)
            s.pg.evaluate(f'window.scrollTo(0,{y0+(y-y0)*e})'); s.snap()
    def click(s,sel,after=0.6):
        s.pg.click(sel); end=time.monotonic()+after
        while time.monotonic()<end: s.snap()
    def top(s,sel,off=16):
        return s.pg.evaluate(f'(()=>{{const e=document.querySelector("{sel}");return Math.max(0,e.getBoundingClientRect().top+window.scrollY-{off})}})()')
    def until(s,T):
        rem=T-(time.monotonic()-s.t0)
        if rem>0: s.hold(rem)
        s.snap()
def scene_now(r,D):
    r.hold(D*0.33); r.scroll(r.top('#place'),1.4); r.hold(D*0.22); r.scroll(0,1.4); r.until(D)
def scene_strip(r,D):
    r.scroll(r.top('.scale-card'),1.0); r.hold(2.0)
    step=(D-3.5)/5
    for i in [35,38,42,50,58]:
        t=time.monotonic(); r.click(f'#strip button[data-i="{i}"]',0.4)
        r.hold(max(0.1,step-(time.monotonic()-t)))
    r.until(D)
def scene_why(r,D):
    r.hold(0.6); r.click('[data-tab=why]',0.8); r.hold(0.8)
    r.click('text=Худший час прогноза',0.6); r.hold(D*0.42)
    r.scroll(r.top('#view-why .card:nth-of-type(2)',70),1.4); r.until(D)
def scene_school(r,D):
    r.hold(0.6); r.click('[data-tab=school]',0.6); r.hold(0.8)
    r.scroll(r.top('#view-school .card',0)+300,1.0)
    cb='#view-school input[type=checkbox] >> nth=2'
    r.click(cb,0.8); r.hold(0.6); r.click(cb,0.8); r.hold(2.0)
    r.scroll(r.top('#view-school .card:nth-of-type(2)',10),1.4); r.hold(1.6)
    r.click('text=Скопировать на русском',0.6); r.hold(1.4)
    r.scroll(r.pg.evaluate('window.scrollY')+330,1.2); r.until(D)
def scene_honest(r,D):
    r.hold(0.5); r.click('[data-tab=honest]',0.6); r.hold(0.6)
    r.scroll(r.top('#view-honest .card:nth-of-type(3)',10),1.4); r.hold(1.5)
    r.scroll(r.pg.evaluate('window.scrollY')+330,1.6); r.until(D)
SC=[('s3_now',scene_now,None),('s4_strip',scene_strip,None),('s5_why',scene_why,None),('s6_school',scene_school,None),('s7_honest',scene_honest,8.0)]
with sync_playwright() as p:
    b=p.chromium.launch()
    for name,fn,fixed in SC:
        D=fixed or dur(name)+0.8
        ctx=b.new_context(viewport={'width':1024,'height':576},device_scale_factor=1.25,color_scheme='light',permissions=['clipboard-read','clipboard-write'])
        pg=ctx.new_page(); pg.goto(U,wait_until='networkidle'); pg.add_style_tag(content=CSS); pg.wait_for_timeout(2500)
        r=R(pg,f'frames_{name}'); fn(r,D); ctx.close()
        lines=[]
        for i,(f,t) in enumerate(r.fr):
            nt=r.fr[i+1][1] if i+1<len(r.fr) else t+0.04
            lines.append(f"file '{os.path.abspath(f)}'\nduration {max(0.001,nt-t):.4f}\n")
        lines.append(f"file '{os.path.abspath(r.fr[-1][0])}'\n")
        open(f'frames_{name}.txt','w').write(''.join(lines))
        subprocess.run([FF,'-y','-v','error','-f','concat','-safe','0','-i',f'frames_{name}.txt','-vf','scale=1280:720,fps=30,format=yuv420p','-c:v','libx264','-crf','18',f'demo_{name}.mp4'],check=True)
        print(name, 'frames',len(r.fr),'span',round(r.fr[-1][1],2),'D',round(D,2))
    b.close()
