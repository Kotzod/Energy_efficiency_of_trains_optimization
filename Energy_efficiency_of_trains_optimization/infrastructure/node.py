from dataclasses import dataclass
from typing import Optional


@dataclass
class Node:
	node_id: str
	name: str
	km: float
	passing_loop: bool = False
	passenger_stop: bool = False
	max_train_length: Optional[float] = None

	def __post_init__(self):
		self.id = self.node_id
		self.slot_capacity = 1 if self.passenger_stop else 0
		self.loop_max_length_m = self.max_train_length
