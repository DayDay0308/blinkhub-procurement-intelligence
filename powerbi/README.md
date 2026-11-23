# Power BI: Procurement Intelligence report

The report reads the **dbt star schema** in the `analytics` schema, the same tables behind the API and the React dashboard. As a result, every surface shows the same numbers: one source of truth.

```
App (PostgreSQL) ──> dbt (staging -> marts, 40 data tests) ──> analytics.* ──┬──> Power BI (this report)
                       orchestrated by Dagster, daily 03:00                    └──> BlinkHub web dashboard
```

| File | What it is |
|---|---|
| `blinkhub.pbids` | Double-click to open Power BI Desktop already connected to the local database |
| `blinkhub-theme.json` | Report theme (validated colour-blind-safe palette) |
| `measures.dax` | All DAX measures, ready to paste |
| `BlinkHub-Procurement-Intelligence.pbix` | *You create this by following the steps below, then commit it* |
| `screenshots/` | *Add one PNG per page for the GitHub README* |

## 1. Connect (5 minutes)

1. Start the stack with `docker compose up` and wait until the `dagster` service logs show the build has finished. The `analytics` tables then exist.
2. **Double-click `blinkhub.pbids`.** Power BI Desktop opens with a PostgreSQL connection to `localhost:5432 / blinkhub`.
   - If you're asked for credentials, choose the **Database** tab and enter user `blinkhub`, password `blinkhub` (or your `.env` values).
   - If you see an encryption error, click **OK** to connect without encryption. That's fine for this local demo.
3. In the Navigator, tick these 8 tables from the **analytics** schema, then click **Load** (Import mode):
   - `analytics.dim_date`, `dim_supplier`, `dim_department`, `dim_category`
   - `analytics.fct_purchase_orders`, `fct_invoices`, `fct_deliveries`, `fct_risk_flags`

## 2. Model (10 minutes)

**Relationships** (Model view). All are many-to-one, with single-direction filtering from the dimension to the fact. Delete any that Power BI auto-detects differently.

| From (many) | To (one) |
|---|---|
| `fct_purchase_orders[supplier_id]` | `dim_supplier[supplier_id]` |
| `fct_purchase_orders[department_id]` | `dim_department[department_id]` |
| `fct_purchase_orders[category_id]` | `dim_category[category_id]` |
| `fct_purchase_orders[order_date_key]` | `dim_date[date_key]` |
| `fct_invoices[supplier_id]` | `dim_supplier[supplier_id]` |
| `fct_invoices[department_id]` | `dim_department[department_id]` |
| `fct_invoices[category_id]` | `dim_category[category_id]` |
| `fct_invoices[received_date_key]` | `dim_date[date_key]` |
| `fct_deliveries[supplier_id]` | `dim_supplier[supplier_id]` |
| `fct_deliveries[received_date_key]` | `dim_date[date_key]` |
| `fct_risk_flags[supplier_id]` | `dim_supplier[supplier_id]` |
| `fct_risk_flags[detected_date_key]` | `dim_date[date_key]` |

**Then:**
- **Mark `dim_date` as the date table:** select the table, then Table tools → Mark as date table → column `date`.
- **Sort `dim_date[month_short]` by `dim_date[month]`:** select the column, then Column tools → Sort by column.
- **Hide the ID and key columns** in report view (all `*_id` and `*_key` columns). Right-click → Hide.
- **Measures:** Home → Enter data → name the table `_Measures` → Load. Then, for each block in `measures.dax`, select `_Measures` → New measure → paste. Set the format shown in the `// [..]` comment.
  - Tip: paste them all at once with **Tabular Editor 2** (free) → File → Open → From DB → `_Measures` → right-click → Create → Measure.
  - `Spend Fiscal YTD` uses `"31/3"`. If your Windows locale is US, use `"3/31"`.
- **Theme:** View → Themes → Browse for themes → `blinkhub-theme.json`.

## 3. Build the four pages

Put the same **slicer row** across the top of every page:
- `dim_supplier[data_source]` (single select; default **CASE_STUDY**)
- `dim_date[fiscal_year_label]`
- `dim_department[department_name]`

Add a **card with `[Data Source Note]`** in the top-right corner of every page. Then sync the slicers (View → Sync slicers).

> **Presentation rule:** open on `CASE_STUDY` for findings about MICS. Switch to `SYNTHETIC` only to show how the report behaves at full scale, and say so out loud. The banner card states which data is on screen.

