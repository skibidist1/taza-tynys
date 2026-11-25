import json,subprocess,sys
FF='/Users/zhumat/.local/bin/ffmpeg'; FP='/Users/zhumat/.local/bin/ffprobe'
out=sys.argv[1]
def dur(f): return float(subprocess.run([FP,'-v','error','-show_entries','format=duration','-of','csv=p=0',f],capture_output=True,text=True).stdout)
plan=[('s1_hook','slide','../slide_03.png'),('s2_problem','slide','../slide_02.png'),('s3_now','rec',None),('s4_strip','rec',None),('s5_why','rec',None),('s6_school','rec',None),('s7_honest','rec',None),('s8_evidence','slide','../slide_07.png'),('s9_scale','slide','../slide_09.png'),('s10_cta','slide','../slide_01.png')]
parts=[];tot=0
for n,kind,src in plan:
    a=dur(n+'.aiff'); D=a+0.8
    if n=='s7_honest': D=8.0
    if n=='s10_cta': D=a+1.5
    aud=['-i',n+'.aiff']
    af=f'adelay=300|300,apad,atrim=0:{D:.3f},aformat=sample_rates=48000:channel_layouts=stereo'
    vf='scale=1280:720:flags=lanczos,format=yuv420p,fps=30'
    o=f'part_{n}.mp4'
    if kind=='slide':
        cmd=[FF,'-y','-v','error','-loop','1','-t',f'{D:.3f}','-i',src]+aud+['-filter_complex',f'[0:v]{vf}[v];[1:a]{af}[a]','-map','[v]','-map','[a]','-t',f'{D:.3f}']
    else:
        cmd=[FF,'-y','-v','error','-i',f'demo_{n}.mp4']+aud+['-filter_complex',f'[0:v]{vf},tpad=stop_mode=clone:stop_duration=3[v];[1:a]{af}[a]','-map','[v]','-map','[a]','-t',f'{D:.3f}']
    cmd+=['-c:v','libx264','-preset','medium','-crf','20','-c:a','aac','-b:a','160k','-ar','48000',o]
    subprocess.run(cmd,check=True); parts.append(o); tot+=D; print(n,round(D,2))
open('list.txt','w').write(''.join(f"file '{p}'\n" for p in parts))
subprocess.run([FF,'-y','-v','error','-f','concat','-safe','0','-i','list.txt','-c:v','libx264','-crf','21','-preset','medium','-c:a','aac','-b:a','160k','-movflags','+faststart',out],check=True)
print('planned',round(tot,2),'actual',dur(out))
