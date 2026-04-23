
import os
import glob
import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt

from scipy.optimize import curve_fit
from scipy.stats import shapiro, pearsonr, spearmanr, levene, kruskal, probplot
from sklearn.metrics import r2_score

mpl.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
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
})

ALPHA = 0.05
LINEAR_PREFERENCE_THRESHOLD = 0.10

MODE_MAP = {
    "outside": "outside compartment",
    "purecap": "purecap ABI",
    "benchmark": "purecap-benchmark ABI",
    "purecap-benchmark": "purecap-benchmark ABI",
}

GROUP_ORDER = {
    "outside compartment": 0,
    "purecap ABI": 1,
    "purecap-benchmark ABI": 2,
}

EXPERIMENT_COLORS = {
    "outside compartment": "#ff7f0e",
    "purecap ABI": "#1f77b4",
    "purecap-benchmark ABI": "#2ca02c",
}

LINE_STYLES = {
    "outside compartment": ":",
    "purecap ABI": "-",
    "purecap-benchmark ABI": "--",
}

MARKERS = {
    "outside compartment": "^",
    "purecap ABI": "o",
    "purecap-benchmark ABI": "s",
}

SIZE_COLUMN = "Input Size (bytes)"
SIZE_LABEL_COLUMN = "Input Size"
LATENCY_COLUMN = "Latency (ms)"
RATE_COLUMN = "Throughput / Rate"
RATE_UNIT_COLUMN = "Rate Unit"

VARIABLE_SPECS = [
    ("sha256", "hash", "SHA-256", "MB/s"),
    ("aes256gcm", "encrypt", "AES-256-GCM encrypt", "MB/s"),
    ("aes256gcm", "decrypt", "AES-256-GCM decrypt", "MB/s"),
    ("ed25519", "sign", "Ed25519 sign", "ops/s"),
    ("ed25519", "verify", "Ed25519 verify", "ops/s"),
]

TARGET_COMPARISONS = [
    ("purecap ABI", "outside compartment"),
    ("purecap-benchmark ABI", "outside compartment"),
]

def pretty_variable_name(workload, operation):
    for w, o, label, _ in VARIABLE_SPECS:
        if workload == w and operation == o:
            return label
    return f"{workload} {operation}"

def rate_unit_for(variable):
    for _, _, label, unit in VARIABLE_SPECS:
        if variable == label:
            return unit
    return ""

def format_size(value):
    value = float(value)
    if value >= 1024**2 and value % (1024**2) == 0:
        return f"{int(value/(1024**2))} MB"
    if value >= 1024 and value % 1024 == 0:
        return f"{int(value/1024)} KB"
    return str(int(value))

def infer_experiment_name(df, file_path):
    mode_values = df["mode"].dropna().astype(str).unique().tolist()
    if len(mode_values) != 1:
        raise ValueError(f"Expected a single mode in {file_path}, found {mode_values}")
    mode_value = mode_values[0].strip().lower()
    if mode_value not in MODE_MAP:
        raise ValueError(f"Unknown mode '{mode_value}' in {file_path}")
    return MODE_MAP[mode_value]

def discover_input_files(base_dir):
    patterns = [
        os.path.join(base_dir, "crypto_*.csv"),
        os.path.join(base_dir, "*crypto*.csv"),
    ]
    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern))
    files = sorted(set(files))
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        raise FileNotFoundError("No crypto CSV files found.")
    return files

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

def compute_iqr(values):
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    if values.size == 0:
        return np.nan
    q1 = np.quantile(values, 0.25, method="linear")
    q3 = np.quantile(values, 0.75, method="linear")
    return q3 - q1

def epsilon_squared_kruskal(H, groups):
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
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    x = x[~np.isnan(x)]
    y = y[~np.isnan(y)]
    if x.size == 0 or y.size == 0:
        return np.nan
    med_x = np.median(x)
    med_y = np.median(y)
    if np.isnan(med_x) or np.isnan(med_y) or np.isclose(med_y, 0.0, atol=atol):
        return np.nan
    return med_x / med_y

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
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.max() == x.min():
        raise ValueError("Need more than one x value for exponential model.")
    x_scaled = (x - x.min()) / (x.max() - x.min())
    popt, _ = curve_fit(lambda t, a, b: a * np.exp(b * t), x_scaled, y, maxfev=10000)
    y_hat = popt[0] * np.exp(popt[1] * x_scaled)
    return (popt[0], popt[1], x.min(), x.max()), y_hat, r2_score(y, y_hat)

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
        a, b, xmin, xmax = params
        x = np.asarray(x, dtype=float)
        x_scaled = (x - xmin) / (xmax - xmin) if xmax != xmin else x.copy()
        return a * np.exp(b * x_scaled)
    if model_name == "Cubic Polynomial":
        return np.polyval(params, x)
    raise ValueError(f"Unknown model: {model_name}")

