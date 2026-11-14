from statsmodels.stats.power import NormalIndPower

n = NormalIndPower().solve_power(effect_size=0.05, alpha=0.05, power=0.8)
