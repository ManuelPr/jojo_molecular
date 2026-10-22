"""Read complete Kaggle status, including hidden rerun errors omitted by CSV."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from kaggle.api.kaggle_api_extended import KaggleApi


def read(submission_ref, output):
    api=KaggleApi();api.authenticate()
    submissions=api.competition_submissions('enveda-CASMI26-molecule-id-mass-spectra',page_size=20)
    values=[{'ref':str(s.ref),'date':str(s.date),'status':str(s.status),
             'public_score':s.public_score,'private_score':s.private_score,
             'error_description':s.error_description} for s in submissions]
    matches=[v for v in values if v['ref']==str(submission_ref)]
    if len(matches)!=1:
        raise ValueError('Submission not found uniquely in recent official history')
    report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'submission':matches[0]}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('ref');parser.add_argument('output');args=parser.parse_args()
    print(json.dumps(read(args.ref,args.output),indent=2))
