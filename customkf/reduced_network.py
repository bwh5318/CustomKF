"""Bounded estimate-only square-root solve without full clock covariance.

Retain the original 900 retained-column and 12000-row ceilings. Local clocks
are eliminated per epoch; do not allocate a matrix spanning all clock columns
or their full covariance. Explicit workspace accounting precedes factorization.
The small full-covariance solver remains the independent regression oracle.
"""
from dataclasses import dataclass
import numpy as np
from .network_square_root import MAX_PARAMETERS, MAX_ROWS, _factor, _checked

WORKSPACE_BYTES=256*2**20


@dataclass
class ReducedSolution:
    estimate: np.ndarray
    retained_covariance: np.ndarray
    projected_rows: int
    workspace_estimate_bytes: int


def budget(blocks,constraints):
    c,z,s=constraints
    if c.ndim!=2 or not blocks or not 0<c.shape[1]<=MAX_PARAMETERS:raise ValueError("Retained-column budget exceeded")
    n=c.shape[1];m=len(c);locals_total=0;largest=0
    for g,l,y,sigma in [(c,np.empty((len(c),0)),z,s)]+[(b.retained,b.local,b.target,b.sigma) for b in blocks]:
        if (g.ndim!=2 or l.ndim!=2 or g.shape!=(len(l),n) or y.shape!=(len(g),) or sigma.shape!=y.shape or
            any(not np.isfinite(v).all() for v in (g,l,y,sigma)) or np.any(sigma<=0)):
            raise ValueError("Invalid reduced block values/dimensions")
    for b in blocks:
        rows,k=b.local.shape
        if not 0<k<=rows:raise ValueError("Invalid local block width")
        m+=rows;locals_total+=k;largest=max(largest,rows)
    if m>MAX_ROWS or m<n+locals_total:raise ValueError("Row budget exceeded or underdetermined")
    # Bound block storage, projections, economic QR/copies, local full Q and
    # recovery matrices. Runtime/framework overhead is additionally OS-guarded.
    workspace=8*(5*m*n+4*largest**2+3*locals_total*n+6*n*n)
    if workspace>WORKSPACE_BYTES:raise ValueError("Reduced QR workspace budget exceeded")
    return n,m,locals_total,workspace


def reduced_qr(blocks,constraints):
    n,m,k_total,workspace=budget(blocks,constraints)
    projected=[];targets=[];recovery=[];norm2=np.zeros(n)
    for b in blocks:
        g=b.retained/b.sigma[:,None];l=b.local/b.sigma[:,None];y=b.target/b.sigma
        norm2+=np.sum(g*g,axis=0)
        q,mapping=_factor(l,full=True);k=l.shape[1]
        projected.append(q[:,k:].T@g);targets.append(q[:,k:].T@y)
        recovery.append((mapping@(q[:,:k].T@y),-mapping@(q[:,:k].T@g)))
    c,z,s=constraints
    projected.append(c/s[:,None]);targets.append(z/s)
    norm2+=np.sum((c/s[:,None])**2,axis=0)
    a=np.vstack(projected);y=np.concatenate(targets)
    _checked(a,y,np.ones(len(y)))
    q,mapping=_factor(a,column_scale=1/np.maximum(np.sqrt(norm2),1e-30))
    retained=mapping@(q.T@y)
    estimate=np.concatenate([retained,*[d+b@retained for d,b in recovery]])
    return ReducedSolution(estimate,mapping@mapping.T,len(y),workspace)
