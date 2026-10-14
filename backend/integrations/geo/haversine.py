"""Cálculo de distância entre dois pontos (fórmula de Haversine)."""

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_M = 6_371_008.8


def haversine_distance_m(lat1, lng1, lat2, lng2):
    """Distância em metros (float) entre dois pontos em graus decimais."""
    phi1, phi2 = radians(float(lat1)), radians(float(lat2))
    d_phi = phi2 - phi1
    d_lambda = radians(float(lng2)) - radians(float(lng1))
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))
