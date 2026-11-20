import pathlib,json,hashlib,collections,datetime,decimal
R=pathlib.Path('/home/iveri/work/vindler-e2.SftLYa2R/continuation');O=pathlib.Path(__file__).parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads((R/p).read_text())
m=load('artex-worker-assessment-runner/runner-source-manifest.json'); root=R/'artex-worker-assessment-runner'
runner={'declared':len(m),'verified':0,'changed':[],'missing':[]}
for k,v in m.items():
 p=root/k
 if not p.is_file():runner['missing'].append(k)
 elif sha(p)==v:runner['verified']+=1
 else:runner['changed'].append(k)
counts=[]
for fn in ['20261119-215904-3998898.log','20261119-215926-3999758.log']:
 events=[json.loads(l) for l in (R/'artex-worker-admission/receipts'/fn).read_text().splitlines() if l.startswith('{')]
 terminal=[x for x in events if x.get('Test') and x['Action'] in ['pass','skip','fail']]
 skips=[{'test':x['Test'],'reason':''.join(e.get('Output','') for e in events if e.get('Test')==x['Test'] and e['Action']=='output')} for x in terminal if x['Action']=='skip']
 counts.append({'path':fn,'counts':dict(collections.Counter(x['Action'] for x in terminal)),'package_terminals':[x['Action'] for x in events if not x.get('Test') and x['Action'] in ['pass','fail']],'skips':skips})
orig=load('artex-native-app-final-build/guest-static-assets.json');cur=load('artex-ui-asset-final/source-inventory.json')
receipt=load('artex-ui-asset-final/local-build-receipt.json'); source=load('artex-worker-admission/source-manifest.json')
changes=[]; missing=[]
for k,v in source.items():
 p=R/'artex-ui-asset-final/build-source'/k
 if not p.is_file():missing.append(k)
 elif sha(p)!=v:changes.append(k)
vmrec=load('artex-ui-asset-final/final-instance-readback.json'); vm=json.loads(vmrec['stdout']); diskrec=load('artex-ui-asset-final/final-disk-readback.json');disk=json.loads(diskrec['stdout'])
ledger=load('artex-standing-cost-ledger.json'); proposed=load('artex-ui-asset-final/ledger-proposed.json');D=decimal.Decimal
r={'runner_manifest':runner,'producer_receipt_counts':counts,'original_ui_map_equal':orig['files']==cur['files'],'build_source_manifest_files':len(source),'build_source_changed':changes,'build_source_missing':missing,'build_source_extra_verification':'generated overlay entries recorded in local-build-receipt; no builds executed','saved_cloud_only':{'observed_utc':vmrec['utc'],'project':'syncfall-ir-range','zone':'us-central1-a','name':vm['name'],'vm_id':vm['id'],'vm_status':vm['status'],'disk_id':disk['id'],'disk_status':disk['status'],'disk_size_gb':disk['sizeGb'],'auto_delete':vm['disks'][0]['autoDelete'],'service_accounts':vm.get('serviceAccounts',[]),'has_external_ip':any(n.get('accessConfigs') for n in vm['networkInterfaces']),'provider_stop':vm['scheduling'],'live_checked':False},'budget':{'authoritative_last_settled':ledger['last_settled_session'],'historical_compute_usd':ledger['historical_estimated_compute_usd'],'unsettled_final_compute_usd':proposed['additional_compute_estimate_usd'],'proposed_total_usd':proposed['proposed_historical_estimated_compute_usd'],'headroom_after_final_and_contingency_usd':str(D(ledger['compute_transfer_ceiling_usd'])-D(proposed['proposed_historical_estimated_compute_usd'])-D(ledger['unpriced_transfer_contingency_usd'])),'proposal_30min_compute_usd':str(D('.26804568')/2),'after_proposed_30min_and_contingency_usd':str(D(ledger['compute_transfer_ceiling_usd'])-D(proposed['proposed_historical_estimated_compute_usd'])-D('.5')-D('.26804568')/2),'final_settlement_not_applied_by_this_lane':True},'handoffs':{p:(R/p).exists() for p in ['artex-worker-admission/HANDOFF.md','artex-worker-admission/receipts/REPORT.md','artex-ui-asset-final/HANDOFF.md','artex-worker-assessment-runner/HANDOFF.md']}}
(O/'receipt-checks.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
