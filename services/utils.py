from __future__ import annotations

import logging
from math import atan2, cos, radians, sin, sqrt
from typing import Iterable

import requests

logger = logging.getLogger(__name__)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in kilometers between two lat/lon pairs."""
    radius_earth_km = 6371.0

    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return radius_earth_km * c


def reverse_geocode(latitude: float, longitude: float) -> dict[str, str | None]:
    """
    Reverse geocode coordinates to get address and postcode.
    Uses OpenStreetMap Nominatim (free, no API key required).
    
    Returns:
        dict with 'address' (full address) and 'postcode' (postal code)
        Returns empty strings if geocoding fails
    """
    try:
        # Use Nominatim (OpenStreetMap) - free, no API key needed
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": str(latitude),
            "lon": str(longitude),
            "format": "json",
            "addressdetails": 1,
        }
        headers = {
            "User-Agent": "MaintenanceDispatch/1.0"  # Required by Nominatim
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if "address" not in data:
            return {"address": "", "postcode": ""}
        
        address_parts = data.get("address", {})
        
        # Extract postcode
        postcode = (
            address_parts.get("postcode") or 
            address_parts.get("postal_code") or 
            ""
        )
        
        # Build full address
        # Try to get formatted address, or build from components
        display_name = data.get("display_name", "")
        
        # If display_name is available, use it (it's usually well formatted)
        if display_name:
            address = display_name
        else:
            # Build address from components
            components = []
            if address_parts.get("house_number"):
                components.append(address_parts["house_number"])
            if address_parts.get("road"):
                components.append(address_parts["road"])
            if address_parts.get("city") or address_parts.get("town"):
                components.append(address_parts.get("city") or address_parts.get("town"))
            if postcode:
                components.append(postcode)
            if address_parts.get("country"):
                components.append(address_parts["country"])
            address = ", ".join(components) if components else ""
        
        return {
            "address": address,
            "postcode": postcode,
        }
    except requests.RequestException as e:
        logger.warning(f"Reverse geocoding failed: {e}")
        return {"address": "", "postcode": ""}
    except Exception as e:
        logger.warning(f"Reverse geocoding error: {e}")
        return {"address": "", "postcode": ""}

