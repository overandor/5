import requests
import time

# The base URL of the KPI Factory service
BASE_URL = "http://localhost:8000"

# A list of 30 sample KPIs to seed the system with, as per the user's detailed description
SAMPLE_KPIS = [
    {"name": "Entropy-Profit Density", "formula": "ewma(zscore(novelty_bits) * realized_usd / token_cost)"},
    {"name": "Prompt Yield", "formula": "usd_per_1k_tokens * reuse_frequency"},
    {"name": "Dormant Reserve Activation", "formula": "sum(value_of_revived_assets)"},
    {"name": "Latency-Liquidity Overlap", "formula": "trade_volume / avg_latency_ms"},
    {"name": "Ambiguity Leverage Index", "formula": "regulatory_risk_score * potential_gain"},
    {"name": "Social Proof Velocity", "formula": "mention_frequency / time_unit"},
    {"name": "Dormancy Time Premium", "formula": "value_multiplier * days_dormant"},
    {"name": "Sovereign Credit Entropy", "formula": "1 / stability_under_replication"},
    {"name": "Cross-Jurisdictional Entropy Spread", "formula": "stddev(licensing_value)"},
    {"name": "Recursive Reuse Yield", "formula": "yield * (1 + reuse_depth)"},
    {"name": "Liquidity Echo Value", "formula": "initial_liquidity * echo_factor"},
    {"name": "Obscurity Extraction Value", "formula": "value_extracted / obscurity_score"},
    {"name": "Prompt Dollar Multiplier", "formula": "revenue_generated / prompt_cost"},
    {"name": "Influence-Dollar Ratio", "formula": "influence_score / usd_spent"},
    {"name": "Cognitive Dollar Extraction", "formula": "perceived_insight / time_spent"},
    {"name": "Settlement Slippage Penalty", "formula": "1 / slippage_percentage"},
    {"name": "Trust Residual", "formula": "post_audit_pass_rate"},
    {"name": "Quality-Latency Tradeoff score", "formula": "quality_score / latency_ms"},
    {"name": "Conversion Ratio from demo to adoption", "formula": "adoptions / demos"},
    {"name": "Stability Under Perturbation", "formula": "1 / deviation_on_perturb"},
    {"name": "Safety Compliance Rate", "formula": "compliant_checks / total_checks"},
    {"name": "Cost-Down Efficiency", "formula": "1 / normalized_cost"},
    {"name": "Retention Velocity", "formula": "retained_users / time_period"},
    {"name": "Error Budget Utilization", "formula": "1 / error_budget_used"},
    {"name": "Uptime Weighted by Users", "formula": "uptime * active_users"},
    {"name": "Performance (ops/s normalized)", "formula": "ops_per_second / baseline"},
    {"name": "Volatility-Adjusted Adoption", "formula": "adoption_rate / volatility"},
    {"name": "ROC-AUC uplift vs baseline", "formula": "model_auc / baseline_auc"},
    {"name": "Human Approval Rate", "formula": "approved_items / total_items"},
    {"name": "Evidence Density", "formula": "proofs_per_1000_usd"}
]

def seed_kpis():
    """
    Sends POST requests to the KPI Factory service to create the sample KPIs.
    """
    print("Seeding the KPI Factory with initial KPIs...")
    for kpi in SAMPLE_KPIS:
        try:
            response = requests.post(f"{BASE_URL}/kpis", json=kpi)
            if response.status_code == 200:
                ticker = response.json().get("ticker")
                print(f"  Successfully created KPI: {kpi['name']} (Ticker: {ticker})")
            else:
                print(f"  Failed to create KPI: {kpi['name']} - Status: {response.status_code}, Response: {response.text}")
        except requests.exceptions.ConnectionError as e:
            print(f"\nError: Could not connect to the KPI Factory service at {BASE_URL}.")
            print("Please ensure the backend service is running.")
            return
        time.sleep(0.1) # a small delay to avoid overwhelming the server

if __name__ == "__main__":
    seed_kpis()