def determine_best_regression(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    models = {}
    try:
        params, _, r2 = fit_linear(x, y)
        models["Linear"] = {"params": params, "r2": r2}
    except Exception:
        pass
    try:
        params, _, r2 = fit_logarithmic(x, y)
        models["Logarithmic"] = {"params": params, "r2": r2}
    except Exception:
        pass
    try:
        params, _, r2 = fit_exponential(x, y)
        models["Exponential"] = {"params": params, "r2": r2}
    except Exception:
        pass
    try:
        params, _, r2 = fit_cubic(x, y)
        models["Cubic Polynomial"] = {"params": params, "r2": r2}
    except Exception:
        pass
    if not models:
        return np.nan, None, np.nan
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
    return best_name, models[best_name]["params"], models[best_name]["r2"]

def load_all_data(base_dir="."):
    frames = []
    input_files = discover_input_files(base_dir)
    for file_path in input_files:
        df = pd.read_csv(file_path)
        experiment = infer_experiment_name(df, file_path)
        df = df[df["success"] == 1].copy()
        df["Experiment"] = experiment
        df[SIZE_COLUMN] = pd.to_numeric(df["size_bytes"], errors="coerce")
        df["start_time_ms"] = pd.to_numeric(df["start_time_ms"], errors="coerce")
        df["end_time_ms"] = pd.to_numeric(df["end_time_ms"], errors="coerce")
        df[LATENCY_COLUMN] = df["end_time_ms"] - df["start_time_ms"]
        df["Variable"] = [pretty_variable_name(w, o) for w, o in zip(df["workload"], df["operation"])]
        df[RATE_UNIT_COLUMN] = df["Variable"].map(rate_unit_for)
        df[SIZE_LABEL_COLUMN] = df[SIZE_COLUMN].map(format_size)
        frames.append(df[[
            "Experiment", "Variable", SIZE_COLUMN, SIZE_LABEL_COLUMN, LATENCY_COLUMN, RATE_UNIT_COLUMN,
            "start_time_ms", "end_time_ms", "repetition"
        ]].copy())
    if not frames:
        raise ValueError("No input files loaded.")
    df_all = pd.concat(frames, ignore_index=True)
    df_all = df_all.dropna(subset=[SIZE_COLUMN, LATENCY_COLUMN, "Variable"])
    return df_all

def iqr_filter_by_group(df, group_cols, value_col):
    kept = []
    for _, g in df.groupby(list(group_cols)):
        vals = g[value_col].dropna()
        if len(vals) < 4:
            kept.append(g)
            continue
        q1 = vals.quantile(0.25, interpolation="linear")
        q3 = vals.quantile(0.75, interpolation="linear")
        iqr = q3 - q1
        if pd.isna(iqr) or iqr == 0:
            kept.append(g)
            continue
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        kept.append(g[(g[value_col] >= lower) & (g[value_col] <= upper)])
    if not kept:
        return df.iloc[0:0].copy()
    return pd.concat(kept, ignore_index=False).sort_index()

def preprocess_dataset(df_all, variable, outlier_mode):
    df = df_all[df_all["Variable"] == variable].copy()
    if outlier_mode == "Without_Outliers":
        df = iqr_filter_by_group(df, ["Experiment", "Variable", SIZE_COLUMN], LATENCY_COLUMN)
    return df

def build_table0_by_size(df_all):
    rows = []
    df_wo = iqr_filter_by_group(df_all.copy(), ["Experiment", "Variable", SIZE_COLUMN], LATENCY_COLUMN)
    for (exp, variable, size, size_label, rate_unit), g in df_wo.groupby(
        ["Experiment", "Variable", SIZE_COLUMN, SIZE_LABEL_COLUMN, RATE_UNIT_COLUMN], sort=False
    ):
        lat = g[LATENCY_COLUMN].dropna().values.astype(float)
        if len(lat) == 0:
            continue
        mean = np.mean(lat)
        std = np.std(lat, ddof=1) if len(lat) > 1 else 0.0
        cv = (std / mean) * 100.0 if mean != 0 else np.nan
        if rate_unit == "MB/s":
            rate = (size / (1024**2)) / (mean / 1000.0)
        else:
            rate = 1000.0 / mean
        rows.append({
            "Mode": exp,
            "Workload": variable,
            "Input Size": size_label,
            "Input Size (bytes)": size,
            "Latency Mean (ms)": mean,
            "Latency Std (ms)": std,
            "Latency (ms)": f"{mean:.4f} ± {std:.4f}",
            "Variability (%)": cv,
            "Throughput / Rate": rate,
            "Rate Unit": rate_unit,
            "N": len(lat),
        })
    out = pd.DataFrame(rows)
    var_order = {v[2]: i for i, v in enumerate(VARIABLE_SPECS)}
    out["ModeOrder"] = out["Mode"].map(GROUP_ORDER).fillna(999)
    out["VariableOrder"] = out["Workload"].map(var_order).fillna(999)
    out = out.sort_values(["ModeOrder", "VariableOrder", "Input Size (bytes)"]).drop(columns=["ModeOrder", "VariableOrder"])
    return out

def experiment_level_summary(df_var, variable, outlier_mode):
    rows = []
    for exp, g in df_var.groupby("Experiment"):
        g = g[[SIZE_COLUMN, LATENCY_COLUMN]].dropna().copy()
        x = g[SIZE_COLUMN].values.astype(float)
        y = g[LATENCY_COLUMN].values.astype(float)
        sh_stat, sh_p = safe_shapiro(y)
        s_r, s_p = safe_spearman(x, y)
        best_reg, best_params, best_r2 = determine_best_regression(x, y)
        rows.append({
            "Mode": exp,
            "OutlierStatus": outlier_mode,
            "Variable": variable,
            "N": len(g),
            "Shapiro_stat": sh_stat,
            "Shapiro_p": sh_p,
            "Spearman_r": s_r,
            "Spearman_p": s_p,
            "BestRegression": best_reg,
            "BestRegression_R2": best_r2,
        })
    return rows

def grouped_comparison_by_size(df_var, variable, outlier_mode):
    summary_rows = []
    pairwise_rows = []
    experiment_order = ["outside compartment", "purecap ABI", "purecap-benchmark ABI"]
    for block_size, g in df_var.groupby(SIZE_COLUMN):
        groups = []
        labels = []
        for exp in experiment_order:
            vals = g.loc[g["Experiment"] == exp, LATENCY_COLUMN].dropna().values.astype(float)
            if len(vals) > 0:
                groups.append(vals)
                labels.append(exp)
        if len(groups) < 2:
            continue
        lev_stat, lev_p = safe_levene(groups)
        H, p = safe_kruskal(groups)
        eps = epsilon_squared_kruskal(H, groups)
        summary_rows.append({
            "Input Size (bytes)": block_size,
            "Input Size": format_size(block_size),
            "OutlierStatus": outlier_mode,
            "Variable": variable,
            "Levene_stat": lev_stat,
            "Levene_p": lev_p,
            "GroupComparison": "Kruskal-Wallis",
            "GroupStat": H,
            "GroupP": p,
            "EffectSizeValue": eps,
            "GroupsIncluded": " | ".join(labels),
        })
        values_by_label = {lab: grp for lab, grp in zip(labels, groups)}
        for exp_a, exp_b in TARGET_COMPARISONS:
            if exp_a not in values_by_label or exp_b not in values_by_label:
                continue
            vals_a = values_by_label[exp_a]
            vals_b = values_by_label[exp_b]
            pairwise_rows.append({
                "Input Size (bytes)": block_size,
                "Input Size": format_size(block_size),
                "OutlierStatus": outlier_mode,
                "Variable": variable,
                "Comparison": f"{exp_a} vs {exp_b}",
                "ExperimentA": exp_a,
                "ExperimentB": exp_b,
                "CliffsDelta": cliffs_delta(vals_a, vals_b),
                "MedianRatio_A_over_B": median_ratio(vals_a, vals_b),
            })
    return summary_rows, pairwise_rows

def aggregated_global_summary(block_df):
    rows = []
    if block_df.empty:
        return rows
    grouped = block_df.groupby(["OutlierStatus", "Variable"])
    for (outlier_status, variable), g in grouped:
        effect_vals = g["EffectSizeValue"].dropna().values
        rows.append({
            "OutlierStatus": outlier_status,
            "Variable": variable,
            "Median epsilon_squared": np.median(effect_vals) if effect_vals.size else np.nan,
            "IQR epsilon_squared": compute_iqr(effect_vals) if effect_vals.size else np.nan,
        })
    return rows

def aggregate_pairwise_effect_sizes(pairwise_df):
    if pairwise_df.empty:
        return pd.DataFrame(columns=[
            "OutlierStatus", "Variable", "Comparison", "Median Cliff's Delta", "IQR Cliff's Delta",
            "Median Ratio", "IQR Median Ratio",
        ])
    agg = pairwise_df.groupby(["OutlierStatus", "Variable", "Comparison"]).agg(
        **{
            "Median Cliff's Delta": ("CliffsDelta", "median"),
            "IQR Cliff's Delta": ("CliffsDelta", lambda v: compute_iqr(v.values)),
            "Median Ratio": ("MedianRatio_A_over_B", "median"),
            "IQR Median Ratio": ("MedianRatio_A_over_B", lambda v: compute_iqr(v.values)),
        }
    )
    return agg.reset_index()

def plot_combined_trendlines(df_all, variables, outlier_mode, save_dir):
    n_vars = len(variables)
    ncols = 2
    nrows = (n_vars + ncols - 1) // ncols
    fig, axs = plt.subplots(nrows, ncols, figsize=(14, 4.5 * nrows), squeeze=False)
    axs_flat = axs.flatten()
    for i, variable in enumerate(variables):
        ax = axs_flat[i]
        df_var = preprocess_dataset(df_all, variable, outlier_mode)
        for exp in ["outside compartment", "purecap ABI", "purecap-benchmark ABI"]:
            g = df_var[df_var["Experiment"] == exp][[SIZE_COLUMN, LATENCY_COLUMN]].dropna().copy()
            if len(g) < 2:
                continue
            summary = g.groupby(SIZE_COLUMN, as_index=False)[LATENCY_COLUMN].mean().sort_values(SIZE_COLUMN)
            x = summary[SIZE_COLUMN].values.astype(float)
            y = summary[LATENCY_COLUMN].values.astype(float)
            best_name, params, _ = determine_best_regression(x, y)
            if params is None:
                continue
            y_fit = evaluate_model(best_name, params, x)
            ax.plot(x, y_fit, linestyle=LINE_STYLES[exp], color=EXPERIMENT_COLORS[exp],
                    marker=MARKERS[exp], markersize=5, linewidth=2.5, label=f"{exp} ({best_name})")
            ax.set_xticks(x)
            ax.set_xticklabels([format_size(v) for v in x], rotation=30)
        ax.set_title(variable)
        ax.grid(True)
    for j in range(n_vars, len(axs_flat)):
        axs_flat[j].axis("off")
    fig.text(0.5, 0.04, "Input Size", ha="center")
    fig.text(0.04, 0.5, "Latency (ms)", va="center", rotation="vertical")
    handles, labels = [], []
    for ax in axs_flat[:n_vars]:
        h, l = ax.get_legend_handles_labels()
        handles.extend(h)
        labels.extend(l)
    if handles:
        by_label = dict(zip(labels, handles))
        fig.legend(by_label.values(), by_label.keys(), loc="upper center", ncol=max(1, len(by_label)))
    plt.subplots_adjust(left=0.08, right=0.98, top=0.92, bottom=0.08, hspace=0.35, wspace=0.25)
    fig.savefig(os.path.join(save_dir, f"combined_trendlines_{outlier_mode}.svg"))
    plt.close()

def plot_combined_qq_data(df_all, variables, outlier_mode, save_dir):
    fig, axs = plt.subplots(len(variables), 3, figsize=(15, 4 * len(variables)))
    if len(variables) == 1:
        axs = np.array([axs])
    exps = ["outside compartment", "purecap ABI", "purecap-benchmark ABI"]
    for i, variable in enumerate(variables):
        df_var = preprocess_dataset(df_all, variable, outlier_mode)
        for j, exp_name in enumerate(exps):
            ax = axs[i][j]
            g = df_var[df_var["Experiment"] == exp_name][[LATENCY_COLUMN]].dropna().copy()
            if len(g) < 3:
                ax.axis("off")
                continue
            y = g[LATENCY_COLUMN].values.astype(float)
            (osm, osr), _ = probplot(y, dist="norm")
            ax.plot(osm, osr, marker=MARKERS[exp_name], linestyle="", color=EXPERIMENT_COLORS[exp_name])
            coef = np.polyfit(osm, osr, 1)
            y_line = np.polyval(coef, osm)
            ax.plot(osm, y_line, linestyle="-", color=EXPERIMENT_COLORS[exp_name], alpha=0.7, linewidth=1.5)
            ax.set_title(f"{exp_name} – {variable}")
            ax.grid(True)
    fig.text(0.5, 0.04, "Theoretical Quantiles", ha="center")
    fig.text(0.04, 0.5, "Data Quantiles", va="center", rotation="vertical")
    plt.subplots_adjust(left=0.08, right=0.98, top=0.95, bottom=0.08, hspace=0.35, wspace=0.25)
    fig.savefig(os.path.join(save_dir, f"combined_qqplots_data_{outlier_mode}.svg"))
    plt.close()

def main(base_dir=".", output_dir="crypto_statistical_results_corrected"):
    os.makedirs(output_dir, exist_ok=True)
    df_all = load_all_data(base_dir)
    variables = [spec[2] for spec in VARIABLE_SPECS]

    table_0_by_size = build_table0_by_size(df_all)

    experiment_rows = []
    block_rows = []
    pairwise_rows = []
    for outlier_mode in ["With_Outliers", "Without_Outliers"]:
        for variable in variables:
            df_var = preprocess_dataset(df_all, variable, outlier_mode)
            experiment_rows.extend(experiment_level_summary(df_var, variable, outlier_mode))
            b_rows, p_rows = grouped_comparison_by_size(df_var, variable, outlier_mode)
            block_rows.extend(b_rows)
            pairwise_rows.extend(p_rows)
        plot_combined_trendlines(df_all, variables, outlier_mode, output_dir)
        plot_combined_qq_data(df_all, variables, outlier_mode, output_dir)

    experiment_df = pd.DataFrame(experiment_rows)
    block_df = pd.DataFrame(block_rows)
    pairwise_df = pd.DataFrame(pairwise_rows)
    global_df = pd.DataFrame(aggregated_global_summary(block_df))
    pairwise_summary_df = aggregate_pairwise_effect_sizes(pairwise_df)

    table_0_by_size.to_csv(os.path.join(output_dir, "table_0_crypto_results_by_size.csv"), index=False)
    experiment_df.to_csv(os.path.join(output_dir, "table_1_experiment_summary.csv"), index=False)
    global_df.to_csv(os.path.join(output_dir, "table_2_global_effect_summary.csv"), index=False)
    pairwise_summary_df.to_csv(os.path.join(output_dir, "table_3_pairwise_aggregated.csv"), index=False)
    block_df.to_csv(os.path.join(output_dir, "block_size_group_comparison_summary_raw.csv"), index=False)
    pairwise_df.to_csv(os.path.join(output_dir, "pairwise_effect_sizes_by_input_size_raw.csv"), index=False)

    print("Files saved in:", output_dir)
    for name in [
        "table_0_crypto_results_by_size.csv",
        "table_1_experiment_summary.csv",
        "table_2_global_effect_summary.csv",
        "table_3_pairwise_aggregated.csv",
        "block_size_group_comparison_summary_raw.csv",
        "pairwise_effect_sizes_by_input_size_raw.csv",
        "combined_trendlines_With_Outliers.svg",
        "combined_trendlines_Without_Outliers.svg",
        "combined_qqplots_data_With_Outliers.svg",
        "combined_qqplots_data_Without_Outliers.svg",
    ]:
        print("-", name)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Statistical analysis")
    parser.add_argument("--base-dir", default=".", help="Directory containing crypto CSV files")
    parser.add_argument("--output-dir", default="crypto_statistical_results_corrected", help="Output directory")
    args = parser.parse_args()
    main(base_dir=args.base_dir, output_dir=args.output_dir)
