import subprocess
from segs import SEGS
tot=0;words=0
for n,t in SEGS:
    subprocess.run(['say','-v','Milena','-r','178','-o',n+'.aiff',t],check=True)
    d=float(subprocess.run(['/Users/zhumat/.local/bin/ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',n+'.aiff'],capture_output=True,text=True).stdout)
    tot+=d; words+=len(t.split()); print(n, round(d,1))
print('total',round(tot,1),'words',words)
