"""
Global substation catalog — emphasis on India (POWERGRID / state transmission hubs).

Coordinates are approximate locations of major grid substations for demo GIS display.
"""

from typing import Any

# (name, lat, lon, voltage_kv, region, state_or_country, health, description)
INDIA_SUBSTATIONS: list[tuple[str, float, float, int, str, str, str, str]] = [
    ("SS-DEL-NORTH-765", 28.7041, 77.1025, 765, "India", "Delhi", "healthy", "POWERGRID Delhi NCR 765kV hub"),
    ("SS-DEL-ROHINI-400", 28.7495, 77.0565, 400, "India", "Delhi", "healthy", "Rohini 400kV AIS substation"),
    ("SS-MUM-KALWA-400", 19.1943, 73.0004, 400, "India", "Maharashtra", "attention_required", "Mumbai Kalwa 400kV — high coastal load"),
    ("SS-MUM-TALOJA-220", 19.0642, 73.0898, 220, "India", "Maharashtra", "healthy", "Mumbai suburban 220kV"),
    ("SS-PNQ-CHAKAN-400", 18.7608, 73.8631, 400, "India", "Maharashtra", "healthy", "Pune Chakan industrial corridor"),
    ("SS-NAG-WARDHA-765", 20.7453, 78.6022, 765, "India", "Maharashtra", "healthy", "Nagpur Wardha 765kV inter-regional hub"),
    ("SS-BLR-ELECTRONIC-400", 12.9591, 77.6974, 400, "India", "Karnataka", "healthy", "Bangalore Electronic City 400kV"),
    ("SS-BLR-NELAMANGALA-765", 13.0982, 77.3910, 765, "India", "Karnataka", "attention_required", "Nelamangala 765kV — Karnataka grid backbone"),
    ("SS-CHN-ENNORE-400", 13.1449, 80.3265, 400, "India", "Tamil Nadu", "healthy", "Chennai Ennore coastal substation"),
    ("SS-CHN-SRIperumbudur-400", 12.9675, 79.9447, 400, "India", "Tamil Nadu", "healthy", "Sriperumbudur industrial 400kV"),
    ("SS-HYD-KONDAPUR-400", 17.4604, 78.3562, 400, "India", "Telangana", "healthy", "Hyderabad western ring 400kV"),
    ("SS-HYD-CHEVELLA-765", 17.3089, 78.1378, 765, "India", "Telangana", "healthy", "Chevella 765kV southern interconnect"),
    ("SS-AMD-SABARMATI-400", 23.0830, 72.5850, 400, "India", "Gujarat", "healthy", "Ahmedabad Sabarmati 400kV"),
    ("SS-AMD-MUNDRA-765", 22.8395, 69.7249, 765, "India", "Gujarat", "attention_required", "Mundra coastal 765kV — thermal corridor"),
    ("SS-KOL-GARIA-400", 22.4707, 88.3903, 400, "India", "West Bengal", "healthy", "Kolkata Garia 400kV"),
    ("SS-KOL-FARAKKA-765", 24.8258, 87.9310, 765, "India", "West Bengal", "healthy", "Farakka 765kV eastern grid hub"),
    ("SS-JAI-CHOMU-400", 27.1524, 75.7120, 400, "India", "Rajasthan", "healthy", "Jaipur Chomu 400kV"),
    ("SS-JAI-BHADLA-765", 27.5156, 71.8567, 765, "India", "Rajasthan", "healthy", "Bhadla solar corridor 765kV"),
    ("SS-LKO-MALIHABAD-220", 26.8500, 80.9500, 220, "India", "Uttar Pradesh", "healthy", "Lucknow Malihabad 220kV"),
    ("SS-KNP-ANPARA-765", 24.2081, 82.7784, 765, "India", "Uttar Pradesh", "critical", "Anpara 765kV — elevated transformer loading"),
    ("SS-BHO-SEHORE-400", 23.1983, 77.0850, 400, "India", "Madhya Pradesh", "healthy", "Bhopal Sehore 400kV"),
    ("SS-BPL-ITARSI-765", 22.6143, 77.7625, 765, "India", "Madhya Pradesh", "healthy", "Itarsi 765kV central India hub"),
    ("SS-PAT-KANKARBAGH-220", 25.5907, 85.1672, 220, "India", "Bihar", "attention_required", "Patna Kankarbagh 220kV"),
    ("SS-CHD-MANALI-220", 30.7415, 76.7681, 220, "India", "Punjab", "healthy", "Chandigarh Manali 220kV"),
    ("SS-KOC-KALAMASSERY-220", 10.0531, 76.3264, 220, "India", "Kerala", "healthy", "Kochi Kalamassery 220kV"),
    ("SS-GUW-AZARA-400", 26.1060, 91.7389, 400, "India", "Assam", "healthy", "Guwahati Azara 400kV NE grid"),
    ("SS-SRI-BEMINA-220", 34.0837, 74.7973, 220, "India", "Jammu & Kashmir", "attention_required", "Srinagar Bemina 220kV — mountain terrain"),
    ("SS-VIZ-ANAKAPALLE-400", 17.6868, 83.0060, 400, "India", "Andhra Pradesh", "healthy", "Visakhapatnam coastal 400kV"),
    ("SS-VJA-NUNNA-765", 16.5193, 80.6305, 765, "India", "Andhra Pradesh", "healthy", "Vijayawada Nunna 765kV"),
    ("SS-CBE-SINGANALLUR-220", 11.0168, 77.0295, 220, "India", "Tamil Nadu", "healthy", "Coimbatore Singanallur 220kV"),
    ("SS-IND-PITHAMPUR-400", 22.6013, 75.6867, 400, "India", "Madhya Pradesh", "healthy", "Indore Pithampur industrial 400kV"),
    ("SS-RNC-TATISILWAI-400", 23.3441, 85.3096, 400, "India", "Jharkhand", "healthy", "Ranchi Tatisilwai 400kV"),
    ("SS-BBS-MANCHESWAR-400", 20.2961, 85.8245, 400, "India", "Odisha", "healthy", "Bhubaneswar Mancheswar 400kV"),
    ("SS-CHN-NAMAKKAL-765", 11.2189, 78.1672, 765, "India", "Tamil Nadu", "healthy", "Namakkal 765kV wind corridor hub"),
    ("SS-RAI-KORBA-765", 22.3595, 82.7501, 765, "India", "Chhattisgarh", "healthy", "Korba 765kV generation pooling"),
]

