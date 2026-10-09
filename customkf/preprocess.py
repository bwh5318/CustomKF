"""Native-epoch GPS IF combinations and conservative ambiguity arc bookkeeping."""
from dataclasses import dataclass
import math

C=299792458.
F1=1575.42e6
F2=1227.60e6
LAMBDA1=C/F1
LAMBDA2=C/F2
ALPHA=F1**2/(F1**2-F2**2)
BETA=-F2**2/(F1**2-F2**2)


@dataclass(frozen=True)
class SignalPair:
    code1:str
    code2:str
    phase1:str
    phase2:str


def choose_signals(types):
    # Code bias convention is a separate input requirement, never guessed from C1.
    for pair in (SignalPair("C1W","C2W","L1W","L2W"),SignalPair("C1W","C2W","L1C","L2W"),
                 SignalPair("P1","P2","L1","L2")):
        if all(code in types for code in pair.__dict__.values()):return pair
    raise ValueError("No supported P(Y)-code-compatible signal pair; explicit code biases required")


def combinations(obs,pair):
    samples=[obs.get(k) for k in pair.__dict__.values()]
    if any(s is None or s.value is None for s in samples):return None
    p1,p2,l1,l2=[s.value for s in samples]
    if not (1e7<p1<4e7 and 1e7<p2<4e7):return None
    return {"code_if_m":ALPHA*p1+BETA*p2,"phase_if_m":ALPHA*LAMBDA1*l1+BETA*LAMBDA2*l2,
            "geometry_free_m":LAMBDA1*l1-LAMBDA2*l2,
            "mw_m":(F1*LAMBDA1*l1-F2*LAMBDA2*l2)/(F1-F2)-(F1*p1+F2*p2)/(F1+F2),
            "loss_of_lock":bool((samples[2].lli|samples[3].lli)&1),
            "half_cycle":bool((samples[2].lli|samples[3].lli)&2)}


class ArcTracker:
    """Initial conservative GF/MW detector, with all decisions exposed for audit.

    Thresholds are development defaults, not validated disturbance-day editing.
    RINEX-2 bit 2 (value 4) is anti-spoofing, not a loss of lock.
    """
    def __init__(self):self.previous={};self.next_arc=0;self.events=[];self.pending={}

    def observe_epoch_event(self,tag,satellites,flag):
        if flag not in (1,6):return
        affected=set(satellites)|(set(self.previous) if flag==1 else set())
        for sat in affected:self.pending[sat]=["receiver_event" if flag==1 else "slip_record"]

    def update(self,tag,sat,data,epoch_flag=0):
        old=self.previous.get(sat);reason=self.pending.pop(sat,[])
        if old is None:reason.append("new")
        elif (tag-old[0])/1e9>60:reason.append("gap")
        else:
            dt=(tag-old[0])/1e9
            if abs(data["geometry_free_m"]-old[1]["geometry_free_m"])>.08+.002*dt:reason.append("geometry_free")
            if abs(data["mw_m"]-old[1]["mw_m"])>5.:reason.append("melbourne_wubbena")
        if data["loss_of_lock"]:reason.append("loss_of_lock")
        if data["half_cycle"]:reason.append("half_cycle")
        if epoch_flag in (1,6):reason.append("receiver_or_slip_event")
        if reason:
            arc=self.next_arc;self.next_arc+=1
            self.events.append({"gps_ns":tag,"satellite":sat,"arc":arc,"reasons":reason})
        else:arc=old[2]
        self.previous[sat]=(tag,data,arc)
        return arc
