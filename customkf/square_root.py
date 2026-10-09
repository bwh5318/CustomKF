"""Small dense weighted QR oracle for Stage 3; no normal equations formed."""
import numpy as np
from scipy.linalg import qr,solve_triangular


def weighted_qr(design,target,sigma):
    a=np.asarray(design,dtype=float);y=np.asarray(target,dtype=float);sigma=np.asarray(sigma,dtype=float)
    if (a.ndim!=2 or a.shape[1]==0 or y.shape!=(len(a),) or sigma.shape!=y.shape or a.shape[0]<a.shape[1]
        or a.shape[0]>12000 or a.shape[1]>900 or not np.isfinite(a).all() or not np.isfinite(y).all()
        or not np.isfinite(sigma).all() or np.any(sigma<=0)):
        raise ValueError("Invalid weighted QR inputs or development matrix budget exceeded")
    scaled=a/sigma[:,None];rhs=y/sigma
    column_scale=1/np.maximum(np.linalg.norm(scaled,axis=0),1e-30)
    q,r,pivot=qr(scaled*column_scale,mode="economic",pivoting=True)
    diagonal=np.abs(np.diag(r));rank=int(np.sum(diagonal>diagonal[0]*1e-10)) if diagonal[0]>0 else 0
    if rank!=a.shape[1]:raise ValueError(f"Rank deficient weighted QR: {rank}/{a.shape[1]}")
    estimate=np.zeros(a.shape[1]);estimate[pivot]=solve_triangular(r,q.T@rhs)
    return estimate*column_scale,rank
