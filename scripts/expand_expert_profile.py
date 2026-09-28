"""Preserve the original expert ranking and append missing IDs round-robin by layer."""
import argparse, hashlib, json, struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',default='vendor/strata/data/expert-profile.bin')
parser.add_argument('--output',default='artifacts/strata/expert-profile-expanded.bin')
args=parser.parse_args()
source=ROOT/args.source
output=ROOT/args.output
blob=source.read_bytes()
magic,version,layers,experts,want,count=struct.unpack_from('<4s5I',blob)
if magic!=b'STRP' or len(blob)<24+count*4: raise ValueError('Invalid STRP header')
original=list(struct.iter_unpack('<HH',blob[24:24+count*4]))
if len(set(original))!=len(original) or any(l>=layers or e>=experts for l,e in original): raise ValueError('Invalid expert IDs')
seen=set(original)
remaining=[[e for e in range(experts) if (l,e) not in seen] for l in range(layers)]
ranked=original+[(l,missing[i]) for i in range(max(map(len,remaining),default=0)) for l,missing in enumerate(remaining) if i<len(missing)]
inverse=[0]*(layers*experts)
for i,(l,e) in enumerate(ranked): inverse[l*experts+e]=i
expanded=struct.pack('<4s5I',magic,version,layers,experts,len(ranked),len(ranked))
expanded+=b''.join(struct.pack('<HH',*pair) for pair in ranked)
expanded+=struct.pack('<'+str(len(inverse))+'I',*inverse)
output.parent.mkdir(parents=True,exist_ok=True)
output.write_bytes(expanded)
record={'source':args.source,'output':args.output,'source_sha256':hashlib.sha256(blob).hexdigest(),
        'output_sha256':hashlib.sha256(expanded).hexdigest(),'original_pairs':len(original),'expanded_pairs':len(ranked),
        'method':'Original order retained; missing experts appended round-robin by layer. Appended order is not a measured routing-frequency ranking.'}
output.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record))
