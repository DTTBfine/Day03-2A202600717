from __future__ import annotations

import os
import re
import json
import math
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Callable

try:
    import requests
except ImportError:  # pragma: no cover - fallback for minimal lab environments.
    requests = None


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

HEADERS = {
    "User-Agent": "lab3-travel-planner-agent/1.0",
}

DEFAULT_TIMEOUT = 15
_MAX_RETRIES = 1

AIRPORT_CODE_LOCATIONS = {
    "HAN": "Sân bay Nội Bài, Hà Nội",
    "DAD": "Sân bay Đà Nẵng",
    "SGN": "Sân bay Tân Sơn Nhất, Thành phố Hồ Chí Minh",
    "CXR": "Sân bay Cam Ranh, Khánh Hòa",
    "PQC": "Sân bay Phú Quốc, Kiên Giang",
    "HUI": "Sân bay Phú Bài, Huế",
    "DLI": "Sân bay Liên Khương, Đà Lạt",
    "VCA": "Sân bay Cần Thơ",
    "VII": "Sân bay Vinh",
    "HPH": "Sân bay Cát Bi, Hải Phòng",
}

# Default origin from environment
DEFAULT_ORIGIN = os.getenv("DEFAULT_ORIGIN", "Hà Nội")

# Interest keywords mapping
INTEREST_KEYWORDS = {
    "beach": ["biển", "bãi biển", "tắm biển", "đảo", "hải sản"],
    "seafood": ["hải sản", "cua", "tôm", "cá", "mực"],
    "mountain": ["núi", "rừng", "cao nguyên", "leo núi"],
    "culture": ["chùa", "đền", "temple", "di tích", "lịch sử", "bảo tàng"],
    "food": ["ẩm thực", "ăn uống", "đặc sản", "món ngon", "quán ngon"],
    "cafe": ["cafe", "cà phê", "coffee", "trà"],
    "photo": ["chụp ảnh", "check-in", "sống ảo", "selfie"],
    "relax": ["nghỉ dưỡng", "spa", "massage", "thư giãn"],
    "shopping": ["mua sắm", "chợ", "market", "shopping"],
    "adventure": ["mạo hiểm", "khám phá", "diving", "lặn", " trekking"],
}

SEASON_KEYWORDS = {
    "summer": ["mùa hè", "nóng", "nắng", "mùa nắng"],
    "winter": ["mùa đông", "lạnh", "se lạnh"],
    "spring": ["mùa xuân", "hoa anh đào", "Tết"],
    "autumn": ["mùa thu"],
    "rainy": ["mùa mưa", "mưa"],
}

DESTINATION_TYPE_KEYWORDS = {
    "beach": ["biển", "bãi biển", "đảo", "ven biển", "coastal"],
    "mountain": ["núi", "rừng", "cao nguyên", "highland", "hill station"],
    "city": ["thành phố", "tp", "tp.", "city", "urban"],
    "countryside": ["miền tây", "miền trung", "miền bắc", "miền nam", "nông thôn"],
}


_WMO_DESCRIPTIONS: Dict[int, str] = {
    0: "Trời quang",
    1: "Chủ yếu quang",
    2: "Có mây rải rác",
    3: "Nhiều mây/âm u",
    45: "Sương mù",
    48: "Sương mù có đá",
    51: "Mưa phùn nhẹ",
    53: "Mưa phùn vừa",
    55: "Mưa phùn dày",
    61: "Mưa nhẹ",
    63: "Mưa vừa",
    65: "Mưa to",
    71: "Tuyết nhẹ",
    73: "Tuyết vừa",
    75: "Tuyết dày",
    77: "Hạt tuyết",
    80: "Mưa rào nhẹ",
    81: "Mưa rào vừa",
    82: "Mưa rào mạnh",
    85: "Mưa tuyết nhẹ",
    86: "Mưa tuyết nặng",
    95: "Giông bão",
    96: "Giông kèm mưa đá nhẹ",
    99: "Giông kèm mưa đá mạnh",
}

_geocode_cache: Dict[str, Dict[str, Any]] = {}


def _wmo_description(code: Optional[int]) -> str:
    if code is None:
        return "Không rõ"
    return _WMO_DESCRIPTIONS.get(int(code), f"Mã thời tiết {code}")


