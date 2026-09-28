"""Repeat direct/Harness measurements from fresh processes; preserve paired warm-cache controls."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time

import run_benchmarks as bench


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def hardware_sample():
    fields = ('used_mib', 'free_mib', 'utilization_percent', 'temperature_c',
              'sm_clock_mhz', 'memory_clock_mhz', 'power_watts')
    command = ['nvidia-smi', '--query-gpu=memory.used,memory.free,utilization.gpu,'
               'temperature.gpu,clocks.sm,clocks.mem,power.draw', '--format=csv,noheader,nounits']
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10,
                                check=True, creationflags=bench.NO_WINDOW)
        return [dict(zip(fields, [float(x.strip()) for x in line.split(',')]))
                for line in result.stdout.strip().splitlines()]
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def sample_loop(output, state, stop):
    while not stop.is_set():
        record = {'utc': utc_now(), **dict(state), 'gpu': hardware_sample()}
        with (output/'hardware.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record)+'\n')
        stop.wait(10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', default='plans/cache-recheck.json')
    parser.add_argument('--paths', default='configs/paths.local.json')
    parser.add_argument('--output', required=True, help='Repository-relative directory under runs/')
    parser.add_argument('--start-at', type=int, default=1, help='One-based process group; use a new output directory for a resumed subset')
    parser.add_argument('--stop-after', type=int, help='Last one-based process group')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    plan_path = bench.repo_file(args.plan)
    plan = bench.load(plan_path)
    paths = bench.paths_for(args.paths if bench.local_path(args.paths).exists() else None)
    output = bench.repo_file(args.output)
    if not output.is_relative_to(bench.ROOT/'runs'):
        raise ValueError('Raw measurements must be saved under runs/.')
    groups = [(i, g) for i, g in enumerate(plan['cases'], 1)
              if i >= args.start_at and (args.stop_after is None or i <= args.stop_after)]
    if not args.dry_run and output.exists():
        raise FileExistsError('Use a new output directory; existing results are never overwritten.')
    if args.dry_run:
        for i, group in groups:
            config, command, cwd, model = bench.build_case(group['engine'], group['id'], paths,
                                                          output/group['case_id'], group['port'])
            for request in group['requests']:
                bench.load(bench.repo_file(request['request_file']))
            if not Path(command[0]).is_file():
                raise FileNotFoundError(command[0])
        print(json.dumps({'processes':len(groups),'requests':sum(len(g['requests']) for _,g in groups),
                          'plan_sha256':hashlib.sha256(plan_path.read_bytes()).hexdigest()}))
        return
    output.mkdir(parents=True)
    bench.save(output/'plan.json', plan)
    bench.save(output/'execution.json', {'started_utc':utc_now(),'start_at':args.start_at,
                                       'stop_after':args.stop_after,'plan_sha256':hashlib.sha256(plan_path.read_bytes()).hexdigest()})
    state = {'case_id':None,'phase':'preparation'}
    stop = threading.Event()
    monitor = threading.Thread(target=sample_loop,args=(output,state,stop),daemon=True)
    monitor.start()
    try:
        for index, group in groups:
            engine, port = group['engine'], group['port']
            folder = output/group['case_id']
            state.update(case_id=group['case_id'],phase='startup')
            for occupied in (8080,8081,8082):
                if bench.port_open(occupied):
                    raise RuntimeError(f'Port {occupied} is occupied; stop other inference servers first.')
            before_gpu = bench.gpu()
            if before_gpu and before_gpu[0]['free_mib'] < 24000:
                raise RuntimeError('Less than 24,000 MiB VRAM free before startup; another workload may be active.')
            folder.mkdir()
            config, command, cwd, model = bench.build_case(engine,group['id'],paths,folder,port)
            bench.save(folder/'server-config.json',config)
            bench.save(folder/'case.json',group)
            print(json.dumps({'event':'start','case':group['case_id'],'process':index,
                              'engine':engine,'phase':group['phase'],'input':group['input_kind']},ensure_ascii=False),flush=True)
            started = time.perf_counter()
            base = f'http://127.0.0.1:{port}'
            with (folder/'server.stdout.log').open('w',encoding='utf-8') as stdout, (folder/'server.stderr.log').open('w',encoding='utf-8') as stderr:
                process = subprocess.Popen(command,cwd=cwd,env=bench.environment(paths),stdout=stdout,stderr=stderr,
                                           creationflags=bench.NO_WINDOW,start_new_session=os.name!='nt')
                try:
                    deadline = time.monotonic()+600
                    while time.monotonic()<deadline:
                        if process.poll() is not None:
                            raise RuntimeError(f'Server exited with code {process.returncode}')
                        try:
                            health = bench.http(base,'/health',timeout=2)
                            if health.get('status')=='ok':
                                break
                        except (OSError,ValueError):
                            pass
                        time.sleep(1)
                    else:
                        raise TimeoutError('Server startup timed out')
                    startup = {'seconds':time.perf_counter()-started,'health':health,
                               'gpu':bench.gpu(),'gpu_before_start':before_gpu,'pid':process.pid}
                    if engine=='strata':
                        text=(folder/'engine.log').read_text(encoding='utf-8',errors='replace')
                        for key,pattern in [('cache_slots',r'expert cache (\d+) slots'),
                                            ('cache_gib',r'expert cache \d+ slots, ([\d.]+) GiB'),
                                            ('pool_workers',r'(\d+) expert-pool workers')]:
                            match=re.search(pattern,text)
                            startup[key]=float(match[1]) if match else None
                    bench.save(folder/'startup.json',startup)
                    if startup['gpu'] and startup['gpu'][0]['free_mib']<512:
                        raise RuntimeError('Less than 512 MiB VRAM remains after startup')
                    group_results=[]
                    for number, request in enumerate(group['requests'],1):
                        state.update(phase='request',request_in_process=number)
                        request_started=utc_now()
                        result=bench.measure(engine,group,request,number,base,model,folder)
                        result.update(case_id=group['case_id'],phase=group['phase'],
                                      repetition=group['repetition'],cache_start='fresh_process' if number==1 else 'same_input_repeat',
                                      started_utc=request_started,finished_utc=utc_now(),startup=startup)
                        result['input_kind']=group['input_kind']
                        if result.get('draft_offered'):
                            result['acceptance']=result['draft_accepted']/result['draft_offered']
                        if engine=='strata' and result['reused_tokens']!=0:
                            raise RuntimeError('Unexpected prompt-cache reuse')
                        bench.save(folder/f'{number:02d}-metrics.json',result)
                        group_results.append(result)
                        with (output/'results.jsonl').open('a',encoding='utf-8') as handle:
                            handle.write(json.dumps(result,ensure_ascii=False)+'\n')
                        print(json.dumps({k:result.get(k) for k in ['case_id','name','request_in_process','output_tokens',
                                                                 'tokens_per_second','acceptance','finish_reason']},ensure_ascii=False),flush=True)
                    bench.save(folder/'completed.json',{'finished_utc':utc_now(),'requests':len(group_results)})
                except BaseException as exc:
                    bench.save(folder/'failure.json',{'error':str(exc),'case_id':group['case_id'],'utc':utc_now()})
                    raise
                finally:
                    state['phase']='shutdown'
                    bench.stop_owned(process)
            time.sleep(3)
        bench.save(output/'completed.json',{'finished_utc':utc_now(),'processes':len(groups)})
    finally:
        stop.set()
        monitor.join(timeout=15)
    print('Saved: '+output.relative_to(bench.ROOT).as_posix(),flush=True)


if __name__=='__main__':
    main()
