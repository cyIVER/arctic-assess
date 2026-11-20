"""Offline comment-boundary guard. No compilation, network or dependencies.
Retains every non-comment byte, including whitespace, literals and newlines.
This is a lexical proof, not a Go parser or compiler.
"""
import hashlib,json,re,sys
from pathlib import Path
E=Path(__file__).resolve().parent
R=E.parent
CJK=re.compile(r'[\u3400-\u9fff]')
def scan(s):
    out=[]; comments=[]; literals=[]; i=0
    while i<len(s):
        start=i
        if s.startswith('//',i):
            end=s.find('\n',i); end=len(s) if end<0 else end
            comments.append((i,end,s[i:end])); out.append('//'); i=end
        elif s.startswith('/*',i):
            end=s.find('*/',i+2)
            if end<0: raise ValueError('unterminated block comment')
            end+=2; comments.append((i,end,s[i:end])); out.append('/*'+'\n'*s[i:end].count('\n')+'*/'); i=end
        elif s[i] in ['"',"'",'`']:
            q=s[i]; i+=1
            while i<len(s):
                if s[i]==q: i+=1;break
                if q!='`' and s[i]=='\\': i+=2
                else: i+=1
            else: raise ValueError('unterminated literal')
            literals.append(s[start:i]);out.append(s[start:i])
        else: out.append(s[i]);i+=1
    return ''.join(out),comments,literals

def structure(s):
    lines=s.splitlines()
    return {'release_headings':re.findall(r'^## .*$',s,re.M),'heading_levels':[len(re.match(r'#+',l)[0]) for l in lines if l.startswith('#')], 'bullets':[re.match(r'^(\s*- )',l)[0] for l in lines if re.match(r'^\s*- ',l)],'links':re.findall(r'https?://[^\s)>]+',s),'inline_code':[sorted(re.findall(r'`[^`\n]*`',line)) for line in lines],'fences':re.findall(r'^\s*```.*$',s,re.M),'unreleased':s[s.index('## [Unreleased]'):s.index('## [0.3.15]')],'line_count':len(lines)}
def write(name,obj): (E/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def files():
    return sorted([p for d in ['server','db','intercept'] for p in (R/'source'/d).rglob('*.go')]+[R/'source/CHANGELOG.md'])
def baseline():
    b={str(p.relative_to(R)):p.read_text() for p in files()};write('baseline.json',b)
    write('before-sha256.json',{k:hashlib.sha256(v.encode()).hexdigest() for k,v in b.items()})
    ch=structure(b['source/CHANGELOG.md'])
    assert [f'## [0.3.{i}]' for i in range(15,1,-1)]==[x.split(' - ')[0] for x in ch['release_headings'][1:]]
    write('changelog-baseline.json',ch)
    s='package p\n// 中文\nvar X = "中文 // not comment"\n/* 块\n注释 */\n'
    assert scan(s)[0]==scan(s)[0]
    translated=s.replace('// 中文','// English').replace('/* 块\n注释 */','/* Block\ncomment */')
    assert scan(s)[0]==scan(translated)[0]
    assert scan(s)[0]!=scan(s.replace('var X','var Y'))[0]
    assert scan(s)[0]!=scan(s.replace('"中文 // not comment"','"English"'))[0]
    for text in b.values():
        if text.startswith('# Changelog'):continue
        scan(text)
    write('red.json',{'same_byte_lexical_positive':True,'comment_translation_positive':True,'identifier_mutation_rejected':True,'literal_mutation_rejected':True,'baseline_files':len(b),'changelog_required_versions':True,'baseline_cjk_lines':sum(bool(CJK.search(l)) for l in b['source/CHANGELOG.md'].splitlines()),'parser_available':False,'note':'No cached Go parser binary located; builds forbidden. Lexical guard tested before edits; no parse/compile claim.'})
    print('BASELINE and mutation self-tests PASS',len(b))
def verify():
    b=json.loads((E/'baseline.json').read_text()); changed=[]; checks={}; remaining=[]
    for k,old in b.items():
        new=(R/k).read_text()
        if old!=new:changed.append(k)
        if k.endswith('.go'):
            a,_,la=scan(old);z,cs,lz=scan(new)
            checks[k]={'noncomment_bytes_equal':a==z,'literal_bytes_equal':la==lz}
            assert a==z and la==lz,k
            # Preserve compiler/tool directives and all URLs in comments.
            def protected(s):return [c for _,_,c in scan(s)[1] if re.search(r'//\s*(go:|\+build|line )|^/\*line ',c)]
            assert protected(old)==protected(new),k
            for start,end,c in cs:
                for n,line in enumerate(c.splitlines()):
                    if CJK.search(line):remaining.append({'path':k,'line':new[:start].count('\n')+1+n,'kind':'comment','text':line})
            for lit in lz:
                if CJK.search(lit): remaining.append({'path':k,'kind':'preserved_code_literal','text':lit})
        else:
            a,z=structure(old),structure(new);checks[k]={t:a[t]==z[t] for t in a}; assert a==z
            for n,l in enumerate(new.splitlines(),1):
                if CJK.search(l):remaining.append({'path':k,'line':n,'kind':'changelog_prose_or_protected_inline_code','text':l})
    write('verification.json',checks);write('remaining-cjk.json',remaining)
    write('after-sha256.json',{k:hashlib.sha256((R/k).read_bytes()).hexdigest() for k in b})
    write('changed-paths.json',changed)
    print('PASS',len(checks),'files;',len(changed),'changed;',len(remaining),'remaining CJK records')
if __name__=='__main__':
    baseline() if sys.argv[1]=='baseline' else verify()
