import pickle,sys
d=pickle.load(open(sys.argv[1],'rb')); prov=d['prov']
def chain(key,n=40):
    out=[]
    while key and n:
        src=prov.get(key); out.append('%06X m%d x%d'%key)
        if src is None or isinstance(src,str): out.append(str(src)); break
        # find state of src that leads here: try all
        cands=[k for k in prov if k[0]==src]
        # prefer one where widths equal (if widths changed by REP/SEP we accept any)
        k2=[k for k in cands if k[1:]==key[1:]] or cands
        key=k2[0]; n-=1
    return out
a=int(sys.argv[2],16)
for k in [k for k in prov if k[0]==a]:
    print(' <- '.join(chain(k,int(sys.argv[3]) if len(sys.argv)>3 else 25))); print()
