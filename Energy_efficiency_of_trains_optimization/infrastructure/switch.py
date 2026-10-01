import json
import os
import random

# Weather configuration for switch failure probabilities
WEATHER_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weather_config.json")

def load_weather_config():
    """Load weather configuration from JSON file."""
    try:
        with open(WEATHER_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Default weather config if file not found
        return {
            "weather": {
                "Clear": {"switch_failure_prob_per_hour": 0.0002}
            },
            "current_weather": "Clear"
        }

WEATHER_CONFIG = load_weather_config()


class Switch:
    """
    Railway turnout switch with failure and clamping capabilities.

    When a switch fails, it can be clamped in a specific position:
    - "normal": straight through, no diverging movement allowed
    - "reverse": diverging movement only, straight movement blocked
    """

    def __init__(self, switch_id, station_id, role):
        self.switch_id = switch_id
        self.station_id = station_id
        self.role = role  # "through", "loop_entry", "loop_exit", "yard"
        self.failed = False
        self.locked_by = None
        self.clamped = False
        self.clamped_position = None  # "normal" or "reverse"
        self._hours_operational = 0.0  # Track operational time for failure probability

    def fail(self):
        """Fail the switch and release any locks."""
        self.failed = True
        self.locked_by = None

    def repair(self):
        """Repair the switch, clearing failure and clamp state."""
        self.failed = False
        self.locked_by = None
        self.clamped = False
        self.clamped_position = None

    def clamp(self, position="normal"):
        """
        Mechanically clamp the switch in a specific position.
        This is used for safe manual operation over failed switches.
        """
        if position not in ("normal", "reverse"):
            raise ValueError(f"Invalid clamp position: {position}")
        self.clamped = True
        self.clamped_position = position

    def release_clamp(self):
        """Release the mechanical clamp."""
        self.clamped = False
        self.clamped_position = None

    def is_available(self, train_id=None):
        """Check if the switch is available for normal operation."""
        if self.failed:
            return False
        return self.locked_by is None or self.locked_by == train_id

    def allows_straight(self):
        """
        Check if straight movement is allowed.
        Returns True if the switch allows trains to pass straight through.
        """
        if not self.failed and not self.clamped:
            return True
        if self.clamped and self.clamped_position == "normal":
            return True
        return False

    def allows_diverging(self):
        """
        Check if diverging movement is allowed.
        Returns True if the switch allows trains to take the diverging route.
        """
        if not self.failed and not self.clamped:
            return True
        if self.clamped and self.clamped_position == "reverse":
            return True
        return False

    def lock(self, train_id):
        if not self.is_available(train_id):
            return False
        self.locked_by = train_id
        return True

    def unlock(self, train_id):
        if self.locked_by == train_id:
            self.locked_by = None

    def update_operational_time(self, hours, current_weather=None, rng=None):
        """Update the operational time and check for weather-based failure."""
        if self.failed:
            return

        self._hours_operational += hours

        weather_map = WEATHER_CONFIG.get("weather", {})
        current_weather = current_weather or WEATHER_CONFIG.get("current_weather", "Clear")
        if current_weather not in weather_map:
            current_weather = "Clear" if "Clear" in weather_map else next(iter(weather_map), "Clear")
        weather_data = weather_map.get(current_weather, {})
        failure_prob_per_hour = weather_data.get("switch_failure_prob_per_hour", 0.0002)

        # Check for failure based on probability
        random_source = rng or random
        if random_source.random() < failure_prob_per_hour * hours:
            self.fail()


def can_proceed_straight(station_switches):
    """Only through-route switches matter for main-line movement."""
    relevant = [sw for sw in station_switches if sw.role == "through"]
    if not relevant:
        return True
    return all(sw.allows_straight() for sw in relevant)


def can_use_passing_loop(station_switches, train_id=None):
    """Only loop entry/exit switches matter for using the passing loop."""
    relevant = [sw for sw in station_switches if sw.role in ("loop_entry", "loop_exit")]
    if not relevant:
        return False
    return all(sw.is_available(train_id) for sw in relevant)


def can_take_diverging_route(station_switches):
    relevant = [sw for sw in station_switches if sw.role in ("loop_entry", "loop_exit")]
    if not relevant:
        return True
    return all(sw.allows_diverging() for sw in relevant)