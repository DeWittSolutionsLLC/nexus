"""
Weather Eye Plugin — Local weather via wttr.in.
No API key required. Fully local requests.
"""

import json
import logging
from datetime import datetime
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.weather_eye")


class WeatherEyePlugin(BasePlugin):
    name = "weather_eye"
    description = "Live weather conditions and forecast — no API key needed"
    icon = "🌤️"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._default_city = config.get("default_city", "")
        self._requests_available = False

    async def connect(self) -> bool:
        try:
            import requests  # noqa: F401
            self._requests_available = True
            self._connected = True
            city_str = f" — default: {self._default_city}" if self._default_city else ""
            self._status_message = f"Ready{city_str}"
            return True
        except ImportError:
            self._status_message = "requests not installed"
            self._connected = False
            return False

    async def execute(self, action: str, params: dict) -> str:
        if not self._requests_available:
            return "⚠️ requests not installed. Run: pip install requests"

        actions = {
            "get_weather":  self._get_weather,
            "get_forecast": self._get_forecast,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown weather action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "get_weather",  "description": "Get current weather conditions for a city", "params": ["city"]},
            {"action": "get_forecast", "description": "Get 3-day weather forecast for a city",     "params": ["city"]},
        ]

    def _resolve_city(self, params: dict) -> str:
        return (
            params.get("city")
            or params.get("location")
            or self._default_city
            or "auto"
        )

    async def _get_weather(self, params: dict) -> str:
        import requests
        city = self._resolve_city(params)
        url = f"https://wttr.in/{city}?format=j1"
        try:
            resp = requests.get(url, timeout=8, headers={"User-Agent": "Nexus/2.0"})
            resp.raise_for_status()
            data = resp.json()
            return self._format_current(data, city)
        except requests.exceptions.Timeout:
            return f"⚠️ Weather request timed out, sir. Check your internet connection."
        except Exception as e:
            return f"⚠️ Could not retrieve weather for '{city}': {e}"

    async def _get_forecast(self, params: dict) -> str:
        import requests
        city = self._resolve_city(params)
        url = f"https://wttr.in/{city}?format=j1"
        try:
            resp = requests.get(url, timeout=8, headers={"User-Agent": "Nexus/2.0"})
            resp.raise_for_status()
            data = resp.json()
            return self._format_forecast(data, city)
        except Exception as e:
            return f"⚠️ Could not retrieve forecast for '{city}': {e}"

    def _format_current(self, data: dict, city: str) -> str:
        try:
            cur = data["current_condition"][0]
            area = data.get("nearest_area", [{}])[0]
            area_name = area.get("areaName", [{}])[0].get("value", city)
            country = area.get("country", [{}])[0].get("value", "")
            location = f"{area_name}, {country}" if country else area_name

            temp_c = cur.get("temp_C", "?")
            temp_f = cur.get("temp_F", "?")
            feels_c = cur.get("FeelsLikeC", "?")
            humidity = cur.get("humidity", "?")
            wind_kmph = cur.get("windspeedKmph", "?")
            wind_dir = cur.get("winddir16Point", "?")
            desc = cur.get("weatherDesc", [{}])[0].get("value", "Unknown")
            visibility = cur.get("visibility", "?")
            uv = cur.get("uvIndex", "?")

            return (
                f"🌤️ WEATHER — {location}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"  Conditions:  {desc}\n"
                f"  Temperature: {temp_c}°C  ({temp_f}°F)\n"
                f"  Feels like:  {feels_c}°C\n"
                f"  Humidity:    {humidity}%\n"
                f"  Wind:        {wind_kmph} km/h {wind_dir}\n"
                f"  Visibility:  {visibility} km\n"
                f"  UV Index:    {uv}"
            )
        except (KeyError, IndexError) as e:
            return f"⚠️ Could not parse weather data: {e}"

    def _format_forecast(self, data: dict, city: str) -> str:
        try:
            area = data.get("nearest_area", [{}])[0]
            area_name = area.get("areaName", [{}])[0].get("value", city)

            lines = [f"📅 3-DAY FORECAST — {area_name}\n━━━━━━━━━━━━━━━━━━━━━━━━━━"]

            weather_days = data.get("weather", [])
            for day in weather_days[:3]:
                date_str = day.get("date", "")
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    day_label = dt.strftime("%A, %b %d")
                except Exception:
                    day_label = date_str

                max_c = day.get("maxtempC", "?")
                min_c = day.get("mintempC", "?")
                hourly = day.get("hourly", [{}])
                desc = hourly[len(hourly)//2].get("weatherDesc", [{}])[0].get("value", "?") if hourly else "?"
                rain_mm = day.get("hourly", [{}])[0].get("precipMM", "0") if day.get("hourly") else "0"

                lines.append(
                    f"\n  {day_label}\n"
                    f"    {desc}\n"
                    f"    High {max_c}°C  /  Low {min_c}°C"
                )

            return "\n".join(lines)
        except Exception as e:
            return f"⚠️ Could not parse forecast data: {e}"
