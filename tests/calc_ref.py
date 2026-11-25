"""Python reference of js/calc.js (computeHouse) for tests."""

ORDER = ["coal_stove", "coal_advanced", "wood_stove", "gas_boiler", "electric"]


def compute_house(f, heater, amount, insulate, prices=None):
    prices = prices or {}
    cur = f["heaters"][heater]
    fuel_gj = amount * f["fuels"][cur["fuel"]]["ncv_gj_per_unit"]["value"]
    e = cur["efficiency"]
    heat = {k: fuel_gj * e[k] for k in ("value", "low", "high")}
    s = f["insulation"]["saving"] if insulate else {"value": 0, "low": 0, "high": 0}
    out = {}
    for key in ORDER:
        h = f["heaters"][key]
        fuel = f["fuels"][h["fuel"]]
        ef = h["pm25_g_per_gj"]
        if key == heater:
            gj, lo, hi = fuel_gj * (1 - s["value"]), fuel_gj * (1 - s["high"]), fuel_gj * (1 - s["low"])
        else:
            gj = heat["value"] * (1 - s["value"]) / h["efficiency"]["value"]
            lo = heat["low"] * (1 - s["high"]) / h["efficiency"]["high"]
            hi = heat["high"] * (1 - s["low"]) / h["efficiency"]["low"]
        amt = gj / fuel["ncv_gj_per_unit"]["value"]
        out[key] = {
            "amount": amt,
            "pm_kg": gj * ef["value"] / 1000,
            "pm_kg_low": lo * ef["low"] / 1000,
            "pm_kg_high": hi * ef["high"] / 1000,
            "cost_kzt": amt * prices.get(h["fuel"], fuel["price_kzt"]),
        }
    return out
