# ==========================
# IMPORTS
# ==========================
import os
import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt

from scipy.optimize import curve_fit
from scipy.stats import (
    shapiro,
    pearsonr,
    spearmanr,
    levene,
    kruskal,
    probplot,
)
from sklearn.metrics import r2_score

# ==========================
# GLOBAL CONFIGURATIONS
# ==========================
mpl.rcParams.update(
    {
        "font.family": "Times New Roman",
        "font.size": 14,
        "axes.labelsize": 14,
        "axes.titlesize": 16,
        "legend.fontsize": 12,
        "xtick.labelsize": 12,
        "ytick.labelsize": 12,
        "axes.edgecolor": "black",
        "axes.linewidth": 1.2,
        "lines.linewidth": 2.5,
        "lines.markersize": 8,
        "grid.linestyle": "--",
        "grid.alpha": 0.7,
    }
)

# ==========================
# CONSTANTS
# ==========================
ALPHA = 0.05
LINEAR_PREFERENCE_THRESHOLD = 0.02

INPUT_FILES = [
    ("memory-in-experiment-purecap-benchmark-results.csv", "purecap-benchmark ABI"),
    ("memory-in-experiment-purecap-results.csv", "purecap ABI"),
    ("memory-out-experiment-results.csv", "outside compartment"),
]

EXPERIMENT_DISPLAY_MAP = {
    "purecap-benchmark ABI": "purecap-benchmark ABI",
    "purecap ABI": "purecap ABI",
    "outside compartment": "outside compartment",
}

GROUP_ORDER = {
    "purecap-benchmark ABI": 0,
    "purecap ABI": 1,
    "outside compartment": 2,
}

EXPERIMENT_COLORS = {
    "purecap-benchmark ABI": "#2ca02c",
    "purecap ABI": "#1f77b4",
    "outside compartment": "#ff7f0e",
}

LINE_STYLES = {
    "purecap-benchmark ABI": "--",
    "purecap ABI": "-",
    "outside compartment": ":",
}

MARKERS = {
    "purecap-benchmark ABI": "s",
    "purecap ABI": "o",
    "outside compartment": "^",
}

BLOCK_SIZE_COLUMN = "Block Size (MB)"

TIME_VARIABLES = [
    "Write Time (ms)",
    "Read Time (ms)",
    "Allocation Time (ms)",
    "Free Time (ms)",
]

TARGET_COMPARISONS = [
    ("purecap-benchmark ABI", "outside compartment"),
    ("purecap ABI", "outside compartment"),
]

# ==========================
# FORMAT FUNCTIONS
# ==========================
def format_normality_text(p_value):
    if pd.isna(p_value):
        return ""
    if p_value < 0.05:
        if p_value < 0.001:
            return "Rejected (p < 0.001)"
        return f"Rejected (p = {p_value:.3f})"
    return f"Accepted (p = {p_value:.3f})"


def format_pvalue_text(p_value):
    if pd.isna(p_value):
        return ""
    if p_value < 0.001:
        return "< 0.001"
    return f"{p_value:.3f}"


# ==========================
# SAFE STAT FUNCTIONS
# ==========================
def safe_shapiro(data):
    data = np.asarray(data, dtype=float)
    data = data[~np.isnan(data)]
    if len(data) < 3:
        return np.nan, np.nan
    try:
        stat, p = shapiro(data)
        return stat, p
    except Exception:
        return np.nan, np.nan


