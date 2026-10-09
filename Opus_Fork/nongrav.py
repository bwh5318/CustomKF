"""Physical Earth radiation pressure (ERP) and antenna thrust for GPS, as fixed a-priori forces.

Test T2.1 in `results/URE_REVIEW_AND_TEST_PLAN.md`. Every number here is fixed from physics or a
cited publication **before** any orbit is fitted with it. Nothing is fitted to, or derived from,
an IGS orbit: the reference census (`reference_census.py`, E5R) measures what IGS implies, and
this model is scored against that measurement, not calibrated to it.

**Antenna thrust.** a = P/(m·c), directed radially away from the Earth (nadir-pointing
antennas). P and m come from the IGS satellite metadata SINEX (`Opus_Fork.satmeta`).

**Earth radiation**, analytical uniform-Earth model:

- **Longwave (IR):** a Lambertian sphere with constant exitance M = (1 − A)·S/4 = 238 W/m²
  (radiative equilibrium, A = 0.3, S = 1361 W/m²). The irradiance on a plate facing the
  Earth's centre at geocentric distance r is M·(R/r)².
- **Shortwave (albedo):** S is scaled by (1 AU / d_sun)². A Lambertian sphere with albedo A
  and the full-disc Lambert phase law gives
  E = A·S·(R/r)²·(2/3π)[sin α + (π − α)cos α], where α is the Sun–Earth–satellite phase
  angle. This is the far-field law; at GPS distance (r/R ≈ 4.2) the visible cap is 76°, not
  90°, so it is approximate at the ~10% level.
- **Direction:** radial, away from the Earth. For a nadir-pointing satellite the flux arrives
  from a 14°-radius disc centred on nadir.
- **Illuminated area:** the Earth-facing bus face plus the solar panels projected on the
  radial direction, A_eff = A_z + A_sp·|d̂·r̂|, where d̂ is the satellite-to-Sun unit vector.
  Under nominal yaw steering the panel normal is the Sun direction.
- **Surface interaction: absorption only**, force = E·A_eff/c along the flux. Reflection
  would add roughly 10–30% depending on the surface. Omitting it is deliberate: it keeps the
  model free of optical coefficients that could be tuned, and makes the prediction a lower
  bound.

**Geometry**, cited and fixed in advance (m²):

| Block | +Z bus | Solar panels | Source |
|---|---:|---:|---|
| IIR-A/B, IIR-M | 4.250 | 13.920 | Duan & Hugentobler (2021), GPS Solut 25:42, Table 3 (after Fliegel & Gallini 1996) |
| IIF | 5.400 | 22.250 | Duan & Hugentobler (2021), Table 4 |
| IIIA | 5.0 | 28.2 | Steigenberger, Thoelert & Montenbruck (2020), Adv Space Res 66:2773, Table 3 |

The +Z value for IIIA is the midpoint of that paper's two box-wing variants (4.0 and 6.0 m²),
chosen here before any use. Masses are the metadata values (IIR 1080, IIF 1633, IIIA 2161 kg),
not the papers' adjusted masses.

Earth's radius for the geometry factor is the mean radius, 6371 km.
"""
import numpy as np

C_LIGHT = 299792458.
AU = 149597870700.
SOLAR_CONSTANT = 1361.
ALBEDO = 0.3
EARTH_RADIUS = 6371000.
IR_EXITANCE = (1-ALBEDO)*SOLAR_CONSTANT/4

GEOMETRY = {  # metadata block name -> (+Z bus m², solar panels m²)
    "GPS-IIR-A": (4.250, 13.920), "GPS-IIR-B": (4.250, 13.920), "GPS-IIR-M": (4.250, 13.920),
    "GPS-IIF": (5.400, 22.250), "GPS-IIIA": (5.0, 28.2),
}
SOURCES = {
    "IIR": "Duan & Hugentobler (2021) GPS Solutions 25:42, Table 3",
    "IIF": "Duan & Hugentobler (2021) GPS Solutions 25:42, Table 4",
    "IIIA": "Steigenberger, Thoelert & Montenbruck (2020) Adv Space Res 66:2773, Table 3 (+Z midpoint of BW-1/BW-2)",
    "mass_power": "IGS satellite metadata SINEX (Steigenberger & Montenbruck, doi:10.57677/metadata-sinex)",
}


def erp_irradiance(r, sun):
    """(IR, albedo) irradiance in W/m² on an Earth-facing plate at inertial position r."""
    distance = np.linalg.norm(r)
    rh, sh = r/distance, sun/np.linalg.norm(sun)
    solar = SOLAR_CONSTANT*(AU/np.linalg.norm(sun))**2
    k = (EARTH_RADIUS/distance)**2
    alpha = np.arccos(np.clip(rh@sh, -1., 1.))
    phase = (2/(3*np.pi))*(np.sin(alpha)+(np.pi-alpha)*np.cos(alpha))
    return IR_EXITANCE*k, ALBEDO*solar*k*phase  # IR is thermal: no Sun-distance scaling


def radial_acceleration(r, sun, satellite, erp=True, thrust=True):
    """Outward radial acceleration magnitude (m/s²) from ERP and/or antenna thrust."""
    total = satellite.thrust_mps2 if thrust else 0.
    if erp:
        bus, panels = GEOMETRY[satellite.block]
        rh = r/np.linalg.norm(r)
        d = sun-r
        d = d/np.linalg.norm(d)
        area = bus+panels*abs(d@rh)
        ir, albedo = erp_irradiance(r, sun)
        total += (ir+albedo)*area/(C_LIGHT*satellite.mass_kg)
    return total


class PhysicalRadiation:
    """The unchanged OrbitForceModel plus fixed ERP/thrust. Same parameters, same interface.

    Parameter count and names are the base model's, so it drops into any path that builds
    an OrbitForceModel (pilot, trajectory cache) without changing the estimated set.
    """

    def __init__(self, base, satellite, erp=True, thrust=True):
        self.base, self.satellite, self.erp, self.thrust = base, satellite, erp, thrust
        self.environment, self.mu_m3ps2, self.radius_m = base.environment, base.mu_m3ps2, base.radius_m
        self.parameter_scales, self.parameter_names = base.parameter_scales, base.parameter_names

    def extra(self, t, r):
        _, sun, _ = self.environment.at(t)
        return radial_acceleration(r, sun, self.satellite, self.erp, self.thrust)

    def evaluate(self, t, state, parameters, *, partials=True):
        a, jr, jv, dp = self.base.evaluate(t, state, parameters, partials=partials)
        r = np.asarray(state[:3], dtype=float)
        distance = np.linalg.norm(r)
        rh = r/distance
        radial = self.extra(t, r)
        a = a+radial*rh
        if not partials:
            return a, None, None, None
        # Direction change only; the magnitude's (R/r)² gradient is ~1e-16 s⁻², negligible.
        return a, jr+radial*(np.eye(3)-np.outer(rh, rh))/distance, jv, dp
