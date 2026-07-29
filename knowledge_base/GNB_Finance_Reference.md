# GNB Property — Finance & Reconciliation Reference

Finance and reconciliation concepts only. (A normal reference document — retrieved
when a finance question needs it, not forced into every answer.)

---

## The client-account model
A managed letting agency collects rent from tenants into a **central client
account**, then pays each landlord after deducting its fees. Keeping that account
correct is the job of reconciliation: comparing the CRM's ledger (the **Accounts
Total Report**) against the actual **bank statement** (and, optionally, an
**office ledger**), so the CRM's expected position and the real bank position agree.

---

## Accounts Total Report — column structure
Exact column names from the CRM export:

| Column | Type | Meaning |
|---|---|---|
| Name (col 1) | Status | "Active", "Inactive", etc. |
| Name (col 2) | Address | Full property address incl. postcode |
| Property Balance() | £ | **Parent ledger** — net position for the property |
| Unallocated Balance() | £ | Tenant advance payments not yet applied to rent |
| Tenant Balance() | £ | Current tenant balance |
| Landlord Balance() | £ | Sub-ledger of Property Balance — do NOT add separately |
| Deposit (held by agency) Balance() | £ | External — deposit held by agency |
| Contractor Balance() | £ | Sub-ledger of Property Balance — do NOT add separately |
| Deposit Balance() | £ | External — DPS-held deposit |
| Float Balance() | £ | **Standalone** — float money for the property |
| Agency Balance() | £ | Sub-ledger of Property Balance — do NOT add separately |
| Offer Progression() | £ | External — money held for offers/progression |
| Pre bank receipts() | £ | Internal — exclude from bank reconciliation |
| Total | £ | CRM total (includes sub-ledgers — do not use for bank rec) |

**Parent vs sub-ledger:** Property Balance is the parent. Landlord, Agency and
Contractor balances are breakdowns *inside* it — never add them on top, or you
double-count. Relationship:
`Property Balance = Landlord + Agency + Contractor + (other internal)`.

**Separate pots (external to Property Balance):** Unallocated Balance (tenant
advance payments), Tenant Balance, Float Balance, Offer Progression, Deposit
(held by agency), Deposit Balance (DPS).

---

## Expected bank balance (per property)
```
Expected Bank = Property Balance + Unallocated + Tenant Balance + Offer Progression + Float
```
Deposits are excluded — held separately, not in the main client account. Do NOT
use the report's "Total" column for reconciliation; it folds the sub-ledgers back in.

## Grand reconciliation
```
Grand Accounts Total = SUM(Expected Bank per property) + Office Ledger Credit - Office Ledger Debit
Grand Bank Total     = SUM(bank money-in - money-out) + net unallocated bank entries + Opening Balance
Target: Grand Accounts Total ~= Grand Bank Total  (difference should be £0)
```

---

## Two different "Unallocated Balance" meanings — don't confuse them
- **Bank statement row** "Unallocated Balance" = real money in the bank not yet
  matched to a property (a genuine unattributed transaction).
- **Accounts Total column** "Unallocated Balance" = tenant advance payments sitting
  in the CRM ledger.

---

## Bank statement structure
Columns: Date, Invoice (reference -> attributes the row to a property), Party
(Name - Address), Item, Money-In, Money-Out, Total Amount (running balance).

Row classification: has invoice -> matched by invoice; has address -> matched by
address; neither -> unattributed ("bank entries with no property").
Exclude system rows: `Opening Balance` (tracked separately) and `Unallocated
Previous balance`. But a Party/Item of **"Unallocated Balance"** IS a real
unattributed transaction and must appear in the reconciliation.

## Office ledger (optional third input)
Columns: Date, Nominal Code (e.g. "01 - Contractor payment"), Title (display),
Description (bank reference, fallback), Credit (money in), Debit (money out), VAT.
`Office Ledger Net = SUM(Credit) - SUM(Debit)`.

## Matching a bank transaction to a tenancy
Match on **exact amount** first (references are often truncated or misspelled),
then use name/reference as a tie-breaker.
- **Inflows:** Rent Payment, Partial Payment, Overpayment, Deposit, Unmatched Inflow.
- **Outflows:** Landlord Payment (rent minus fee), Agency Fee (commission),
  Maintenance/Repair, Insurance, Utility, Bank Charges, HMRC, Unmatched Outflow.
- **Confidence:** Exact (green), Probable (amber), No match (red), Manual review (blue).
