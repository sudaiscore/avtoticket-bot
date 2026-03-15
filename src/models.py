import hashlib
from typing import List, Optional
from pydantic import BaseModel, Field

class Trip(BaseModel):
    trip_date: str
    departure_time: str
    arrival_time: str
    route_name: str
    available_seats: int
    price: str
    bus_model: str

    @property
    def unique_id(self) -> str:
        raw_str = (f"{self.trip_date}-{self.departure_time}-{self.arrival_time}-"
                   f"{self.route_name}-{self.bus_model}-{self.price}")
        return hashlib.md5(raw_str.encode("utf-8")).hexdigest()

class ParseResult(BaseModel):
    success: bool
    source: Optional[str] = None
    trips: List[Trip] = Field(default_factory=list)
    confidence: float = 0.0
    error: Optional[str] = None