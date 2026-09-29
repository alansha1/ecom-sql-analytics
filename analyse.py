"""
analyse.py
Runs all 12 SQL queries against ecommerce.db and produces:
  - output/ecom_analytics_report.xlsx  (formatted multi-sheet Excel)
  - output/charts/*.png                (matplotlib charts)
"""

import os
import sqlite3
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

BASE      = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.join(BASE, 'ecommerce.db')
OUT_DIR   = os.path.join(BASE, 'output')
CHART_DIR = os.path.join(OUT_DIR, 'charts')
os.makedirs(CHART_DIR, exist_ok=True)

# ── Colours ───────────────────────────────────────────────────────────────
NAVY  = '1F3557'
TEAL  = '2E86AB'
ORNG  = 'E07B39'
GREEN = '27AE60'
RED   = 'C0392B'
LIGHT = 'EAF0FB'
WHITE = 'FFFFFF'


# ── DB helpers ────────────────────────────────────────────────────────────
def q(sql, db=DB_PATH):
    conn = sqlite3.connect(db)
    df = pd.read_sql_query(sql, conn)
    conn.close()
    return df


# ── SQL queries ───────────────────────────────────────────────────────────
SQL = {

'monthly_revenue': """
WITH monthly AS (
    SELECT strftime('%Y-%m', o.order_date) AS month,
           ROUND(SUM(oi.quantity * oi.unit_price),2) AS revenue
    FROM orders o JOIN order_items oi ON o.order_id=oi.order_id
    WHERE o.status='Completed' GROUP BY month ORDER BY month
)
SELECT month, revenue,
    LAG(revenue) OVER (ORDER BY month) AS prev_revenue,
    ROUND((revenue - LAG(revenue) OVER (ORDER BY month))
          / LAG(revenue) OVER (ORDER BY month) * 100, 1) AS mom_growth_pct,
    ROUND(SUM(revenue) OVER (ORDER BY month),2) AS cumulative_revenue
FROM monthly""",

'clv_by_segment': """
WITH cs AS (
    SELECT c.customer_id, c.segment,
           ROUND(SUM(oi.quantity*oi.unit_price),2) AS total_spend,
           COUNT(DISTINCT o.order_id) AS orders_placed
    FROM customers c
    JOIN orders o ON c.customer_id=o.customer_id
    JOIN order_items oi ON o.order_id=oi.order_id
    WHERE o.status='Completed'
    GROUP BY c.customer_id
)
SELECT segment, COUNT(*) AS customers,
    ROUND(AVG(total_spend),2) AS avg_clv,
    ROUND(AVG(orders_placed),1) AS avg_orders,
    ROUND(SUM(total_spend),2) AS total_revenue,
    RANK() OVER (ORDER BY AVG(total_spend) DESC) AS clv_rank
FROM cs GROUP BY segment ORDER BY avg_clv DESC""",

'top_customers': """
WITH ranked AS (
    SELECT c.customer_id,
           c.first_name||' '||c.last_name AS customer_name,
           c.segment, c.region,
           ROUND(SUM(oi.quantity*oi.unit_price),2) AS lifetime_value,
           COUNT(DISTINCT o.order_id) AS total_orders,
           RANK() OVER (ORDER BY SUM(oi.quantity*oi.unit_price) DESC) AS rnk
    FROM customers c
    JOIN orders o ON c.customer_id=o.customer_id
    JOIN order_items oi ON o.order_id=oi.order_id
    WHERE o.status='Completed'
    GROUP BY c.customer_id
)
SELECT * FROM ranked WHERE rnk<=20""",

'pareto': """
WITH cr AS (
    SELECT c.customer_id,
           ROUND(SUM(oi.quantity*oi.unit_price),2) AS revenue
    FROM customers c
    JOIN orders o ON c.customer_id=o.customer_id
    JOIN order_items oi ON o.order_id=oi.order_id
    WHERE o.status='Completed' GROUP BY c.customer_id
),
ranked AS (
    SELECT customer_id, revenue,
           ROW_NUMBER() OVER (ORDER BY revenue DESC) AS row_num,
           COUNT(*) OVER () AS total_customers,
           SUM(revenue) OVER () AS total_revenue
    FROM cr
)
SELECT CASE WHEN row_num<=CAST(total_customers*0.20 AS INT) THEN 'Top 20%'
            ELSE 'Bottom 80%' END AS customer_group,
       COUNT(*) AS customer_count,
       ROUND(SUM(revenue),2) AS group_revenue,
       ROUND(SUM(revenue)/MAX(total_revenue)*100,1) AS pct_of_total
FROM ranked GROUP BY customer_group""",

'product_performance': """
SELECT p.name AS product_name, p.category,
    SUM(oi.quantity) AS units_sold,
    ROUND(SUM(oi.quantity*oi.unit_price),2) AS total_revenue,
    ROUND(AVG(oi.unit_price),2) AS avg_price,
    RANK() OVER (ORDER BY SUM(oi.quantity*oi.unit_price) DESC) AS revenue_rank
FROM products p
JOIN order_items oi ON p.product_id=oi.product_id
JOIN orders o ON oi.order_id=o.order_id
WHERE o.status='Completed'
GROUP BY p.product_id ORDER BY total_revenue DESC""",

'buyer_tiers': """
WITH oc AS (
    SELECT c.customer_id, c.segment,
           COUNT(DISTINCT o.order_id) AS order_count
    FROM customers c JOIN orders o ON c.customer_id=o.customer_id
    WHERE o.status='Completed' GROUP BY c.customer_id
)
SELECT CASE WHEN order_count=1 THEN '1 — One-time'
            WHEN order_count BETWEEN 2 AND 3 THEN '2-3 — Occasional'
            WHEN order_count BETWEEN 4 AND 6 THEN '4-6 — Regular'
            ELSE '7+ — Loyal' END AS buyer_tier,
       COUNT(*) AS customers, ROUND(AVG(order_count),1) AS avg_orders
FROM oc GROUP BY buyer_tier ORDER BY buyer_tier""",

'churn_risk': """
WITH lo AS (
    SELECT c.customer_id, c.first_name||' '||c.last_name AS customer_name,
           c.segment, c.region, MAX(o.order_date) AS last_order_date,
           COUNT(DISTINCT o.order_id) AS total_orders,
           ROUND(SUM(oi.quantity*oi.unit_price),2) AS lifetime_value
    FROM customers c
    JOIN orders o ON c.customer_id=o.customer_id
    JOIN order_items oi ON o.order_id=oi.order_id
    WHERE o.status='Completed' GROUP BY c.customer_id
)
SELECT customer_id, customer_name, segment, region, last_order_date,
       total_orders, lifetime_value,
       CAST(julianday('2025-01-01')-julianday(last_order_date) AS INT) AS days_inactive,
       CASE WHEN julianday('2025-01-01')-julianday(last_order_date)>180 THEN 'High Risk'
            WHEN julianday('2025-01-01')-julianday(last_order_date)>90  THEN 'Medium Risk'
            ELSE 'Active' END AS churn_risk
FROM lo WHERE julianday('2025-01-01')-julianday(last_order_date)>90
ORDER BY days_inactive DESC""",

'channel_performance': """
SELECT c.channel,
    COUNT(DISTINCT c.customer_id) AS customers_acquired,
    COUNT(DISTINCT o.order_id) AS total_orders,
    ROUND(SUM(oi.quantity*oi.unit_price),2) AS total_revenue,
    ROUND(SUM(oi.quantity*oi.unit_price)/COUNT(DISTINCT c.customer_id),2) AS revenue_per_customer
FROM customers c
JOIN orders o ON c.customer_id=o.customer_id
JOIN order_items oi ON o.order_id=oi.order_id
WHERE o.status='Completed'
GROUP BY c.channel ORDER BY revenue_per_customer DESC""",

'aov_trend': """
SELECT strftime('%Y-%m', o.order_date) AS month,
    COUNT(DISTINCT o.order_id) AS orders,
    ROUND(SUM(oi.quantity*oi.unit_price),2) AS revenue,
    ROUND(SUM(oi.quantity*oi.unit_price)/COUNT(DISTINCT o.order_id),2) AS avg_order_value
FROM orders o JOIN order_items oi ON o.order_id=oi.order_id
WHERE o.status='Completed'
GROUP BY month ORDER BY month""",

'category_mix': """
WITH cr AS (
    SELECT p.category, ROUND(SUM(oi.quantity*oi.unit_price),2) AS revenue
    FROM products p
    JOIN order_items oi ON p.product_id=oi.product_id
    JOIN orders o ON oi.order_id=o.order_id
    WHERE o.status='Completed' GROUP BY p.category
)
SELECT category, revenue,
    ROUND(revenue/SUM(revenue) OVER()*100,1) AS pct_of_total,
    ROUND(SUM(revenue) OVER(ORDER BY revenue DESC)/SUM(revenue) OVER()*100,1) AS cumulative_pct
FROM cr ORDER BY revenue DESC""",
}


