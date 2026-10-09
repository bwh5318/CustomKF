"""Fixed a-priori box-wing solar radiation pressure for GPS under nominal yaw steering.

Why: `results/ECOM7_RESULTS.md` showed that the 12 h common-height swing is a Sun-direction
twice-per-revolution SRP effect (free Dc2/Ds2 remove 30–37% of it), but that free parameters cost
far more radial accuracy than they recover. A box-wing model puts the same physics in as a *known*
force: the Sun-lit bus faces change their projected area with the Earth–satellite–Sun angle, which
is what produces the 2/rev signature. It adds no parameters; ECOM5 is still estimated on top, as in
the CODE-style "a priori box-wing + ECOM" approach.

**Attitude:** nominal yaw steering, IGS body frame. +Z points to the Earth (−r̂); +Y = (Z × e)/|Z × e|,
with e the satellite-to-Sun unit vector; +X = Y × Z, so the Sun lies in the +X half of the X–Z
plane. Noon/midnight turns are not modelled.

**Surface force**, per flat or part-cylindrical surface of area A and outward normal n facing the
Sun (cos θ = n·e > 0), following Duan & Hugentobler (2021, eq. 2) with instantaneous thermal
re-radiation (their δ + κα with κ = 1 is the tabulated α + δ):

    a = −(S/c)(A/m) cos θ [ (α+δ) e + (π/6·s + 2/3·(1−s))(α+δ) n + (4/3·s + 2(1−s)) ρ cos θ n ]

Here s is the cylindrical shape factor. S = 1361 W/m² × (1 AU / d_sun)², scaled by the penumbral
sunlit fraction. The solar panels track the Sun (n = e, cos θ = 1).

**Parameters, cited and fixed before any fit**:

| Block | Surface | A m² | s | α+δ | ρ | Mass used | Source |
|---|---|---:|---:|---:|---:|---:|---|
| IIR, IIR-M | +Z | 4.250 | 0 | 1.095 | −0.137 | 1100 kg | Duan & Hugentobler (2021) GPS Solut 25:42, Table 3 |
| | −Z | 4.250 | 0 | 0.935 | 0.096 | | |
| | +X | 4.117 | 0.258 | 0.730 | 0.175 | | |
| | panels | 13.920 | 0 | 0.959 | 0.044 | | |
| IIF | +Z | 5.400 | 0 | 0.533 | 0.070 | 1555 kg | same, Table 4 |
| | −Z | 5.400 | 0 | 0.388 | 0.198 | | |
| | +X | 5.720 | 0 | 0.262 | 0.255 | | |
| | panels | 22.250 | 0 | 1.104 | 0.035 | | |
| IIIA | +Z | 5.0 | 0 | 0.90 | 0.10 | 2600 kg | Steigenberger, Thoelert & Montenbruck (2020) ASR 66:2773, Table 3 |
| | −Z | 5.0 | 0 | 1.00 | 0.00 | | |
| | +X | 6.6 | 0 | 0.90 | 0.10 | | |
| | panels | 28.2 | 0 | 0.92 | 0.08 | | |

The masses are **the papers' own**. Duan & Hugentobler's optical parameters were adjusted with 1100
and 1555 kg, so only the product (coefficient × A/m) is meaningful; using another mass would
misstate their model. Steigenberger et al. adopt 2600 kg in both their GPS III models. The IIIA
+Z and +X areas are the midpoints of that paper's BW-1/BW-2 variants (4.0/6.0 and 7.5/5.7 m²),
following the same rule declared for `nongrav.py`. Some published adjusted values are unphysical
(negative ρ on IIR +Z); they are used as published, since that is what the model is.

Because the full box-wing includes the panels' constant Sun-direction force (about 1e-7 m/s²),
the ECOM5 D0 estimated on top starts at **0** rather than −1e-7. D0 then becomes a correction to
the a-priori model.
"""
import numpy as np

from customkf.orbit_forces import shadow_fraction

C_LIGHT = 299792458.
AU = 149597870700.
SOLAR_CONSTANT = 1361.

# (area m², shape s, alpha+delta, rho) per surface; mass kg.
MODELS = {
    "IIR": dict(mass=1100., surfaces={"+Z": (4.250, 0., 1.095, -0.137), "-Z": (4.250, 0., 0.935, 0.096),
                                      "+X": (4.117, 0.258, 0.730, 0.175), "SP": (13.920, 0., 0.959, 0.044)}),
    "IIF": dict(mass=1555., surfaces={"+Z": (5.400, 0., 0.533, 0.070), "-Z": (5.400, 0., 0.388, 0.198),
                                      "+X": (5.720, 0., 0.262, 0.255), "SP": (22.250, 0., 1.104, 0.035)}),
    "IIIA": dict(mass=2600., surfaces={"+Z": (5.0, 0., 0.90, 0.10), "-Z": (5.0, 0., 1.00, 0.00),
                                       "+X": (6.6, 0., 0.90, 0.10), "SP": (28.2, 0., 0.92, 0.08)}),
}
BLOCK_MODEL = {"GPS-IIR-A": "IIR", "GPS-IIR-B": "IIR", "GPS-IIR-M": "IIR", "GPS-IIF": "IIF", "GPS-IIIA": "IIIA"}


def surface(e, n, cos_t, area, shape, ad, rho):
    return -area*cos_t*(ad*e+(np.pi/6*shape+2/3*(1-shape))*ad*n+(4/3*shape+2*(1-shape))*rho*cos_t*n)


def acceleration(r, sun, block, include_panels=True):
    """Box-wing SRP acceleration (m/s²) in inertial axes, nominal yaw steering."""
    model = MODELS[BLOCK_MODEL[block]]
    e = sun-r
    distance = np.linalg.norm(e)
    e = e/distance
    z = -r/np.linalg.norm(r)
    total = np.zeros(3)
    s = model["surfaces"]
    y = np.cross(z, e)
    yn = np.linalg.norm(y)
    if yn >= 1e-9:  # yaw steering is undefined only with the Sun exactly on the Z axis; panels still apply
        y /= yn
        x = np.cross(y, z)
        for name, n in (("+X", x), ("+Z", z), ("-Z", -z)):
            cos_t = float(n@e)
            if cos_t > 0:
                total += surface(e, n, cos_t, *s[name])
    if include_panels:
        total += surface(e, e, 1., *s["SP"])
    flux = SOLAR_CONSTANT*(AU/distance)**2*shadow_fraction(r, sun)
    return total*flux/(C_LIGHT*model["mass"])


class BoxWing:
    """Unchanged base model (OrbitForceModel or a wrapper) plus fixed box-wing SRP. Same parameters."""

    def __init__(self, base, block):
        self.base, self.block = base, block
        self.environment = getattr(base, "environment", None) or base.base.environment
        self.mu_m3ps2, self.parameter_scales = base.mu_m3ps2, base.parameter_scales
        self.parameter_names = base.parameter_names

    def evaluate(self, t, state, parameters, *, partials=True):
        a, jr, jv, dp = self.base.evaluate(t, state, parameters, partials=partials)
        _, sun, _ = self.environment.at(t)
        a = a+acceleration(np.asarray(state[:3], dtype=float), sun, self.block)
        # Attitude-driven direction changes give position partials of order |a|/r ≈ 4e-15 s⁻², negligible
        # beside the gravity gradient (~2e-8 s⁻²); they are omitted.
        return (a, None, None, None) if not partials else (a, jr, jv, dp)
