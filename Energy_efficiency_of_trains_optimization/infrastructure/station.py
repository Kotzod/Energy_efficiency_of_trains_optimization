from dataclasses import dataclass


@dataclass
class Station:
	station_id: str
	name: str
	passenger_stop: bool = False
	passing_loop: bool = False

