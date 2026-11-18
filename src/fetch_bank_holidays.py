"""Refresh the real GOV.UK bank-holiday API; keep labelled offline fixture if request fails."""
import json, urllib.request
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'data'/'external'/'uk_bank_holidays.json'
URL='https://www.gov.uk/bank-holidays.json'

def refresh():
    try:
        req=urllib.request.Request(URL,headers={'User-Agent':'WarehousePortfolioLearningProject/1.0'})
        with urllib.request.urlopen(req,timeout=12) as response:
            data=json.load(response)
        events=data['england-and-wales']['events']
        if not events or any('date' not in e for e in events): raise ValueError('API schema unexpected')
        info={'source':URL,'source_type':'live_public_api','retrieved_utc':datetime.now(timezone.utc).isoformat(),
              'region':'england-and-wales','events':[{'date':e['date'],'title':e['title']} for e in events]}
        DEST.write_text(json.dumps(info,indent=2),encoding='utf-8')
        print(f'Refreshed {len(events)} real GOV.UK bank-holiday events: {DEST}')
    except Exception as ex:
        print(f'Cannot refresh online: {ex}. Keeping clearly labelled offline reference fixture: {DEST}')
        if not DEST.exists(): raise RuntimeError('Missing offline fixture. Re-download project zip.')
if __name__=='__main__':refresh()
