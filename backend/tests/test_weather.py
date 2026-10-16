"""The SMHI SNOW1G point-forecast schema as observed live on 16 October 2026: flat `data` per time step, `time` as the valid time."""
from app.weather import parse_forecast

PAYLOAD = {
    "createdTime": "2026-10-16T19:47:22Z", "referenceTime": "2026-10-16T19:30:00Z",
    "geometry": {"type": "Point", "coordinates": [18.077207, 59.330360]},
    "timeSeries": [
        {"time": "2000-01-01T00:00:00Z", "data": {"air_temperature": -5.0, "wind_speed": 1.0}},
        {"time": "2099-01-01T00:00:00Z", "data": {"air_temperature": 13.0, "wind_from_direction": 186, "wind_speed": 4.2, "wind_speed_of_gust": 7.1,
                                                   "visibility_in_air": 28.4, "cloud_area_fraction": 75, "probability_of_precipitation": 10, "symbol_code": "cloudy"}},
    ],
}


def test_parse_snow1g_picks_first_future_step_and_flat_data():
    r = parse_forecast(PAYLOAD, "stockholm")
    assert r["status"] == "connected"
    assert r["validTime"] == "2099-01-01T00:00:00Z"
    assert r["gridPoint"] == [18.077207, 59.33036]
    assert r["data"]["air_temperature"] == 13.0 and r["data"]["wind_speed_of_gust"] == 7.1
    assert r["units"]["wind_speed"] == "m/s"
    assert "relative_humidity" not in r["data"]


def test_parse_legacy_parameter_list_still_works():
    legacy = {"referenceTime": "x", "geometry": {"coordinates": [[18.0, 59.0]]},
              "timeSeries": [{"validTime": "2099-01-01T00:00:00Z", "parameters": [{"name": "air_temperature", "values": [2.5]}]}]}
    r = parse_forecast(legacy, "visby")
    assert r["data"] == {"air_temperature": 2.5} and r["gridPoint"] == [18.0, 59.0]
