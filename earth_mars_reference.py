#!/usr/bin/env python3
"""Reproduce the non-operational Earth--Mars study's numerical examples.

Uses only Python's standard library. The default is completely offline.
--fetch-horizons explicitly retrieves two read-only JPL Horizons responses and
preserves the exact response bytes and provenance alongside the report.

This is an independently inspectable study calculator, not flight software.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DAY = 86400.0
AU_KM = 149597870.7
MU_SUN = 1.32712440041279419e11  # km^3/s^2, JPL DE440 astrodynamic parameters
MU_EARTH = 398600.435507
MU_MARS_SYSTEM = 42828.375816
R_EARTH = 6378.1366  # km, equatorial radius used for this spherical example
R_MARS = 3396.19
G0 = 9.80665  # m/s^2, conventional standard acceleration
HERE = Path(__file__).resolve().parent
Vec = tuple[float, float, float]


def add(a: Vec, b: Vec) -> Vec:
    return tuple(x + y for x, y in zip(a, b))


def sub(a: Vec, b: Vec) -> Vec:
    return tuple(x - y for x, y in zip(a, b))


def mul(a: Vec, factor: float) -> Vec:
    return tuple(x * factor for x in a)


def dot(a: Vec, b: Vec) -> float:
    return sum(x * y for x, y in zip(a, b))


def cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a: Vec) -> float:
    return math.sqrt(dot(a, a))


def unit(a: Vec) -> Vec:
    length = norm(a)
    if length <= 1e-15:
        raise ValueError("Cannot normalize a zero vector")
    return mul(a, 1 / length)


def degrees_between(a: Vec, b: Vec) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(unit(a), unit(b))))))


def radec(vector: Vec) -> dict[str, float]:
    return {"right_ascension_deg": math.degrees(math.atan2(vector[1], vector[0])) % 360,
            "declination_deg": math.degrees(math.asin(unit(vector)[2]))}


def rotate(vector: Vec, axis: Vec, angle: float) -> Vec:
    axis = unit(axis)
    return add(add(mul(vector, math.cos(angle)), mul(cross(axis, vector), math.sin(angle))),
               mul(axis, dot(axis, vector) * (1 - math.cos(angle))))


def mass_before_burn(final_mass: float, delta_v_m_s: float, isp_seconds: float) -> float:
    if final_mass <= 0 or delta_v_m_s < 0 or isp_seconds <= 0:
        raise ValueError("Invalid rocket-equation inputs")
    return final_mass * math.exp(delta_v_m_s / (G0 * isp_seconds))


def hyperbola(v_infinity_km_s: float, periapsis_km: float, mu: float) -> dict[str, float]:
    eccentricity = 1 + periapsis_km * v_infinity_km_s**2 / mu
    return {
        "v_infinity_km_s": v_infinity_km_s,
        "c3_km2_s2": v_infinity_km_s**2,
        "periapsis_radius_km": periapsis_km,
        "eccentricity": eccentricity,
        "v_periapsis_km_s": math.sqrt(v_infinity_km_s**2 + 2 * mu / periapsis_km),
        "v_circular_km_s": math.sqrt(mu / periapsis_km),
        "asymptote_true_anomaly_deg": math.degrees(math.acos(-1 / eccentricity)),
        "total_deflection_deg": math.degrees(2 * math.asin(1 / eccentricity)),
        "impact_parameter_km": periapsis_km * math.sqrt(1 + 2 * mu / (periapsis_km * v_infinity_km_s**2)),
    }


def analytic_reference() -> dict:
    # Ideal circular, coplanar orbits. Mars a is the nominal J2000 element,
    # deliberately frozen for this comparison, not an ephemeris at a date.
    earth_r, mars_r = AU_KM, 1.52371034 * AU_KM
    axis = (earth_r + mars_r) / 2
    tof = math.pi * math.sqrt(axis**3 / MU_SUN)
    n_earth = math.sqrt(MU_SUN / earth_r**3)
    n_mars = math.sqrt(MU_SUN / mars_r**3)
    earth_v = math.sqrt(MU_SUN / earth_r)
    mars_v = math.sqrt(MU_SUN / mars_r)
    depart_v = math.sqrt(MU_SUN * (2 / earth_r - 1 / axis))
    arrive_v = math.sqrt(MU_SUN * (2 / mars_r - 1 / axis))
    departure = hyperbola(depart_v - earth_v, R_EARTH + 200, MU_EARTH)
    arrival = hyperbola(mars_v - arrive_v, R_MARS + 250, MU_MARS_SYSTEM)
    tmi = departure["v_periapsis_km_s"] - departure["v_circular_km_s"]
    capture = arrival["v_periapsis_km_s"] - arrival["v_circular_km_s"]
    entry_radius = R_MARS + 125
    entry_speed = math.sqrt(arrival["v_infinity_km_s"]**2 + 2 * MU_MARS_SYSTEM / entry_radius)
    gamma = math.radians(-12)  # A hypothetical target, not a validated corridor.
    h_entry = entry_radius * entry_speed * math.cos(gamma)
    b_entry = h_entry / arrival["v_infinity_km_s"]
    e_entry = math.sqrt(1 + (b_entry * arrival["v_infinity_km_s"]**2 / MU_MARS_SYSTEM)**2)
    vacuum_periapsis = MU_MARS_SYSTEM / arrival["v_infinity_km_s"]**2 * (e_entry - 1)

    # Constant-g, drag-free vertical braking reference. Feedback varies thrust
    # with mass to hold a constant net upward acceleration.
    gravity = MU_MARS_SYSTEM / R_MARS**2 * 1000
    initial_down_speed, net_up_accel, landing_isp = 100.0, 5.0, 330.0
    brake_time = initial_down_speed / net_up_accel
    brake_height = initial_down_speed**2 / (2 * net_up_accel)
    landing_dv = (gravity + net_up_accel) * brake_time
    final_mass = 200000.0  # Generic retained mass; no Starship dry-mass claim.
    before_landing = mass_before_burn(final_mass, landing_dv, landing_isp)
    before_tcm = mass_before_burn(before_landing, 100, 380)
    before_tmi = mass_before_burn(before_tcm, tmi * 1000, 380)
    propellant = before_tmi - final_mass
    # Mixture ratio is an example assumption, not a Raptor specification.
    ox_fuel_ratio = 3.6

    return {
        "model": "Ideal circular coplanar Hohmann; no departure date; point-mass patched conics",
        "earth_orbit_radius_au": 1.0, "mars_orbit_radius_au": 1.52371034,
        "transfer_semimajor_axis_au": axis / AU_KM,
        "time_of_flight_days": tof / DAY,
        "earth_period_days": 2 * math.pi / n_earth / DAY,
        "mars_period_days": 2 * math.pi / n_mars / DAY,
        "synodic_period_days": 2 * math.pi / (n_earth - n_mars) / DAY,
        "mars_lead_angle_at_departure_deg": math.degrees(math.pi - n_mars * tof),
        "earth_departure_heliocentric_velocity_km_s": [0, earth_v, 0],
        "transfer_departure_heliocentric_velocity_km_s": [0, depart_v, 0],
        "mars_arrival_heliocentric_speed_km_s": mars_v,
        "transfer_arrival_heliocentric_speed_km_s": arrive_v,
        "earth_escape_from_200km": departure,
        "tmi_delta_v_km_s": tmi,
        "departure_periapsis_polar_angle_deg_in_arbitrary_plane": 90 - departure["asymptote_true_anomaly_deg"],
        "departure_tangential_burn_polar_angle_deg_in_arbitrary_plane": 180 - departure["asymptote_true_anomaly_deg"],
        "mars_capture_to_250km": arrival,
        "mars_circular_capture_delta_v_km_s": capture,
        "entry_reference": {"altitude_km": 125, "inertial_speed_km_s": entry_speed,
                            "assumed_inertial_flight_path_angle_deg": -12,
                            "vacuum_impact_parameter_km": b_entry,
                            "vacuum_periapsis_altitude_km": vacuum_periapsis - R_MARS},
        "terminal_braking_reference": {
            "gravity_m_s2": gravity, "initial_down_speed_m_s": initial_down_speed,
            "net_up_acceleration_m_s2": net_up_accel, "isp_s_assumed": landing_isp,
            "ideal_time_s": brake_time, "ideal_height_m": brake_height,
            "propulsive_delta_v_m_s": landing_dv, "retained_touchdown_mass_kg_assumed": final_mass,
            "mass_at_ignition_kg": before_landing,
            "propellant_burned_kg": before_landing - final_mass,
            "initial_thrust_N": before_landing * (gravity + net_up_accel),
            "final_thrust_N": final_mass * (gravity + net_up_accel),
        },
        "direct_entry_ideal_mass_ledger": {
            "architecture": "TMI + assumed 100 m/s TCM + unvalidated aerodynamic deceleration + ideal terminal example",
            "vacuum_isp_s_assumed": 380, "terminal_isp_s_assumed": landing_isp,
            "tmi_initial_mass_kg": before_tmi, "tmi_propellant_kg": before_tmi - before_tcm,
            "tcm_initial_mass_kg": before_tcm, "tcm_propellant_kg": before_tcm - before_landing,
            "terminal_initial_mass_kg": before_landing, "terminal_propellant_kg": before_landing - final_mass,
            "touchdown_retained_mass_kg": final_mass, "total_propellant_kg": propellant,
            "hypothetical_oxidizer_to_fuel_mass_ratio": ox_fuel_ratio,
            "methane_kg_if_assumed_ratio": propellant / (1 + ox_fuel_ratio),
            "oxygen_kg_if_assumed_ratio": propellant * ox_fuel_ratio / (1 + ox_fuel_ratio),
            "exclusions": ["Earth ascent", "refueling transfer losses", "boiloff", "finite-burn losses",
                           "reserve policy", "hover/divert", "engine startup/shutdown", "aerothermal feasibility",
                           "entry thrust", "plane changes", "surface stay", "return mission"],
        },
    }


def stumpff(z: float) -> tuple[float, float]:
    if abs(z) < 1e-5:
        return (.5 - z / 24 + z*z / 720 - z**3 / 40320,
                1/6 - z / 120 + z*z / 5040 - z**3 / 362880)
    if z > 0:
        root = math.sqrt(z)
        return (1 - math.cos(root)) / z, (root - math.sin(root)) / root**3
    root = math.sqrt(-z)
    return (math.cosh(root) - 1) / (-z), (math.sinh(root) - root) / root**3


def lambert(r1v: Vec, r2v: Vec, tof: float, mu: float, normal: Vec) -> tuple[Vec, Vec]:
    """Zero-revolution universal-variable solution; rejects collinear endpoints."""
    r1, r2 = norm(r1v), norm(r2v)
    cosine = max(-1.0, min(1.0, dot(r1v, r2v) / (r1 * r2)))
    sine = math.sqrt(max(0.0, 1 - cosine * cosine))
    if dot(cross(r1v, r2v), normal) < 0:
        sine = -sine
    if abs(sine) < 1e-10:
        raise ValueError("Collinear Lambert boundary: select a different epoch or algorithm")
    a = sine * math.sqrt(r1 * r2 / (1 - cosine))

    def evaluate(z: float) -> tuple[float, float] | None:
        c, s = stumpff(z)
        if c <= 0:
            return None
        y = r1 + r2 + a * (z * s - 1) / math.sqrt(c)
        if y < 0:
            return None
        return ((y / c)**1.5 * s + a * math.sqrt(y)) / math.sqrt(mu), y

    low_edge, high_edge = -4 * math.pi**2, 4 * math.pi**2 - 1e-6
    previous_z, previous_value = low_edge, None
    bracket = None
    for i in range(2001):
        z = low_edge + (high_edge - low_edge) * i / 2000
        result = evaluate(z)
        if result is not None and result[0] >= tof:
            bracket = (previous_z, z)
            break
        previous_z, previous_value = z, result
    if bracket is None:
        raise ValueError("No zero-revolution Lambert root in the supported range")
    lo, hi = bracket
    if previous_value is not None and previous_value[0] > tof:
        raise ValueError("Root bracket has no lower physical branch")
    for _ in range(110):
        z = (lo + hi) / 2
        result = evaluate(z)
        if result is None or result[0] < tof:
            lo = z
        else:
            hi = z
    z = (lo + hi) / 2
    result = evaluate(z)
    if result is None or abs(result[0] - tof) > 1e-10 * tof:
        raise ValueError("Lambert time residual exceeds tolerance")
    _, y = result
    f, g, gd = 1 - y / r1, a * math.sqrt(y / mu), 1 - y / r2
    return mul(sub(r2v, mul(r1v, f)), 1 / g), mul(sub(mul(r2v, gd), r1v), 1 / g)


def rk4_orbit(r: Vec, v: Vec, seconds: float, step: float = 1800) -> tuple[Vec, Vec]:
    """Independent Cartesian RK4 check, not the Lambert algorithm's f/g map."""
    def acceleration(position: Vec) -> Vec:
        return mul(position, -MU_SUN / norm(position)**3)

    count = max(1, math.ceil(abs(seconds) / step))
    h = seconds / count
    for _ in range(count):
        a1 = acceleration(r)
        v2, r2 = add(v, mul(a1, h / 2)), add(r, mul(v, h / 2))
        a2 = acceleration(r2)
        v3, r3 = add(v, mul(a2, h / 2)), add(r, mul(v2, h / 2))
        a3 = acceleration(r3)
        v4, r4 = add(v, mul(a3, h)), add(r, mul(v3, h))
        a4 = acceleration(r4)
        r = add(r, mul(add(add(v, mul(v2, 2)), add(mul(v3, 2), v4)), h / 6))
        v = add(v, mul(add(add(a1, mul(a2, 2)), add(mul(a3, 2), a4)), h / 6))
    return r, v


