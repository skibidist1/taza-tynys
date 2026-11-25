// Private-house heating calculator. Pure functions, no DOM.
// Python twin for tests: tests/calc_ref.py
// Ranges: emission-factor 95% CI (EMEP/EEA 2023) x efficiency range x insulation range.

export const HEATER_ORDER = ['coal_stove', 'coal_advanced', 'wood_stove', 'gas_boiler', 'electric'];

export function computeHouse(f, { heater, amount, insulate, prices = {} }) {
  const cur = f.heaters[heater];
  const fuelGJ = amount * f.fuels[cur.fuel].ncv_gj_per_unit.value;
  const eff = cur.efficiency;
  const heat = { value: fuelGJ * eff.value, low: fuelGJ * eff.low, high: fuelGJ * eff.high };
  const s = insulate ? f.insulation.saving : { value: 0, low: 0, high: 0 };
  const price = (fuel) => (prices[fuel] ?? f.fuels[fuel].price_kzt);

  const options = HEATER_ORDER.map((key) => {
    const h = f.heaters[key];
    const fuel = f.fuels[h.fuel];
    const ef = h.pm25_g_per_gj;
    let gj;
    let gjLow;
    let gjHigh;
    if (key === heater) {
      // Same appliance: fuel use is what the user told us, scaled by insulation.
      gj = fuelGJ * (1 - s.value);
      gjLow = fuelGJ * (1 - s.high);
      gjHigh = fuelGJ * (1 - s.low);
    } else {
      gj = (heat.value * (1 - s.value)) / h.efficiency.value;
      gjLow = (heat.low * (1 - s.high)) / h.efficiency.high;
      gjHigh = (heat.high * (1 - s.low)) / h.efficiency.low;
    }
    const amountOut = gj / fuel.ncv_gj_per_unit.value;
    return {
      key,
      fuel: h.fuel,
      unit: fuel.unit,
      amount: amountOut,
      gj,
      pm_kg: (gj * ef.value) / 1000,
      pm_kg_low: (gjLow * ef.low) / 1000,
      pm_kg_high: (gjHigh * ef.high) / 1000,
      cost_kzt: amountOut * price(h.fuel),
    };
  });
  const base = {
    key: heater,
    fuel: cur.fuel,
    unit: f.fuels[cur.fuel].unit,
    amount,
    gj: fuelGJ,
    pm_kg: (fuelGJ * cur.pm25_g_per_gj.value) / 1000,
    pm_kg_low: (fuelGJ * cur.pm25_g_per_gj.low) / 1000,
    pm_kg_high: (fuelGJ * cur.pm25_g_per_gj.high) / 1000,
    cost_kzt: amount * price(cur.fuel),
  };
  return { heat, base, options };
}
