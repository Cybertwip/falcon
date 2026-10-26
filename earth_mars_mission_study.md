# Earth–Mars Mission Mathematics and Simulation Evidence

**Prepared for:** Cybertwip  
**Proposed addressees:** SpaceX mission design teams and NASA exploration/navigation teams  
**Status:** Independent engineering study draft, 26 October 2026  
**Attribution:** US Navy coauthorship, authorization, and endorsement have not been established and are not claimed. This document has not been submitted to the proposed addressees.

To the engineering teams at SpaceX and NASA:

This study sets out a reproducible route from Earth departure conditions to a Mars arrival and a physically constrained landing model. It supplies the equations, data contracts, calculated reference cases, and simulation evidence needed to examine such a route. It keeps three different things explicit: an analytic comparison, a dated trajectory computed from NASA/JPL observations-based ephemerides, and a separately identified application-run evidence section for the experimental EX-1 vehicle.

A trajectory that reaches Mars is only part of a landing design. An operational solution also needs the actual vehicle's aerodynamic and propulsion models, landing-site terrain, atmospheric dispersions, navigation covariance, and verified flight constraints. There is no epoch-independent angle or fuel quantity that lands every Starship configuration. All numbers below identify their frame, units, epoch, architecture, and assumptions.

## 1. Deliverables and reproduction

The numerical companion is [earth_mars_reference.py](earth_mars_reference.py). The complete precision output is [earth_mars_reference_results.json](earth_mars_reference_results.json). Exact JPL response files and their provenance are in [earth_mars_data](earth_mars_data/). The printable HTML and PDF are generated from this Markdown source and the telemetry attachments; they do not depend on a remote mathematics renderer.

```sh
# Offline: use the preserved JPL responses; reproduce both worked examples.
python3 Sandbox/Space/reports/earth_mars_reference.py

# Optional explicit refresh: retrieve two small, read-only JPL vector tables.
python3 Sandbox/Space/reports/earth_mars_reference.py --fetch-horizons

# Render the report; add the complete application run when available.
python3 Sandbox/Space/reports/render_earth_mars_study.py \
  --telemetry Sandbox/Space/reports/telemetry/earth_mars_run.json \
  --telemetry-csv Sandbox/Space/reports/telemetry/earth_mars_run.csv
```

The calculator uses Python's standard library. The renderer uses Python-Markdown and ReportLab; its output manifest records their installed versions and all input hashes. All telemetry rows stay in the attached JSON and CSV rather than being reduced to selected points in the document. Document plots may downsample the displayed line; the original attached records are retained.

## 2. Data required before selecting a mission

| Domain | Required inputs | Why they matter |
| --- | --- | --- |
| Time and geometry | Departure/arrival epochs, time scale, ephemeris version, reference axes and origin | The same numerical coordinates mean different things in different frames or at different epochs. |
| Earth departure | Launch site, Earth orientation, launch azimuth constraints, parking orbit, vehicle state and covariance | A heliocentric transfer direction does not specify a surface launch bearing. |
| Vehicle | Dry/payload/propellant masses, center of mass and inertia, tank geometry, usable residuals, thrust and Isp maps, throttle limits, engine-out rules | Mass, burn duration, attitude authority, and fuel reserve depend on the selected configuration. |
| Cruise | Power/thermal pointing, communications, radiation environment, navigation measurements, correction allocation, boiloff and transfer losses | A passive two-body coast does not model all operational constraints. |
| Mars arrival | Target B-plane, entry interface, landing site and season, atmosphere/wind distributions, gravity field, terrain and hazards | Entry state must fall inside a vehicle-specific corridor and reachable terrain region. |
| Entry/descent | Aerodynamic coefficient tables, TPS response, plume interaction, control surfaces, sensor performance, propulsion transients | Neither a generic drag coefficient nor a fixed landing angle can establish landing feasibility. |
| Acceptance | Dispersions, probability requirements, reserve policy, structural/thermal limits, navigation and guidance tolerances | A nominal trajectory passing through a point is insufficient evidence. |

NASA's Mars-GRAM 2024 estimates atmospheric mean conditions and statistical variations. It supplies an engineering environment, not one universal atmosphere for every place and time. A mission should preserve the exact configuration, input data, and random seeds used for its dispersion study. [NASA Mars-GRAM 2024 user guide](https://ntrs.nasa.gov/citations/20240012934).

## 3. Frames, units, time, and the moving Solar System

Use SI units for dynamics and mass accounting, or an explicitly consistent kilometre-second unit system for orbital calculations. Here the orbital calculator uses km, km/s and km³/s², then explicitly converts delta-v to m/s for the rocket equation. Angles are radians inside algorithms and degrees in tables. A tonne is 1,000 kg. Conventional standard acceleration is `g0 = 9.80665 m/s²`; it is not local Mars gravity.