### Page 1: Executive overview
| Visual | Fields |
|---|---|
| 6 cards (top row) | `Total Spend` · `SMME Share %` · `B-BBEE Recognition %` · `Overdue Value` · `% Paid Within Terms` · `Open Flags` |
| Line chart | X `dim_date[year_month]` · Y `Total Spend` |
| Bar chart (horizontal) | Y `dim_department[department_name]` · X `Total Spend` · sort descending |
| Gauge | Value `SMME Share %` · Target `SMME Target %` · Max `1` |
| Text box | 3 bullet headline findings (from the analysis notebook) |

### Page 2: Spend & SMME (Problem 3, Path B Options 1-2)
| Visual | Fields |
|---|---|
| Clustered bar | Y `dim_category[category_name]` · X `Total Spend` · Legend `dim_supplier[supplier_type]` |
| Bar (horizontal) | Y `dim_supplier[province]` · X `Total Spend` · Tooltip `SMME Share %` |
| Table: top suppliers | `dim_supplier[supplier_name]`, `supplier_type`, `bbbee_level_label`, `Total Spend`, `Top Supplier Share %` (rename "Share"). Top N filter = 10 by `Total Spend` |
| Matrix: concentration | Rows `dim_category[category_name]` · Values `HHI`, `Top Supplier Share %`, `Concentration Band`, `Suppliers Paid`. Conditional formatting on `HHI`: background, rules >2500 red `#e34948`, >1500 amber `#eda100` |
| Cards | `SMME Spend` · `SMME Gap to Target %` · `Black Women Owned Spend %` |

### Page 3: Invoice performance (Problem 4)
| Visual | Fields |
|---|---|
| Cards | `Open Invoices` · `Overdue Invoices` · `Overdue Value` · `Overdue SMME Invoices` · `SMME Payment Gap (days)` |
| Column chart | X `fct_invoices[ageing_bucket]` (filter out "Closed") · Y `Invoices` |
| Line chart | X `dim_date[year_month]` · Y `Avg Days to Pay SMME`, `Avg Days to Pay Large`. Add a constant line at 30 (Analytics pane) labelled "30-day terms" |
| Table: chase list | `fct_invoices[invoice_number]`, `dim_supplier[supplier_name]`, `dim_supplier[supplier_type]`, `invoice_amount`, `days_outstanding`. Filter `is_open = True`; sort `days_outstanding` descending; data bars on `days_outstanding` |
| Card | `% Invoices Without PO` (title: "Invoices with no PO reference") |

### Page 4: Risk & supplier performance (Problem 6)
| Visual | Fields |
|---|---|
| Cards | `Open Flags` · `Critical & High Flags` · `Value Under Review` · `Confirmed Flags` · `On-Time Delivery %` |
| Bar (horizontal) | Y `fct_risk_flags[rule_name]` · X `Open Flags` · Legend `fct_risk_flags[severity]` |
| Table: investigation queue | `severity`, `score`, `rule_name`, `dim_supplier[supplier_name]`, `reason`, `value_at_risk`, `flag_status`. Sorted by `score` descending; conditional icons on `severity` |
| Table: supplier delivery | `dim_supplier[supplier_name]`, `On-Time Delivery %`, `Avg Days Late (late deliveries)`, `Total Spend`. Filter suppliers with `Total Spend` > 0 |

## 4. Check the numbers (case-study filter)

With `data_source = CASE_STUDY` selected, the report must show:

| Measure | Expected |
|---|---|
| Total Spend | **R4,027,000** |
| SMME Share % | **16.3%** |
| Overdue Value | **R955,000** (5 invoices) |
| Top Supplier Share % (all categories) | **33.0%** (Metro Logistics) |
| % Invoices Without PO | **100%** |

If a number differs, check the relationships (step 2) first. Invoices you submit during the Swagger demo also change these figures; `docker compose down -v` followed by `docker compose up` resets to the original data.

## 5. Save and commit

Save the file as `powerbi/BlinkHub-Procurement-Intelligence.pbix`, export one screenshot per page to `powerbi/screenshots/`, then commit. The `.pbix` contains imported data; it's synthetic and case-study data only, so it's safe to commit.

## Production notes (for the interview)

- **Refresh:** publish to Power BI Service, connect through an **on-premises data gateway** (or Azure/AWS private connectivity to RDS), and schedule refresh for 03:30, after the 03:00 Dagster build.
- **Security:** apply row-level security on `dim_department` so department heads see only their own spend.
- **Embedding** the report in the BlinkHub web app would need Power BI Embedded capacity. The prototype instead has its own React dashboard on the same marts.