def _request_json(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    last_error: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            if requests is None:
                query = urllib.parse.urlencode(params or {})
                full_url = f"{url}?{query}" if query else url
                request = urllib.request.Request(full_url, headers=HEADERS)
                with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
                    return json.loads(response.read().decode("utf-8"))

            resp = requests.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_error = exc
    raise last_error  # type: ignore[misc]


def _resolve_place_query(location: str) -> str:
    return AIRPORT_CODE_LOCATIONS.get(str(location).upper(), location)


def _safe_error(tool_name: str, error: Exception) -> Dict[str, Any]:
    return {
        "tool": tool_name,
        "status": "error",
        "error": str(error),
        "message": (
            "Không lấy được dữ liệu trực tuyến lúc này. "
            "Agent nên nói rõ giới hạn này thay vì tự bịa kết quả."
        ),
    }


def _normalize_limit(limit: int, default: int = 5, max_limit: int = 12) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, max_limit))


def _haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return 2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _format_vnd(amount: int) -> str:
    return f"{amount:,} VND".replace(",", ".")


def _daily_value(daily: Dict[str, List[Any]], key: str, index: int) -> Any:
    values = daily.get(key, [])
    if index >= len(values):
        return None
    return values[index]


def geocode_location(location: str) -> Dict[str, Any]:
    """
    Tìm tọa độ và thông tin định danh cơ bản của một địa điểm.
    Dùng Nominatim/OpenStreetMap nên không cần API key.
    Kết quả thành công được cache trong bộ nhớ để tránh gọi API lặp.
    """
    cache_key = location.strip().lower()
    if cache_key in _geocode_cache:
        return _geocode_cache[cache_key]

    try:
        data = _request_json(
            NOMINATIM_URL,
            {
                "q": _resolve_place_query(location),
                "format": "json",
                "limit": 1,
                "addressdetails": 1,
            },
        )

        if not data:
            return {
                "tool": "geocode_location",
                "status": "not_found",
                "query": location,
                "message": "Không tìm thấy địa điểm phù hợp.",
            }

        item = data[0]
        result: Dict[str, Any] = {
            "tool": "geocode_location",
            "status": "ok",
            "query": location,
            "name": item.get("display_name"),
            "latitude": float(item["lat"]),
            "longitude": float(item["lon"]),
            "type": item.get("type"),
            "address": item.get("address", {}),
            "source": "OpenStreetMap Nominatim",
        }
        _geocode_cache[cache_key] = result
        return result
    except Exception as error:
        return _safe_error("geocode_location", error)


def get_weather(location: str, forecast_days: int = 3) -> Dict[str, Any]:
    """
    Lấy dự báo thời tiết theo ngày cho địa điểm.
    """
    place = geocode_location(location)
    if place.get("status") != "ok":
        return {
            "tool": "get_weather",
            "status": "error",
            "location": location,
            "message": "Không thể lấy thời tiết vì không xác định được tọa độ.",
            "geocode": place,
        }

    days = max(1, min(int(forecast_days or 3), 7))
    try:
        data = _request_json(
            OPEN_METEO_URL,
            {
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "daily": ",".join(
                    [
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "precipitation_probability_max",
                        "weather_code",
                    ]
                ),
                "timezone": "auto",
                "forecast_days": days,
            },
        )

        daily = data.get("daily", {})
        forecasts = []
        for index, day in enumerate(daily.get("time", [])[:days]):
            weather_code = _daily_value(daily, "weather_code", index)
            forecasts.append(
                {
                    "date": day,
                    "temp_min_c": _daily_value(daily, "temperature_2m_min", index),
                    "temp_max_c": _daily_value(daily, "temperature_2m_max", index),
                    "rain_probability_percent": _daily_value(
                        daily,
                        "precipitation_probability_max",
                        index,
                    ),
                    "weather_code": weather_code,
                    "weather_description": _wmo_description(weather_code),
                }
            )

        return {
            "tool": "get_weather",
            "status": "ok",
            "location": location,
            "resolved_location": place.get("name"),
            "forecast_days": days,
            "forecasts": forecasts,
            "source": "Open-Meteo",
        }
    except Exception as error:
        return _safe_error("get_weather", error)


