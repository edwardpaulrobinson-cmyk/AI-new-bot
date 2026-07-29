# GNB Property — Deep Reference (Retrievable)

Detailed finance/reporting tables the assistant pulls in when a question needs
them. Property/CRM matters only.

---

## Accounts Total Report — full column structure
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

**Relationship:** `Property Balance = Landlord + Agency + Contractor + (other internal)`.

**Expected bank balance per property:**
`Property Balance + Unallocated + Tenant Balance + Offer Progression + Float`
(deposits excluded — held separately).

**Grand reconciliation:**
```
Grand Accounts Total = SUM(Expected Bank per property) + Office Ledger Credit - Office Ledger Debit
Grand Bank Total     = SUM(bank money-in - money-out) + net unallocated bank entries + Opening Balance
Target: Grand Accounts Total ≈ Grand Bank Total  (difference should be £0)
```

## Bank statement structure
Columns: Date, Invoice (ref → attributes row to a property), Party (Name -
Address), Item, Money-In, Money-Out, Total Amount (running balance).

Row classification: has invoice → matched by invoice; has address → matched by
address; neither → unattributed ("bank entries with no property"). Exclude system
rows: `Opening Balance` (tracked separately) and `Unallocated Previous balance`.
But a Party/Item of **"Unallocated Balance"** IS a real unattributed transaction
(money in the bank not yet matched to a property) and must appear in output.

## Office ledger (optional third input)
Columns: Date, Nominal Code (e.g. "01 - Contractor payment"), Title (display),
Description (bank ref, fallback), Credit (in), Debit (out), VAT.
`Office Ledger Net = SUM(Credit) - SUM(Debit)`.

## Matching a bank transaction to a tenancy
Match on **exact amount** first (references are often truncated/misspelled), then
use name/reference as a tie-breaker.
- **Inflows:** Rent Payment, Partial Payment, Overpayment, Deposit, Unmatched Inflow.
- **Outflows:** Landlord Payment (rent minus fee), Agency Fee (commission),
  Maintenance/Repair, Insurance, Utility, Bank Charges, HMRC, Unmatched Outflow.
- **Confidence:** Exact (green), Probable (amber), No match (red), Manual review (blue).