WORLD_SUBSTATIONS: list[tuple[str, float, float, int, str, str, str, str]] = [
    ("SS-LON-BARKING-400", 51.5362, 0.0785, 400, "Europe", "United Kingdom", "healthy", "London Barking 400kV"),
    ("SS-BER-MITTE-380", 52.5200, 13.4050, 380, "Europe", "Germany", "healthy", "Berlin Mitte 380kV"),
    ("SS-PAR-COURBEVOIE-400", 48.8975, 2.2567, 400, "Europe", "France", "healthy", "Paris La Défense 400kV"),
    ("SS-TYO-SHINAGAWA-275", 35.6090, 139.7300, 275, "Asia", "Japan", "healthy", "Tokyo Shinagawa 275kV"),
    ("SS-SYD-LIDCOMBE-330", -33.8688, 151.0450, 330, "Oceania", "Australia", "healthy", "Sydney Lidcombe 330kV"),
    ("SS-SAO-ITAIPU-500", -25.4050, -54.5889, 500, "South America", "Brazil", "healthy", "Itaipu 500kV export hub"),
    ("SS-JNB-KELVIN-400", -26.0890, 28.0550, 400, "Africa", "South Africa", "attention_required", "Johannesburg Kelvin 400kV"),
    ("SS-DXB-JEBEL-ALI-400", 25.0053, 55.0954, 400, "Middle East", "UAE", "healthy", "Dubai Jebel Ali 400kV"),
    ("SS-SIN-JURONG-230", 1.3329, 103.7436, 230, "Asia", "Singapore", "healthy", "Jurong 230kV"),
    ("SS-LAX-Vernon-230", 34.0030, -118.2300, 230, "North America", "USA", "healthy", "Los Angeles Vernon 230kV"),
    ("SS-TOR-Pearson-230", 43.6777, -79.6248, 230, "North America", "Canada", "healthy", "Toronto Pearson 230kV"),
    ("SS-MEX-VALLE-400", 19.4326, -99.1332, 400, "North America", "Mexico", "healthy", "Mexico City Valle 400kV"),
    ("SS-BJG-FANGSHAN-500", 39.7355, 116.0090, 500, "Asia", "China", "healthy", "Beijing Fangshan 500kV"),
    ("SS-SEL-GANGNAM-345", 37.4979, 127.0276, 345, "Asia", "South Korea", "healthy", "Seoul Gangnam 345kV"),
    ("SS-RUH-RIYADH-380", 24.7136, 46.6753, 380, "Middle East", "Saudi Arabia", "healthy", "Riyadh central 380kV"),
    ("SS-MOS-KHIMKI-500", 55.8970, 37.4297, 500, "Europe", "Russia", "healthy", "Moscow Khimki 500kV"),
]


def _footprint(lon: float, lat: float, half: float = 0.012) -> dict[str, Any]:
    """Square substation footprint in WGS84 degrees."""
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon - half, lat + half],
            [lon + half, lat + half],
            [lon + half, lat - half],
            [lon - half, lat - half],
            [lon - half, lat + half],
        ]],
    }


def build_substation_assets(
    start_id: int = 100,
) -> list[dict[str, Any]]:
    """Build substation asset dicts from catalog entries."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    assets: list[dict[str, Any]] = []
    idx = start_id

    for entry in INDIA_SUBSTATIONS + WORLD_SUBSTATIONS:
        name, lat, lon, kv, region, location, health, desc = entry
        idx += 1
        transformers = 2 if kv <= 220 else 4 if kv <= 400 else 6
        assets.append({
            "id": f"asset-{idx:03d}",
            "name": name,
            "asset_type": "substation",
            "latitude": lat,
            "longitude": lon,
            "status": "active",
            "health_score": health,
            "description": desc,
            "metadata": {
                "voltage_kv": kv,
                "transformer_count": transformers,
                "region": region,
                "country_or_state": location,
                "operator": "POWERGRID" if region == "India" else "Regional TSO",
            },
            "geometry": _footprint(lon, lat),
            "created_at": now - timedelta(days=200 + idx),
            "updated_at": now - timedelta(hours=idx % 48),
        })

    return assets
