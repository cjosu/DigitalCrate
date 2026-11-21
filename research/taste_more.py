import numpy as np
import taste_variants as T
from digitalcrate import taste
E,N,meta=T.E,T.N,T.meta
# richer features: 64 PCA dims, + quality, + genre one-hot
def feats(npca):
    taste.N_PCA=npca;fz=taste.Featurizer(E);return np.stack([fz(E[i],meta[i]) for i in range(N)])
X64=feats(64);X16=feats(16);X128=feats(128)
q=np.array([r["quality"] for r in T.rows])[:,None]
Xq=np.hstack([T.X_full,q-q.mean()])
for name,X in [("32 PCA (current)",T.X_full),("16 PCA",X16),("64 PCA",X64),("128 PCA",X128),("32 PCA + quality",Xq)]:
    T.run("explicit, blend, "+name,"none",X,"blend")
    T.run("seconds,  blend, "+name,"seconds",X,"blend")
