"""Stage 2 empirical dynamic-fit model, with explicit remaining physics omissions."""
import numpy as np
from scipy.interpolate import CubicSpline
from numba import njit
from .gravity import read_gravity, solid_tides, acceleration

AU=149597870700.
C_LIGHT=299792458.
GM_SUN=1.327124400419394e20
GM_MOON=4.90280011845755e12


@njit(cache=False)
def shadow_fraction(position,sun):
    """Visible fraction for overlapping angular solar/Earth discs (penumbra)."""
    earth=-position;solar=sun-position
    de,ds=np.linalg.norm(earth),np.linalg.norm(solar)
    a=np.arcsin(696340000./ds);b=np.arcsin(6378136.3/de)
    separation=np.arccos(min(1.,max(-1.,(earth@solar)/(de*ds))))
    if separation>=a+b:return 1.
    if separation<=b-a:return 0.
    if separation<=a-b:return 1.-(b/a)**2
    x=(separation**2+a*a-b*b)/(2*separation)
    y=np.sqrt(max(0.,a*a-x*x))
    area=a*a*np.arccos(min(1.,max(-1.,x/a)))+b*b*np.arccos(min(1.,max(-1.,(separation-x)/b)))-separation*y
    return min(1.,max(0.,1-area/(np.pi*a*a)))


@njit(cache=False)
def srp_basis(state,sun,count):
    r,v=state[:3],state[3:]
    d=sun-r;distance=np.linalg.norm(d);d=d/distance
    rh=r/np.linalg.norm(r)
    y=np.cross(rh,d);yn=np.linalg.norm(y)
    normal=np.cross(r,v);normal=normal/np.linalg.norm(normal)
    if yn<1e-8:raise ValueError("Nominal yaw axes degenerate")
    y=y/yn;b=np.cross(d,y)
    if count==5:
        origin=np.cross(np.array([0.,0.,1.]),normal)
    else:
        origin=sun-(sun@normal)*normal
    origin=origin/np.linalg.norm(origin)
    co=rh@origin;si=rh@np.cross(normal,origin)
    columns=np.zeros((3,count))
    columns[:,0]=d;columns[:,1]=y;columns[:,2]=b;columns[:,3]=co*b;columns[:,4]=si*b
    if count==7:
        columns[:,5]=(co*co-si*si)*d;columns[:,6]=2*si*co*d
    return columns*shadow_fraction(r,sun)*(AU/distance)**2


@njit(cache=False)
def relativity(state,mu):
    r,v=state[:3],state[3:];distance=np.linalg.norm(r)
    return mu/(C_LIGHT*C_LIGHT*distance**3)*((4*mu/distance-v@v)*r+4*(r@v)*v)


class OrbitForceModel:
    def __init__(self,environment,gravity_path,count=5,solid_earth=True):
        if count not in (5,7):raise ValueError("Only declared ECOM5/ECOM2-7 variants")
        self.environment=environment
        self.mu_m3ps2,self.radius_m,c,s,norms=read_gravity(gravity_path)
        c[0,0]=0.  # Central gravity is evaluated/differentiated analytically in inertial axes.
        self.parameter_scales=np.full(count,1e-7)
        self.parameter_names=("D0","Y0","B0","Bc1","Bs1")+(("Dc2","Ds2") if count==7 else ())
        grid=np.arange(environment.start,environment.end+1,120.)
        if grid[-1]<environment.end:grid=np.r_[grid,environment.end]
        coefficients=[]
        for t in grid:
            rotation,sun,moon=environment.at(t)
            coefficients.append(solid_tides(rotation,sun,moon,self.mu_m3ps2,self.radius_m,c,s,norms) if solid_earth else (c,s))
        self.coefficients=CubicSpline(grid,np.array(coefficients),extrapolate=False)

    def evaluate(self,t,state,parameters,*,partials=True):
        state=np.asarray(state,dtype=float);p=np.asarray(parameters,dtype=float)
        if state.shape!=(6,) or p.shape!=self.parameter_scales.shape or not np.isfinite(state).all() or not np.isfinite(p).all():
            raise ValueError("Invalid dynamic-fit state/parameters")
        rotation,sun,moon=self.environment.at(t)
        c,s=self.coefficients(t)
        r=state[:3];distance=np.linalg.norm(r);rt=rotation@r
        a=-self.mu_m3ps2*r/distance**3+rotation.T@acceleration(rt,self.mu_m3ps2,self.radius_m,c,s)
        jac=self.mu_m3ps2*(3*np.outer(r,r)/distance**5-np.eye(3)/distance**3) if partials else None
        for body,mu in ((sun,GM_SUN),(moon,GM_MOON)):
            delta=body-r;length=np.linalg.norm(delta)
            a+=mu*(delta/length**3-body/np.linalg.norm(body)**3)
            if partials:jac+=mu*(3*np.outer(delta,delta)/length**5-np.eye(3)/length**3)
        def small_force(x):
            basis=srp_basis(x,sun,len(p))
            return relativity(x,self.mu_m3ps2)+basis@p,basis
        small,dp=small_force(state);a+=small
        if not partials:return a,None,None,None
        terrestrial_jac=np.empty((3,3))
        for k in range(3):
            delta=np.eye(3)[k]*10.
            terrestrial_jac[:,k]=(acceleration(rt+delta,self.mu_m3ps2,self.radius_m,c,s)-acceleration(rt-delta,self.mu_m3ps2,self.radius_m,c,s))/20.
        jac+=rotation.T@terrestrial_jac@rotation
        nongrav_jac=np.empty((3,6))
        for k in range(6):
            h=10. if k<3 else .01
            delta=np.zeros(6);delta[k]=h
            nongrav_jac[:,k]=(small_force(state+delta)[0]-small_force(state-delta)[0])/(2*h)
        return a,jac+nongrav_jac[:,:3],nongrav_jac[:,3:],dp