def _overpass_search(
    location: str,
    radius: int,
    limit: int,
    filters: List[str],
    tool_name: str,
) -> Dict[str, Any]:
    place = geocode_location(location)
    if place.get("status") != "ok":
        return {
            "tool": tool_name,
            "status": "error",
            "location": location,
            "message": "Không thể tìm xung quanh vì không xác định được tọa độ.",
            "geocode": place,
        }

    safe_limit = _normalize_limit(limit)
    safe_radius = max(500, min(int(radius or 5000), 30000))
    lat = float(place["latitude"])
    lon = float(place["longitude"])
    filter_query = "\n".join(
        filter_expression.format(radius=safe_radius, lat=lat, lon=lon)
        for filter_expression in filters
    )
    query = f"""
    [out:json][timeout:25];
    (
      {filter_query}
    );
    out center tags {safe_limit};
    """

    try:
        data = _request_json(OVERPASS_URL, {"data": query})
        items = []
        for element in data.get("elements", []):
            tags = element.get("tags", {})
            item_lat = element.get("lat") or element.get("center", {}).get("lat")
            item_lon = element.get("lon") or element.get("center", {}).get("lon")
            if item_lat is None or item_lon is None:
                continue

            name = tags.get("name") or tags.get("name:vi") or tags.get("name:en")
            if not name:
                continue

            items.append(
                {
                    "name": name,
                    "category": (
                        tags.get("tourism")
                        or tags.get("amenity")
                        or tags.get("historic")
                        or tags.get("leisure")
                    ),
                    "latitude": float(item_lat),
                    "longitude": float(item_lon),
                    "distance_km": round(
                        _haversine_km(lat, lon, float(item_lat), float(item_lon)),
                        2,
                    ),
                    "address_hint": tags.get("addr:street"),
                    "website": tags.get("website"),
                    "phone": tags.get("phone"),
                }
            )

        items.sort(key=lambda item: item["distance_km"])
        return {
            "tool": tool_name,
            "status": "ok",
            "location": location,
            "resolved_location": place.get("name"),
            "radius_m": safe_radius,
            "count": len(items[:safe_limit]),
            "results": items[:safe_limit],
            "source": "OpenStreetMap Overpass",
            "warning": (
                "Dữ liệu OSM có thể thiếu giá phòng, giờ mở cửa hoặc đánh giá. "
                "Nên kiểm tra thêm trước khi đặt dịch vụ."
            ),
        }
    except Exception as error:
        return _safe_error(tool_name, error)


def search_attractions(
    location: str,
    radius: int = 10000,
    limit: int = 8,
) -> Dict[str, Any]:
    """
    Tìm điểm tham quan/địa điểm vui chơi quanh một khu vực.
    """
    radius_value = max(500, min(int(radius or 10000), 30000))
    filters = [
        'node(around:{radius},{lat},{lon})["tourism"~"attraction|museum|viewpoint|zoo|theme_park|gallery"];',
        'way(around:{radius},{lat},{lon})["tourism"~"attraction|museum|viewpoint|zoo|theme_park|gallery"];',
        'node(around:{radius},{lat},{lon})["historic"];',
        'way(around:{radius},{lat},{lon})["historic"];',
    ]
    return _overpass_search(location, radius_value, limit, filters, "search_attractions")


def search_stays(
    location: str,
    radius: int = 5000,
    limit: int = 5,
) -> Dict[str, Any]:
    """
    Tìm khách sạn/homestay/hostel quanh một địa điểm.
    """
    radius_value = max(500, min(int(radius or 5000), 30000))
    _stay_types = "hotel|hostel|guest_house|apartment|motel|chalet|resort|villa|cottage|camp_site"
    filters = [
        f'node(around:{{radius}},{{lat}},{{lon}})["tourism"~"{_stay_types}"];',
        f'way(around:{{radius}},{{lat}},{{lon}})["tourism"~"{_stay_types}"];',
    ]
    result = _overpass_search(location, radius_value, limit, filters, "search_stays")
    if result.get("status") == "ok":
        result["price_note"] = (
            "OSM thường không có giá phòng. Hãy xem đây là danh sách khu vực/lựa chọn "
            "để kiểm tra tiếp trên Booking, Agoda hoặc trang trực tiếp của chỗ ở."
        )
    return result


def search_restaurants(
    location: str,
    cuisine: Optional[str] = None,
    radius: int = 5000,
    limit: int = 5,
) -> Dict[str, Any]:
    """
    Tìm quán ăn/nhà hàng/cafe quanh một địa điểm.
    """
    radius_value = max(500, min(int(radius or 5000), 30000))
    cuisine_filter = ""
    if cuisine:
        cuisine_filter = f'["cuisine"~"{cuisine}",i]'

    _food_types = "restaurant|cafe|fast_food|food_court|bar|pub|biergarten|ice_cream|bakery"
    filters = [
        f'node(around:{{radius}},{{lat}},{{lon}})["amenity"~"{_food_types}"]{cuisine_filter};',
        f'way(around:{{radius}},{{lat}},{{lon}})["amenity"~"{_food_types}"]{cuisine_filter};',
    ]
    result = _overpass_search(location, radius_value, limit, filters, "search_restaurants")
    if result.get("status") == "ok":
        result["cuisine_filter"] = cuisine
    return result


