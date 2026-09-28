"""Replay recorded requests with repository-relative assets. Python 3.10+; no tool execution."""
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
TIMING = re.compile(r'strata serve: prompt (\d+) tokens = (\d+) reused \+ (\d+) read in ([\d.]+) ms '
                    r'\(([\d.]+) tok/s\), (\d+) generated in ([\d.]+) ms \(([\d.]+) tok/s\), drafts accepted (\d+) of (\d+)')

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def save(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def local_path(value):
    path = Path(value).expanduser()
    return (ROOT/path).resolve() if not path.is_absolute() else path.resolve()

def repo_file(value):
    path = local_path(value)
    if not path.is_relative_to(ROOT):
        raise ValueError('Plan and fixture paths must stay inside this repository.')
    return path

def paths_for(path):
    paths = load(ROOT/'configs/paths.example.json')
    if path:
        paths.update(load(local_path(path)))
    return {key:str(local_path(value)) for key,value in paths.items() if value}

def expand(value, paths):
    if isinstance(value,dict): return {key:expand(item,paths) for key,item in value.items()}
    if isinstance(value,list): return [expand(item,paths) for item in value]
    if isinstance(value,str):
        return re.sub(r'\{([a-z0-9_]+)\}',lambda m:paths[m[1]],value)
    return value

def option(args, flag, value):
    if flag in args:
        index = args.index(flag)
        del args[index:index+2]
    if value is not None: args.extend([flag,str(value)])

def http(base, endpoint, payload=None, timeout=5):
    body = json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None
    req = urllib.request.Request(base+endpoint,data=body,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as response:
        return json.load(response)

def gpu():
    try:
        result = subprocess.run(['nvidia-smi','--query-gpu=memory.used,memory.free,utilization.gpu,temperature.gpu',
                                 '--format=csv,noheader,nounits'],capture_output=True,text=True,
                                creationflags=NO_WINDOW,timeout=10,check=True)
        return [dict(zip(('used_mib','free_mib','utilization_percent','temperature_c'),
                         [int(v.strip()) for v in line.split(',')])) for line in result.stdout.strip().splitlines()]
    except (OSError,ValueError,subprocess.SubprocessError):
        return None

def port_open(port):
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(('127.0.0.1',port))==0

def environment(paths, use_runtime=False):
    env = dict(os.environ)
    env.update(PYTHONUTF8='1',PYTHONUNBUFFERED='1')
    for name in ('STRATA_DEBUG','STRATA_TRACE','STRATA_API_KEY'):
        env.pop(name,None)
    directories = []
    if use_runtime and paths.get('cuda_runtime') and Path(paths['cuda_runtime']).exists():
        directories.append(paths['cuda_runtime'])
    if env.get('CUDA_PATH'):
        for suffix in ('bin','bin/x64'):
            candidate = Path(env['CUDA_PATH'])/suffix
            if candidate.exists(): directories.append(str(candidate))
    env['PATH'] = os.pathsep.join(directories+[env.get('PATH','')])
    return env

def build_case(engine, identifier, paths, folder, port):
    if engine=='strata':
        case = load(ROOT/'configs/strata.json')[identifier]
        config = load(ROOT/'configs/strata-base.json')
        for flag,value in case.get('overrides',{}).items(): option(config['args'],flag,value)
        config['args'].extend(case.get('flags',[]))
        config = expand(config,paths)
        config.update(port=port,log=str(folder/'engine.log'))
        command = [paths['strata_python'],str(Path(paths['strata_root'])/'serve/server.py'),
                   '--engine','strata','--config',str(folder/'server-config.json'),'--host','127.0.0.1','--port',str(port)]
        return config,command,config['cwd'],config['model_name']
    config = expand(copy.deepcopy(load(ROOT/'configs/llama_cpp.json')[identifier]),paths)
    option(config['args'],'--host','127.0.0.1')
    option(config['args'],'--port',port)
    command = [config['executable']]+config['args']
    model = config['args'][config['args'].index('--alias')+1]
    return config,command,str(ROOT),model

def stop_owned(process):
    if process.poll() is not None: return
    if os.name=='nt':
        subprocess.run(['taskkill.exe','/PID',str(process.pid),'/T','/F'],capture_output=True,creationflags=NO_WINDOW)
    else:
        os.killpg(process.pid,signal.SIGTERM)
    try: process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        if os.name!='nt': os.killpg(process.pid,signal.SIGKILL)
        else: process.kill()
        process.wait(timeout=10)

def measure(engine, group, measurement, number, base, model, folder):
    payload = load(repo_file(measurement['request_file']))
    payload.update(copy.deepcopy(measurement.get('overrides',{})))
    payload.update(model=model,stream=False,cache_prompt=False)
    # These are prerecorded prompt/tool definitions only. No returned tool is invoked.
    name = re.sub(r'[^A-Za-z0-9_.-]','_',measurement.get('name',f'request-{number}'))
    prefix = folder/f'{number:02d}-{name}'
    save(prefix.with_suffix('.request.json'),payload)
    log = folder/('engine.log' if engine=='strata' else 'server.stderr.log')
    before = log.stat().st_size if log.exists() else 0
    if engine=='strata':
        if http(base,'/status').get('busy'): raise RuntimeError('Server is busy.')
    elif any(slot.get('is_processing') for slot in http(base,'/slots')):
        raise RuntimeError('Server is busy.')
    started = time.perf_counter()
    response = http(base,'/v1/chat/completions',payload,timeout=1800)
    wall = time.perf_counter()-started
    save(prefix.with_suffix('.response.json'),response)
    result = {'engine':engine,'config_id':group['id'],'historical_run':measurement.get('historical_run'),
              'name':name,'request_in_process':number,'max_tokens':payload['max_tokens'],
              'thinking':payload.get('chat_template_kwargs',{}).get('enable_thinking',True),
              'input_kind':'harness' if payload.get('tools') else 'direct',
              'temperature':payload.get('temperature'),'usage':response.get('usage'),
              'wall_seconds':wall,'finish_reason':response['choices'][0]['finish_reason'],
              'request_sha256':hashlib.sha256(prefix.with_suffix('.request.json').read_bytes()).hexdigest(),
              'files':prefix.relative_to(ROOT).as_posix(),'gpu_after':gpu()}
    if engine=='strata':
        matches = list(TIMING.finditer(log.read_bytes()[before:].decode('utf-8',errors='replace')))
        if not matches: raise RuntimeError('Strata engine timing line is missing.')
        p,reused,fresh,pp_ms,pp_rate,n,gen_ms,rate,accepted,offered = matches[-1].groups()
        result.update(prompt_tokens=int(p),reused_tokens=int(reused),output_tokens=int(n),
                      prefill_seconds=float(pp_ms)/1000,generation_seconds=float(gen_ms)/1000,
                      tokens_per_second=int(n)*1000/float(gen_ms),engine_reported_tps=float(rate),
                      draft_accepted=int(accepted),draft_offered=int(offered),effective_sampling='greedy',
                      engine_timing_line=matches[-1].group(0))
    else:
        timing = response.get('timings')
        if not timing: raise RuntimeError('llama.cpp returned no timing statistics.')
        result.update(timings=timing,prompt_tokens=response['usage']['prompt_tokens'],
                      output_tokens=response['usage']['completion_tokens'],
                      prefill_seconds=timing['prompt_ms']/1000,generation_seconds=timing['predicted_ms']/1000,
                      tokens_per_second=timing['predicted_per_second'])
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',required=True,help='Repository-relative plan JSON')
    parser.add_argument('--configs',help='Comma-separated setting IDs to retain, including their repeats')
    parser.add_argument('--paths',default='configs/paths.local.json')
    parser.add_argument('--port',type=int,help='Default: llama.cpp 8081, Strata 8082')
    parser.add_argument('--dry-run',action='store_true',help='Print resolved commands; no servers or requests')
    parser.add_argument('--startup-timeout',type=int,default=360)
    parser.add_argument('--min-free-vram-mib',type=int,default=8192,help='Pre-start guard on GPU0; 0 disables')
    args = parser.parse_args()
    plan = load(repo_file(args.plan))
    engine = plan['engine']
    if engine not in ('strata','llama_cpp'): parser.error('Unknown engine')
    paths = paths_for(args.paths if local_path(args.paths).exists() else None)
    groups = plan['cases']
    if args.configs:
        selected = set(args.configs.split(','))
        unknown = selected-{g['id'] for g in groups}
        if unknown: parser.error(f'IDs not present in plan: {sorted(unknown)}')
        groups = [g for g in groups if g['id'] in selected]
    if not groups: parser.error('No cases selected')
    port = args.port or (8082 if engine=='strata' else 8081)
    base = f'http://127.0.0.1:{port}'
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output = ROOT/'runs'/f'{stamp}-{engine}'
    if not args.dry_run:
        output.mkdir(parents=True)
        save(output/'plan.json',{'engine':engine,'cases':groups})
    print(json.dumps({'engine':engine,'processes':len(groups),'requests':sum(len(g['requests']) for g in groups),'dry_run':args.dry_run}),flush=True)
    for group_number,group in enumerate(groups,1):
        folder = output/f'{group_number:02d}-{group["id"]}'
        config,command,cwd,model = build_case(engine,group['id'],paths,folder,port)
        if args.dry_run:
            print(json.dumps({'id':group['id'],'command':[x.replace(str(ROOT),'.') for x in command],
                              'server_config':config,'requests':group['requests']},ensure_ascii=False))
            continue
        if port_open(port): raise RuntimeError(f'Port {port} is occupied. No existing process was stopped.')
        for other in ({8080,8081,8082}-{port}):
            if not port_open(other): continue
            try: health=http(f'http://127.0.0.1:{other}','/health',timeout=2)
            except (OSError,ValueError): continue
            if health.get('status')=='ok':
                raise RuntimeError(f'Another server is active on port {other}. Stop it before benchmarking.')
        before_gpu=gpu()
        if before_gpu and args.min_free_vram_mib and before_gpu[0]['free_mib']<args.min_free_vram_mib:
            raise RuntimeError('Insufficient free VRAM before startup; release the other GPU workload first.')
        folder.mkdir(parents=True)
        save(folder/'server-config.json',config)
        save(folder/'case.json',group)
        started=time.perf_counter()
        with (folder/'server.stdout.log').open('w',encoding='utf-8') as stdout, (folder/'server.stderr.log').open('w',encoding='utf-8') as stderr:
            process=subprocess.Popen(command,cwd=cwd,env=environment(paths,use_runtime=engine=='llama_cpp' and group['id'].startswith('U')),stdout=stdout,stderr=stderr,
                                     creationflags=NO_WINDOW,start_new_session=os.name!='nt')
            try:
                deadline=time.monotonic()+args.startup_timeout
                while time.monotonic()<deadline:
                    if process.poll() is not None: raise RuntimeError(f'Server exited with code {process.returncode}; see {folder.name}/server.stderr.log')
                    try:
                        health=http(base,'/health',timeout=2)
                        if health.get('status')=='ok': break
                    except (OSError,ValueError): pass
                    time.sleep(1)
                else: raise TimeoutError('Server startup timed out')
                startup={'seconds':time.perf_counter()-started,'health':health,'gpu':gpu()}
                if engine=='strata':
                    text=(folder/'engine.log').read_text(encoding='utf-8',errors='replace')
                    for key,pattern in [('cache_slots',r'expert cache (\d+) slots'),('cache_gib',r'expert cache \d+ slots, ([\d.]+) GiB'),('pool_workers',r'(\d+) expert-pool workers')]:
                        match=re.search(pattern,text); startup[key]=float(match[1]) if match else None
                save(folder/'startup.json',startup)
                if startup['gpu'] and startup['gpu'][0]['free_mib']<512:
                    raise RuntimeError('Less than 512 MiB VRAM remains after startup; skipped generation.')
                for number,measurement in enumerate(group['requests'],1):
                    result=measure(engine,group,measurement,number,base,model,folder)
                    result['startup']=startup
                    with (output/'results.jsonl').open('a',encoding='utf-8') as handle: handle.write(json.dumps(result,ensure_ascii=False)+'\n')
                    print(json.dumps({k:result[k] for k in ('config_id','name','output_tokens','tokens_per_second','finish_reason')},ensure_ascii=False),flush=True)
            except BaseException as exc:
                save(folder/'failure.json',{'error':str(exc),'config_id':group['id']})
                raise
            finally:
                stop_owned(process)
                time.sleep(1)
    if not args.dry_run: print('Saved: '+output.relative_to(ROOT).as_posix())

if __name__=='__main__': main()
