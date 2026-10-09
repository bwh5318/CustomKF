"""GPS LNAV initialization, not a precise-orbit force model.

IS-GPS-200 user equations as reproduced in ESA Navipedia, GPS and Galileo
Satellite Coordinates Computation. af0/1/2 excludes periodic relativity here;
measurement.geometry adds it once. No TGD term enters the IF clock profile.
"""
import numpy as np

MU = 3.986005e14
OMEGA = 7.2921151467e-5
WEEK = 604800.


def select_record(records, gps_ns):
    """Legacy Stage 5a selector, retained solely to reproduce archived pilots.

    This past-toc rule is NOT a correct operational GPS applicability policy.
    New processing should use select_fit_record with an explicit data cutoff.
    """
    eligible = [r for r in records if 0 <= (gps_ns-r["gps_ns"])/1e9 <= 4*3600 and r["health"] == 0]
    if not eligible:
        raise ValueError("No healthy past GPS LNAV clock epoch within four hours")
    record = max(eligible, key=lambda r: r["gps_ns"])
    # RINEX stores a full continuous GPS week. Refuse truncation/rollover guesses.
    toe = record["week"]*WEEK+record["toe"]
    if abs(gps_ns/1e9-toe) > 4*3600:
        raise ValueError("GPS LNAV toe outside bounded initialization age")
    return record


def select_fit_record(records, gps_ns, *, available_before_ns):
    """Nominal four-hour LNAV profile, centred on toe/toc (IS-GPS-200N 20.3.4.5).

    Supports hour-aligned, matching toe/toc and explicit four-hour RINEX fit
    intervals only. Offset reference times and extended fits need separate
    validated policies. The supplied file/cutoff establishes allowed data;
    nonzero transmission tags are additionally checked. Zero/missing tags do
    not certify historical receipt and must remain declared in provenance.
    """
    eligible=[]
    for r in records:
        toe=r["week"]*WEEK+r["toe"]
        if (r["health"]!=0 or r.get("fit_interval")!=4. or r["toe"]%3600!=0 or
                abs(r["gps_ns"]/1e9-toe)>1e-6 or abs(gps_ns/1e9-toe)>7200.):continue
        if r["gps_ns"]>available_before_ns:continue
        tx=r.get("transmission_time")
        if tx not in (None,0.):
            transmission=r["week"]*WEEK+tx
            transmission-=round((transmission-toe)/WEEK)*WEEK
            if transmission>available_before_ns/1e9:continue
        eligible.append(r)
    if not eligible:raise ValueError("No eligible nominal four-hour LNAV fit at requested epoch/cutoff")
    return min(eligible,key=lambda r:(abs(gps_ns/1e9-(r["week"]*WEEK+r["toe"])), -r["gps_ns"]))


def position(record, gps_ns):
    a = record["sqrt_a"]**2
    e = record["e"]
    if not 2e7 < a < 3e7 or not 0 <= e < .1:
        raise ValueError("Unsupported GPS LNAV orbit")
    t = gps_ns/1e9
    tk = t-(record["week"]*WEEK+record["toe"])
    if abs(tk) > 4*3600:
        raise ValueError("GPS LNAV extrapolation refused")
    mean = record["m0"]+(np.sqrt(MU/a**3)+record["delta_n"])*tk
    eccentric = mean
    for _ in range(12):
        step = (eccentric-e*np.sin(eccentric)-mean)/(1-e*np.cos(eccentric))
        eccentric -= step
        if abs(step) < 1e-14:
            break
    else:
        raise ValueError("Kepler iteration did not converge")
    true = np.arctan2(np.sqrt(1-e*e)*np.sin(eccentric), np.cos(eccentric)-e)
    phi = true+record["omega"]
    cos2, sin2 = np.cos(2*phi), np.sin(2*phi)
    u = phi+record["cuc"]*cos2+record["cus"]*sin2
    r = a*(1-e*np.cos(eccentric))+record["crc"]*cos2+record["crs"]*sin2
    inclination = record["i0"]+record["idot"]*tk+record["cic"]*cos2+record["cis"]*sin2
    node = record["omega0"]+(record["omega_dot"]-OMEGA)*tk-OMEGA*record["toe"]
    x, y = r*np.cos(u), r*np.sin(u)
    return np.array([x*np.cos(node)-y*np.cos(inclination)*np.sin(node),
                     x*np.sin(node)+y*np.cos(inclination)*np.cos(node), y*np.sin(inclination)])


def state_inertial(record, epoch, gps_origin_ns, t=0., step=.5):
    def at(s):
        return epoch.celestial_to_terrestrial(s).T@position(record, gps_origin_ns+int(round(s*1e9)))
    return np.r_[at(t), (at(t+step)-at(t-step))/(2*step)]


def clock(record, gps_ns):
    dt = (gps_ns-record["gps_ns"])/1e9
    if abs(dt) > 4*3600:
        raise ValueError("GPS LNAV clock extrapolation refused")
    return record["af0"]+record["af1"]*dt+record["af2"]*dt*dt
