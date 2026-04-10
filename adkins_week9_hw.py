# =============================================================
# STAGE 1 — COLLECT
# Scenario 2: Threat Intel Enricher
# Build both DataFrames with realistic messy data, then inspect
# =============================================================

import pandas as pd
import numpy as np

np.random.seed(42)  # makes random data reproducible every run

# -----------------------------------------------------------------
# Part A: Build the DNS log (dns_log)
# This simulates 90 days of internal DNS resolver logs
# -----------------------------------------------------------------

n = 320  # we need at least 300 rows per the assignment

# Pool of internal client IPs (our employees/machines)
client_ips = [
    "192.168.1.10", "192.168.1.25", "192.168.1.88",
    "192.168.2.14", "192.168.2.57", "10.0.0.5", "10.0.0.22"
]

# Pool of domains — mix of safe ones and malicious ones
# The malicious ones will match the threat feed
safe_domains = [
    "google.com", "microsoft.com", "github.com", "stackoverflow.com",
    "office365.com", "zoom.us", "slack.com", "aws.amazon.com",
    "cloudflare.com", "wikipedia.org"
]

malicious_domains = [
    "badsite-c2.ru", "malware-drop.xyz", "phish-login.net",
    "ransomware-gate.io", "spyware-track.com", "botnet-cmd.top",
    "exfil-server.cc", "fake-update.biz"
]

all_domains = safe_domains + malicious_domains

# Randomly pick domains — malicious ones appear ~15% of the time
domain_weights = [0.75 / len(safe_domains)] * len(safe_domains) + \
                 [0.25 / len(malicious_domains)] * len(malicious_domains)

queried_domains = np.random.choice(all_domains, size=n, p=domain_weights)

# DATA QUALITY ISSUE #2: Inconsistent capitalization
# About 20% of domain entries are randomly uppercased
capitalization_mask = np.random.random(n) < 0.2
queried_domains = [
    d.upper() if capitalization_mask[i] else d
    for i, d in enumerate(queried_domains)
]

