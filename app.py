import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import requests
import io
import os
from datetime import datetime, timedelta
import random

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="RetainIQ",
    page_icon="🔁",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# CUSTOM CSS  — clean, professional, startup feel
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=DM+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: #0f0f0f;
}
[data-testid="stSidebar"] * {
    color: #e5e5e5 !important;
}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stFileUploader label {
    color: #999 !important;
    font-size: 12px !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

/* Metric cards */
[data-testid="metric-container"] {
    background: #f8f8f6;
    border: 1px solid #e8e8e4;
    border-radius: 12px;
    padding: 1rem;
}

/* Tab styling */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: #f8f8f6;
    border-radius: 10px;
    padding: 4px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    color: #666;
}
.stTabs [aria-selected="true"] {
    background: #fff !important;
    color: #0f0f0f !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

/* Buttons */
.stButton > button {
    background: #0f0f0f;
    color: #fff;
    border: none;
    border-radius: 8px;
    font-family: 'DM Sans', sans-serif;
    font-weight: 500;
    padding: 0.5rem 1.25rem;
    transition: opacity 0.15s;
}
.stButton > button:hover {
    background: #333;
    color: #fff;
    border: none;
}

/* Status badges via markdown */
.badge-active   { background:#dcfce7; color:#166534; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:600; }
.badge-atrisk   { background:#fef9c3; color:#854d0e; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:600; }
.badge-churned  { background:#fee2e2; color:#991b1b; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:600; }

/* Code blocks in SQL tab */
code { font-family: 'DM Mono', monospace; font-size: 13px; }

/* Divider */
hr { border-color: #e8e8e4; }

/* Hide streamlit branding */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────
DB = "retainiq.db"

def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db():
    with get_conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, email TEXT, brand TEXT, segment TEXT,
            total_revenue REAL, orders INTEGER,
            last_purchase_date TEXT, status TEXT,
            churn_risk TEXT, days_inactive INTEGER,
            uploaded_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_name TEXT, brand TEXT, channel TEXT,
            spend REAL, revenue_generated REAL,
            customers_reached INTEGER, repeat_purchases INTEGER,
            launch_date TEXT, created_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS upload_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT, rows INTEGER, uploaded_at TEXT
        )""")

# ─────────────────────────────────────────────
# CHURN LOGIC
# Mirrors what Xeno actually does for retailers
# ─────────────────────────────────────────────
def compute_churn_risk(days_inactive, orders):
    """
    Rules:
    - Active    : inactive < 30 days
    - At Risk   : 30–90 days inactive OR only 1 order ever
    - Churned   : inactive > 90 days
    """
    if days_inactive > 90:
        return "Churned"
    elif days_inactive > 30 or orders <= 1:
        return "At Risk"
    else:
        return "Active"

def process_upload(df: pd.DataFrame, filename: str):
    """Normalize columns, compute churn risk, save to SQLite."""
    # Flexible column mapping — handles messy real-world headers
    rename = {}
    mapping = {
        "name": ["name","customer","customer name","client"],
        "email": ["email","email address","mail"],
        "brand": ["brand","brand name","retailer","store"],
        "segment": ["segment","tier","category","type"],
        "total_revenue": ["total_revenue","revenue","ltv","spend","total spend","total_spend"],
        "orders": ["orders","order count","purchases","num_orders","num orders"],
        "last_purchase_date": ["last_purchase_date","last purchase","last_purchase","last order","last_order_date"],
    }
    for std, variants in mapping.items():
        for col in df.columns:
            if col.lower().strip().replace(" ","_") in [v.replace(" ","_") for v in variants]:
                rename[col] = std
                break
    df = df.rename(columns=rename)

    # Fill missing columns with sensible defaults
    today = datetime.today()
    for col in ["name","email","brand","segment","last_purchase_date"]:
        if col not in df.columns:
            df[col] = "Unknown"
    for col in ["total_revenue","orders"]:
        if col not in df.columns:
            df[col] = 0

    # Compute days inactive
    def days_since(d):
        try:
            return (today - pd.to_datetime(d)).days
        except:
            return random.randint(10, 120)

    df["days_inactive"] = df["last_purchase_date"].apply(days_since)
    df["total_revenue"]  = pd.to_numeric(df["total_revenue"], errors="coerce").fillna(0)
    df["orders"]         = pd.to_numeric(df["orders"],        errors="coerce").fillna(1).astype(int)
    df["churn_risk"]     = df.apply(lambda r: compute_churn_risk(r["days_inactive"], r["orders"]), axis=1)
    df["status"]         = df["churn_risk"]   # alias
    df["uploaded_at"]    = today.isoformat()

    cols = ["name","email","brand","segment","total_revenue","orders",
            "last_purchase_date","status","churn_risk","days_inactive","uploaded_at"]
    df = df[[c for c in cols if c in df.columns]]

    with get_conn() as conn:
        conn.execute("DELETE FROM customers")
        df.to_sql("customers", conn, if_exists="append", index=False)
        conn.execute("INSERT INTO upload_log(filename,rows,uploaded_at) VALUES(?,?,?)",
                     (filename, len(df), today.isoformat()))
    return len(df)

def load_customers() -> pd.DataFrame:
    with get_conn() as c:
        try:
            df = pd.read_sql("SELECT * FROM customers", c)
            df["total_revenue"] = pd.to_numeric(df["total_revenue"], errors="coerce").fillna(0)
            df["orders"]        = pd.to_numeric(df["orders"],        errors="coerce").fillna(0)
            df["days_inactive"] = pd.to_numeric(df["days_inactive"], errors="coerce").fillna(0)
            return df
        except:
            return pd.DataFrame()

def load_campaigns() -> pd.DataFrame:
    with get_conn() as c:
        try:
            df = pd.read_sql("SELECT * FROM campaigns ORDER BY id DESC", c)
            for col in ["spend","revenue_generated","customers_reached","repeat_purchases"]:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
            return df
        except:
            return pd.DataFrame()

# ─────────────────────────────────────────────
# SAMPLE DATA — Xeno-flavoured brands
# ─────────────────────────────────────────────
def generate_sample_excel() -> bytes:
    random.seed(7)
    brands   = ["Tommy Hilfiger","Calvin Klein","Jack & Jones","Levi's","Taco Bell","Barbeque Nation"]
    segments = ["VIP","Regular","Occasional","New"]
    today    = datetime.today()

    rows = []
    for i in range(120):
        days_ago = random.choice(
            [random.randint(1,25), random.randint(31,85), random.randint(91,200)]
        )
        last_purchase = (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        orders = random.randint(1, 30)
        rows.append({
            "Name":               f"Customer {i+1:03d}",
            "Email":              f"customer{i+1}@example.com",
            "Brand":              random.choice(brands),
            "Segment":            random.choice(segments),
            "Total Revenue":      round(random.uniform(500, 80000), 2),
            "Orders":             orders,
            "Last Purchase Date": last_purchase,
        })

    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return buf.read()

def generate_sample_campaigns() -> list:
    """Pre-load some campaigns so the tab isn't empty."""
    random.seed(42)
    brands    = ["Tommy Hilfiger","Calvin Klein","Jack & Jones","Levi's","Taco Bell"]
    channels  = ["WhatsApp","Email","SMS","Push Notification","Instagram DM"]
    campaigns = []
    names     = ["Summer Re-engagement","Win-back 90D","VIP Loyalty Blast",
                 "New Collection Drop","Festive Bonanza","Flash Sale 24H",
                 "Birthday Personalised","Lapsed Customer Nudge"]
    for i, name in enumerate(names):
        spend    = round(random.uniform(5000, 50000), 2)
        revenue  = round(spend * random.uniform(1.5, 6.0), 2)
        reached  = random.randint(500, 10000)
        repeats  = random.randint(int(reached * 0.05), int(reached * 0.35))
        days_ago = random.randint(5, 180)
        campaigns.append((
            name,
            random.choice(brands),
            random.choice(channels),
            spend, revenue, reached, repeats,
            (datetime.today() - timedelta(days=days_ago)).strftime("%Y-%m-%d"),
            datetime.now().isoformat()
        ))
    return campaigns

def seed_campaigns_if_empty():
    with get_conn() as c:
        count = c.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
        if count == 0:
            c.executemany("""INSERT INTO campaigns
                (campaign_name,brand,channel,spend,revenue_generated,
                 customers_reached,repeat_purchases,launch_date,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""", generate_sample_campaigns())

# ─────────────────────────────────────────────
# EXCHANGE RATE API
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600)
def fetch_rates(base="INR"):
    try:
        r = requests.get(f"https://open.er-api.com/v6/latest/{base}", timeout=6)
        if r.status_code == 200:
            d = r.json()
            return d.get("rates", {}), d.get("time_last_update_utc", "")
    except:
        pass
    return {}, ""

# ─────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────
init_db()
seed_campaigns_if_empty()

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔁 RetainIQ")
    st.markdown("<p style='color:#666;font-size:13px;margin-top:-12px;'>Customer Retention Intelligence</p>", unsafe_allow_html=True)
    st.divider()

    st.markdown("<p style='color:#999;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;'>Upload Customer Data</p>", unsafe_allow_html=True)
    uploaded = st.file_uploader("Excel or CSV", type=["xlsx","xls","csv"], label_visibility="collapsed")

    if uploaded:
        try:
            if uploaded.name.endswith(".csv"):
                df_raw = pd.read_csv(uploaded)
            else:
                df_raw = pd.read_excel(uploaded, engine="openpyxl")
            n = process_upload(df_raw, uploaded.name)
            st.success(f"✅ {n} customers loaded")
        except Exception as e:
            st.error(f"Upload error: {e}")

    st.divider()

    # Download sample
    sample_bytes = generate_sample_excel()
    st.download_button(
        "⬇️ Download sample Excel",
        sample_bytes,
        file_name="sample_customers_retainiq.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

    st.divider()
    st.markdown("<p style='color:#555;font-size:11px;'>Retail Customer Intelligence</p>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────
df       = load_customers()
df_camps = load_campaigns()
has_data = not df.empty

# ─────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📊  Churn Dashboard",
    "📣  Campaign ROI",
    "🗄️  SQL Console",
    "💱  Revenue Converter",
])

# ════════════════════════════════════════════
# TAB 1 — CHURN DASHBOARD
# ════════════════════════════════════════════
with tab1:
    st.markdown("### Customer Churn Risk Dashboard")
    st.caption("Upload your customer Excel file (sidebar) to analyse churn risk across brands and segments.")

    if not has_data:
        st.info("👈 No data yet. Download the sample Excel from the sidebar, then upload it to see the dashboard.")
        st.stop()

    # ── KPI ROW ──
    total      = len(df)
    active_n   = len(df[df["churn_risk"] == "Active"])
    atrisk_n   = len(df[df["churn_risk"] == "At Risk"])
    churned_n  = len(df[df["churn_risk"] == "Churned"])
    total_rev  = df["total_revenue"].sum()
    at_risk_rev = df[df["churn_risk"].isin(["At Risk","Churned"])]["total_revenue"].sum()
    repeat_rate = round((df[df["orders"] > 1].shape[0] / total) * 100, 1) if total else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Customers",    f"{total:,}")
    c2.metric("🟢 Active",          f"{active_n:,}",   f"{round(active_n/total*100)}%")
    c3.metric("🟡 At Risk",         f"{atrisk_n:,}",   f"{round(atrisk_n/total*100)}%")
    c4.metric("🔴 Churned",         f"{churned_n:,}",  f"{round(churned_n/total*100)}%")
    c5.metric("💰 Total LTV",       f"₹{total_rev:,.0f}")
    c6.metric("🔁 Repeat Rate",     f"{repeat_rate}%")

    st.divider()

    # ── CHURN RISK ALERT BOX ──
    rev_at_risk_pct = round(at_risk_rev / total_rev * 100, 1) if total_rev else 0
    st.warning(f"⚠️  **₹{at_risk_rev:,.0f}** ({rev_at_risk_pct}% of total LTV) is at risk from At Risk + Churned customers. "
               f"Re-engagement campaigns could recover this revenue.")

    st.divider()

    # ── CHARTS ROW 1 ──
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**Churn Risk Breakdown**")
        risk_counts = df["churn_risk"].value_counts().reset_index()
        risk_counts.columns = ["Status","Customers"]
        color_map = {"Active":"#22c55e","At Risk":"#f59e0b","Churned":"#ef4444"}
        fig = px.pie(risk_counts, names="Status", values="Customers",
                     color="Status", color_discrete_map=color_map, hole=0.55)
        fig.update_layout(margin=dict(l=0,r=0,t=10,b=0), height=280,
                          legend=dict(orientation="h", y=-0.1),
                          font_family="DM Sans")
        fig.update_traces(textposition="outside", textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.markdown("**Revenue by Churn Segment**")
        rev_by_risk = df.groupby("churn_risk")["total_revenue"].sum().reset_index()
        rev_by_risk.columns = ["Status","Revenue"]
        fig2 = px.bar(rev_by_risk, x="Status", y="Revenue",
                      color="Status", color_discrete_map=color_map,
                      text_auto=".2s")
        fig2.update_layout(showlegend=False, height=280,
                           margin=dict(l=0,r=0,t=10,b=0),
                           yaxis_title="Revenue (₹)", font_family="DM Sans")
        st.plotly_chart(fig2, use_container_width=True)

    # ── CHARTS ROW 2 ──
    col_c, col_d = st.columns(2)

    with col_c:
        st.markdown("**Churn Risk by Brand**")
        if "brand" in df.columns:
            brand_risk = df.groupby(["brand","churn_risk"]).size().reset_index(name="count")
            fig3 = px.bar(brand_risk, x="brand", y="count", color="churn_risk",
                          color_discrete_map=color_map, barmode="stack")
            fig3.update_layout(height=300, margin=dict(l=0,r=0,t=10,b=0),
                               xaxis_title="", yaxis_title="Customers",
                               legend_title="", font_family="DM Sans")
            st.plotly_chart(fig3, use_container_width=True)

    with col_d:
        st.markdown("**Days Inactive Distribution**")
        fig4 = px.histogram(df, x="days_inactive", color="churn_risk",
                            color_discrete_map=color_map, nbins=30, opacity=0.85)
        fig4.add_vline(x=30,  line_dash="dash", line_color="#f59e0b",
                       annotation_text="At Risk threshold (30d)")
        fig4.add_vline(x=90,  line_dash="dash", line_color="#ef4444",
                       annotation_text="Churned threshold (90d)")
        fig4.update_layout(height=300, margin=dict(l=0,r=0,t=10,b=0),
                           xaxis_title="Days since last purchase",
                           legend_title="", font_family="DM Sans")
        st.plotly_chart(fig4, use_container_width=True)

    st.divider()

    # ── AT RISK TABLE ──
    st.markdown("**🚨 At Risk Customers — Prioritise for Re-engagement**")
    at_risk_df = df[df["churn_risk"] == "At Risk"].sort_values("total_revenue", ascending=False)
    if not at_risk_df.empty:
        display_cols = [c for c in ["name","email","brand","segment","total_revenue","orders","days_inactive"] if c in at_risk_df.columns]
        st.dataframe(
            at_risk_df[display_cols].rename(columns={
                "name":"Customer","email":"Email","brand":"Brand",
                "segment":"Segment","total_revenue":"LTV (₹)",
                "orders":"Orders","days_inactive":"Days Inactive"
            }).reset_index(drop=True),
            use_container_width=True, height=320
        )
        csv = at_risk_df.to_csv(index=False).encode()
        st.download_button("⬇️ Export At-Risk List", csv,
                           file_name="at_risk_customers.csv", mime="text/csv")
    else:
        st.success("No at-risk customers right now!")

# ════════════════════════════════════════════
# TAB 2 — CAMPAIGN ROI
# ════════════════════════════════════════════
with tab2:
    st.markdown("### Campaign ROI Tracker")
    st.caption("Track which campaigns drove repeat purchases across your brand portfolio.")

    # ── ADD CAMPAIGN FORM ──
    with st.expander("➕ Add New Campaign", expanded=False):
        f1, f2, f3 = st.columns(3)
        camp_name  = f1.text_input("Campaign Name", placeholder="e.g. Summer Re-engagement")
        camp_brand = f2.selectbox("Brand", ["Tommy Hilfiger","Calvin Klein","Jack & Jones","Levi's","Taco Bell","Barbeque Nation","Other"])
        camp_chan  = f3.selectbox("Channel", ["WhatsApp","Email","SMS","Push Notification","Instagram DM","Other"])

        f4, f5, f6, f7 = st.columns(4)
        camp_spend   = f4.number_input("Spend (₹)", min_value=0.0, value=10000.0, step=500.0)
        camp_rev     = f5.number_input("Revenue Generated (₹)", min_value=0.0, value=35000.0, step=1000.0)
        camp_reached = f6.number_input("Customers Reached", min_value=0, value=1000, step=100)
        camp_repeat  = f7.number_input("Repeat Purchases", min_value=0, value=150, step=10)
        camp_date    = st.date_input("Launch Date", value=datetime.today())

        if st.button("Save Campaign"):
            if camp_name.strip():
                with get_conn() as conn:
                    conn.execute("""INSERT INTO campaigns
                        (campaign_name,brand,channel,spend,revenue_generated,
                         customers_reached,repeat_purchases,launch_date,created_at)
                        VALUES(?,?,?,?,?,?,?,?,?)""",
                        (camp_name, camp_brand, camp_chan, camp_spend, camp_rev,
                         camp_reached, camp_repeat, str(camp_date), datetime.now().isoformat()))
                st.success(f"✅ Campaign '{camp_name}' saved!")
                st.rerun()
            else:
                st.warning("Please enter a campaign name.")

    df_camps = load_campaigns()

    if df_camps.empty:
        st.info("No campaigns yet. Add one above.")
    else:
        # ── KPIs ──
        total_spend   = df_camps["spend"].sum()
        total_rev_c   = df_camps["revenue_generated"].sum()
        total_roi     = round((total_rev_c - total_spend) / total_spend * 100, 1) if total_spend else 0
        avg_repeat    = round(df_camps["repeat_purchases"].sum() / df_camps["customers_reached"].sum() * 100, 1) if df_camps["customers_reached"].sum() else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Campaigns",    len(df_camps))
        k2.metric("Total Spend",        f"₹{total_spend:,.0f}")
        k3.metric("Total Revenue",      f"₹{total_rev_c:,.0f}")
        k4.metric("Overall ROI",        f"{total_roi}%",
                  delta=f"{'Profitable' if total_roi > 0 else 'Loss'}")

        st.divider()

        # ── ROI TABLE ──
        df_camps["ROI %"] = ((df_camps["revenue_generated"] - df_camps["spend"]) / df_camps["spend"] * 100).round(1)
        df_camps["Repeat Rate %"] = (df_camps["repeat_purchases"] / df_camps["customers_reached"] * 100).round(1)

        st.markdown("**Campaign Performance Table**")
        disp = df_camps[["campaign_name","brand","channel","spend","revenue_generated",
                          "ROI %","customers_reached","repeat_purchases","Repeat Rate %","launch_date"]].copy()
        disp.columns = ["Campaign","Brand","Channel","Spend (₹)","Revenue (₹)",
                        "ROI %","Reached","Repeat Buys","Repeat Rate %","Launch Date"]
        st.dataframe(disp.reset_index(drop=True), use_container_width=True, height=320)

        st.divider()

        # ── CHARTS ──
        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("**ROI % by Campaign**")
            fig_roi = px.bar(df_camps.sort_values("ROI %", ascending=True),
                             x="ROI %", y="campaign_name", orientation="h",
                             color="ROI %", color_continuous_scale=["#ef4444","#f59e0b","#22c55e"],
                             text_auto=".1f")
            fig_roi.update_layout(height=360, margin=dict(l=0,r=0,t=10,b=0),
                                  yaxis_title="", font_family="DM Sans",
                                  coloraxis_showscale=False)
            st.plotly_chart(fig_roi, use_container_width=True)

        with col_b:
            st.markdown("**Revenue by Channel**")
            ch_rev = df_camps.groupby("channel")["revenue_generated"].sum().reset_index()
            ch_rev.columns = ["Channel","Revenue"]
            fig_ch = px.pie(ch_rev, names="Channel", values="Revenue", hole=0.5,
                            color_discrete_sequence=px.colors.qualitative.Set2)
            fig_ch.update_layout(height=360, margin=dict(l=0,r=0,t=10,b=0),
                                 font_family="DM Sans")
            st.plotly_chart(fig_ch, use_container_width=True)

        st.download_button("⬇️ Export Campaign Report",
                           disp.to_csv(index=False).encode(),
                           file_name="campaign_roi_report.csv", mime="text/csv")

# ════════════════════════════════════════════
# TAB 3 — SQL CONSOLE
# ════════════════════════════════════════════
with tab3:
    st.markdown("### SQL Query Console")
    st.caption("Run live SQL queries on the RetainIQ SQLite database. Tables: `customers`, `campaigns`")

    # Preset queries a TAM would actually run
    presets = {
        "-- Select a preset query --": "",
        "Top 10 customers by revenue":
            "SELECT name, brand, segment, total_revenue, orders, churn_risk\nFROM customers\nORDER BY total_revenue DESC\nLIMIT 10;",
        "Churn risk summary by brand":
            "SELECT brand, churn_risk, COUNT(*) AS customers,\n       ROUND(SUM(total_revenue),2) AS total_ltv\nFROM customers\nGROUP BY brand, churn_risk\nORDER BY brand, customers DESC;",
        "At-risk customers with high LTV (>₹10,000)":
            "SELECT name, email, brand, total_revenue, days_inactive\nFROM customers\nWHERE churn_risk = 'At Risk'\n  AND total_revenue > 10000\nORDER BY total_revenue DESC;",
        "Churned customers — win-back list":
            "SELECT name, email, brand, total_revenue, days_inactive\nFROM customers\nWHERE churn_risk = 'Churned'\nORDER BY total_revenue DESC\nLIMIT 50;",
        "Repeat purchase rate by segment":
            "SELECT segment,\n       COUNT(*) AS total_customers,\n       SUM(CASE WHEN orders > 1 THEN 1 ELSE 0 END) AS repeat_buyers,\n       ROUND(100.0 * SUM(CASE WHEN orders > 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS repeat_rate_pct\nFROM customers\nGROUP BY segment\nORDER BY repeat_rate_pct DESC;",
        "Best performing campaigns by ROI":
            "SELECT campaign_name, brand, channel,\n       spend, revenue_generated,\n       ROUND((revenue_generated - spend) * 100.0 / spend, 1) AS roi_pct,\n       repeat_purchases\nFROM campaigns\nORDER BY roi_pct DESC;",
        "Average days inactive by churn segment":
            "SELECT churn_risk,\n       ROUND(AVG(days_inactive), 1) AS avg_days_inactive,\n       COUNT(*) AS customers\nFROM customers\nGROUP BY churn_risk;",
    }

    chosen = st.selectbox("Quick presets", list(presets.keys()))
    sql_input = st.text_area("SQL query", value=presets[chosen],
                              height=160, placeholder="SELECT * FROM customers LIMIT 10;")

    col_run, col_tip = st.columns([1, 4])
    run = col_run.button("▶️ Run Query", type="primary")
    col_tip.caption("Tip: both `customers` and `campaigns` tables are queryable. You can JOIN them on `brand`.")

    if run:
        if not sql_input.strip():
            st.warning("Enter a SQL query first.")
        else:
            try:
                with get_conn() as conn:
                    result = pd.read_sql(sql_input, conn)
                st.success(f"✅ {len(result):,} rows returned")
                st.dataframe(result, use_container_width=True, height=380)
                st.download_button("⬇️ Export as CSV",
                                   result.to_csv(index=False).encode(),
                                   file_name="query_result.csv", mime="text/csv")
            except Exception as e:
                st.error(f"Query error: {e}")

    st.divider()
    st.markdown("**Schema Reference**")
    sch1, sch2 = st.columns(2)
    with sch1:
        st.markdown("`customers` table")
        st.code("id, name, email, brand, segment\ntotal_revenue, orders, last_purchase_date\nstatus, churn_risk, days_inactive, uploaded_at", language="sql")
    with sch2:
        st.markdown("`campaigns` table")
        st.code("id, campaign_name, brand, channel\nspend, revenue_generated\ncustomers_reached, repeat_purchases\nlaunch_date, created_at", language="sql")

# ════════════════════════════════════════════
# TAB 4 — REVENUE CONVERTER
# ════════════════════════════════════════════
with tab4:
    st.markdown("### Multi-Brand Revenue Converter")
    st.caption("Convert customer LTV across currencies. Useful when managing global brands like Tommy Hilfiger or Calvin Klein.")

    currencies = ["INR","USD","GBP","EUR","AED","SGD","AUD","CAD","JPY","MYR"]

    c1, c2, c3 = st.columns(3)
    base   = c1.selectbox("Base currency", currencies, index=0)
    target = c2.selectbox("Convert to",    currencies, index=1)
    amount = c3.number_input("Amount", min_value=0.0, value=50000.0, step=1000.0)

    rates, updated = fetch_rates(base)

    if rates:
        if target in rates:
            converted = amount * rates[target]
            rate_val  = rates[target]

            st.markdown(f"""
            <div style='background:#f8f8f6;border:1px solid #e8e8e4;border-radius:12px;
                        padding:1.5rem 2rem;margin:1rem 0;display:inline-block;'>
                <p style='margin:0;font-size:13px;color:#666;'>Converted amount</p>
                <p style='margin:4px 0 0;font-size:32px;font-weight:600;color:#0f0f0f;'>
                    {target} {converted:,.2f}</p>
                <p style='margin:4px 0 0;font-size:13px;color:#999;'>
                    1 {base} = {rate_val:.4f} {target} · Last updated: {updated[:22]}</p>
            </div>
            """, unsafe_allow_html=True)

        st.divider()

        # Convert all customer LTV if data exists
        if has_data and target in rates:
            st.markdown(f"**Customer LTV in {target}**")
            conv_df = df[["name","brand","segment","total_revenue","churn_risk"]].copy() if "name" in df.columns else df[["brand","segment","total_revenue","churn_risk"]].copy()
            conv_df[f"ltv_{target}"] = (conv_df["total_revenue"] * rates[target]).round(2)
            conv_df = conv_df.rename(columns={
                "name":"Customer","brand":"Brand","segment":"Segment",
                "total_revenue":f"LTV ({base})","churn_risk":"Churn Risk",
                f"ltv_{target}":f"LTV ({target})"
            })
            st.dataframe(conv_df.head(30), use_container_width=True, height=350)

        st.divider()

        # Top 10 currency rates bar chart
        st.markdown(f"**Exchange Rates vs {base} — Top currencies for retail brands**")
        show_currencies = ["USD","GBP","EUR","AED","SGD","AUD","CAD","JPY","MYR","THB"]
        rates_show = {k: v for k, v in rates.items() if k in show_currencies}
        rates_df = pd.DataFrame(rates_show.items(), columns=["Currency", f"1 {base} ="])
        fig_r = px.bar(rates_df.sort_values(f"1 {base} =", ascending=False),
                       x="Currency", y=f"1 {base} =",
                       color=f"1 {base} =", color_continuous_scale="Blues",
                       text_auto=".4f")
        fig_r.update_layout(height=320, margin=dict(l=0,r=0,t=10,b=0),
                            coloraxis_showscale=False, font_family="DM Sans")
        st.plotly_chart(fig_r, use_container_width=True)

    else:
        st.warning("⚠️ Could not fetch live rates. Check internet connection.")
        st.info("Using free API: `https://open.er-api.com/v6/latest/INR` — no API key required.")