The dated example uses geometric states in ICRF axes, with the Sun as origin, and TDB epochs. Earth is target 399 and Mars is target 499; these are body centers rather than Earth–Moon or Mars-system barycenter target IDs. Horizons requests explicitly select `VECTORS`, `REF_SYSTEM=ICRF`, `REF_PLANE=FRAME`, `CENTER=500@10`, `VEC_CORR=NONE`, `OUT_UNITS=KM-S`, and `TIME_TYPE=TDB`. Exact requests and response hashes accompany the data. [JPL Horizons API documentation](https://ssd-api.jpl.nasa.gov/doc/horizons.html).

Use geometric simultaneous states for force integration and targeting. A sky display may instead need light-time and stellar-aberration corrections; those observed directions cannot be substituted as simultaneous force-model positions. In SPICE, `spkezr` returns state vectors with an explicit frame, observer and aberration setting. [NAIF state-vector interface](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/spkezr_c.html).

Civil UTC, TT, TDB and UT1 serve different purposes. Convert UTC to the integration time scale using a versioned leap-second kernel and an appropriate time model; use Earth-orientation data for Earth-fixed transformations. The companion's date parser intentionally treats the supplied calendar labels as TDB and does not silently claim to convert UTC. [NAIF time subsystem](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/req/time.html).

For an inertial barycentric formulation, let `r_i` be each body's position and `mu_j = G m_j`:

```text
dr_i/dt = v_i
dv_i/dt = sum_(j != i) mu_j (r_j - r_i) / |r_j - r_i|^3 + a_non_gravitational
```

The Sun responds to other bodies; it need not be fixed at an artificial origin. A common velocity added to every object changes inertial positions but preserves relative velocities and Newtonian encounters. In particular, a large Galactic translation must not be included in an Earth departure's `v_infinity` or the ship's heliocentric attitude heading.

In a Sun-centered accelerating frame, third-body accelerations need the indirect term:

```text
a_third_body,j = mu_j [ (r_j-r_sc)/|r_j-r_sc|^3 - r_j/|r_j|^3 ]
```

An external Galactic potential mainly supplies common Solar System acceleration on an interplanetary mission. Its differential tidal field is the relevant relative effect. A Galaxy viewer's catalogue objects are not automatically a complete self-consistent mass model: missing stellar masses, gas and dark matter must not be silently replaced by equal-mass points. Do not double-count a star as both a resolved gravitating body and part of an unresolved smooth potential.

For precise mission work, use versioned observationally fitted ephemerides rather than describing a Kepler approximation as a precision ephemeris. JPL's DE440/DE441 work combines numerical dynamics with fitted observations; differing time-span and modeling choices matter. [JPL DE440/DE441 publication](https://ssd.jpl.nasa.gov/doc/de440_de441.html).

## 4. A force-model hierarchy that can be validated

The following is a mission-model specification, not a claim that every term is implemented by the application or the analytic companion.

| Phase | Baseline dynamics | Refinements to assess and validate |
| --- | --- | --- |
| Broad window search | Sun-centered two-body Lambert transfers | Multiple branches, departure/arrival constraints, launch energy, inclination and entry-state bounds |
| Committed interplanetary trajectory | Consistent planetary ephemerides, finite burns, navigation corrections | Planet/Moon perturbations, solar radiation pressure, thermal recoil if material, relativistic terms at the required accuracy |
| Earth departure / Mars orbit | Body-centered numerical propagation | Nonspherical gravity, rotation, third bodies, drag and eclipse geometry where relevant |
| Entry/descent | Six-degree-of-freedom vehicle and mass dynamics | Atmospheric dispersions, gas chemistry/heating, aero tables, thrust/plume interaction, actuator and sensor dynamics |
| Touchdown | Terrain-relative motion and contact dynamics | Landing gear compliance, friction, slopes, soil response, plume–surface interaction and stability |

For example, a solar test-particle first post-Newtonian correction in a suitable Sun-centered approximation is:

```text
a_1PN = mu_sun/(c² r³) [ (4 mu_sun/r - v²) r_vector
                         + 4 (r_vector dot v_vector) v_vector ]
```

This compact term is not the complete relativistic N-body model. It must not be blindly added to an already supplied spacecraft ephemeris. The integration model, ephemeris definition and observable corrections must be consistent. An accuracy target and convergence/error budget are more useful than attaching a new model name without validation.

Near an oblate body's polar axis frame, a common `J2` acceleration added to the central point-mass term is:

```text
K = 3 J2 mu R² / (2 r^5)
a_J2 = K [ x(5z²/r²-1), y(5z²/r²-1), z(5z²/r²-3) ]
```

The gravity coefficients, normalization and body orientation must match the source model. Solar radiation pressure can start with a shadow-aware cannonball approximation, `a_SRP = P_1AU C_R (A/m) (1 AU/r)² s_hat`, where `s_hat` points away from the Sun. Coefficient, area, attitude and shadow assumptions should remain visible in metadata.

Convergence must be demonstrated by step/tolerance reduction and independent propagation. Conservative-force validation includes energy and angular-momentum residuals; finite thrust and atmospheric flight require accounting for work, mass flow and dissipative terms rather than demanding spurious energy conservation. The study companion checks its Lambert solution with a separate Cartesian RK4 integration; agreement is a numerical consistency test, not real-flight validation.

## 5. Analytic reference: circular, coplanar Hohmann transfer

Assume a circular Earth orbit of `r_E = 1 AU`, a circular Mars orbit of `r_M = 1.52371034 AU`, and a Sun point mass. The Mars radius in this ideal comparison uses a nominal J2000 semimajor-axis value; eccentricity, actual orbital phases and inclination are deliberately omitted. The common transfer plane is an arbitrary ideal plane, not Earth's equator. The model is useful for dimensional checks and intuition. [JPL approximate planetary elements](https://ssd.jpl.nasa.gov/planets/approx_pos.html), [NASA trajectory fundamentals](https://science.nasa.gov/learn/basics-of-space-flight/chapter4-1/).

```text
a_T = (r_E + r_M)/2
v_circular(r) = sqrt(mu_sun/r)
v_transfer(r) = sqrt(mu_sun [2/r - 1/a_T])
t_flight = pi sqrt(a_T³/mu_sun)
n_E = sqrt(mu_sun/r_E³),  n_M = sqrt(mu_sun/r_M³)
P_synodic = 2 pi / |n_E - n_M|
Mars lead at departure = pi - n_M t_flight
```

| Calculated quantity | Reference value |
| --- | --- |
| Transfer semimajor axis | 1.26185517 AU |
| Time of flight | 258.870581 days |
| Ideal synodic recurrence | 779.922127 days |
| Mars ahead of Earth at departure, measured around the Sun | 44.345829° |
| Earth's heliocentric speed | 29.784692 km/s |
| Transfer speed at departure | 32.729514 km/s |
| Outbound Earth excess speed | 2.944823 km/s |
| Mars heliocentric speed at arrival | 24.129143 km/s |
| Transfer speed at arrival | 21.480142 km/s |
| Mars arrival excess speed magnitude | 2.649001 km/s |

The phase angle is a Sun-centered planet-to-planet angle at departure. It is not a rocket pitch angle, launch-site bearing or fixed latitude. The recurrence above is an ideal orbital-period calculation, not a schedule of approved launch opportunities.

The constants used are `AU = 149597870.7 km`, `mu_sun = 1.32712440041279419e11 km³/s²`, `mu_Earth = 398600.435507 km³/s²`, and `mu_Mars-system = 42828.375816 km³/s²`. The reference approximates the Mars-system parameter as a central point mass; precision local Mars modeling must distinguish Mars from its moons. Reference spherical surface radii are Earth's equatorial `6378.1366 km` and Mars's equatorial `3396.19 km`. [JPL astrodynamic parameters](https://ssd.jpl.nasa.gov/astro_par.html), [JPL physical parameters](https://ssd.jpl.nasa.gov/planets/phys_par.html).

## 6. Earth departure: excess velocity, parking orbit and the actual burn direction

The departure excess-velocity vector is the difference between the spacecraft's heliocentric transfer velocity and Earth's heliocentric velocity:

```text
v_inf,E = v_sc,departure - v_Earth,departure
C3 = |v_inf,E|²
r_p = R_Earth + parking_altitude
v_p,hyp = sqrt(|v_inf,E|² + 2 mu_Earth/r_p)
v_p,circ = sqrt(mu_Earth/r_p)
Delta-v_TMI = v_p,hyp - v_p,circ             [aligned impulsive case]
```

For the ideal case from a 200 km circular orbit, `r_p = 6578.1366 km`, `C3 = 8.671980 km²/s²`, the circular speed is `7.784262 km/s`, hyperbolic periapsis speed is `11.395677 km/s`, and the aligned impulsive injection is `3.611415 km/s`. This excludes Earth ascent, finite-burn losses and plane mismatch.

Hyperbola geometry determines the periapsis orientation relative to the outgoing asymptote:

```text
e_h = 1 + r_p |v_inf|²/mu_Earth
nu_inf = acos(-1/e_h)
total flyby deflection = 2 asin(1/e_h)
b = r_p sqrt(1 + 2 mu_Earth/[r_p |v_inf|²])
```

Here `e_h = 1.143114`, `nu_inf = 151.021677°`, and the complete incoming-to-outgoing deflection would be `122.043354°`. These are different angles and must not be interchanged.

For a reproducible arbitrary-plane construction, place Earth at heliocentric `(+r_E,0,0)`, moving along `+Y`, with prograde normal `+Z`. The ideal outgoing Earth excess velocity is also `+Y`. One departure periapsis radius points at `-61.021677°` from `+X`; the tangential injection direction points at `+28.978323°` from `+X`. The burn is locally horizontal/prograde in the assumed circular parking orbit. These two angles are illustrative coordinate components, not Earth-fixed launch commands.

In the general 3D case, let `s_hat = unit(v_inf,E)` and select an admissible escape-plane normal `n_hat` with `n_hat dot s_hat = 0`. Construct:

```text
p_hat = rotate_about(n_hat, -nu_inf) s_hat
q_hat = n_hat cross p_hat
r_periapsis = r_p p_hat
v_periapsis = v_p,hyp q_hat
Delta-v_vector = v_periapsis - v_actual_parking_orbit
```

The launch location, parking orbit and timing constrain which `n_hat` is reachable. If inertial asymptote declination is `delta`, a necessary geometric condition is an orbit-plane inclination at least `|delta|`; launch latitude and operational azimuth restrictions add further constraints. An orbit plane and a departure asymptote do not determine a surface launch command by themselves.

For a nonrotating spherical Earth and a directly reached prograde orbit, the familiar launch-bearing relation is `cos(i) = cos(latitude) sin(azimuth)`, with azimuth measured clockwise from north. Actual ascent targeting must include Earth's rotation, winds, finite thrust, flight-path shaping and range constraints. A plane change costs `2 v sin(Delta-i/2)` for equal-speed impulsive reorientation; combining speed and plane changes gives `sqrt(v1² + v2² - 2 v1 v2 cos(Delta-i))`.

## 7. Dated 3D reference from preserved NASA/JPL vectors

This example selects two explicit TDB epochs to demonstrate the full calculation. It is not an optimized or recommended mission: departure is **20 November 2026, 00:00:00 TDB**, arrival is **18 July 2027, 00:00:00 TDB**, and time of flight is **240 days**. The state-vector snapshots preserve the exact JPL output used.

Lambert's boundary-value problem is:

```text
Find v1 and v2 such that a trajectory under -mu_sun r/|r|³ has:
r(t_departure) = r_Earth(t_departure)
r(t_arrival)   = r_Mars(t_arrival)
t_arrival - t_departure = selected flight time
```

The companion solves a zero-revolution universal-variable branch with the prograde sense selected relative to Earth's instantaneous orbital normal. It rejects unsupported collinear/singular cases. Operational window searches must compare all admissible branches and refine the selected finite-burn trajectory. A Lambert result is a seed for further targeting, not proof of landing feasibility. [NASA trajectory survey method](https://trajbrowser.arc.nasa.gov/user_guide.php), [original Lambert algorithm research](https://arxiv.org/abs/1403.2705).

Using Stumpff functions `C(z)` and `S(z)`, one convenient formulation is:

```text
A = sin(Delta-theta) sqrt(r1 r2/[1-cos(Delta-theta)])
y(z) = r1 + r2 + A [z S(z)-1]/sqrt(C(z))
t(z) = { [y/C]^(3/2) S(z) + A sqrt(y) } / sqrt(mu_sun)
Solve t(z) = selected time of flight
f = 1-y/r1,  g = A sqrt(y/mu_sun),  g_dot = 1-y/r2
v1 = (r2_vector - f r1_vector)/g
v2 = (g_dot r2_vector - r1_vector)/g
```

| Dated-case result | Value, in ICRF axes unless noted |
| --- | --- |
| Departure excess velocity vector | (-1.500051, +2.778535, +1.920817) km/s |
| Departure excess speed | 3.695937 km/s |
| Departure `C3` | 13.659947 km²/s² |
| Departure asymptote right ascension / declination | 118.363344° / +31.312835° |
| Arrival excess velocity vector | (-3.496342, +0.180817, +0.473340) km/s |
| Arrival excess speed | 3.532867 km/s |
| Arrival velocity-vector right ascension / declination | 177.039531° / +7.699741° |
| Injection from an aligned 200 km circular Earth orbit | 3.828206 km/s |
| Capture into an aligned 250 km circular Mars orbit | 2.570520 km/s |
| One illustrative escape-plane inclination to the ICRF equator | 33.023688° |
| Its unit injection direction | (+0.508812, +0.743325, +0.434257) |
| Its injection-direction right ascension / declination | 55.608056° / +25.738035° |
| Mars–Earth instantaneous center distance at arrival | 252,171,731.753 km |
| Instantaneous distance divided by light speed | 841.154 seconds, approximately 14.019 minutes |

The displayed arrival vector points along the planet-relative incoming velocity. An arrival radiant points in the opposite direction. The one-way light-time estimate above is instantaneous `range/c`; a precise link observable solves retarded transmission/reception geometry and adds the propagation corrections appropriate to the measurement.

The complete heliocentric boundary states, transfer velocities, hyperbola parameters, escape-plane construction and independent endpoint residual are in the JSON companion. No out-of-plane component is projected away. An independent 1,800 s-step Cartesian RK4 propagation arrives within approximately `4.05e-6 km` of the Lambert endpoint for this case. That small mathematical residual does not represent actual trajectory uncertainty or landing accuracy.

## 8. Propellant accounting, reserves and finite burns

For a constant equivalent exhaust velocity, the ideal rocket equation is:

```text
v_e = g0 Isp
Delta-v = v_e ln(m_before/m_after)
m_before = m_after exp(Delta-v/v_e)
m_propellant = m_before - m_after
dm/dt = -T/(g0 Isp)
```

Propellant includes fuel and oxidizer. For oxidizer/fuel mass ratio `OF`, `m_fuel = m_propellant/(1+OF)` and `m_oxidizer = OF m_fuel`. An Isp value belongs to an operating condition and engine configuration, not to the Mars atmosphere or a universal vessel. [NASA Glenn specific impulse](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/specific-impulse/), [NASA rocket-equation discussion](https://science.nasa.gov/learn/basics-of-space-flight/chapter3-2/).

For sequential burns, work backward from the retained final mass. Each earlier burn must accelerate all propellant retained for later burns. Simply adding fuel estimates calculated with the same starting mass gives the wrong result. Include hardware jettison, transfers, leakage, unusable residuals and uncertainty explicitly between burn segments.

The following is an **ideal arithmetic ledger**, not a Starship mission fuel budget. It uses the analytic Hohmann injection, assumes a 100 m/s correction allocation, assumes aerodynamic deceleration can deliver the terminal reference state in Section 10, assumes 380 s cruise Isp and 330 s terminal Isp, and retains 200,000 kg at touchdown. Those vehicle/performance values are user-adjustable study assumptions; no public SpaceX performance map was used to validate them.

| Step | Mass before, kg | Propellant consumed, kg | Mass after, kg |
| --- | --- | --- | --- |
| Earth orbital injection, 3,611.415 m/s at assumed 380 s | 571,411.980 | 354,606.531 | 216,805.448 |
| Assumed corrections, 100 m/s at assumed 380 s | 216,805.448 | 5,740.529 | 211,064.920 |
| Ideal final braking, 174.264 m/s at assumed 330 s | 211,064.920 | 11,064.920 | 200,000.000 |
| Total | 571,411.980 | 371,411.980 | 200,000.000 |

If one additionally assumes `OF = 3.6`, the ledger's total consists of about `80,741.735 kg` fuel and `290,670.245 kg` oxidizer. This mixture ratio is an illustrative input, not a certified Raptor value. The ledger excludes Earth ascent, orbital refilling losses, boiloff, finite-burn losses, reserve policy, hover/divert, plane changes, entry thrust, surface stay and Earth return. The unvalidated aerodynamic step is particularly consequential.

A propulsive-capture architecture must additionally budget capture, deorbit and the changed entry state; the 250 km circular capture cost cannot be silently omitted or simultaneously credited as free atmospheric braking. Conversely, direct entry does not require paying a circularization burn first. These are alternative mission architectures, not interchangeable labels for the same burn sequence.

For a finite burn, integrate `T(t)`, `Isp(t)`, mass, position and orientation. A simple `burn_time = m_propellant g0 Isp/T` is valid only for constant thrust/Isp and the specified consumed mass. Long Earth-periapsis burns cannot generally be replaced by one instantaneous impulse without assessing losses, arc splitting and retargeting. Capacity alone does not establish delivered delta-v.

## 9. Mars approach, capture or entry, and B-plane targeting

For the analytic excess speed of `2.649001 km/s`, a point-mass 250 km Mars capture has incoming periapsis speed `5.523525 km/s` and circular speed `3.427253 km/s`, yielding an aligned impulsive capture cost of `2.096273 km/s`. The dated example has different values because its boundary geometry is different.

For an arbitrary target ellipse with periapsis `r_p` and apoapsis `r_a`:

```text
a_target = (r_p+r_a)/2
v_target,p = sqrt(mu_Mars [2/r_p - 1/a_target])
Delta-v_capture = |v_incoming,p_vector - v_target,p_vector|
```

Capture must be targeted at the correct position and orientation, not just the correct radius. In a B-plane construction, choose the incoming asymptote convention explicitly. For example, use `S_hat = unit(v_inf,in)`, pick a nonparallel reference axis, define `T_hat = unit(reference cross S_hat)`, and `R_hat = S_hat cross T_hat`. The B-plane coordinates `B_T` and `B_R` specify the transverse offset. Different software packages use different signs/reference axes; exchange the basis vectors alongside the numbers.

In an unpowered point-mass hyperbola, impact parameter magnitude and periapsis are related by:

```text
b = (mu_Mars/v_inf²) sqrt(e_h²-1)
e_h = 1 + r_p v_inf²/mu_Mars
```

At a selected atmospheric interface radius `r_EI`, define inertial flight-path angle by `gamma = asin(r_hat dot v_hat)`; descending is negative. Before appreciable drag:

```text
v_EI = sqrt(v_inf² + 2 mu_Mars/r_EI)
h_specific = r_EI v_EI cos(gamma)
b = h_specific/v_inf
```

For the analytic case at 125 km altitude, `v_EI = 5.598508 km/s`. Selecting an illustrative inertial `gamma = -12°` gives `b = 7279.205 km` and a vacuum periapsis approximately `0.182 km` below the selected reference sphere. Atmospheric forces substantially alter the subsequent path. This does not establish a safe corridor: changing gamma can trade skipping, heat load, load factor, range and propellant in ways that depend on the actual vehicle.

For atmospheric calculations, use velocity relative to the rotating atmosphere and wind:

```text
v_air = v_inertial - omega_Mars cross r - v_wind
q_dynamic = rho |v_air|²/2
D = q_dynamic C_D A,  L = q_dynamic C_L A
ballistic_coefficient = m/(C_D A)
```

Body attitude, angle of attack, sideslip and bank determine aerodynamic force/moment directions. A hypersonic heating correlation may have the form `q_dot = k sqrt(rho/R_n) |v_air|³`, but its coefficient and regime must be appropriate to the gas, shape and chemistry. It is not a substitute for aerothermal/TPS analysis. Current NASA high-mass Mars work examines interactions between supersonic flow, engine plumes and vehicle geometry; low-mass rover hardware should not be scaled by mass alone. [NASA powered-descent wind-tunnel study](https://ntrs.nasa.gov/citations/20240007603), [NASA high-mass EDL shortfalls](https://www.nasa.gov/wp-content/uploads/2024/07/civil-space-shortfall-descriptions-july-2024.pdf).

## 10. Terminal guidance, orientation and physical touchdown

The local landing-frame dynamics must retain thrust direction, local gravity, drag, mass flow and attitude dynamics. For a body-to-inertial orientation `R(q)` and body-axis thrust `T_body`:

```text
r_dot = v
v_dot = gravity + R(q) T_body/m + aerodynamic_force/m
m_dot = -|T_body|/(g0 Isp)
I omega_dot + omega cross (I omega) = commanded_torque + external_torque
q_dot = quaternion_kinematics(q, omega)
```

A spacecraft in cruise does not have a universal correct nose direction: thermal, power and communications requirements can set attitude. If the visualization labels an attitude as **prograde**, use the velocity relative to the selected central body, not its absolute Galactic velocity. A departure burn should show its actual thrust direction; braking usually points thrust against the relevant planet-relative motion, while final hover aligns thrust approximately against local gravity.

For the current model's nose axis `a_hat = +Y`, a shortest-arc display quaternion that aligns it to a requested unit direction `d_hat` can be constructed as `q = normalize([a_hat cross d_hat, 1 + a_hat dot d_hat])`, using vector-first/scalar-last notation. The antiparallel case requires an explicit perpendicular rotation axis; roll requires a secondary reference and continuity handling. Quaternion interpolation should avoid sign flips between equivalent `q` and `-q`. This display construction is separate from integrating physical attitude/actuator limits.

For a simple drag-free vertical braking comparison, assume downward speed `v_down = 100 m/s`, constant local gravity `g = 3.713194 m/s²`, and a constant commanded net upward acceleration of `a_net = 5 m/s²`:

```text
t_brake = v_down/a_net = 20 s
h_brake = v_down²/(2 a_net) = 1000 m
T(t) = m(t) [g + a_net]
Delta-v_propulsive = (g+a_net) t_brake = 174.263881 m/s
m_ignition = m_touchdown exp(Delta-v_propulsive/[g0 Isp])
```

At an assumed `Isp = 330 s` and retained touchdown mass of `200,000 kg`, this model requires `211,064.920 kg` at ignition and consumes `11,064.920 kg` propellant. To keep the net acceleration constant as mass falls, thrust decreases from `1.839050 MN` to `1.742639 MN`. Holding thrust constant would produce a different trajectory. The 1,000 m ideal braking height contains no ignition delay, terrain, sensor, guidance, throttle or reserve margin and is not a commanded ignition altitude.

A reachable landing design must satisfy available thrust, throttle floor, gimbal/attitude bounds, propellant and control authority throughout the trajectory. A necessary vertical deceleration condition is `T_vertical/m > g` while reducing downward velocity; tilting diverts thrust from vertical support. Include horizontal divert, wind rejection, engine startup and terrain clearance in the reachable-set calculation rather than merely changing a visual pitch angle.

Touchdown success requires measured support/contact, bounded vertical and lateral speeds, acceptable attitude/rates, and stable support over a dwell period. Landing gear can be modeled initially with compliant normal forces `F_n = max(0, k penetration - c v_normal)` and friction bounded by the contact normal load. The normal/contact sign convention must be consistent. A depleted tank or impact cannot be converted into a successful landing by assigning a final position. After a terminal event, contact processing should terminate or settle under a bounded workload; it should not run an enormous fast-forward catch-up loop during the touchdown frame.

## 11. Starship public-data profile and what is still unknown

The public-data profile is preserved separately in [starship_public_profile.json](starship_public_profile.json). These values are an attributed snapshot of the official design page, not a configuration-controlled vehicle interface document. SpaceX can revise them. The official page describes on-orbit refilling as part of the Mars architecture. [SpaceX Starship design](https://www.spacex.com/vehicles/starship/design), checked 26 October 2026.

| Public item | Attributed design-page value |
| --- | --- |
| Full system height / diameter | 124 m / 9 m |
| Starship upper-stage height / diameter | 52 m / 9 m |
| Upper-stage propellant capacity | 1,600 tonnes |
| Upper-stage published aggregate thrust | 1,614 tonne-force |
| Published payload capacity | More than 100 tonnes |
| Upper-stage engine arrangement | Three Raptor and three Raptor Vacuum engines |
| Super Heavy height / diameter | 72 m / 9 m |
| Super Heavy propellant capacity | 3,650 tonnes |
| Super Heavy published thrust / engine count | 8,240 tonne-force / 33 engines |
| Propellant constituents | Liquid methane and liquid oxygen |

The listed aggregate thrust is not a throttle/altitude-dependent engine map, nor proof that that thrust is usable in a particular Mars landing configuration. Converting tonne-force uses `1 tf = 9,806.65 N`. The profile intentionally leaves dry mass, usable landing reserve, vacuum/ambient Isp maps, mixture ratio, throttle floor, engine-restart envelope, thrust transients, aero/TPS coefficients, landing stability limits, and certified Mars entry/landing corridor **unknown** unless a configuration-specific primary source is supplied.

The application's **EX-1** experimental transfer tug is a separate vehicle. Its configured 3,500 s transfer Isp is not a methane/oxygen Raptor specification. A complete EX-1 simulation demonstrates the application's modeled trajectory and event sequence only. It cannot validate Starship performance, predict real Starship tank sizes or serve as a universal Mars landing program. The analytic example's assumed 380/330 s Isp values also remain distinct from the public-data profile's unknown performance maps.

## 12. Complete Earth–Mars application run and telemetry contract

The renderer ingests the deterministic complete run supplied by the application's telemetry exporter and appends an evidence section to HTML/PDF. It reports the actual vehicle identifier and profile, epoch, achieved phases, burns, mass/fuel changes, touchdown result and any absent required field. No placeholder values are substituted for missing telemetry.

The expected attachments are [earth_mars_run.json](telemetry/earth_mars_run.json) and [earth_mars_run.csv](telemetry/earth_mars_run.csv), with any separate event history. The document manifest hashes those exact files. The PDF includes representative plots/tables; the full resolution records remain in the attachments. Until the exporter has provided these files, the generated evidence section explicitly says that no full application run has been ingested and makes no completion claim.

| Telemetry group | Fields needed for useful reconstruction |
| --- | --- |
| Identity/provenance | Run/ship/profile IDs, source revision, ephemeris and force model versions, deterministic seed, units, frame and time scale |
| Time/events | Simulated UTC, integration seconds, phase, event identity, event time, selected/achieved clock rate |
| Translational state | Heliocentric and/or barycentric position and velocity, target-relative state, local position and velocity |
| Propulsion | Total mass, propellant remaining, thrust, throttle, mass-flow/Isp configuration, burn impulse and jettison events |
| Attitude | Nose/thrust vector, quaternion convention, angular rates, commanded pointing mode |
| Approach/contact | Altitude definition/datum, vertical/lateral speed, target range, leg loads, contact dwell and success/failure reason |
| Communications | Range, geometric/retarded light time distinction, RF/optical frequency, powers, gains, losses, received power and link margin |
| Error/performance | Integration residuals/tolerances, navigation covariance, missed deadlines, frame-time percentiles, model exceptions |

For an RF link, a basic accounting relation is `P_r,dBW = P_t,dBW + G_t,dBi + G_r,dBi - FSPL_dB - L_other,dB`, with `FSPL = 20 log10(4 pi range/lambda)`. Received power alone is not a data-rate or availability guarantee: noise temperature/bandwidth, coding, pointing, occultation, plasma and hardware constraints are additional inputs. Propagation latency and a live image feed are different data products; a simulation view must not be described as live spacecraft camera data.

For a first-order link-budget audit, distinguish carrier power, spectral noise density and the chosen data rate:

```text
lambda = c/frequency
noise_density_W_per_Hz = k_B T_system
(C/N0)_dBHz = carrier_dBW - 10 log10(k_B T_system)
(Eb/N0)_dB = (C/N0)_dBHz - 10 log10(bit_rate_bits_per_s)
margin_dB = available_EbN0 - required_EbN0 - implementation_margin
first_order_one_way_Doppler_Hz = -frequency * range_rate/c
vacuum_one_way_delay = range/c
Shannon_upper_bound_bits_per_s = bandwidth * log2(1 + signal_to_noise_power_ratio)
```

The Doppler sign above makes receding positive range rate a negative frequency shift. A coherent two-way transponder needs its turnaround ratio and both light-time legs; it is not the same observable. Thermal noise uses absolute temperature in kelvin and Boltzmann's constant. Receiver noise figure, antenna efficiency/pointing, bandwidth, modulation/coding thresholds and ground-station conditions must be explicit. Shannon capacity is an ideal theoretical upper bound, not a usable guaranteed telemetry data rate. Consult versioned station/interface models rather than assuming every DSN antenna has the same gain or temperature. [JPL DSN telecommunications handbook](https://deepspace.jpl.nasa.gov/dsndocs/810-005/).

At interplanetary latency, the final descent needs onboard state estimation and guidance; a terrestrial viewer cannot close the touchdown control loop as if it were a local joystick. Range, Doppler and angular observations constrain different components of navigation and are not interchangeable measurements. [NASA navigation fundamentals](https://science.nasa.gov/learn/basics-of-space-flight/chapter13-1/).

The run should preserve the full sequence `READY -> ASCENT -> WAITING WINDOW -> TRANSFER -> CAPTURE ORBIT -> BRAKING + DESCENT -> LANDED`, or record the actual alternative/abort sequence. Automated reporting must read event records rather than infer successful landing from the final image. Every field needs a stable definition so a change in reference frame or phase cannot masquerade as a velocity impulse.

An interactive Play/reset epoch and a deterministic reference-run epoch serve different purposes. Interactive initialization should capture the current time once for the whole shared simulation. A regression run should deliberately freeze its epoch and identify it in the exported metadata so results can be reproduced. Neither the TDB study example nor a deterministic telemetry fixture should be presented as live current-time observations.

## 13. Turning the study into a vehicle-specific mission design

1. Freeze vehicle configuration, payload, mass properties, available propellant after Earth-orbit refilling, reserves, and validated engine/aerodynamic models. Select launch/landing sites and terrain/atmospheric assumptions.
2. Acquire versioned ephemerides, orientation kernels and time/Earth-orientation data; validate frame conversions and units with known geometric cases.
3. Search departure/arrival grids with Lambert seeds. Retain admissible branches under launch-energy, flight-time, arrival-speed, plane, thermal, power, communications and reserve constraints.
4. Design the Earth parking/escape geometry and finite burns. Produce state-vector targets and covariance requirements rather than reusing the analytic reference's coordinate angles as commands.
5. Refine the trajectory in a consistent perturbed numerical model. Design navigation measurements and correction opportunities; propagate covariance and operational uncertainties.
6. Select capture/direct-entry architecture and target B-plane/entry states. Optimize the entry corridor, bank/angle-of-attack history, propulsion transition and reachable landing region with the actual vehicle.
7. Run atmosphere, navigation, mass, engine, aero, wind and terrain dispersions. Track joint constraints and probabilities; assess abort/divert options and required reserves.
8. Verify six-degree-of-freedom guidance, sensors and actuators, software/hardware timing, plume/ground interactions and touchdown stability. Use appropriate independent simulation, test data and flight qualification processes.
9. Export the complete trajectory, phases, state/attitude histories, mass/propellant ledger, covariance/dispersions, source versions and all failures for independent review. A successful nominal application run is one test artifact within this larger process.

## 14. Primary references and scope of evidence

| Reference | Use in this study |
| --- | --- |
| [NASA/JPL Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html) | Exact boundary-state query settings and reproducible response snapshots |
| [JPL Horizons manual](https://ssd.jpl.nasa.gov/horizons/manual.html) | Object centers, reference frames, epochs and ephemeris interpretation |
| [NAIF state vectors](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/spkezr_c.html) | Distinguishing geometric states from corrected observed directions |
| [NAIF time subsystem](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/req/time.html) | Time-scale definitions and conversion requirements |
| [JPL astrodynamic parameters](https://ssd.jpl.nasa.gov/astro_par.html) | AU, day and gravitational parameters |
| [JPL planet physical parameters](https://ssd.jpl.nasa.gov/planets/phys_par.html) | Reference equatorial radii |
| [JPL approximate elements](https://ssd.jpl.nasa.gov/planets/approx_pos.html) | Nominal semimajor axis for the analytic comparison |
| [JPL DE440/DE441 paper](https://ssd.jpl.nasa.gov/doc/de440_de441.html) | Observations-based precision ephemeris modeling |
| [NASA trajectory fundamentals](https://science.nasa.gov/learn/basics-of-space-flight/chapter4-1/) | Transfer geometry context |
| [NASA trajectory browser methodology](https://trajbrowser.arc.nasa.gov/user_guide.php) | Efficient Lambert survey seeds and their limitations |
| [Izzo, Revisiting Lambert's Problem](https://arxiv.org/abs/1403.2705) | Primary algorithm research for robust Lambert families |
| [NASA Glenn specific impulse](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/specific-impulse/) | Propulsion definitions |
| [NASA rocket equation](https://science.nasa.gov/learn/basics-of-space-flight/chapter3-2/) | Propellant and delta-v relation |
| [NASA Mars-GRAM 2024](https://ntrs.nasa.gov/citations/20240012934) | Atmospheric environment/dispersions |
| [NASA powered-descent experimental study](https://ntrs.nasa.gov/citations/20240007603) | Aero/plume/geometry interactions in high-mass descent research |
| [NASA high-mass EDL shortfalls, July 2024](https://www.nasa.gov/wp-content/uploads/2024/07/civil-space-shortfall-descriptions-july-2024.pdf) | Need for high-mass-specific entry/descent validation |
| [SpaceX Starship design](https://www.spacex.com/vehicles/starship/design) | Attributed public dimensions, capacities and architecture snapshot |
| [JPL DSN telecommunications handbook](https://deepspace.jpl.nasa.gov/dsndocs/810-005/) | Versioned station, RF and navigation interface models |
| [NASA navigation fundamentals](https://science.nasa.gov/learn/basics-of-space-flight/chapter13-1/) | Range, Doppler and angular measurement roles |

The worked values are calculations from the stated assumptions and retained source data. They are not figures attributed to a real NASA, SpaceX or US Navy flight plan. The public-data profile, mathematical study and experimental application run remain separate evidence categories throughout the attachments.
