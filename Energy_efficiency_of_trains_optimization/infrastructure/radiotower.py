class RadioTower:
    def __init__(
        self,
        tower_id,
        position_km,
        radius_km,
    ):
        self.tower_id = tower_id
        self.position_km = position_km  # Position along the route in km
        self.radius_km = radius_km  # Coverage radius in km
        self.failed = False

    def fail(self):
        self.failed = True

    def repair(self):
        self.failed = False

    def strength_at_distance(self, distance_km):
        """Signal strength as a function of raw distance from the tower.
        Shared by the 1D route lookup (get_signal_strength) and the 2D
        map visualization, so both stay in sync."""
        if distance_km >= self.radius_km:
            return 0.0
        return max(0.0, 1.0 - (distance_km / self.radius_km) ** 2)

    def get_signal_strength(self, position_km):
        """
        Calculate signal strength at a given position based on distance from tower.
        Returns a value between 0 and 1, where 1 is maximum signal at tower position.
        Signal decreases with distance, reaching 0 at the edge of coverage radius.
        """
        distance = abs(position_km - self.position_km)
        return self.strength_at_distance(distance)

    def covers_position(self, position_km):
        """Check if a position is within the tower's coverage radius."""
        return abs(position_km - self.position_km) <= self.radius_km

    def is_operational(self):
        if self.failed:
            return False
        return True

    def get_status(self):
        return {
            "tower_id": self.tower_id,
            "position_km": self.position_km,
            "radius_km": self.radius_km,
            "failed": self.failed,
            "operational": self.is_operational(),
        }