def estimate_transport_cost(
    origin: str,
    destination: str,
    mode: str = "bus",
    departure_date: Optional[str] = None,
    passengers: int = 1,
) -> Dict[str, Any]:
    """
    Ước tính chi phí di chuyển khi không có API vé real-time.
    mode: flight, bus, train, car.
    """
    origin_place = geocode_location(origin)
    destination_place = geocode_location(destination)
    if origin_place.get("status") != "ok" or destination_place.get("status") != "ok":
        return {
            "tool": "estimate_transport_cost",
            "status": "error",
            "message": "Không thể ước tính vì không xác định được tọa độ đi/đến.",
            "origin_geocode": origin_place,
            "destination_geocode": destination_place,
        }

    passenger_count = max(1, int(passengers or 1))
    distance_km = _haversine_km(
        origin_place["latitude"],
        origin_place["longitude"],
        destination_place["latitude"],
        destination_place["longitude"],
    )

    normalized_mode = (mode or "bus").lower()
    rates = {
        "flight": (1200000, 2600000, "vé máy bay nội địa phổ thông"),
        "bus": (1200, 2500, "vé xe khách theo km"),
        "train": (1400, 3200, "vé tàu theo km"),
        "car": (3500, 6500, "xăng/thuê xe hoặc taxi đường dài theo km"),
    }
    low_rate, high_rate, label = rates.get(normalized_mode, rates["bus"])

    if normalized_mode == "flight":
        one_way_low = low_rate
        one_way_high = high_rate
    else:
        road_factor = 1.25
        billable_km = max(distance_km * road_factor, 20)
        one_way_low = int(billable_km * low_rate)
        one_way_high = int(billable_km * high_rate)

    return {
        "tool": "estimate_transport_cost",
        "status": "ok",
        "origin": origin,
        "destination": destination,
        "mode": normalized_mode,
        "departure_date": departure_date,
        "passengers": passenger_count,
        "straight_line_distance_km": round(distance_km, 1),
        "estimated_one_way_per_person_vnd": {
            "low": one_way_low,
            "high": one_way_high,
            "display": f"{_format_vnd(one_way_low)} - {_format_vnd(one_way_high)}",
        },
        "estimated_total_vnd": {
            "low": one_way_low * passenger_count,
            "high": one_way_high * passenger_count,
            "display": (
                f"{_format_vnd(one_way_low * passenger_count)} - "
                f"{_format_vnd(one_way_high * passenger_count)}"
            ),
        },
        "source": "Local heuristic estimate",
        "pricing_basis": label,
        "warning": (
            "Đây là ước tính, không phải giá vé real-time. "
            "Giá thực tế phụ thuộc hãng, ngày đi, hành lý và thời điểm đặt."
        ),
    }


def search_flight_cost(
    origin_code: str,
    destination_code: str,
    departure_date: str,
    adults: int = 1,
) -> Dict[str, Any]:
    """
    Alias theo prompt hiện có của agent. Trả về ước tính vé máy bay theo mã sân bay.
    """
    return estimate_transport_cost(
        origin=origin_code,
        destination=destination_code,
        mode="flight",
        departure_date=departure_date,
        passengers=adults,
    )