def safe_pearson(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = (~np.isnan(x)) & (~np.isnan(y))
    if mask.sum() < 2:
        return np.nan, np.nan
    try:
        return pearsonr(x[mask], y[mask])
    except Exception:
        return np.nan, np.nan


def safe_spearman(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = (~np.isnan(x)) & (~np.isnan(y))
    if mask.sum() < 2:
        return np.nan, np.nan
    try:
        return spearmanr(x[mask], y[mask])
    except Exception:
        return np.nan, np.nan


def safe_levene(groups):
    cleaned = [np.asarray(g, dtype=float)[~np.isnan(g)] for g in groups]
    cleaned = [g for g in cleaned if len(g) >= 2]
    if len(cleaned) < 2:
        return np.nan, np.nan
    try:
        stat, p = levene(*cleaned)
        return stat, p
    except Exception:
        return np.nan, np.nan


def safe_kruskal(groups):
    cleaned = [np.asarray(g, dtype=float)[~np.isnan(g)] for g in groups]
    cleaned = [g for g in cleaned if len(g) >= 2]
    if len(cleaned) < 2:
        return np.nan, np.nan
    try:
        stat, p = kruskal(*cleaned)
        return stat, p
    except Exception:
        return np.nan, np.nan


# ==========================
# EFFECT SIZES
# ==========================
def compute_iqr(values):
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]

    if values.size == 0:
        return np.nan

    q1 = np.quantile(values, 0.25, method="linear")
    q3 = np.quantile(values, 0.75, method="linear")
    return q3 - q1


def epsilon_squared_kruskal(H, groups):
    """
    Epsilon squared for Kruskal-Wallis:
        epsilon² = (H - k + 1) / (n - k)
    """
    if np.isnan(H):
        return np.nan

    cleaned = []
    for g in groups:
        arr = np.asarray(g, dtype=float)
        arr = arr[~np.isnan(arr)]
        if arr.size > 0:
            cleaned.append(arr)

    k = len(cleaned)
    n = sum(len(g) for g in cleaned)

    if k < 2 or n <= k:
        return np.nan

    eps2 = (H - k + 1) / (n - k)
    return max(0.0, eps2)


def cliffs_delta(x, y):
    """
    Cliff's delta:
        delta = P(X > Y) - P(Y > X)
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    x = x[~np.isnan(x)]
    y = y[~np.isnan(y)]

    if x.size == 0 or y.size == 0:
        return np.nan

    diff = x[:, None] - y[None, :]
    gt = np.sum(diff > 0)
    lt = np.sum(diff < 0)
    return (gt - lt) / (x.size * y.size)


def median_ratio(x, y, atol=1e-12):
    """
    Ratio of medians:
        median(x) / median(y)
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    x = x[~np.isnan(x)]
    y = y[~np.isnan(y)]

    if x.size == 0 or y.size == 0:
        return np.nan

    med_x = np.median(x)
    med_y = np.median(y)

    if np.isnan(med_x) or np.isnan(med_y):
        return np.nan

    if np.isclose(med_y, 0.0, atol=atol):
        return np.nan

    return med_x / med_y


# ==========================
# LOADING / PREPROCESSING
# ==========================
def load_all_data():
    frames = []
    available_cols_sets = []

    for file_path, exp_name in INPUT_FILES:
        df = pd.read_csv(file_path)
        df = df.apply(pd.to_numeric, errors="coerce")

        if BLOCK_SIZE_COLUMN not in df.columns:
            raise ValueError(
                f"The file '{file_path}' does not contain the required column: {BLOCK_SIZE_COLUMN}"
            )

        available_cols_sets.append(set(df.columns))
        df = df.dropna(subset=[BLOCK_SIZE_COLUMN]).copy()
        df[BLOCK_SIZE_COLUMN] = df[BLOCK_SIZE_COLUMN].astype(float)
        df["Experiment"] = exp_name
        frames.append(df.copy())

    if not frames:
        raise ValueError("No files were loaded.")

    common_cols = set.intersection(*available_cols_sets)
    selected_time_vars = [v for v in TIME_VARIABLES if v in common_cols]

    if not selected_time_vars:
        raise ValueError(
            f"No time variable found among {TIME_VARIABLES}. "
            f"Common columns: {sorted(common_cols)}"
        )

    df_all = pd.concat(frames, ignore_index=True)
    df_all = df_all[["Experiment", BLOCK_SIZE_COLUMN] + selected_time_vars].copy()

    return df_all, selected_time_vars


def compute_iqr_for_cleanup(df: pd.DataFrame, column: str) -> float:
    if column not in df.columns or df[column].dropna().empty:
        return np.nan

    q1 = df[column].quantile(0.25)
    q3 = df[column].quantile(0.75)
    return q3 - q1


def remove_outliers(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Removes outliers using only the IQR."""
    if column not in df.columns or df[column].dropna().empty:
        return df.copy()

    q1 = df[column].quantile(0.25)
    q3 = df[column].quantile(0.75)
    iqr = compute_iqr_for_cleanup(df, column)

    if np.isnan(iqr) or iqr == 0:
        return df.copy()

    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    outliers_iqr = (df[column] < lower_bound) | (df[column] > upper_bound)
    return df.loc[~outliers_iqr].copy()


def remove_outliers_residual(df, variable, z_thresh=3.0):
    """
    Removes outliers based on the residuals from a linear fit y ~ x within each experiment.
    """
    pieces = []

    for exp, g in df.groupby("Experiment"):
        g = g[["Experiment", BLOCK_SIZE_COLUMN, variable]].dropna().copy()

        if len(g) < 3:
            pieces.append(g)
            continue

        x = g[BLOCK_SIZE_COLUMN].values.astype(float)
        y = g[variable].values.astype(float)

        if np.unique(x).size < 2:
            pieces.append(g)
            continue

        try:
            coef = np.polyfit(x, y, 1)
            y_hat = np.polyval(coef, x)
            resid = y - y_hat
            resid_std = np.std(resid, ddof=1)

            if resid_std == 0 or np.isnan(resid_std):
                pieces.append(g)
                continue

            mask = np.abs(resid / resid_std) <= z_thresh
            pieces.append(g.loc[mask].copy())
        except Exception:
            pieces.append(g)

    if not pieces:
        return df.iloc[0:0].copy()

    return pd.concat(pieces, ignore_index=True)


def preprocess_dataset(df_all, variable, outlier_mode):
    df = df_all[["Experiment", BLOCK_SIZE_COLUMN, variable]].dropna().copy()

    if outlier_mode == "Without_Outliers":
        df = remove_outliers_residual(df, variable)

    return df


# ==========================
# REGRESSION
# ==========================
def fit_linear(x, y):
    coef = np.polyfit(x, y, 1)
    y_hat = np.polyval(coef, x)
    return coef, y_hat, r2_score(y, y_hat)


def fit_logarithmic(x, y):
    if not np.all(x > 0):
        raise ValueError("x <= 0 in logarithmic model.")
    coef = np.polyfit(np.log(x), y, 1)
    y_hat = np.polyval(coef, np.log(x))
    return coef, y_hat, r2_score(y, y_hat)


def fit_exponential(x, y):
    if np.any(y <= 0):
        raise ValueError("y <= 0 in exponential model.")
    popt, _ = curve_fit(lambda t, a, b: a * np.exp(b * t), x, y, maxfev=10000)
    y_hat = popt[0] * np.exp(popt[1] * x)
    return popt, y_hat, r2_score(y, y_hat)


def fit_cubic(x, y):
    if len(np.unique(x)) < 4:
        raise ValueError("Need at least 4 unique x values for cubic polynomial.")
    coef = np.polyfit(x, y, 3)
    y_hat = np.polyval(coef, x)
    return coef, y_hat, r2_score(y, y_hat)


def evaluate_model(model_name, params, x):
    if model_name == "Linear":
        return np.polyval(params, x)
    if model_name == "Logarithmic":
        return np.polyval(params, np.log(x))
    if model_name == "Exponential":
        return params[0] * np.exp(params[1] * x)
    if model_name == "Cubic Polynomial":
        return np.polyval(params, x)
    raise ValueError(f"Unknown model: {model_name}")


def determine_best_regression(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    models = {}

    try:
        params, y_hat, r2 = fit_linear(x, y)
        models["Linear"] = {"params": params, "r2": r2}
    except Exception:
        pass

    try:
        params, y_hat, r2 = fit_logarithmic(x, y)
        models["Logarithmic"] = {"params": params, "r2": r2}
    except Exception:
        pass

    try:
        params, y_hat, r2 = fit_exponential(x, y)
        models["Exponential"] = {"params": params, "r2": r2}
    except Exception:
        pass

    try:
        params, y_hat, r2 = fit_cubic(x, y)
        models["Cubic Polynomial"] = {"params": params, "r2": r2}
    except Exception:
        pass

    if not models:
        return np.nan, None, np.nan, {
            "Linear_r2": np.nan,
            "Log_r2": np.nan,
            "Exp_r2": np.nan,
            "Cubic_r2": np.nan,
        }

    best_name = max(models, key=lambda m: models[m]["r2"])
    best_r2 = models[best_name]["r2"]

    if (
        "Linear" in models
        and best_name != "Linear"
        and not np.isnan(best_r2)
        and not np.isnan(models["Linear"]["r2"])
        and (best_r2 - models["Linear"]["r2"]) < LINEAR_PREFERENCE_THRESHOLD
    ):
        best_name = "Linear"

    all_r2 = {
        "Linear_r2": models["Linear"]["r2"] if "Linear" in models else np.nan,
        "Log_r2": models["Logarithmic"]["r2"] if "Logarithmic" in models else np.nan,
        "Exp_r2": models["Exponential"]["r2"] if "Exponential" in models else np.nan,
        "Cubic_r2": models["Cubic Polynomial"]["r2"] if "Cubic Polynomial" in models else np.nan,
    }

    return best_name, models[best_name]["params"], models[best_name]["r2"], all_r2


# ==========================
# ANALYSIS STAGE 1:
# EXPERIMENT-LEVEL SUMMARY
# ==========================
def experiment_level_summary(df_var, variable, outlier_mode):
    rows = []

    for exp, g in df_var.groupby("Experiment"):
        g = g[[BLOCK_SIZE_COLUMN, variable]].dropna().copy()
        x = g[BLOCK_SIZE_COLUMN].values.astype(float)
        y = g[variable].values.astype(float)

        sh_stat, sh_p = safe_shapiro(y)
        p_r, p_p = safe_pearson(x, y)
        s_r, s_p = safe_spearman(x, y)
        best_reg, best_params, best_r2, all_r2 = determine_best_regression(x, y)

        rows.append(
            {
                "Experiment": exp,
                "Compartment": EXPERIMENT_DISPLAY_MAP.get(exp, exp),
                "OutlierStatus": outlier_mode,
                "Variable": variable,
                "N": len(g),
                "Mean": np.mean(y) if len(y) else np.nan,
                "StdDev": np.std(y, ddof=1) if len(y) > 1 else np.nan,
                "CV": (
                    np.std(y, ddof=1) / np.mean(y)
                    if len(y) > 1 and np.mean(y) != 0
                    else np.nan
                ),
                "Shapiro_stat": sh_stat,
                "Shapiro_p": sh_p,
                "Pearson_r": p_r,
                "Pearson_p": p_p,
                "Spearman_r": s_r,
                "Spearman_p": s_p,
                "BestRegression": best_reg,
                "BestRegression_R2": best_r2,
                **all_r2,
            }
        )

    return rows


# ==========================
# ANALYSIS STAGE 2:
# GLOBAL COMPARISON BY BLOCK SIZE
# ==========================
def grouped_comparison_by_block(df_var, variable, outlier_mode):
    summary_rows = []
    pairwise_rows = []

    experiment_order = [name for _, name in INPUT_FILES]

    for block_size, g in df_var.groupby(BLOCK_SIZE_COLUMN):
        groups = []
        labels = []

        for exp in experiment_order:
            vals = g.loc[g["Experiment"] == exp, variable].dropna().values.astype(float)
            if len(vals) > 0:
                groups.append(vals)
                labels.append(exp)

        if len(groups) < 2:
            continue

        shapiro_ps = []
        for vals in groups:
            _, p = safe_shapiro(vals)
            shapiro_ps.append(p)

        normal = all(
            (not np.isnan(p) and p > ALPHA)
            for p in shapiro_ps
            if not np.isnan(p)
        )
        lev_stat, lev_p = safe_levene(groups)

        # Pipeline fixado como não-paramétrico
        test_name = "Kruskal-Wallis"
        test_stat, test_p = safe_kruskal(groups)
        effect_name = "epsilon_squared"
        effect_value = epsilon_squared_kruskal(test_stat, groups)

        summary_rows.append(
            {
                "BlockSize": block_size,
                "OutlierStatus": outlier_mode,
                "Variable": variable,
                "NormalAcrossGroups": normal,
                "Levene_stat": lev_stat,
                "Levene_p": lev_p,
                "GroupComparison": test_name,
                "GroupStat": test_stat,
                "GroupP": test_p,
                "EffectSizeName": effect_name,
                "EffectSizeValue": effect_value,
                "GroupsIncluded": " | ".join(labels),
            }
        )

        values_by_label = {lab: grp for lab, grp in zip(labels, groups)}

        for exp_a, exp_b in TARGET_COMPARISONS:
            if exp_a not in values_by_label or exp_b not in values_by_label:
                continue

            vals_a = values_by_label[exp_a]
            vals_b = values_by_label[exp_b]

            pairwise_rows.append(
                {
                    "BlockSize": block_size,
                    "OutlierStatus": outlier_mode,
                    "Variable": variable,
                    "Comparison": f"{exp_a} vs {exp_b}",
                    "ExperimentA": exp_a,
                    "ExperimentB": exp_b,
                    "N_A": len(vals_a),
                    "N_B": len(vals_b),
                    "Median_A": np.median(vals_a) if len(vals_a) else np.nan,
                    "Median_B": np.median(vals_b) if len(vals_b) else np.nan,
                    "Mean_A": np.mean(vals_a) if len(vals_a) else np.nan,
                    "Mean_B": np.mean(vals_b) if len(vals_b) else np.nan,
                    "CliffsDelta": cliffs_delta(vals_a, vals_b),
                    "MedianRatio_A_over_B": median_ratio(vals_a, vals_b),
                }
            )

    return summary_rows, pairwise_rows


# ==========================
# ANALYSIS STAGE 3:
# AGGREGATED GLOBAL SUMMARY
# ==========================
def aggregated_global_summary(block_df):
    """
    It summarises the overall results by block, by variable and outlier status.
    The overall p-value here is the lowest p-value found across the blocks.
    This is not a formal meta-analysis.
    """
    rows = []

    if block_df.empty:
        return rows

    grouped = block_df.groupby(["OutlierStatus", "Variable"])

    for (outlier_status, variable), g in grouped:
        valid_p = g["GroupP"].dropna()
        global_p = valid_p.min() if not valid_p.empty else np.nan

        effect_vals = g["EffectSizeValue"].dropna().values
        rows.append(
            {
                "OutlierStatus": outlier_status,
                "Variable": variable,
                "GlobalGroupP": global_p,
                "GlobalEffectSizeName": "epsilon_squared",
                "GlobalEffectSizeMedian": np.median(effect_vals) if effect_vals.size else np.nan,
                "GlobalEffectSizeIQR": compute_iqr(effect_vals) if effect_vals.size else np.nan,
            }
        )

    return rows


def aggregate_pairwise_effect_sizes(pairwise_df):
    """
    Aggregates the desired pairwise comparisons between blocks.
    """
    if pairwise_df.empty:
        return pd.DataFrame(
            columns=[
                "OutlierStatus",
                "Variable",
                "Comparison",
                "MedianCliffsDelta",
                "IQRCliffsDelta",
                "MedianMedianRatio",
                "IQRMedianRatio",
            ]
        )

    agg = pairwise_df.groupby(["OutlierStatus", "Variable", "Comparison"]).agg(
        MedianCliffsDelta=("CliffsDelta", "median"),
        IQRCliffsDelta=("CliffsDelta", lambda v: compute_iqr(v.values)),
        MedianMedianRatio=("MedianRatio_A_over_B", "median"),
        IQRMedianRatio=("MedianRatio_A_over_B", lambda v: compute_iqr(v.values)),
    )

    return agg.reset_index()


# ==========================
# FINAL TABLE BUILDERS
# ==========================
def build_experiment_summary_table(experiment_df, selected_time_vars):
    if experiment_df.empty:
        return pd.DataFrame()

    rows = []
    for _, row in experiment_df.iterrows():
        rows.append(
            {
                "Compartment": row["Compartment"],
                "Outliers": "With" if row["OutlierStatus"] == "With_Outliers" else "Without",
                "Variable": row["Variable"],
                "N": row["N"],
                "Norm. (Shap.)": format_normality_text(row["Shapiro_p"]),
                "Pearson Correl.": row["Pearson_r"],
                "Spearman Correl.": row["Spearman_r"],
                "Best Reg.": row["BestRegression"],
                "R²": row["BestRegression_R2"],
            }
        )

    summary_df = pd.DataFrame(rows)
    variable_order = {var: i for i, var in enumerate(selected_time_vars)}
    summary_df["GroupOrder"] = summary_df["Compartment"].map(GROUP_ORDER).fillna(999)
    summary_df["OutlierOrder"] = summary_df["Outliers"].map({"With": 0, "Without": 1}).fillna(999)
    summary_df["VariableOrder"] = summary_df["Variable"].map(variable_order).fillna(999)

    summary_df = summary_df.sort_values(
        by=["GroupOrder", "OutlierOrder", "VariableOrder"]
    ).drop(columns=["GroupOrder", "OutlierOrder", "VariableOrder"])

    return summary_df


def build_block_global_table(block_df, selected_time_vars):
    if block_df.empty:
        return pd.DataFrame()

    table = block_df.copy()
    table["Outliers"] = table["OutlierStatus"].map(
        {"With_Outliers": "With", "Without_Outliers": "Without"}
    )
    table["KW"] = table["GroupP"].apply(format_pvalue_text)

    table = table[
        [
            "BlockSize",
            "Outliers",
            "Variable",
            "KW",
            "EffectSizeName",
            "EffectSizeValue",
            "NormalAcrossGroups",
            "Levene_p",
            "GroupsIncluded",
        ]
    ].copy()

    variable_order = {var: i for i, var in enumerate(selected_time_vars)}
    table["OutlierOrder"] = table["Outliers"].map({"With": 0, "Without": 1}).fillna(999)
    table["VariableOrder"] = table["Variable"].map(variable_order).fillna(999)

    table = table.sort_values(
        by=["OutlierOrder", "VariableOrder", "BlockSize"]
    ).drop(columns=["OutlierOrder", "VariableOrder"])

    return table


def build_pairwise_block_table(pairwise_df, selected_time_vars):
    if pairwise_df.empty:
        return pd.DataFrame()

    table = pairwise_df.copy()
    table["Outliers"] = table["OutlierStatus"].map(
        {"With_Outliers": "With", "Without_Outliers": "Without"}
    )

    table = table[
        [
            "BlockSize",
            "Outliers",
            "Variable",
            "Comparison",
            "N_A",
            "N_B",
            "Median_A",
            "Median_B",
            "CliffsDelta",
            "MedianRatio_A_over_B",
        ]
    ].copy()

    variable_order = {var: i for i, var in enumerate(selected_time_vars)}
    table["OutlierOrder"] = table["Outliers"].map({"With": 0, "Without": 1}).fillna(999)
    table["VariableOrder"] = table["Variable"].map(variable_order).fillna(999)

    table = table.sort_values(
        by=["OutlierOrder", "VariableOrder", "Comparison", "BlockSize"]
    ).drop(columns=["OutlierOrder", "VariableOrder"])

    return table


def build_pairwise_aggregated_table(pairwise_summary_df, selected_time_vars):
    if pairwise_summary_df.empty:
        return pd.DataFrame()

    table = pairwise_summary_df.copy()
    table["Outliers"] = table["OutlierStatus"].map(
        {"With_Outliers": "With", "Without_Outliers": "Without"}
    )

    table = table[
        [
            "Outliers",
            "Variable",
            "Comparison",
            "MedianCliffsDelta",
            "IQRCliffsDelta",
            "MedianMedianRatio",
            "IQRMedianRatio",
        ]
    ].copy()

    variable_order = {var: i for i, var in enumerate(selected_time_vars)}
    comparison_order = {
        f"{a} vs {b}": i for i, (a, b) in enumerate(TARGET_COMPARISONS)
    }

    table["OutlierOrder"] = table["Outliers"].map({"With": 0, "Without": 1}).fillna(999)
    table["VariableOrder"] = table["Variable"].map(variable_order).fillna(999)
    table["ComparisonOrder"] = table["Comparison"].map(comparison_order).fillna(999)

    table = table.sort_values(
        by=["OutlierOrder", "VariableOrder", "ComparisonOrder"]
    ).drop(columns=["OutlierOrder", "VariableOrder", "ComparisonOrder"])

    return table


# ==========================
# PLOTTING
# ==========================
def plot_combined_trendlines(df_all, variables, outlier_mode, save_dir):
    n_vars = len(variables)
    ncols = 2
    nrows = (n_vars + ncols - 1) // ncols
    fig, axs = plt.subplots(nrows, ncols, figsize=(14, 5 * nrows), squeeze=False)
    axs_flat = axs.flatten()

    for i, variable in enumerate(variables):
        ax = axs_flat[i]
        df_var = preprocess_dataset(df_all, variable, outlier_mode)

        for exp in [name for _, name in INPUT_FILES]:
            g = df_var[df_var["Experiment"] == exp][[BLOCK_SIZE_COLUMN, variable]].dropna().copy()
            if len(g) < 2:
                continue

            x = g[BLOCK_SIZE_COLUMN].values.astype(float)
            y = g[variable].values.astype(float)

            sort_idx = np.argsort(x)
            x_sorted = x[sort_idx]
            y_sorted = y[sort_idx]

            best_name, params, best_r2, _ = determine_best_regression(x_sorted, y_sorted)
            if params is None:
                continue

            y_fit = evaluate_model(best_name, params, x_sorted)

            ax.plot(
                x_sorted,
                y_fit,
                linestyle=LINE_STYLES[exp],
                color=EXPERIMENT_COLORS[exp],
                marker=MARKERS[exp],
                markersize=5,
                markevery=max(1, len(x_sorted) // 8),
                linewidth=2.5,
                label=f"{EXPERIMENT_DISPLAY_MAP.get(exp, exp)} ({best_name})",
            )

        ax.set_title(variable)
        ax.grid(True)

    for j in range(n_vars, len(axs_flat)):
        axs_flat[j].axis("off")

    fig.text(0.5, 0.04, "Block Size (MB)", ha="center")
    fig.text(0.04, 0.5, "Time (ms)", va="center", rotation="vertical")

    handles, labels = [], []
    for ax in axs_flat[:n_vars]:
        h, l = ax.get_legend_handles_labels()
        handles.extend(h)
        labels.extend(l)

    if handles:
        by_label = dict(zip(labels, handles))
        fig.legend(by_label.values(), by_label.keys(), loc="upper center", ncol=max(1, len(by_label)))

    plt.subplots_adjust(left=0.08, right=0.98, top=0.94, bottom=0.08, hspace=0.28, wspace=0.22)
    fig.savefig(os.path.join(save_dir, f"combined_trendlines_{outlier_mode}.svg"))
    plt.close()


def plot_combined_qq_data(df_all, variables, outlier_mode, save_dir):
    fig, axs = plt.subplots(len(variables), len(INPUT_FILES), figsize=(15, 5 * len(variables)))
    if len(variables) == 1:
        axs = np.array([axs])

    for i, variable in enumerate(variables):
        df_var = preprocess_dataset(df_all, variable, outlier_mode)

        for j, (_, exp_name) in enumerate(INPUT_FILES):
            ax = axs[i][j]
            g = df_var[df_var["Experiment"] == exp_name][[variable]].dropna().copy()

            if len(g) < 3:
                ax.axis("off")
                continue

            y = g[variable].values.astype(float)

            if len(y) < 3:
                ax.axis("off")
                continue

            (osm, osr), _ = probplot(y, dist="norm")

            ax.plot(
                osm,
                osr,
                marker=MARKERS[exp_name],
                linestyle="",
                color=EXPERIMENT_COLORS[exp_name],
            )

            coef = np.polyfit(osm, osr, 1)
            y_line = np.polyval(coef, osm)
            ax.plot(
                osm,
                y_line,
                linestyle="-",
                color=EXPERIMENT_COLORS[exp_name],
                alpha=0.7,
                linewidth=1.5,
            )

            ax.set_title(f"{EXPERIMENT_DISPLAY_MAP.get(exp_name, exp_name)} – {variable}")
            ax.grid(True)

    fig.text(0.5, 0.04, "Theoretical Quantiles", ha="center")
    fig.text(0.04, 0.5, "Data Quantiles", va="center", rotation="vertical")

    plt.subplots_adjust(left=0.08, right=0.98, top=0.94, bottom=0.08, hspace=0.30, wspace=0.25)
    fig.savefig(os.path.join(save_dir, f"combined_qqplots_data_{outlier_mode}.svg"))
    plt.close()


# ==========================
# MAIN
# ==========================
def main():
    output_dir = "statistical_results"
    os.makedirs(output_dir, exist_ok=True)

    df_all, selected_time_vars = load_all_data()

    experiment_rows = []
    block_rows = []
    pairwise_rows = []

    for outlier_mode in ["With_Outliers", "Without_Outliers"]:
        for variable in selected_time_vars:
            df_var = preprocess_dataset(df_all, variable, outlier_mode)

            experiment_rows.extend(
                experiment_level_summary(df_var, variable, outlier_mode)
            )

            b_rows, p_rows = grouped_comparison_by_block(df_var, variable, outlier_mode)
            block_rows.extend(b_rows)
            pairwise_rows.extend(p_rows)

        plot_combined_trendlines(df_all, selected_time_vars, outlier_mode, output_dir)
        plot_combined_qq_data(df_all, selected_time_vars, outlier_mode, output_dir)

    experiment_df = pd.DataFrame(experiment_rows)
    block_df = pd.DataFrame(block_rows)
    pairwise_df = pd.DataFrame(pairwise_rows)
    global_df = pd.DataFrame(aggregated_global_summary(block_df))
    pairwise_summary_df = aggregate_pairwise_effect_sizes(pairwise_df)

    table_1_experiment_summary = build_experiment_summary_table(experiment_df, selected_time_vars)
    table_2_block_global = build_block_global_table(block_df, selected_time_vars)
    table_3_pairwise_by_block = build_pairwise_block_table(pairwise_df, selected_time_vars)
    table_4_pairwise_aggregated = build_pairwise_aggregated_table(
        pairwise_summary_df, selected_time_vars
    )

    experiment_df.to_csv(
        os.path.join(output_dir, "experiment_level_summary_raw.csv"),
        index=False
    )
    block_df.to_csv(
        os.path.join(output_dir, "block_size_group_comparison_summary_raw.csv"),
        index=False
    )
    pairwise_df.to_csv(
        os.path.join(output_dir, "pairwise_effect_sizes_by_block_size_raw.csv"),
        index=False
    )
    global_df.to_csv(
        os.path.join(output_dir, "global_group_summary_raw.csv"),
        index=False
    )
    pairwise_summary_df.to_csv(
        os.path.join(output_dir, "pairwise_effect_sizes_aggregated_raw.csv"),
        index=False
    )

    table_1_experiment_summary.to_csv(
        os.path.join(output_dir, "table_1_experiment_summary.csv"),
        index=False
    )
    table_2_block_global.to_csv(
        os.path.join(output_dir, "table_2_block_global_comparison.csv"),
        index=False
    )
    table_3_pairwise_by_block.to_csv(
        os.path.join(output_dir, "table_3_pairwise_by_block.csv"),
        index=False
    )
    table_4_pairwise_aggregated.to_csv(
        os.path.join(output_dir, "table_4_pairwise_aggregated.csv"),
        index=False
    )

    print("Files saved in:", output_dir)
    print("- experiment_level_summary_raw.csv")
    print("- block_size_group_comparison_summary_raw.csv")
    print("- pairwise_effect_sizes_by_block_size_raw.csv")
    print("- global_group_summary_raw.csv")
    print("- pairwise_effect_sizes_aggregated_raw.csv")
    print("- table_1_experiment_summary.csv")
    print("- table_2_block_global_comparison.csv")
    print("- table_3_pairwise_by_block.csv")
    print("- table_4_pairwise_aggregated.csv")
    print("- combined_trendlines_With_Outliers.svg")
    print("- combined_trendlines_Without_Outliers.svg")
    print("- combined_qqplots_data_With_Outliers.svg")
    print("- combined_qqplots_data_Without_Outliers.svg")


if __name__ == "__main__":
    main()