# DATA QUALITY ISSUE #1: Mixed timestamp formats
# Some rows use dashes, some use slashes — both are common in real exports
timestamps_dash   = pd.date_range("2024-01-01", periods=n // 2, freq="7h")
timestamps_slash  = pd.date_range("2024-03-01", periods=n - n // 2, freq="5h")

formatted_timestamps = (
    [ts.strftime("%Y-%m-%d %H:%M:%S") for ts in timestamps_dash] +
    [ts.strftime("%Y/%m/%d %H:%M:%S") for ts in timestamps_slash]
)

# Shuffle so the two timestamp formats are mixed throughout
shuffle_idx = np.random.permutation(n)
formatted_timestamps = [formatted_timestamps[i] for i in shuffle_idx]

# Response codes — NOERROR is most common in real DNS
response_codes = np.random.choice(
    ["NOERROR", "NXDOMAIN", "SERVFAIL", "REFUSED"],
    size=n,
    p=[0.75, 0.15, 0.06, 0.04]
)

# DATA QUALITY ISSUE #3: ~8% of response codes are missing (NaN)
missing_mask = np.random.random(n) < 0.08
response_codes = response_codes.astype(object)
response_codes[missing_mask] = np.nan

# Query types
query_types = np.random.choice(
    ["A", "AAAA", "MX", "TXT", "CNAME"],
    size=n,
    p=[0.65, 0.15, 0.08, 0.07, 0.05]
)

# Assemble the DNS log DataFrame
dns_log = pd.DataFrame({
    "timestamp":      formatted_timestamps,
    "client_ip":      np.random.choice(client_ips, size=n),
    "queried_domain": queried_domains,
    "response_code":  response_codes,
    "query_type":     query_types
})

# DATA QUALITY ISSUE #4: Add ~15 exact duplicate rows
duplicates = dns_log.sample(15, random_state=1)
dns_log = pd.concat([dns_log, duplicates], ignore_index=True)

# Shuffle the final DataFrame so duplicates aren't all at the end
dns_log = dns_log.sample(frac=1, random_state=99).reset_index(drop=True)

# -----------------------------------------------------------------
# Part B: Build the Threat Intelligence Feed (threat_feed)
# Small reference table — one row per known malicious domain
# -----------------------------------------------------------------

threat_feed = pd.DataFrame({
    "domain": [
        "badsite-c2.ru", "malware-drop.xyz", "phish-login.net",
        "ransomware-gate.io", "spyware-track.com", "botnet-cmd.top",
        "exfil-server.cc", "fake-update.biz"
    ],
    "threat_category": [
        "c2", "malware", "phishing",
        "ransomware", "spyware", "botnet",
        "exfiltration", "malware"
    ],
    # DATA QUALITY ISSUE #5: confidence_score is string for some rows
    "confidence_score": [
        0.95, "0.88", 0.76,          # <-- row 2 is a string, not float
        0.91, 0.65, "0.80", 0.72, 0.85
    ],
    "first_seen_date": [
        "2023-11-01", "2023-12-15", "2024-01-02",
        "2023-10-20", "2023-09-05", "2023-08-14",
        "2024-01-18", "2023-11-30"
    ]
})

# =============================================================
# INSPECTION — Run all 5 required commands on dns_log
# Add a comment after each one identifying the problem you see
# =============================================================

print("=" * 55)
print("DNS LOG — INSPECTION")
print("=" * 55)

print("\n--- .shape ---")
print(dns_log.shape)
# Tells us: total rows (should be 300+) and 5 columns

print("\n--- .dtypes ---")
print(dns_log.dtypes)
# PROBLEM SPOTTED: timestamp is 'object' (string), not datetime
# PROBLEM SPOTTED: response_code is 'object' — nulls prevent numeric type

print("\n--- .info() ---")
dns_log.info()
# PROBLEM SPOTTED: response_code has fewer non-null entries than other columns
# This is where the ~8% missing values show up clearly

print("\n--- .describe() ---")
print(dns_log.describe(include="all"))
# PROBLEM SPOTTED: queried_domain has mixed case (GOOGLE.COM vs google.com)
# visible in the 'top' row — some entries will appear as duplicates

print("\n--- .isnull().sum() ---")
print(dns_log.isnull().sum())
# PROBLEM SPOTTED: response_code has NaN values — exactly ~8% of rows

# -----------------------------------------------------------------
# Run the same 5 inspection commands on the threat feed
# -----------------------------------------------------------------

print("\n")
print("=" * 55)
print("THREAT FEED — INSPECTION")
print("=" * 55)

print("\n--- .shape ---")
print(threat_feed.shape)

print("\n--- .dtypes ---")
print(threat_feed.dtypes)
# PROBLEM SPOTTED: confidence_score is 'object' — should be float64
# Caused by the mixed string/float values we inserted

print("\n--- .info() ---")
threat_feed.info()

print("\n--- .describe() ---")
print(threat_feed.describe(include="all"))
# PROBLEM SPOTTED: confidence_score stats won't compute because it's object type

print("\n--- .isnull().sum() ---")
print(threat_feed.isnull().sum())
# Threat feed is clean for nulls — problems are type-based, not missing data

# ------------------------------------------------------------------------------------------------------------------------------------------------------

# =============================================================
# STAGE 2 — CLEAN
# Fix every data quality problem found during inspection
# Print row count before AND after — the difference matters
# =============================================================

print("=" * 55)
print("STAGE 2 — CLEAN")
print("=" * 55)

# Always record row count BEFORE you touch anything
rows_before = len(dns_log)
print(f"\nRow count BEFORE cleaning: {rows_before}")

# -----------------------------------------------------------------
# Fix #1 — Timestamp parsing (mixed formats)
# pd.to_datetime() is smart enough to handle both dash and slash
# formats automatically. errors='coerce' turns anything it can't
# parse into NaT (Not a Time) instead of crashing the whole script.
# -----------------------------------------------------------------

dns_log["timestamp"] = pd.to_datetime(dns_log["timestamp"], errors="coerce", format="mixed")

# Verify the fix
print("\n[Fix #1] Timestamp dtype after parsing:")
print(dns_log["timestamp"].dtype)
# Should now show: datetime64[ns]  — no longer 'object'

unparseable = dns_log["timestamp"].isnull().sum()
print(f"Timestamps that couldn't be parsed (NaT): {unparseable}")
# Should be 0 — both formats are handled cleanly

# -----------------------------------------------------------------
# Fix #2 — String normalization on queried_domain
# .str.lower() makes everything lowercase
# .str.strip() removes any accidental leading/trailing spaces
# THIS MUST HAPPEN BEFORE THE MERGE — if a domain is "BADSITE-C2.RU"
# in dns_log but "badsite-c2.ru" in threat_feed, the merge produces
# zero matches. Normalization makes them identical.
# -----------------------------------------------------------------

dns_log["queried_domain"] = dns_log["queried_domain"].str.lower().str.strip()

# Verify the fix — spot-check a few values
print("\n[Fix #2] Sample queried_domain values after normalization:")
print(dns_log["queried_domain"].sample(5, random_state=7).values)
# All entries should now be lowercase with no leading/trailing spaces

# -----------------------------------------------------------------
# Fix #3 — Null handling on response_code
# response_code is non-critical — a missing code doesn't mean the
# query didn't happen. We fill with "UNKNOWN" so we keep the row
# but don't pretend we know what the code was.
# Use .dropna() only on columns where a null means the row is useless.
# -----------------------------------------------------------------

dns_log["response_code"] = dns_log["response_code"].fillna("UNKNOWN")

# Verify the fix
print("\n[Fix #3] Null count in response_code after fillna:")
print(dns_log["response_code"].isnull().sum())
# Should now be 0

print("Value counts for response_code (including UNKNOWN):")
print(dns_log["response_code"].value_counts())
# You should see an UNKNOWN entry with ~25-27 rows

# -----------------------------------------------------------------
# Fix #4 — Deduplication
# We use subset= to define what "duplicate" means.
# Two rows are a duplicate if ALL FOUR of these columns match exactly.
# We keep the first occurrence and drop the rest.
# -----------------------------------------------------------------

dns_log = dns_log.drop_duplicates(
    subset=["timestamp", "client_ip", "queried_domain", "query_type"],
    keep="first"
)

rows_after = len(dns_log)
print(f"\n[Fix #4] Row count AFTER deduplication: {rows_after}")
print(f"Duplicate rows removed: {rows_before - rows_after}")
# Should show ~15 rows removed — the ones we intentionally added

# -----------------------------------------------------------------
# Fix #5 — Type conversion on threat_feed
# confidence_score has a mix of floats and strings like "0.88"
# pd.to_numeric() converts everything it can to a float.
# errors='coerce' turns anything that truly can't convert into NaN.
# -----------------------------------------------------------------

threat_feed["confidence_score"] = pd.to_numeric(
    threat_feed["confidence_score"], errors="coerce"
)

# Verify the fix
print("\n[Fix #5] threat_feed confidence_score dtype after conversion:")
print(threat_feed["confidence_score"].dtype)
# Should now show: float64

print("\nthreat_feed after cleaning:")
print(threat_feed)
# All confidence_score values should now be proper floats

# -----------------------------------------------------------------
# FINAL SUMMARY — Print before vs after clearly
# The assignment specifically says: "the difference matters"
# -----------------------------------------------------------------

print("\n" + "=" * 55)
print("CLEANING SUMMARY")
print("=" * 55)
print(f"  Rows before cleaning : {rows_before}")
print(f"  Rows after cleaning  : {rows_after}")
print(f"  Rows removed         : {rows_before - rows_after}")
print(f"\n  dns_log dtypes after cleaning:")
print(dns_log.dtypes)
print(f"\n  Remaining nulls in dns_log:")
print(dns_log.isnull().sum())

# ----------------------------------------------------------------------------------------------------------------------------------------------------------

# =============================================================
# STAGE 3 — ANALYZE
# Answer all 3 assignment questions using GroupBy and .agg()
# A temporary merge is performed here to enable enriched analysis
# =============================================================

print("=" * 55)
print("STAGE 3 — ANALYZE")
print("=" * 55)

# -----------------------------------------------------------------
# Temporary merge — needed so threat columns are available
# Left join keeps ALL dns_log rows.
# Rows with no threat match get NaN in threat columns.
# We'll do this properly again in Stage 5 with alerting logic.
# -----------------------------------------------------------------

dns_enriched = dns_log.merge(
    threat_feed,
    left_on="queried_domain",
    right_on="domain",
    how="left"
)

# Isolate only the rows that matched a threat domain
# (i.e. threat_category is NOT NaN)
malicious_hits = dns_enriched[dns_enriched["threat_category"].notna()].copy()

print(f"\nTotal DNS log rows       : {len(dns_enriched)}")
print(f"Rows matching threat feed: {len(malicious_hits)}")
print(f"Rows with clean domains  : {len(dns_enriched) - len(malicious_hits)}")

# -----------------------------------------------------------------
# Question 1 — How many unique internal hosts queried a
#              domain on the threat intel list?
#
# Why this matters: each unique client_ip is a potentially
# infected or compromised machine that needs investigation.
# -----------------------------------------------------------------

print("\n" + "-" * 55)
print("Q1: Unique internal hosts that queried a threat domain")
print("-" * 55)

unique_host_count = malicious_hits["client_ip"].nunique()
print(f"\nTotal unique internal hosts that hit a threat domain: {unique_host_count}")

# Break it down — show WHICH hosts, and how many queries each made
hosts_breakdown = (
    malicious_hits
    .groupby("client_ip")
    .agg(
        total_threat_queries=("queried_domain", "count"),
        unique_threat_domains=("queried_domain", "nunique")
    )
    .sort_values("total_threat_queries", ascending=False)
    .reset_index()
)

print("\nBreakdown by host:")
print(hosts_breakdown.to_string(index=False))
# Each row = one internal machine
# total_threat_queries = how many times it queried a bad domain
# unique_threat_domains = how many *different* bad domains it reached

# -----------------------------------------------------------------
# Question 2 — What threat categories are most represented
#              in the matched DNS queries?
#
# Named aggregation required by assignment (.agg with labels)
# This tells us WHAT KIND of threat is most active in our network
# -----------------------------------------------------------------

print("\n" + "-" * 55)
print("Q2: Threat categories most represented in matched queries")
print("-" * 55)

category_summary = (
    malicious_hits
    .groupby("threat_category")
    .agg(
        query_count=("queried_domain", "count"),
        unique_hosts_affected=("client_ip", "nunique"),
        avg_confidence=("confidence_score", "mean")
    )
    .sort_values("query_count", ascending=False)
    .reset_index()
)

# Round avg_confidence for clean display
category_summary["avg_confidence"] = category_summary["avg_confidence"].round(2)

print("\nThreat category breakdown:")
print(category_summary.to_string(index=False))
# query_count          = total DNS queries to domains in this category
# unique_hosts_affected = how many internal machines touched this category
# avg_confidence       = average reliability of the intel for this category

# -----------------------------------------------------------------
# Question 3 — Which internal IPs had the highest volume of
#              queries to malicious domains?
#
# Derived metric required: query_share (% of all malicious queries)
# Multi-column groupby: group by both client_ip AND threat_category
# -----------------------------------------------------------------

print("\n" + "-" * 55)
print("Q3: Internal IPs with highest malicious query volume")
print("-" * 55)

# Part A — Top IPs by raw volume with derived metric
total_malicious_queries = len(malicious_hits)

ip_volume = (
    malicious_hits
    .groupby("client_ip")
    .agg(
        malicious_query_count=("queried_domain", "count"),
        unique_domains_hit=("queried_domain", "nunique"),
        categories_seen=("threat_category", "nunique")
    )
    .reset_index()
)

# Derived metric: what share of ALL malicious queries came from this IP?
ip_volume["query_share_pct"] = (
    (ip_volume["malicious_query_count"] / total_malicious_queries * 100)
    .round(1)
)

ip_volume = ip_volume.sort_values("malicious_query_count", ascending=False)

print("\nTop internal IPs by malicious query volume:")
print(ip_volume.to_string(index=False))

# Part B — Multi-column groupby: which IPs queried which categories?
# This is the richer picture — shows behaviour patterns per host
print("\nIP + Threat category breakdown (multi-column groupby):")

ip_category = (
    malicious_hits
    .groupby(["client_ip", "threat_category"])
    .agg(
        query_count=("queried_domain", "count")
    )
    .sort_values(["client_ip", "query_count"], ascending=[True, False])
    .reset_index()
)

print(ip_category.to_string(index=False))
# Each row = one IP + one threat category combination
# Helps identify: is this host hitting one category or many?

# -----------------------------------------------------------------
# STAGE 3 SUMMARY
# -----------------------------------------------------------------

print("\n" + "=" * 55)
print("ANALYSIS SUMMARY")
print("=" * 55)
print(f"  Unique infected hosts found      : {unique_host_count}")
print(f"  Total malicious DNS queries      : {total_malicious_queries}")
print(f"  Threat categories observed       : {malicious_hits['threat_category'].nunique()}")
top_category = category_summary.iloc[0]["threat_category"]
top_ip = ip_volume.iloc[0]["client_ip"]
print(f"  Most active threat category      : {top_category}")
print(f"  Highest-risk internal IP         : {top_ip}")

# -------------------------------------------------------------------------------------------------------------------------------------------------------------

# =============================================================
# STAGE 4 — VISUALIZE
# 3 charts: category breakdown, time-of-day pattern, top IPs
# All charts have: title, labeled axes, legend where applicable
# =============================================================

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

print("=" * 55)
print("STAGE 4 — VISUALIZE")
print("=" * 55)

# -----------------------------------------------------------------
# Prep — extract hour from timestamp for time-based chart
# This only works because Stage 2 parsed timestamp to datetime64
# If timestamp were still a string, .dt.hour would crash here
# -----------------------------------------------------------------

dns_enriched["hour"] = dns_enriched["timestamp"].dt.hour
malicious_hits["hour"] = malicious_hits["timestamp"].dt.hour

# Use a clean, readable style
plt.style.use("seaborn-v0_8-whitegrid")

# -----------------------------------------------------------------
# Chart 1 — Malicious query count by threat category
# Shows WHAT types of threats are hitting our network most
# -----------------------------------------------------------------

fig1, ax1 = plt.subplots(figsize=(9, 5))

chart1_data = (
    malicious_hits
    .groupby("threat_category")["queried_domain"]
    .count()
    .sort_values(ascending=False)
)

bars = ax1.bar(
    chart1_data.index,
    chart1_data.values,
    color="#4a6fa5",
    edgecolor="white",
    linewidth=0.8
)

# Add value labels on top of each bar
for bar in bars:
    height = bar.get_height()
    ax1.text(
        bar.get_x() + bar.get_width() / 2,
        height + 0.3,
        str(int(height)),
        ha="center", va="bottom",
        fontsize=10, fontweight="bold"
    )

ax1.set_title("Malicious DNS Queries by Threat Category", fontsize=14, fontweight="bold", pad=14)
ax1.set_xlabel("Threat Category", fontsize=11)
ax1.set_ylabel("Number of DNS Queries", fontsize=11)
ax1.tick_params(axis="x", rotation=25)
ax1.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

plt.tight_layout()
plt.savefig("chart1_threat_categories.png", dpi=150, bbox_inches="tight")
plt.show()
print("\n[Chart 1 saved] chart1_threat_categories.png")

# -----------------------------------------------------------------
# Chart 2 — Malicious queries by hour of day (time-based)
# Required: at least one chart must show a time-based pattern
# Shows WHEN infected hosts are most active — useful for SOC shifts
# We plot all DNS traffic vs malicious-only to show the contrast
# -----------------------------------------------------------------

fig2, ax2 = plt.subplots(figsize=(11, 5))

# Count queries per hour for all traffic vs malicious only
all_by_hour = (
    dns_enriched
    .groupby("hour")["queried_domain"]
    .count()
    .reindex(range(24), fill_value=0)
)

malicious_by_hour = (
    malicious_hits
    .groupby("hour")["queried_domain"]
    .count()
    .reindex(range(24), fill_value=0)
)

hours = range(24)

ax2.plot(
    hours, all_by_hour.values,
    marker="o", linewidth=2, markersize=5,
    color="#4a6fa5", label="All DNS queries"
)

ax2.plot(
    hours, malicious_by_hour.values,
    marker="o", linewidth=2, markersize=5,
    color="#c0392b", label="Malicious domain queries",
    linestyle="--"
)

ax2.set_title("DNS Query Volume by Hour of Day — All Traffic vs Malicious", fontsize=14, fontweight="bold", pad=14)
ax2.set_xlabel("Hour of Day (24hr)", fontsize=11)
ax2.set_ylabel("Number of DNS Queries", fontsize=11)
ax2.set_xticks(range(24))
ax2.set_xticklabels([f"{h:02d}:00" for h in range(24)], rotation=45, fontsize=8)
ax2.legend(fontsize=10)
ax2.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

plt.tight_layout()
plt.savefig("chart2_hourly_pattern.png", dpi=150, bbox_inches="tight")
plt.show()
print("[Chart 2 saved] chart2_hourly_pattern.png")

# -----------------------------------------------------------------
# Chart 3 — Top internal IPs by malicious query volume (bonus)
# Shows WHO is most at risk — the merge finding made visual
# Horizontal bar is easier to read when x-axis labels are IPs
# -----------------------------------------------------------------

fig3, ax3 = plt.subplots(figsize=(9, 5))

chart3_data = (
    malicious_hits
    .groupby("client_ip")["queried_domain"]
    .count()
    .sort_values(ascending=True)   # ascending=True so highest is at top
)

colors = ["#c0392b" if v == chart3_data.max() else "#4a6fa5"
          for v in chart3_data.values]

bars3 = ax3.barh(
    chart3_data.index,
    chart3_data.values,
    color=colors,
    edgecolor="white",
    linewidth=0.8
)

# Value labels at end of each bar
for bar in bars3:
    width = bar.get_width()
    ax3.text(
        width + 0.2,
        bar.get_y() + bar.get_height() / 2,
        str(int(width)),
        ha="left", va="center",
        fontsize=10, fontweight="bold"
    )

ax3.set_title("Internal IPs Ranked by Malicious Domain Query Volume", fontsize=14, fontweight="bold", pad=14)
ax3.set_xlabel("Number of Queries to Malicious Domains", fontsize=11)
ax3.set_ylabel("Internal IP Address", fontsize=11)

# Add a legend explaining the red bar
from matplotlib.patches import Patch
legend_elements = [
    Patch(facecolor="#c0392b", label="Highest risk host"),
    Patch(facecolor="#4a6fa5", label="Other internal hosts")
]
ax3.legend(handles=legend_elements, fontsize=10)

plt.tight_layout()
plt.savefig("chart3_top_ips.png", dpi=150, bbox_inches="tight")
plt.show()
print("[Chart 3 saved] chart3_top_ips.png")

print("\n[Stage 4 complete] 3 charts produced and saved.")

# -----------------------------------------------------------------------------------------------------------------------------------------------------------------------

# =============================================================
# STAGE 5 — ACT AND ENRICH
# Two components:
#   A) The official pd.merge() enrichment
#   B) Statistical alerting check (IQR-based anomaly flagging)
# =============================================================

print("=" * 55)
print("STAGE 5 — ACT AND ENRICH")
print("=" * 55)

# -----------------------------------------------------------------
# COMPONENT A — THE MERGE
# This is the official required merge for the assignment.
# Show what you could answer BEFORE vs AFTER to prove it adds value.
# -----------------------------------------------------------------

print("\n--- BEFORE THE MERGE ---")
print("Questions we CANNOT answer with dns_log alone:")
print("  - Is this domain malicious or safe?")
print("  - What type of threat does it represent?")
print("  - How confident is the intel on this domain?")
print(f"\ndns_log columns: {list(dns_log.columns)}")

# The real merge — left join keeps all DNS rows
dns_final = dns_log.merge(
    threat_feed,
    left_on="queried_domain",
    right_on="domain",
    how="left"
)

print("\n--- AFTER THE MERGE ---")
print("Questions we CAN NOW answer:")
print("  - Which queries hit known malicious domains?")
print("  - What threat category is each hit classified as?")
print("  - Which domains have high vs low confidence intel?")
print(f"\ndns_final columns: {list(dns_final.columns)}")

# Prove the merge worked — show matched vs unmatched rows
matched   = dns_final["threat_category"].notna().sum()
unmatched = dns_final["threat_category"].isna().sum()

print(f"\nMerge results:")
print(f"  Total rows after merge        : {len(dns_final)}")
print(f"  Rows matched to threat feed   : {matched}  (malicious domain queries)")
print(f"  Rows NOT matched              : {unmatched}  (clean/unknown domains)")
print(f"  Row count unchanged from dns_log: {len(dns_final) == len(dns_log)}")
# This last line should print True — left join never drops rows

# Preview the enriched data — show a few matched rows
print("\nSample enriched rows (malicious hits only):")
sample_cols = ["timestamp", "client_ip", "queried_domain",
               "threat_category", "confidence_score"]
print(
    dns_final[dns_final["threat_category"].notna()][sample_cols]
    .head(8)
    .to_string(index=False)
)

# -----------------------------------------------------------------
# COMPONENT B — STATISTICAL ALERTING CHECK
# Method: IQR (Interquartile Range)
# IQR flags values that are unusually high compared to the
# distribution of the data — more robust than z-score for
# small datasets because it isn't skewed by extreme outliers.
#
# How IQR works:
#   Q1 = 25th percentile, Q3 = 75th percentile
#   IQR = Q3 - Q1  (the middle 50% spread)
#   Upper fence = Q3 + 1.5 * IQR
#   Any value above the fence = statistical anomaly
# -----------------------------------------------------------------

print("\n" + "=" * 55)
print("STATISTICAL ALERTING — IQR ANOMALY DETECTION")
print("=" * 55)

# Count malicious queries per internal IP
ip_query_counts = (
    dns_final[dns_final["threat_category"].notna()]
    .groupby("client_ip")["queried_domain"]
    .count()
    .reset_index()
    .rename(columns={"queried_domain": "malicious_query_count"})
)

print("\nMalicious query counts per internal IP:")
print(ip_query_counts.to_string(index=False))

# Calculate IQR thresholds
Q1  = ip_query_counts["malicious_query_count"].quantile(0.25)
Q3  = ip_query_counts["malicious_query_count"].quantile(0.75)
IQR = Q3 - Q1
upper_fence = Q3 + 1.5 * IQR

print(f"\nIQR calculation:")
print(f"  Q1  (25th percentile) : {Q1:.2f}")
print(f"  Q3  (75th percentile) : {Q3:.2f}")
print(f"  IQR (Q3 - Q1)         : {IQR:.2f}")
print(f"  Upper fence (Q3 + 1.5*IQR): {upper_fence:.2f}")
print(f"  Any IP above {upper_fence:.1f} queries is flagged as anomalous")

# Apply the alert flag
ip_query_counts["alert_flag"] = (
    ip_query_counts["malicious_query_count"] > upper_fence
)

# Pull out the flagged IPs
flagged_ips = ip_query_counts[ip_query_counts["alert_flag"] == True]

print(f"\nFlagged IPs (anomalously high malicious query volume):")
if len(flagged_ips) > 0:
    print(flagged_ips.to_string(index=False))
else:
    print("  No IPs exceeded the IQR threshold.")
    print("  This is valid — it means query volume is evenly distributed.")
    print("  Lower the multiplier to 1.0 to make the threshold stricter.")

# -----------------------------------------------------------------
# Build a final alert report — merge the flag back into dns_final
# so each DNS row knows whether its source IP is flagged
# -----------------------------------------------------------------

dns_final = dns_final.merge(
    ip_query_counts[["client_ip", "alert_flag"]],
    on="client_ip",
    how="left"
)

dns_final["alert_flag"] = dns_final["alert_flag"].fillna(False)

print("\nAlert flag distribution across all DNS rows:")
print(dns_final["alert_flag"].value_counts())

# -----------------------------------------------------------------
# FINAL PIPELINE SUMMARY
# Print a clean end-to-end summary of every stage
# -----------------------------------------------------------------

print("\n" + "=" * 55)
print("FULL PIPELINE SUMMARY")
print("=" * 55)
print(f"  [Stage 1] Raw rows loaded            : {rows_before}")
print(f"  [Stage 2] Rows after cleaning        : {rows_after}")
print(f"  [Stage 2] Duplicates removed         : {rows_before - rows_after}")
print(f"  [Stage 5] Rows after merge           : {len(dns_final)}")
print(f"  [Stage 5] Malicious query hits       : {matched}")
print(f"  [Stage 5] Clean/unknown queries      : {unmatched}")
print(f"  [Stage 5] IQR upper fence            : {upper_fence:.2f}")
print(f"  [Stage 5] IPs flagged as anomalous   : {len(flagged_ips)}")
print(f"\nPipeline complete. dns_final is your enriched, analysis-ready DataFrame.")