def build_travel_plan(
    destination: str,
    days: int = 3,
    origin: Optional[str] = None,
    origin_code: Optional[str] = None,
    destination_code: Optional[str] = None,
    departure_date: Optional[str] = None,
    adults: int = 1,
    budget_vnd: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Tổng hợp dữ liệu từ các tool và gợi ý lịch trình đơn giản theo ngày.
    """
    safe_days = max(1, min(int(days or 3), 10))
    resolved_origin = origin or origin_code
    resolved_destination = destination_code or destination

    with ThreadPoolExecutor() as executor:
        future_weather = executor.submit(get_weather, destination, min(safe_days, 7))
        future_attractions = executor.submit(search_attractions, destination, limit=min(8, safe_days * 3))
        future_stays = executor.submit(search_stays, destination, limit=5)
        future_restaurants = executor.submit(search_restaurants, destination, limit=min(8, safe_days * 2))
        future_transport = (
            executor.submit(
                estimate_transport_cost,
                origin=resolved_origin,
                destination=resolved_destination,
                mode="flight" if origin_code or destination_code else "bus",
                departure_date=departure_date,
                passengers=adults,
            )
            if resolved_origin
            else None
        )

        weather = future_weather.result()
        attractions = future_attractions.result()
        stays = future_stays.result()
        restaurants = future_restaurants.result()
        transport = future_transport.result() if future_transport else None

    attraction_names = [
        item["name"] for item in attractions.get("results", []) if item.get("name")
    ]
    restaurant_names = [
        item["name"] for item in restaurants.get("results", []) if item.get("name")
    ]

    itinerary = []
    start_date = _parse_start_date(departure_date)
    for index in range(safe_days):
        day_attractions = attraction_names[index * 2 : index * 2 + 2]
        day_restaurants = restaurant_names[index * 2 : index * 2 + 2]
        itinerary.append(
            {
                "day": index + 1,
                "date": (start_date + timedelta(days=index)).isoformat()
                if start_date
                else None,
                "morning": day_attractions[0] if day_attractions else "Khám phá khu trung tâm",
                "afternoon": day_attractions[1] if len(day_attractions) > 1 else "Nghỉ ngơi/cafe nhẹ",
                "food_suggestions": day_restaurants,
            }
        )

    budget_note = _budget_note(budget_vnd, safe_days, transport)
    return {
        "tool": "build_travel_plan",
        "status": "ok",
        "destination": destination,
        "days": safe_days,
        "budget_vnd": budget_vnd,
        "budget_note": budget_note,
        "weather": weather,
        "attractions": attractions,
        "stays": stays,
        "restaurants": restaurants,
        "transport": transport,
        "suggested_itinerary": itinerary,
        "planning_notes": [
            "Ưu tiên gom điểm gần nhau trong cùng ngày để giảm thời gian di chuyển.",
            "Kiểm tra lại giờ mở cửa, giá vé và chính sách đặt phòng trước khi chốt.",
            "Nếu trời mưa, chuyển các hoạt động ngoài trời sang bảo tàng, cafe hoặc điểm trong nhà.",
        ],
    }


def _parse_start_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _budget_note(
    budget_vnd: Optional[int],
    days: int,
    transport: Optional[Dict[str, Any]],
) -> str:
    if not budget_vnd:
        return "Chưa có ngân sách cụ thể; agent nên đưa phương án tiết kiệm, cân bằng và thoải mái."

    per_day = int(budget_vnd) // max(days, 1)
    note = f"Ngân sách trung bình khoảng {_format_vnd(per_day)}/ngày."
    if transport and transport.get("status") == "ok":
        high_transport = transport["estimated_total_vnd"]["high"]
        remaining = int(budget_vnd) - int(high_transport)
        note += f" Sau ước tính di chuyển cao nhất, còn khoảng {_format_vnd(max(remaining, 0))}."
    return note


def validate_travel_input(user_message: str) -> Dict[str, Any]:
    """
    Validate and normalize user's travel request.

    Extracts: origin, destination, destination_type, budget, people, days, nights,
    season, and interests from Vietnamese text.

    Returns:
        Dict with is_valid, missing_fields, normalized_input, assumptions, follow_up_question
    """
    msg_lower = user_message.lower().strip()
    assumptions = []
    missing_fields = []

    # 1. First detect destination_type (before extracting destination)
    # This prevents "du lịch gần biển" from being captured as destination
    destination_type = None
    for dtype, keywords in DESTINATION_TYPE_KEYWORDS.items():
        if any(kw in msg_lower for kw in keywords):
            destination_type = dtype
            break

    # 2. Extract destination - only if it's a specific place name
    destination = None
    # Simpler approach: find "đi" followed by text, then check if it's a generic phrase
    dest_match = re.search(r"đi\s+([\w\s]+?)(?:\s+từ|\s+ngày|\s+cho\s+\d|\s+budget|\s+ngân\s|sách|,|$)", msg_lower)
    if dest_match:
        dest_candidate = dest_match.group(1).strip()
        # Filter out phrases containing generic keywords
        generic_keywords = ["du lịch", "nghỉ dưỡng", "nghỉ", "biển", "núi", "đảo", "rừng", "gần", "mùa hè", "mùa đông", "tắm", "nắng", "khám phá", "nghỉ ngơi"]
        is_generic = any(kw in dest_candidate for kw in generic_keywords)
        if dest_candidate and not is_generic:
            destination = dest_candidate.title()
    else:
        # Try other patterns
        for pattern in [r"tới\s+([\w\s]+?)(?:\s+từ|,|$)", r"đến\s+([\w\s]+?)(?:\s+từ|,|$)"]:
            match = re.search(pattern, msg_lower)
            if match:
                dest_candidate = match.group(1).strip()
                if dest_candidate:
                    destination = dest_candidate.title()
                break

    # Normalize destination names
    destination = _normalize_destination_name(destination) if destination else None

    # 3. Extract origin
    origin = None
    origin_patterns = [
        r"(?:từ|xuất phát từ|khởi hành từ)\s+([A-Za-zÀ-ỹ\s]+?)(?:\s+ngày|\s+cho|\s+budget|\s+ngân sách|,|$)",
    ]
    for pattern in origin_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            origin_candidate = match.group(1).strip()
            if origin_candidate and len(origin_candidate) > 1:
                origin = origin_candidate.title()
                break

    # Normalize origin names
    origin = _normalize_origin_name(origin) if origin else None
    if not origin:
        origin = DEFAULT_ORIGIN
        assumptions.append("User did not provide origin point, using default.")

    # 4. Extract budget
    budget = None
    budget_patterns = [
        r"(?:budget|ngân sách)\s*:?\s*(\d+(?:[.,]\d+)?)\s*(?:triệu|tr|m)",
        r"(\d+(?:[.,]\d+)?)\s*(?:triệu|tr|m)\s*(?:budget|ngân sách)?",
        r"(\d+(?:[.,]\d+)?)\s*(?:k|nghìn|ngàn)\s*(?:budget|ngân sách)?",
    ]
    for pattern in budget_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            number = float(match.group(1).replace(",", "."))
            if "triệu" in match.group(0) or "tr" in match.group(0) or "m" in match.group(0):
                budget = int(number * 1_000_000)
            else:
                budget = int(number * 1_000)
            break

    # 5. Extract people
    people = None
    people_patterns = [
        r"(\d+)\s*(?:người|người lớn|person|people|người đi)",
        r"(?:cho)\s+(\d+)\s*(?:người|người lớn|person|people)",
        r"(?:với)\s+(\d+)\s*(?:người|người lớn|person|people)",
    ]
    for pattern in people_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            people = int(match.group(1))
            break

    if not people:
        people = 1
        assumptions.append("User did not provide number of people, assumed 1 person.")

    # 6. Extract days
    days = None
    days_patterns = [
        r"(\d+)\s*(?:ngày|days?)(?:\s+(?:\d+|một|hai|ba|bốn|năm)\s*(?:đêm|đêm|nights?))?",
        r"(?:một|hai|ba|bốn|năm)\s*(?:ngày|days?)",
        r"(?:trong)\s+(\d+)\s*(?:ngày|days?)",
    ]
    # Try numeric first
    match = re.search(r"(\d+)\s*(?:ngày|days?)", msg_lower)
    if match:
        days = int(match.group(1))
    # Try word form
    word_to_num = {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5}
    for word, num in word_to_num.items():
        if f"{word} ngày" in msg_lower or f"{word} days" in msg_lower:
            days = num
            break

    # 7. Extract nights
    nights = None
    nights_patterns = [
        r"(\d+)\s*(?:đêm|đêm|nights?)",
        r"(?:một|hai|ba|bốn|năm)\s*(?:đêm|đêm|nights?)",
    ]
    match = re.search(r"(\d+)\s*(?:đêm|đêm|nights?)", msg_lower)
    if match:
        nights = int(match.group(1))
    else:
        word_to_num_night = {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5}
        for word, num in word_to_num_night.items():
            if f"{word} đêm" in msg_lower or f"{word} đêm" in msg_lower:
                nights = num
                break

    if nights is None and days:
        nights = max(days - 1, 0)
        assumptions.append(f"User provided days ({days}) but not nights, calculated as {nights} nights.")

    # 8. Extract season
    season = None
    for seas, keywords in SEASON_KEYWORDS.items():
        if any(kw in msg_lower for kw in keywords):
            season = seas
            break

    # 9. Extract interests
    interests = []
    for interest, keywords in INTEREST_KEYWORDS.items():
        if any(kw in msg_lower for kw in keywords):
            if interest not in interests:
                interests.append(interest)

    # 10. Determine validity
    # Required: (destination OR destination_type) AND budget AND days AND people
    has_destination = bool(destination)
    has_destination_type = bool(destination_type)
    has_required_for_planning = (has_destination or has_destination_type) and budget and days and people

    if not (destination or destination_type):
        missing_fields.append("destination or destination_type")
    if not budget:
        missing_fields.append("budget")
    if not days:
        missing_fields.append("days")

    is_valid = len(missing_fields) == 0

    # Build normalized input
    normalized_input = {
        "origin": origin,
        "destination": destination,
        "destination_type": destination_type,
        "budget": budget,
        "people": people,
        "days": days,
        "nights": nights,
        "season": season,
        "interests": interests,
    }

    # Build follow-up question if missing fields
    follow_up_question = None
    if not is_valid:
        if missing_fields:
            questions = []
            if "destination or destination_type" in missing_fields:
                questions.append("bạn muốn đi đâu? (VD: biển, núi, hoặc địa điểm cụ thể)")
            if "budget" in missing_fields:
                questions.append("ngân sách của bạn là bao nhiêu? (VD: 5 triệu)")
            if "days" in missing_fields:
                questions.append("bạn muốn đi trong bao nhiêu ngày? (VD: 3 ngày)")
            follow_up_question = "Bạn cần cung cấp thêm thông tin: " + ", ".join(questions)

    return {
        "is_valid": is_valid,
        "missing_fields": missing_fields,
        "normalized_input": normalized_input,
        "assumptions": assumptions,
        "follow_up_question": follow_up_question,
    }


def _normalize_destination_name(name: str) -> Optional[str]:
    """Normalize common destination name variations."""
    if not name:
        return None
    name_lower = name.lower().strip()

    # Common aliases
    aliases = {
        "tphcm": "TP. Hồ Chí Minh",
        "tp hcm": "TP. Hồ Chí Minh",
        "tphcm": "TP. Hồ Chí Minh",
        "hcm": "TP. Hồ Chí Minh",
        "saigon": "TP. Hồ Chí Minh",
        "sài gòn": "TP. Hồ Chí Minh",
        "hn": "Hà Nội",
        "hà nội": "Hà Nội",
        "đà nẵng": "Đà Nẵng",
        "nha trang": "Nha Trang",
        "phú quốc": "Phú Quốc",
        "huế": "Huế",
        "đà lạt": "Đà Lạt",
        "sa pa": "Sa Pa",
        "vũng tàu": "Vũng Tàu",
        "quy nhơn": "Quy Nhơn",
        "cần thơ": "Cần Thơ",
        "hội an": "Hội An",
        "mũi né": "Mũi Né",
    }

    for alias, normalized in aliases.items():
        if alias in name_lower:
            return normalized
    return name.strip().title()


def _normalize_origin_name(name: str) -> Optional[str]:
    """Normalize common origin/starting point variations."""
    if not name:
        return None
    name_lower = name.lower().strip()

    aliases = {
        "tphcm": "TP. Hồ Chí Minh",
        "tp hcm": "TP. Hồ Chí Minh",
        "tphcm": "TP. Hồ Chí Minh",
        "hcm": "TP. Hồ Chí Minh",
        "saigon": "TP. Hồ Chí Minh",
        "sài gòn": "TP. Hồ Chí Minh",
        "hn": "Hà Nội",
        "hà nội": "Hà Nội",
    }

    for alias, normalized in aliases.items():
        if alias in name_lower:
            return normalized
    return name.strip().title()


# =============================================================================
# ASYNC RESEARCH FUNCTIONS
# =============================================================================
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# Timeout settings (in seconds)
TIMEOUT_GEOCODE = 10
TIMEOUT_WEATHER = 10
TIMEOUT_OVERPASS = 20
TIMEOUT_TOTAL_RESEARCH = 30


def _run_with_timeout(func: Callable, *args, timeout: int = 12, **kwargs) -> Dict[str, Any]:
    """Run a sync function with timeout using ThreadPoolExecutor."""
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            return future.result(timeout=timeout)
    except asyncio.TimeoutError:
        return _safe_error(func.__name__, TimeoutError(f"Timeout after {timeout}s"))
    except Exception as e:
        return _safe_error(func.__name__, e)


async def _async_call_tool(func: Callable, *args, timeout: int = 12, **kwargs) -> Dict[str, Any]:
    """Async wrapper to run sync functions in thread pool with timeout."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, partial(_run_with_timeout, func, *args, timeout=timeout, **kwargs)
    )