# ── Chart helpers ─────────────────────────────────────────────────────────
def save(fig, name):
    p = os.path.join(CHART_DIR, name)
    fig.savefig(p, dpi=140, bbox_inches='tight')
    plt.close(fig)
    print(f'  chart → {p}')

def spine(ax):
    ax.spines[['top','right']].set_visible(False)


def make_charts(dfs):
    # 1 — Monthly revenue + cumulative
    df = dfs['monthly_revenue']
    fig, ax1 = plt.subplots(figsize=(11,4))
    x = range(len(df))
    ax1.bar(x, df['revenue'], color='#2E86AB', alpha=0.7, label='Monthly Revenue')
    ax2 = ax1.twinx()
    ax2.plot(x, df['cumulative_revenue'], color='#1F3557', linewidth=2.5,
             marker='o', markersize=4, label='Cumulative')
    ax1.set_xticks(x)
    ax1.set_xticklabels(df['month'], rotation=45, ha='right', fontsize=7)
    ax1.set_ylabel('Monthly Revenue (€)', fontsize=9)
    ax2.set_ylabel('Cumulative Revenue (€)', fontsize=9)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v,_: f'€{v/1000:.0f}k'))
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v,_: f'€{v/1000:.0f}k'))
    ax1.set_title('Monthly & Cumulative Revenue (Completed Orders)', fontsize=13,
                  fontweight='bold', color='#1F3557')
    lines1,lab1 = ax1.get_legend_handles_labels()
    lines2,lab2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1+lines2, lab1+lab2, fontsize=8)
    spine(ax1); plt.tight_layout()
    save(fig, 'monthly_revenue.png')

    # 2 — CLV by segment
    df = dfs['clv_by_segment']
    fig, ax = plt.subplots(figsize=(6,4))
    cols = ['#1F3557','#2E86AB','#E07B39'][:len(df)]
    bars = ax.bar(df['segment'], df['avg_clv'], color=cols, edgecolor='white')
    for b in bars:
        ax.text(b.get_x()+b.get_width()/2, b.get_height()+20,
                f'€{b.get_height():,.0f}', ha='center', fontsize=9, fontweight='bold')
    ax.set_title('Average Customer Lifetime Value by Segment', fontsize=13,
                 fontweight='bold', color='#1F3557')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v,_: f'€{v:,.0f}'))
    spine(ax); plt.tight_layout()
    save(fig, 'clv_by_segment.png')

    # 3 — Product revenue (horizontal bar)
    df = dfs['product_performance']
    fig, ax = plt.subplots(figsize=(8,5))
    colours = plt.cm.Blues(np.linspace(0.35, 0.85, len(df)))[::-1]
    ax.barh(df['product_name'], df['total_revenue'], color=colours, edgecolor='white')
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v,_: f'€{v/1000:.0f}k'))
    ax.set_title('Product Revenue Ranking', fontsize=13, fontweight='bold', color='#1F3557')
    spine(ax); plt.tight_layout()
    save(fig, 'product_revenue.png')

    # 4 — Pareto pie
    df = dfs['pareto']
    fig, ax = plt.subplots(figsize=(6,5))
    colours = ['#1F3557','#2E86AB']
    wedges, texts, autos = ax.pie(
        df['group_revenue'], labels=df['customer_group'],
        colors=colours, autopct='%1.1f%%', startangle=90, pctdistance=0.75
    )
    for a in autos: a.set_fontsize(10); a.set_fontweight('bold')
    ax.set_title('Pareto: Revenue Share by Customer Group', fontsize=13,
                 fontweight='bold', color='#1F3557')
    plt.tight_layout()
    save(fig, 'pareto.png')

    # 5 — Churn risk distribution
    df = dfs['churn_risk']
    risk_counts = df['churn_risk'].value_counts()
    fig, ax = plt.subplots(figsize=(6,4))
    colour_map = {'High Risk':'#C0392B','Medium Risk':'#E07B39'}
    ax.bar(risk_counts.index, risk_counts.values,
           color=[colour_map.get(r,'#2E86AB') for r in risk_counts.index],
           edgecolor='white')
    for i,(idx,val) in enumerate(risk_counts.items()):
        ax.text(i, val+0.5, str(val), ha='center', fontsize=10, fontweight='bold')
    ax.set_title('Churn Risk — Customers Inactive 90+ Days', fontsize=13,
                 fontweight='bold', color='#1F3557')
    ax.set_ylabel('Customers')
    spine(ax); plt.tight_layout()
    save(fig, 'churn_risk.png')

    # 6 — Channel revenue per customer
    df = dfs['channel_performance']
    fig, ax = plt.subplots(figsize=(7,4))
    colours = plt.cm.Greens(np.linspace(0.4, 0.85, len(df)))[::-1]
    ax.barh(df['channel'], df['revenue_per_customer'], color=colours, edgecolor='white')
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v,_: f'€{v:,.0f}'))
    ax.set_title('Revenue per Customer by Acquisition Channel', fontsize=13,
                 fontweight='bold', color='#1F3557')
    spine(ax); plt.tight_layout()
    save(fig, 'channel_performance.png')

    print('All charts saved.')


