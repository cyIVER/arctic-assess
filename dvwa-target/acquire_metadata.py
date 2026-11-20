"""Public HTTPS metadata only; never retrieves image layers."""
import urllib.request, urllib.parse, json, hashlib, pathlib, datetime
ROOT = pathlib.Path(__file__).resolve().parent
ACCEPT = 'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'
def get(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=40) as r:
        data=r.read(4_000_001)
        if len(data)>4_000_000: raise RuntimeError('metadata budget exceeded')
        return data

def image(host, repo, tag, token_url, service):
    query=urllib.parse.urlencode({'service':service,'scope':f'repository:{repo}:pull'})
    token=json.loads(get(token_url+'?'+query))['token']
    headers={'Authorization':'Bearer '+token,'Accept':ACCEPT}
    base=f'https://{host}/v2/{repo}'
    raw=get(base+'/manifests/'+tag, headers); index=json.loads(raw)
    index_digest='sha256:'+hashlib.sha256(raw).hexdigest()
    if 'manifests' in index:
        matches=[x for x in index['manifests'] if x.get('platform',{}).get('os')=='linux' and x.get('platform',{}).get('architecture')=='amd64']
        if len(matches)!=1: raise RuntimeError('ambiguous platform')
        digest=matches[0]['digest']; raw=get(base+'/manifests/'+digest,headers)
        if 'sha256:'+hashlib.sha256(raw).hexdigest()!=digest: raise RuntimeError('manifest digest mismatch')
    else: digest=index_digest
    manifest=json.loads(raw); cfgraw=get(base+'/blobs/'+manifest['config']['digest'],headers)
    if 'sha256:'+hashlib.sha256(cfgraw).hexdigest()!=manifest['config']['digest']: raise RuntimeError('config digest mismatch')
    config=json.loads(cfgraw)
    if (config['os'],config['architecture'])!=('linux','amd64'): raise RuntimeError('platform mismatch')
    ref=('docker.io' if host=='registry-1.docker.io' else host)+'/'+repo
    return dict(source=ref+':'+tag, index_digest=index_digest, digest=digest, pinned=ref+'@'+digest, config_digest=manifest['config']['digest'], architecture='amd64', os='linux', config={k:config['config'].get(k) for k in ['User','Entrypoint','Cmd','Volumes','ExposedPorts','Labels','WorkingDir','Env']}, layers=manifest['layers'], compressed_layer_bytes=sum(x['size'] for x in manifest['layers']), config_bytes=len(cfgraw))

if __name__=='__main__':
    commit=json.loads(get('https://api.github.com/repos/digininja/DVWA/commits/master',{'User-Agent':'dvwa-private-metadata'}))['sha']
    for name in ['Dockerfile','compose.yml','config/config.inc.php.dist','setup.php','dvwa/includes/DBMS/MySQL.php']:
        data=get(f'https://raw.githubusercontent.com/digininja/DVWA/{commit}/{name}')
        (ROOT/('source-'+name.replace('/','_'))).write_bytes(data)
    images={'dvwa':image('ghcr.io','digininja/dvwa','latest','https://ghcr.io/token','ghcr.io'), 'db':image('registry-1.docker.io','library/mariadb','10','https://auth.docker.io/token','registry.docker.io')}
    unique={x['digest']:x['size'] for im in images.values() for x in im['layers']}
    total=sum(unique.values())
    result=dict(collected_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), source_commit=commit, source_url=f'https://github.com/digininja/DVWA/tree/{commit}', images=images, unique_compressed_layer_bytes=total, budget_bytes=1_800_000_000, fits_download_budget=total<=1_800_000_000, notes='Layer downloads excluded. Unpacked disk, Docker overhead and tar duplication not included. Tag source revision not proof image was built from current master; inspect OCI labels.')
    (ROOT/'pins.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if total>1_800_000_000: raise SystemExit('BLOCKED: download exceeds remaining budget')