def julian_day_tdb_calendar(text: str) -> float:
    # This parses a TDB calendar label. It does not convert civil UTC to TDB.
    value = datetime.fromisoformat(text)
    if value.tzinfo is not None:
        raise ValueError("Supply a timezone-free calendar explicitly interpreted as TDB")
    return 2451545 + (value - datetime(2000, 1, 1, 12)).total_seconds() / DAY


def fetch_horizons(target: str, departure: str, arrival: str, destination: Path) -> Path:
    parameters = {
        "format": "json", "COMMAND": f"'{target}'", "OBJ_DATA": "'YES'",
        "MAKE_EPHEM": "'YES'", "EPHEM_TYPE": "'VECTORS'", "CENTER": "'500@10'",
        "TLIST": "'" + " ".join(f"{julian_day_tdb_calendar(t):.12f}" for t in (departure, arrival)) + "'",
        "TLIST_TYPE": "'JD'", "TIME_TYPE": "'TDB'", "REF_SYSTEM": "'ICRF'",
        "REF_PLANE": "'FRAME'", "VEC_CORR": "'NONE'", "OUT_UNITS": "'KM-S'",
        "CSV_FORMAT": "'YES'", "VEC_TABLE": "'2'", "TIME_DIGITS": "'FRACSEC'",
    }
    url = "https://ssd.jpl.nasa.gov/api/horizons.api?" + urlencode(parameters)
    request = Request(url, headers={"User-Agent": "Cybertwip-Space-study/1.0"})
    with urlopen(request, timeout=45) as response:
        raw = response.read(2_000_000)
    packet = json.loads(raw)
    if "error" in packet or "$$SOE" not in packet.get("result", ""):
        raise ValueError(f"Horizons request rejected: {packet.get('error', packet)}")
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"horizons_{target}.json"
    path.write_bytes(raw)
    provenance = {"retrieved_utc": datetime.now(timezone.utc).isoformat(), "url": url,
                  "sha256": hashlib.sha256(raw).hexdigest(), "parameters": parameters,
                  "source_signature": packet.get("signature", {})}
    path.with_suffix(".provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return path


def read_horizons(path: Path, expected_target: str) -> list[dict]:
    packet = json.loads(path.read_text())
    result = packet["result"]
    for required in ("ICRF", "KM-S", "TDB", "Sun (10)", f"({expected_target})"):
        if required not in result:
            raise ValueError(f"Unexpected Horizons frame/units/target: missing {required!r}")
    if "geometric" not in result.lower():
        raise ValueError("Geometric vector state required")
    block = result.split("$$SOE", 1)[1].split("$$EOE", 1)[0]
    output = []
    for row in csv.reader(io.StringIO(block)):
        if not row or not row[0].strip():
            continue
        values = [float(v) for v in row[2:8]]
        output.append({"jd_tdb": float(row[0]), "calendar_tdb": row[1].strip(),
                       "r_km": tuple(values[:3]), "v_km_s": tuple(values[3:])})
    if len(output) != 2:
        raise ValueError("Expected exactly two epochs per Horizons response")
    return output


def epoch_case(earth_path: Path, mars_path: Path) -> dict:
    earth, mars = read_horizons(earth_path, "399"), read_horizons(mars_path, "499")
    if [r["jd_tdb"] for r in earth] != [r["jd_tdb"] for r in mars]:
        raise ValueError("Earth and Mars epochs do not match")
    tof = (earth[1]["jd_tdb"] - earth[0]["jd_tdb"]) * DAY
    if tof <= 0:
        raise ValueError("Arrival must follow departure")
    e0, m1 = earth[0], mars[1]
    earth_normal = unit(cross(e0["r_km"], e0["v_km_s"]))
    v1, v2 = lambert(e0["r_km"], m1["r_km"], tof, MU_SUN, earth_normal)
    excess_out, excess_in = sub(v1, e0["v_km_s"]), sub(v2, m1["v_km_s"])
    departure = hyperbola(norm(excess_out), R_EARTH + 200, MU_EARTH)
    arrival = hyperbola(norm(excess_in), R_MARS + 250, MU_MARS_SYSTEM)
    transfer_normal = unit(cross(e0["r_km"], v1))
    # One illustrative escape plane, chosen by projecting the Earth orbital
    # normal orthogonal to v_infinity. It is not a launch-site feasibility solve.
    s = unit(excess_out)
    escape_normal = unit(sub(earth_normal, mul(s, dot(earth_normal, s))))
    p = rotate(s, escape_normal, -math.radians(departure["asymptote_true_anomaly_deg"]))
    q = unit(cross(escape_normal, p))
    endpoint, endpoint_velocity = rk4_orbit(e0["r_km"], v1, tof)
    distance = norm(sub(m1["r_km"], earth[1]["r_km"]))
    return {
        "model": "JPL geometric boundary states; zero-revolution Sun-only Lambert and patched-conic reference; not optimized",
        "departure_tdb": e0["calendar_tdb"], "arrival_tdb": m1["calendar_tdb"],
        "frame": "ICRF axes, Sun origin, geometric vectors, km and km/s",
        "time_of_flight_days": tof / DAY,
        "earth_at_departure": e0, "mars_at_arrival": m1,
        "spacecraft_departure_v_km_s": v1, "spacecraft_arrival_v_km_s": v2,
        "earth_departure_v_infinity_km_s": excess_out,
        "mars_arrival_v_infinity_km_s": excess_in,
        "departure_asymptote_icrf": radec(excess_out),
        "arrival_velocity_asymptote_icrf": radec(excess_in),
        "transfer_inclination_to_icrf_equator_deg": degrees_between(transfer_normal, (0, 0, 1)),
        "transfer_inclination_to_earth_osculating_orbit_deg": degrees_between(transfer_normal, earth_normal),
        "departure_hyperbola": departure, "arrival_hyperbola": arrival,
        "tmi_from_200km_aligned_circle_km_s": departure["v_periapsis_km_s"] - departure["v_circular_km_s"],
        "capture_to_250km_aligned_circle_km_s": arrival["v_periapsis_km_s"] - arrival["v_circular_km_s"],
        "one_mathematical_escape_plane": {
            "normal_icrf": escape_normal, "periapsis_r_km": mul(p, R_EARTH + 200),
            "burn_direction_icrf": q, "burn_direction_angles": radec(q),
            "inclination_to_icrf_equator_deg": degrees_between(escape_normal, (0, 0, 1)),
            "note": "Illustrative only; Earth orientation, launch site, parking orbit, eclipse and finite burns not solved",
        },
        "independent_rk4_endpoint_error_km": norm(sub(endpoint, m1["r_km"])),
        "independent_rk4_velocity_error_km_s": norm(sub(endpoint_velocity, v2)),
        "earth_mars_distance_at_arrival_km": distance,
        "instantaneous_range_over_c_seconds": distance / 299792.458,
        "source_files": [earth_path.name, mars_path.name],
        "source_sha256": [hashlib.sha256(pth.read_bytes()).hexdigest() for pth in (earth_path, mars_path)],
    }


def verify(result: dict) -> dict:
    ref = result["analytic_reference"]
    assert 258 < ref["time_of_flight_days"] < 260
    assert 43 < ref["mars_lead_angle_at_departure_deg"] < 46
    assert 778 < ref["synodic_period_days"] < 782
    assert 3.5 < ref["tmi_delta_v_km_s"] < 3.8
    assert 1.9 < ref["mars_circular_capture_delta_v_km_s"] < 2.3
    ledger = ref["direct_entry_ideal_mass_ledger"]
    consumed = sum(ledger[key] for key in ("tmi_propellant_kg", "tcm_propellant_kg", "terminal_propellant_kg"))
    assert abs(consumed - ledger["total_propellant_kg"]) < 1e-7
    assert abs(ledger["tmi_initial_mass_kg"] - consumed - ledger["touchdown_retained_mass_kg"]) < 1e-7
    # Independent integration of the analytic half ellipse.
    r, _ = rk4_orbit((AU_KM, 0, 0), tuple(ref["transfer_departure_heliocentric_velocity_km_s"]), ref["time_of_flight_days"] * DAY)
    analytic_error = norm(sub(r, (-ref["mars_orbit_radius_au"] * AU_KM, 0, 0)))
    assert analytic_error < .1, analytic_error
    if "horizons_epoch_case" in result:
        case = result["horizons_epoch_case"]
        assert case["independent_rk4_endpoint_error_km"] < .1
        assert case["independent_rk4_velocity_error_km_s"] < 1e-6
    return {"passed": True, "analytic_horizon_rk4_endpoint_error_km": analytic_error,
            "checks": ["units/ranges", "positive propellant ledger", "mass conservation",
                       "independent Cartesian integration of analytic transfer"] +
                      (["independent Cartesian integration of epoch Lambert transfer"] if "horizons_epoch_case" in result else [])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "earth_mars_reference_results.json")
    parser.add_argument("--data-dir", type=Path, default=HERE / "earth_mars_data")
    parser.add_argument("--fetch-horizons", action="store_true")
    parser.add_argument("--departure", default="2026-11-20 00:00:00", help="Calendar interpreted as TDB, not UTC")
    parser.add_argument("--arrival", default="2027-07-18 00:00:00", help="Calendar interpreted as TDB, not UTC")
    args = parser.parse_args()
    if args.fetch_horizons:
        for target in ("399", "499"):
            fetch_horizons(target, args.departure, args.arrival, args.data_dir)
    result = {
        "document": "Draft study for Cybertwip; proposed addressees SpaceX and NASA; no US Navy authorship or endorsement claimed",
        "constants_units": "distances km; speeds km/s unless field says m/s; SI rocket equation; TDB boundary epochs",
        "constants": {"au_km": AU_KM, "mu_sun_km3_s2": MU_SUN, "mu_earth_km3_s2": MU_EARTH,
                      "mu_mars_system_km3_s2_point_mass_approximation": MU_MARS_SYSTEM,
                      "earth_equatorial_radius_km": R_EARTH, "mars_equatorial_radius_km": R_MARS, "g0_m_s2": G0},
        "analytic_reference": analytic_reference(),
    }
    earth_path, mars_path = [args.data_dir / f"horizons_{target}.json" for target in ("399", "499")]
    if earth_path.exists() and mars_path.exists():
        result["horizons_epoch_case"] = epoch_case(earth_path, mars_path)
    result["verification"] = verify(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "verification": result["verification"],
                      "time_of_flight_days": result["analytic_reference"]["time_of_flight_days"],
                      "tmi_delta_v_km_s": result["analytic_reference"]["tmi_delta_v_km_s"],
                      "epoch_case_included": "horizons_epoch_case" in result}, indent=2))


if __name__ == "__main__":
    main()