async def research_destination_async(
    destination: str,
    params: dict,
    destination_option: dict = None,
) -> dict:
    """
    Research a single destination asynchronously.

    Runs geocode, then parallel calls to weather, attractions, stays, restaurants,
    and transport (if origin is available).

    Returns:
        dict with destination research data
    """
    start_time = time.time()
    days = params.get("days") or 3
    origin = params.get("origin")
    transport_mode = params.get("transport_mode") or "flight"
    cuisine = params.get("cuisine")
    adults = params.get("adults") or params.get("people") or 1
    departure_date = params.get("departure_date")

    result = {
        "destination": destination,
        "destination_option": destination_option or {"destination": destination},
        "research_latency_ms": 0,
        "tool_results": {},
        "errors": [],
    }

    # Step 1: Geocode destination (must be done first)
    try:
        geocode_result = await _async_call_tool(
            geocode_location, destination, timeout=TIMEOUT_GEOCODE
        )
        result["tool_results"]["geocode"] = geocode_result

        if geocode_result.get("status") != "ok":
            result["errors"].append("geocode_failed")
            result["research_latency_ms"] = int((time.time() - start_time) * 1000)
            return result

        lat = geocode_result.get("latitude")
        lon = geocode_result.get("longitude")

        # Step 2: Run independent API calls in parallel
        tasks = {
            "weather": _async_call_tool(
                get_weather, destination, min(days, 7), timeout=TIMEOUT_WEATHER
            ),
            "attractions": _async_call_tool(
                search_attractions, destination, radius=10000,
                limit=min(6, max(3, days * 2)), timeout=TIMEOUT_OVERPASS
            ),
            "stays": _async_call_tool(
                search_stays, destination, radius=5000, limit=4, timeout=TIMEOUT_OVERPASS
            ),
            "restaurants": _async_call_tool(
                search_restaurants, destination, cuisine=cuisine,
                radius=5000, limit=min(5, max(3, days * 2)), timeout=TIMEOUT_OVERPASS
            ),
        }

        # Add transport if origin is available
        if origin:
            tasks["transport"] = _async_call_tool(
                estimate_transport_cost, origin, destination, transport_mode,
                departure_date, adults, timeout=TIMEOUT_OVERPASS
            )

        # Wait for all parallel tasks
        tool_results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        # Process results
        for key, res in zip(tasks.keys(), tool_results):
            if isinstance(res, Exception):
                result["tool_results"][key] = _safe_error(key, res)
                result["errors"].append(f"{key}_error")
            else:
                result["tool_results"][key] = res

    except Exception as e:
        result["errors"].append(f"research_error: {str(e)}")

    result["research_latency_ms"] = int((time.time() - start_time) * 1000)
    return result