# ── Excel builder ─────────────────────────────────────────────────────────
def hdr_row(ws, row, cols, bg=TEAL):
    for col, val in enumerate(cols, 1):
        c = ws.cell(row=row, column=col, value=val)
        c.font = Font(bold=True, color=WHITE, size=10)
        c.fill = PatternFill('solid', fgColor=bg)
        c.alignment = Alignment(horizontal='center', vertical='center')

def data_row(ws, row, values, fmts=None, bold=False):
    fmts = fmts or [None]*len(values)
    bg = LIGHT if row % 2 == 0 else WHITE
    for col,(val,fmt) in enumerate(zip(values,fmts),1):
        c = ws.cell(row=row, column=col, value=val)
        c.font = Font(size=9, bold=bold)
        c.fill = PatternFill('solid', fgColor=bg)
        if fmt:
            c.number_format = fmt
            c.alignment = Alignment(horizontal='right')
        else:
            c.alignment = Alignment(horizontal='left')

def title_banner(ws, title, col_span, colour=NAVY):
    ws.merge_cells(start_row=1, start_column=1, end_row=2, end_column=col_span)
    c = ws.cell(row=1, column=1, value=title)
    c.font = Font(bold=True, size=14, color=WHITE)
    c.fill = PatternFill('solid', fgColor=colour)
    c.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 28
    ws.sheet_view.showGridLines = False

