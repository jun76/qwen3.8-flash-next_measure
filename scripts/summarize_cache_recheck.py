"""Summarize each cache-recheck cell and the paired Strata repeats without pooling different conditions."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics


def distribution(values):
    values=list(values)
    return {'n':len(values),'median':statistics.median(values),'min':min(values),'max':max(values)}


def summarize(rows):
    cells=defaultdict(list)
    seen=set()
    for row in rows:
        identity=(row['case_id'],row['request_in_process'])
        if identity in seen:
            raise ValueError('Duplicate request: '+str(identity))
        seen.add(identity)
        # In the pinned Generel fork, the first generated token comes from the
        # prompt batch. Its API rate counts predicted_n - 1 decode steps.
        timed_tokens=(max(0,row['timings']['predicted_n']-1)
                      if row['engine']=='llama_cpp' else row['output_tokens'])
        rate=timed_tokens/row['generation_seconds']
        if abs(rate-row['tokens_per_second'])>1e-6*max(1,rate):
            raise ValueError('Token/time ratio does not match rate: '+row['case_id'])
        if row['engine']=='strata' and row['reused_tokens']!=0:
            raise ValueError('Unexpected prompt reuse: '+row['case_id'])
        if row['engine']=='llama_cpp' and row['timings'].get('cache_n',0)!=0:
            raise ValueError('Unexpected prompt reuse: '+row['case_id'])
        key=(row['phase'],row['engine'],row['config_id'],row['input_kind'],row['cache_start'])
        cells[key].append(row)
    summaries=[]
    for key,items in sorted(cells.items()):
        phase,engine,config_id,input_kind,cache_start=key
        item=dict(zip(('phase','engine','config_id','input_kind','cache_start'),key))
        item.update(requests=len(items),repetitions=sorted(r['repetition'] for r in items),
                    finish_reasons=dict(Counter(r['finish_reason'] for r in items)),
                    cases=[r['case_id'] for r in items])
        for metric in ('tokens_per_second','output_tokens','prompt_tokens','generation_seconds','prefill_seconds','wall_seconds'):
            item[metric]=distribution(r[metric] for r in items)
        if engine=='strata':
            item['acceptance']=distribution(r['draft_accepted']/r['draft_offered'] for r in items if r['draft_offered'])
            item['cache_slots']=distribution(r['startup']['cache_slots'] for r in items)
        summaries.append(item)
    paired=[]
    by_case=defaultdict(dict)
    for row in rows:
        if row['engine']=='strata' and row['phase']=='fixed':
            if row['cache_start'] in by_case[row['case_id']]:
                raise ValueError('Duplicate pair member: '+row['case_id'])
            by_case[row['case_id']][row['cache_start']]=row
    for case_id,pair in sorted(by_case.items()):
        if set(pair)!={'fresh_process','same_input_repeat'}:
            raise ValueError('Incomplete paired measurement: '+case_id)
        fresh,warm=pair['fresh_process'],pair['same_input_repeat']
        if fresh['prompt_tokens']!=warm['prompt_tokens'] or fresh['max_tokens']!=warm['max_tokens']:
            raise ValueError('Paired input/limit mismatch: '+case_id)
        for hash_key in ('published_request_sha256','request_sha256'):
            if fresh.get(hash_key) and warm.get(hash_key) and fresh[hash_key]!=warm[hash_key]:
                raise ValueError('Paired request bodies differ: '+case_id)
        item={'case_id':case_id,'input_kind':fresh['input_kind'],'repetition':fresh['repetition'],
              'fresh_tps':fresh['tokens_per_second'],'warm_tps':warm['tokens_per_second'],
              'change_percent':100*(warm['tokens_per_second']/fresh['tokens_per_second']-1),
              'fresh_output_tokens':fresh['output_tokens'],'warm_output_tokens':warm['output_tokens'],
              'fresh_acceptance':fresh['draft_accepted']/fresh['draft_offered'],
              'warm_acceptance':warm['draft_accepted']/warm['draft_offered']}
        if fresh.get('semantic_output_sha256') and warm.get('semantic_output_sha256'):
            item['same_semantic_output']=fresh['semantic_output_sha256']==warm['semantic_output_sha256']
        paired.append(item)
    return {'requests':len(rows),'processes':len({r['case_id'] for r in rows}),
            'aggregation':'Median and observed minimum/maximum across the three requests in each cell; ranges are not confidence intervals.',
            'cells':summaries,'paired_strata_fixed':paired,
            'paired_change_percent':{kind:distribution(p['change_percent'] for p in paired if p['input_kind']==kind)
                                     for kind in sorted({p['input_kind'] for p in paired})}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,help='JSONL file produced by run_cache_recheck.py')
    parser.add_argument('--output',required=True,help='Destination summary JSON')
    args=parser.parse_args()
    rows=[json.loads(line) for line in Path(args.input).read_text(encoding='utf-8').splitlines() if line]
    result=summarize(rows)
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'requests':result['requests'],'processes':result['processes'],'cells':len(result['cells'])}))


if __name__=='__main__':
    main()