async def research_all_destinations_async(
    destinations: list,
    params: dict,
) -> list:
    """
    Research all destinations in parallel.

    Args:
        destinations: List of destination names or dicts with destination info
        params: Trip parameters

    Returns:
        List of research results
    """
    # Normalize destinations
    destination_options = []
    for dest in destinations:
        if isinstance(dest, dict):
            destination_options.append(dest)
        else:
            destination_options.append({"destination": str(dest)})

    if not destination_options:
        return []

    # Create research tasks for each destination
    tasks = [
        research_destination_async(
            option.get("destination", option),
            params,
            option,
        )
        for option in destination_options
    ]

    # Run all in parallel with overall timeout
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=TIMEOUT_TOTAL_RESEARCH,
        )

        # Process results
        processed_results = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                processed_results.append({
                    "destination": destination_options[i].get("destination", "unknown"),
                    "destination_option": destination_options[i],
                    "research_latency_ms": 0,
                    "tool_results": {},
                    "errors": [f"async_error: {str(res)}"],
                })
            else:
                processed_results.append(res)

        return processed_results

    except asyncio.TimeoutError:
        # Partial results on timeout
        return []


def research_destination_sync(destination: str, params: dict, destination_option: dict = None) -> dict:
    """Sync wrapper for research_destination_async (for backward compatibility)."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                research_destination_async(destination, params, destination_option)
            )
        finally:
            loop.close()
    except Exception as e:
        return {
            "destination": destination,
            "destination_option": destination_option or {"destination": destination},
            "research_latency_ms": 0,
            "tool_results": {},
            "errors": [f"sync_error: {str(e)}"],
        }


def research_all_destinations_sync(destinations: list, params: dict) -> list:
    """Sync wrapper for research_all_destinations_async (for backward compatibility)."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                research_all_destinations_async(destinations, params)
            )
        finally:
            loop.close()
    except Exception as e:
        return []


