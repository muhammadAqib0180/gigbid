from scipy import stats

def ab_result(conv_a, n_a, conv_b, n_b):
    table = [[conv_a, n_a - conv_a], [conv_b, n_b - conv_b]]
    return stats.chi2_contingency(table)
