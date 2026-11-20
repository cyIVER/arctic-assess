"""Current admission extension; no keys, self-approval, or moving-source defaults."""
import json
from pathlib import Path
from guest import need,pinned,PINS,HELPER

def require_current(c):
    need(c.get('source_profile')=='reviewed-environment-proxy-v2','new proxy source profile required')
    h=c['reviews']
    need(h['source']['sha256']!=PINS and h['helper']['sha256']!=HELPER,'stale original source/helper forbidden')
    need(h['host']['sha256']==h['source']['sha256'],'single exact source+host manifest required')
    lease=c.get('parent_scope_lease')
    need(isinstance(lease,dict) and set(lease)=={'handle','vm','created','deadline','lane'} and isinstance(lease['handle'],str) and 0<len(lease['handle'])<=256,'parent scope lease required')
    need(lease['vm']==c['vm'] and lease['created']==c['created'] and lease['deadline']==c['deadline'] and lease['lane']==c['lane'],'scope lease mismatch')
    for kind,v in h.items():
        review=json.loads(pinned(v['review_path'],v['review_sha256']))
        need(review.get('parent_scope_lease')==lease['handle'],'review not bound to parent scope lease')
        need(isinstance(review.get('code_review_handle'),str) and bool(review['code_review_handle']),'actual independent code-review handle missing')
    pf=c.get('preflight')
    need(isinstance(pf,dict) and set(pf)=={'path','sha256'},'independent default Docker preflight required')
    checkpoint=json.loads(pinned(pf['path'],pf['sha256']))
    need(checkpoint=={'status':'verified','requirement':'already-private-default-quiescent','vm':c['vm'],'created':c['created'],'deadline':c['deadline'],'parent_scope_lease':lease['handle'],'default_service_changes_owner':'parent'},'default Docker checkpoint not independently verified')
    # guard's independent fresh readback must corroborate this exact checkpoint.
    return checkpoint