# =============================================================================
# TOOL REGISTRY
# =============================================================================

TRAVEL_TOOLS = [
    {
        "name": "validate_travel_input",
        "description": "Validate and normalize user's travel request. Use this first before calling travel research tools. It extracts origin, destination, budget, people, days, nights, season, and interests. If required fields are missing, it returns a follow-up question.",
        "function": validate_travel_input,
    },
    {
        "name": "geocode_location",
        "description": "Tìm tọa độ và tên chuẩn của một địa điểm.",
        "function": geocode_location,
    },
    {
        "name": "get_weather",
        "description": "Xem dự báo thời tiết theo ngày cho một địa điểm.",
        "function": get_weather,
    },
    {
        "name": "search_attractions",
        "description": "Tìm điểm tham quan, địa điểm du lịch hoặc vui chơi quanh địa điểm.",
        "function": search_attractions,
    },
    {
        "name": "search_stays",
        "description": "Tìm khách sạn, homestay, hostel hoặc guest house quanh địa điểm.",
        "function": search_stays,
    },
    {
        "name": "search_restaurants",
        "description": "Tìm quán ăn, cafe hoặc nhà hàng xung quanh địa điểm.",
        "function": search_restaurants,
    },
    {
        "name": "estimate_transport_cost",
        "description": "Ước tính chi phí di chuyển bằng máy bay, xe khách, tàu hoặc ô tô.",
        "function": estimate_transport_cost,
    },
    {
        "name": "search_flight_cost",
        "description": "Ước tính chi phí vé máy bay theo mã điểm đi/đến.",
        "function": search_flight_cost,
    },
    {
        "name": "build_travel_plan",
        "description": "Tổng hợp thời tiết, điểm chơi, lưu trú, ăn uống, di chuyển và gợi ý lịch trình.",
        "function": build_travel_plan,
    },
]