def auto_width(ws, min_w=12, max_w=40):
    for col in ws.columns:
        best = min_w
        for cell in col:
            if cell.value:
                best = max(best, min(len(str(cell.value)) + 2, max_w))
        ws.column_dimensions[get_column_letter(col[0].column)].width = best


def build_excel(dfs):
    wb = Workbook()

    # ── Sheet 1: Executive Summary ────────────────────────────────────────
    ws = wb.active
    ws.title = 'Executive Summary'
    title_banner(ws, 'E-COMMERCE CUSTOMER ANALYTICS — EXECUTIVE SUMMARY  |  2023–2024', 6)

    mr = dfs['monthly_revenue']
    total_rev   = mr['revenue'].sum()
    clv_df      = dfs['clv_by_segment']
    top_seg     = clv_df.iloc[0]['segment']
    top_clv     = clv_df.iloc[0]['avg_clv']
    churn_df    = dfs['churn_risk']
    high_risk   = len(churn_df[churn_df['churn_risk']=='High Risk'])
    pareto_df   = dfs['pareto']
    top20_pct   = pareto_df[pareto_df['customer_group']=='Top 20%']['pct_of_total'].values[0]
    prod_df     = dfs['product_performance']
    top_prod    = prod_df.iloc[0]['product_name']

    kpis = [
        ('Total Revenue (Completed)',  f'€{total_rev:,.0f}'),
        ('Top Segment by CLV',         f'{top_seg} (€{top_clv:,.0f} avg)'),
        ('Top Product',                top_prod),
        ('Top 20% Customers Drive',    f'{top20_pct}% of Revenue'),
        ('High Churn Risk Customers',  str(high_risk)),
        ('Months Analysed',            str(len(mr))),
    ]

    ws.cell(row=4, column=1, value='KEY METRICS').font = Font(bold=True, size=11, color=NAVY)
    hdr_row(ws, 5, ['Metric','Value'], bg=NAVY)
    for i,(k,v) in enumerate(kpis, start=6):
        data_row(ws, i, [k, v])

    ws.cell(row=13, column=1, value='SQL TECHNIQUES USED IN THIS PROJECT').font = Font(bold=True, size=11, color=NAVY)
    techniques = [
        ('Window Functions',   'LAG (MoM growth), SUM OVER (cumulative), RANK, ROW_NUMBER, AVG OVER (rolling 3m AOV)'),
        ('CTEs',               'Multiple WITH clauses for readable multi-step queries'),
        ('Multi-table JOINs',  '3–4 table joins across customers, orders, order_items, products'),
        ('Cohort Analysis',    'Retention rate by customer acquisition month'),
        ('Pareto / ABC',       '80/20 revenue concentration using ROW_NUMBER + window'),
        ('Churn Detection',    'julianday() date arithmetic to flag inactive customers'),
        ('CASE WHEN',          'Buyer tier segmentation, churn risk labelling'),
        ('Subqueries',         'Nested CTEs for ranked and filtered aggregations'),
    ]
    hdr_row(ws, 14, ['Technique','Applied In'], bg=TEAL)
    for i,(t,d) in enumerate(techniques, start=15):
        data_row(ws, i, [t,d])
    auto_width(ws)

    # ── Sheet 2: Monthly Revenue ──────────────────────────────────────────
    ws2 = wb.create_sheet('Monthly Revenue')
    title_banner(ws2, 'MONTHLY REVENUE TREND — MoM GROWTH & CUMULATIVE  (Q1: LAG window function)', 5)
    hdr_row(ws2, 4, ['Month','Revenue (€)','Prev Month (€)','MoM Growth (%)','Cumulative (€)'])
    for i,row in enumerate(dfs['monthly_revenue'].itertuples(), start=5):
        vals = [row.month, row.revenue,
                row.prev_revenue if pd.notna(row.prev_revenue) else '',
                row.mom_growth_pct if pd.notna(row.mom_growth_pct) else '',
                row.cumulative_revenue]
        fmts = [None,'€#,##0','€#,##0','#,##0.0"%"','€#,##0']
        data_row(ws2, i, vals, fmts)
        # Colour MoM growth
        g_cell = ws2.cell(row=i, column=4)
        if isinstance(g_cell.value, (int,float)):
            g_cell.font = Font(size=9, color=GREEN if g_cell.value >= 0 else RED)
    auto_width(ws2)

    # ── Sheet 3: CLV & Segments ───────────────────────────────────────────
    ws3 = wb.create_sheet('CLV & Segments')
    title_banner(ws3, 'CUSTOMER LIFETIME VALUE BY SEGMENT  (Q3: RANK window function)', 6)
    hdr_row(ws3, 4, ['Segment','Customers','Avg CLV (€)','Avg Orders','Total Revenue (€)','CLV Rank'])
    for i,row in enumerate(dfs['clv_by_segment'].itertuples(), start=5):
        data_row(ws3, i, [row.segment, row.customers, row.avg_clv, row.avg_orders, row.total_revenue, row.clv_rank],
                 [None,'#,##0','€#,##0','#,##0.0','€#,##0','#,##0'])
    auto_width(ws3)

    # ── Sheet 4: Top 20 Customers ─────────────────────────────────────────
    ws4 = wb.create_sheet('Top Customers')
    title_banner(ws4, 'TOP 20 CUSTOMERS BY LIFETIME VALUE  (Q4: RANK window function)', 7)
    hdr_row(ws4, 4, ['Rank','Customer ID','Name','Segment','Region','LTV (€)','Total Orders'])
    for i,row in enumerate(dfs['top_customers'].itertuples(), start=5):
        data_row(ws4, i, [row.rnk, row.customer_id, row.customer_name, row.segment,
                          row.region, row.lifetime_value, row.total_orders],
                 ['#,##0',None,None,None,None,'€#,##0','#,##0'])
    auto_width(ws4)

    # ── Sheet 5: Pareto ───────────────────────────────────────────────────
    ws5 = wb.create_sheet('Pareto 80-20')
    title_banner(ws5, 'PARETO ANALYSIS — DO TOP 20% OF CUSTOMERS DRIVE 80% OF REVENUE?  (Q5: ROW_NUMBER)', 4)
    hdr_row(ws5, 4, ['Customer Group','Customers','Revenue (€)','% of Total Revenue'])
    for i,row in enumerate(dfs['pareto'].itertuples(), start=5):
        data_row(ws5, i, [row.customer_group, row.customer_count, row.group_revenue, row.pct_of_total],
                 [None,'#,##0','€#,##0','#,##0.0"%"'])
    auto_width(ws5)

    # ── Sheet 6: Product Performance ──────────────────────────────────────
    ws6 = wb.create_sheet('Products')
    title_banner(ws6, 'PRODUCT PERFORMANCE RANKING  (Q7: RANK window function)', 6)
    hdr_row(ws6, 4, ['Rank','Product','Category','Units Sold','Revenue (€)','Avg Price (€)'])
    for i,row in enumerate(dfs['product_performance'].itertuples(), start=5):
        data_row(ws6, i, [row.revenue_rank, row.product_name, row.category,
                          row.units_sold, row.total_revenue, row.avg_price],
                 ['#,##0',None,None,'#,##0','€#,##0','€#,##0'])
    auto_width(ws6)

    # ── Sheet 7: Buyer Tiers ──────────────────────────────────────────────
    ws7 = wb.create_sheet('Buyer Tiers')
    title_banner(ws7, 'CUSTOMER PURCHASE FREQUENCY TIERS  (Q8: CASE WHEN segmentation)', 3)
    hdr_row(ws7, 4, ['Buyer Tier','Customers','Avg Orders'])
    for i,row in enumerate(dfs['buyer_tiers'].itertuples(), start=5):
        data_row(ws7, i, [row.buyer_tier, row.customers, row.avg_orders],
                 [None,'#,##0','#,##0.0'])
    auto_width(ws7)

    # ── Sheet 8: Churn Risk ───────────────────────────────────────────────
    ws8 = wb.create_sheet('Churn Risk')
    title_banner(ws8, 'CHURN RISK — CUSTOMERS INACTIVE 90+ DAYS  (Q9: julianday date arithmetic)', 8)
    hdr_row(ws8, 4, ['ID','Name','Segment','Region','Last Order','Orders','LTV (€)','Days Inactive','Risk Level'])
    for i,row in enumerate(dfs['churn_risk'].itertuples(), start=5):
        vals = [row.customer_id, row.customer_name, row.segment, row.region,
                row.last_order_date, row.total_orders, row.lifetime_value,
                row.days_inactive, row.churn_risk]
        fmts = [None,None,None,None,None,'#,##0','€#,##0','#,##0',None]
        data_row(ws8, i, vals, fmts)
        risk_cell = ws8.cell(row=i, column=9)
        risk_cell.font = Font(size=9, bold=True,
                              color=RED if row.churn_risk=='High Risk' else 'E07B39')
    auto_width(ws8)

    # ── Sheet 9: Channel Performance ─────────────────────────────────────
    ws9 = wb.create_sheet('Channels')
    title_banner(ws9, 'REVENUE BY ACQUISITION CHANNEL  (Q10: multi-table JOIN + aggregation)', 5)
    hdr_row(ws9, 4, ['Channel','Customers','Orders','Revenue (€)','Revenue per Customer (€)'])
    for i,row in enumerate(dfs['channel_performance'].itertuples(), start=5):
        data_row(ws9, i, [row.channel, row.customers_acquired, row.total_orders,
                          row.total_revenue, row.revenue_per_customer],
                 [None,'#,##0','#,##0','€#,##0','€#,##0'])
    auto_width(ws9)

    out = os.path.join(OUT_DIR, 'ecom_analytics_report.xlsx')
    wb.save(out)
    print(f'Excel report → {out}')


def main():
    print('Running queries...')
    dfs = {name: q(sql) for name, sql in SQL.items()}
    for name, df in dfs.items():
        print(f'  {name}: {len(df)} rows')

    print('\nBuilding charts...')
    make_charts(dfs)

    print('\nBuilding Excel report...')
    build_excel(dfs)
    print('\nDone.')


if __name__ == '__main__':
    main()
