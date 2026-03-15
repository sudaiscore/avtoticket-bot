import httpx
import re
from bs4 import BeautifulSoup, Tag
from typing import List, Dict, Any, Generator, Optional
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from src.models import Trip, ParseResult
from src.config import settings, logger

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, application/xhtml+xml",
}

def extract_trip_date_from_url(url: str) -> str:
    match = re.search(r'\b20\d{2}-\d{2}-\d{2}\b', url)
    return match.group(0) if match else "Noma'lum Sana"

def normalize_text(text: str) -> str:
    if not text: return ""
    return re.sub(r'\s+', ' ', text).strip()

def clean_price(text: str) -> str:
    return re.sub(r'(?i)(сум|sum|uzs|so\'m|so‘m)', '', text).replace(' ', '').strip()

def matches_target_route(route_name: str) -> bool:
    route_lower = route_name.lower()
    origins = [k.strip().lower() for k in settings.target_origin_keywords.split(',') if k.strip()]
    dests = [k.strip().lower() for k in settings.target_destination_keywords.split(',') if k.strip()]

    has_origin = any(o in route_lower for o in origins) if origins else True
    has_dest = any(d in route_lower for d in dests) if dests else True

    if settings.require_all_route_keywords:
        return has_origin and has_dest
    return has_origin or has_dest

def calculate_confidence(departure: str, route: str, seats: Any, price: str, bus: str) -> float:
    conf = 0.0
    if departure and departure != "Noma'lum": conf += 0.20
    if route and route != "Noma'lum": conf += 0.20
    if seats is not None: conf += 0.30
    if price and price != "Noma'lum": conf += 0.15
    if bus and bus != "Noma'lum": conf += 0.15
    return min(conf, 1.0)

def find_candidate_lists(data: Any) -> Generator[List[Dict[str, Any]], None, None]:
    if isinstance(data, list):
        if len(data) > 0 and all(isinstance(x, dict) for x in data):
            yield data
        for item in data: yield from find_candidate_lists(item)
    elif isinstance(data, dict):
        for value in data.values(): yield from find_candidate_lists(value)

def parse_json(data: Any, trip_date: str) -> ParseResult:
    trips = []
    seen_ids = set()
    total_conf = 0.0

    for candidate_list in find_candidate_lists(data):
        for item in candidate_list:
            dep_time = item.get("departure_time", item.get("time"))
            arr_time = item.get("arrival_time", "Noma'lum")
            seats_val = item.get("available_seats", item.get("seats", item.get("free_seats")))
            route_val = item.get("route_name", item.get("title", item.get("route")))
            price_val = item.get("price", item.get("tariff"))
            bus_val = item.get("bus_model", item.get("model", "Noma'lum"))

            if dep_time and seats_val is not None and route_val and price_val is not None:
                if not matches_target_route(str(route_val)): continue

                conf = calculate_confidence(str(dep_time), str(route_val), seats_val, str(price_val), str(bus_val))
                try:
                    trip = Trip(
                        trip_date=str(item.get("date", trip_date)), departure_time=str(dep_time),
                        arrival_time=str(arr_time), route_name=str(route_val),
                        available_seats=int(seats_val), price=clean_price(str(price_val)), bus_model=str(bus_val)
                    )
                    if trip.unique_id not in seen_ids:
                        seen_ids.add(trip.unique_id)
                        trips.append(trip)
                        total_conf += conf
                except (ValueError, TypeError): continue

    if trips:
        return ParseResult(success=True, source="json", trips=trips, confidence=total_conf/len(trips))
    return ParseResult(success=True, source="json", trips=[], confidence=0.0)

def get_table_header_mapping(table: Tag) -> Dict[str, int]:
    mapping = {}
    header_row = table.find('thead')
    first_row = header_row.find('tr') if header_row else table.find('tr')
    if not first_row: return mapping

    cells = first_row.find_all(['th', 'td'])
    for idx, cell in enumerate(cells[:15]):
        text = normalize_text(cell.get_text()).lower()
        if any(k in text for k in ['отправление', 'vaqt', 'chiqish', 'dep']): mapping['dep'] = idx
        elif any(k in text for k in ['прибытие', 'kelish', 'arr']): mapping['arr'] = idx
        elif any(k in text for k in ['название', "yo'nalish", 'рейс']): mapping['route'] = idx
        elif any(k in text for k in ['мест', 'joy', 'seat']): mapping['seats'] = idx
        elif any(k in text for k in ['тариф', 'narx', 'sum', 'price']): mapping['price'] = idx
        elif any(k in text for k in ['модель', 'avtobus', 'bus']): mapping['bus'] = idx
    return mapping

