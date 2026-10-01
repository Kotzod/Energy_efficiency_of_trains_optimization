class TrackEdge:
    """
    Physical track segment between two stations.
    Single-track segments have an `opposite` reference linking
    both directions so head-on conflicts are prevented.
    """

    def __init__(self, from_node, to_node, distance_km, tracks=1, gradient=0.0, speed_limit_kmh=140.0):
        self.from_node = from_node
        self.to_node = to_node
        self.distance_km = distance_km
        self.tracks = tracks
        self.gradient = gradient
        self.speed_limit_kmh = speed_limit_kmh
        self.occupied_by = None
        self.opposite = None      # set by graph_builder for single-track pairs
        self.radio_towers = []

    def request_clearance(self, train_id):
        # Block if opposite direction is occupied by a different train
        if self.opposite and self.opposite.occupied_by is not None:
            if self.opposite.occupied_by != train_id:
                return False

        if self.occupied_by is None:
            self.occupied_by = train_id
            return True

        return self.occupied_by == train_id

    def release_clearance(self, train_id):
        if self.occupied_by == train_id:
            self.occupied_by = None

    def add_radio_tower(self, tower):
        if tower not in self.radio_towers:
            self.radio_towers.append(tower)

    def clear_radio_towers(self):
        """Clear previously attached towers before recalculating coverage."""
        self.radio_towers.clear()

    def get_communication_status(self, position_km):
        """
        Determine the communication status for this track edge.

        Since multiple towers may overlap this edge, the train is assumed
        to use the strongest operational signal.
        Returns:
            "no_coverage"
            "degraded"
            "normal"
        """

        operational_towers = [
            tower for tower in self.radio_towers
            if tower.is_operational()
        ]

        if not operational_towers:
            return "no_coverage"

        strongest_signal = max(
            tower.get_signal_strength(position_km)
            for tower in operational_towers
        )

        if strongest_signal <= 0:
            return "no_coverage"
        elif strongest_signal < 0.5:
            return "degraded"
        else:
            return "normal"