def extract_trip_from_row(cells: List[str], mapping: Dict[str, int], trip_date: str) -> Optional[Trip]:
    try:
        if 'dep' not in mapping or len(cells) <= mapping['dep']: return None

        dep_raw = cells[mapping['dep']]
        dep_match = re.search(r'\b(?:[01]\d|2[0-3]):[0-5]\d\b', dep_raw)
        if not dep_match: return None
        departure = dep_match.group(0)

        arr_raw = cells[mapping['arr']] if 'arr' in mapping and len(cells) > mapping['arr'] else "Noma'lum"
        arr_match = re.search(r'\b(?:[01]\d|2[0-3]):[0-5]\d\b', arr_raw)
        arrival = arr_match.group(0) if arr_match else "Noma'lum"

        route = cells[mapping['route']] if 'route' in mapping and len(cells) > mapping['route'] else "Noma'lum"
        if not matches_target_route(route): return None

        seats_raw = cells[mapping['seats']] if 'seats' in mapping and len(cells) > mapping['seats'] else ""
        seats_match = re.search(r'\d+', seats_raw)
        if not seats_match: return None
        seats = int(seats_match.group(0))

        price_raw = cells[mapping['price']] if 'price' in mapping and len(cells) > mapping['price'] else "Noma'lum"
        price = clean_price(price_raw)
        bus = cells[mapping['bus']] if 'bus' in mapping and len(cells) > mapping['bus'] else "Noma'lum"

        return Trip(
            trip_date=trip_date, departure_time=departure, arrival_time=arrival,
            route_name=route, available_seats=seats, price=price, bus_model=bus
        )
    except Exception as e:
        logger.debug(f"Row extraction error: {e}")
        return None

def parse_html(html_content: str, trip_date: str) -> ParseResult:
    soup = BeautifulSoup(html_content, "html.parser")
    trips = []
    seen_ids = set()
    total_conf = 0.0

    for table in soup.find_all('table'):
        mapping = get_table_header_mapping(table)
        if not mapping: continue

        for row in table.find_all('tr')[1:]:
            cells = [normalize_text(td.get_text()) for td in row.find_all(['td', 'th'])]
            trip = extract_trip_from_row(cells, mapping, trip_date)

            if trip and trip.unique_id not in seen_ids:
                seen_ids.add(trip.unique_id)
                trips.append(trip)
                total_conf += calculate_confidence(trip.departure_time, trip.route_name, trip.available_seats, trip.price, trip.bus_model)

    if not trips:
        target_containers = soup.select('.row, .trip-card, .ticket-item, div[class*="flex"]:not(header):not(footer)')
        for container in target_containers:
            text = normalize_text(container.get_text(separator=" "))
            times = re.findall(r'\b(?:[01]\d|2[0-3]):[0-5]\d\b', text)
            if not times or len(times) > 4: continue

            departure = times[0]
            arrival = times[1] if len(times) > 1 else "Noma'lum"
            route_match = re.search(r'([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\s\-]+(?:\(\d+\)\s*\d{3}-\d{2}-\d{2})?)', text)
            route = route_match.group(1).strip() if route_match else "Noma'lum"
            if not matches_target_route(route): continue

            seats_match = re.search(r'(?i)(?:мест|joy(?:lar)?|seats)[:\s-]*(\d+)', text)
            seats = int(seats_match.group(1)) if seats_match else None

            price_match = re.search(r'\b[1-9]\d{3,6}\b', text.replace(' ', ''))
            price = price_match.group(0) if price_match else "Noma'lum"

            bus_match = re.search(r'\b([A-Z]{3,}[A-Z\s0-9]*)\b', text)
            bus = bus_match.group(1).strip() if bus_match and "UZS" not in bus_match.group(1) else "Noma'lum"

            conf = calculate_confidence(departure, route, seats, price, bus)
            if seats is not None and conf >= 0.5:
                trip = Trip(
                    trip_date=trip_date, departure_time=departure, arrival_time=arrival,
                    route_name=route, available_seats=seats, price=price, bus_model=bus
                )
                if trip.unique_id not in seen_ids:
                    seen_ids.add(trip.unique_id)
                    trips.append(trip)
                    total_conf += conf

    if trips:
        return ParseResult(success=True, source="html", trips=trips, confidence=total_conf/len(trips))
    return ParseResult(success=True, source="html", trips=[], confidence=0.0)

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError))
)
async def fetch_data(client: httpx.AsyncClient, target_url: str) -> ParseResult:
    trip_date = extract_trip_date_from_url(target_url)

    try:
        response = await client.get(target_url, headers=HEADERS, timeout=15.0)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status in [403, 429]: logger.warning(f"[HTTP {status}] Server so'rovni blokladi (WAF/Rate Limit). Retry qilinadi...")
        elif status >= 500: logger.warning(f"[HTTP {status}] Server ichki xatosi. Retry qilinadi...")
        raise e
    except httpx.RequestError as e:
        logger.warning(f"Tarmoq xatosi: {e}. Retry qilinadi...")
        raise e

    try:
        data = response.json()
        result = parse_json(data, trip_date)
        if result.success and result.trips: return result
    except ValueError: pass

    return parse_html(response.text, trip_date)