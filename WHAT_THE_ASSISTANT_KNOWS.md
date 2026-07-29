# What the Assistant Understands About GNB Property
### The product knowledge we are feeding the bot

This document sets out what the assistant understands about the **GNB Property**
product itself — what the CRM is for, what its main sections and reports contain,
and, most importantly, how the financial figures are read and interpreted. The aim
is transparency: the team can read exactly what the bot treats as known, confirm
it is right, and see where the knowledge is strong versus where it needs a
document or a screenshot to fill in. It is deliberately limited to property and
CRM matters.

---

## 1. What GNB Property is

GNB Property is a CRM platform for **UK letting and estate agencies**. In plain
terms it is where an agency runs its properties, landlords, tenants and tenancies,
keeps the client money accounted for, markets available properties, and manages
the websites and email behind its client brands. The assistant treats the product
as a single connected system rather than separate tools, because the useful
questions usually cross more than one part of it — a question about a balance, for
example, is really a question about how rent, fees and payments have flowed through
a property.

---

## 2. What the CRM manages

At its core the CRM holds **property records**, and around each property it links
the **landlord**, the **tenant(s)** and the **tenancy**. A property record carries
the details an agency works from day to day: the full UK address and postcode, the
property type, the number of bedrooms, bathrooms and reception rooms, the asking
rent or sale price, the EPC rating, the available date, a written description, a
features list, photographs, and the associated landlord information. That same
record is the source the marketing tools draw on later, so the assistant
understands the property record as the hub that everything else hangs off.

Everything below is about how that hub is read — financially, for marketing, and
operationally.

---

## 3. The money side — how balances are read and interpreted

This is the area the assistant understands most precisely, and it is the part most
worth confirming, because the terms look similar but mean different things.

**The underlying model.** A managed letting agency collects rent from tenants into
a **central client account**, then pays each landlord after deducting its fees.
Keeping that account correct is the job of reconciliation, and the CRM's view of
the position is the **Accounts Total Report** — a per-property export of balances.
The **reconciliation process** compares that report against the actual **bank
statement** (and, optionally, an **office ledger**) so that the CRM's expected
position and the real bank position can be made to agree.

**Reading a property's balances.** For each property the report shows a set of
balances, and the single most important thing to understand is that **Property
Balance is the parent** — it is the net position the agency holds for that
property. Sitting *inside* Property Balance are three breakdowns that must never be
added on top of it, because doing so double-counts the money:

- **Landlord Balance** — the portion currently held for the landlord.
- **Agency Balance** — the portion attributable to the agency (e.g. accrued fees).
- **Contractor Balance** — the portion held back for contractor/works costs.

Separate from Property Balance sit genuinely distinct pots of money, each tracked
on its own:

- **Unallocated Balance** — tenant money paid in advance that has not yet been
  applied to a rent charge (a credit sitting ahead of the rent).
- **Tenant Balance** — the tenant's current position (in credit or in arrears).
- **Float Balance** — a working buffer held for the property.
- **Offer Progression** — money held while a sale offer is progressing.
- **Deposit (held by agency)** and **Deposit Balance (DPS)** — the deposit, held
  either by the agency or in the protection scheme.

From this the assistant knows how to derive what *should* be in the client bank for
a property — the **expected bank balance**:

```
Expected Bank = Property Balance + Unallocated + Tenant Balance + Offer Progression + Float
```

Deposits are deliberately excluded because they are held separately. And it knows
**not to use the report's "Total" column** for reconciliation, because that column
folds the sub-ledgers back in and no longer maps cleanly to the bank.

**One trap it has been taught explicitly:** the phrase **"Unallocated Balance"
means two different things** depending on where it appears. On the **bank
statement** it is real money in the account that has not yet been matched to a
property. In the **Accounts Total Report** it is tenant advance payments inside the
CRM. Same words, different meaning — the assistant keeps them apart.

**How this reads as a statement.** A property or landlord statement is essentially
this ledger expressed for a period: the rent received, less the agency's
commission and fees, less any expenses or contractor costs, leaving the balance
held for the landlord and what is paid out to them. So when someone asks "what does
this balance mean" or "why is the landlord balance what it is", the assistant
reasons from the parent/sub-ledger structure above rather than guessing.

**The bank and office ledgers.** On the bank side, transactions are attributed to a
property by their reference or the address on the entry; anything with neither is
an unattributed entry that still has to be accounted for. Matching a payment to a
tenancy is done **by exact amount first** (because references are so often
truncated or misspelled), using name or reference only as a tie-breaker. The
optional office ledger nets its credits against its debits and feeds into the
overall reconciliation.


---

## 5. Property intelligence

The assistant understands **EPC Property Intelligence**: given a postcode, it
returns the property's address, its EPC rating, an estimate of the number of
bedrooms, and its council-tax band. This is the tool that enriches a property with
energy and tax data without manual lookup.


---

## 7. Websites and email infrastructure

Finally, the assistant understands the infrastructure GNB Property manages behind
its clients' estate-agent websites, almost all of it through **Cloudflare**. It
knows the common DNS record types (A, CNAME, MX, TXT), and the important rule that
email-authentication records and third-party verifications (such as SendGrid and
SPECTRE) must stay "DNS only" rather than proxied, because proxying them breaks
email. It understands **SPF, DKIM and DMARC** as the records that keep client email
deliverable, and the pattern SendGrid needs to authenticate a domain.

---

## 8. Where the knowledge is strong — and where it needs filling in

In the interest of honesty: the assistant's understanding of **how balances and the
Accounts Total Report are read and interpreted** is detailed and specific, and its
grasp of the **property record, marketing, property intelligence, communications
and infrastructure** is accurate at the level of what each part is and contains.

What it does **not** yet have is the live product's exact **screen-by-screen,
button-by-button** detail — for instance the precise on-screen layout of a property
statement, or the exact label and position of every icon in a given section. That
kind of granular UI knowledge is best supplied by uploading the relevant SOP, a
screenshot, or a short field list, and the bot is designed to fold that straight in.
So the fastest way to make it sharper on any specific screen is simply to add a
document describing it.

---

## 9. What this means for the bot

Everything above is the product knowledge the assistant carries by default. The
orientation — what GNB Property is, the property record, and how the balances are
read — travels with every answer, and the heavier reference detail is pulled in
only when a question needs it. Anything not covered here is added by uploading a
document, and the bot folds it into this same understanding.

In short: this is what it knows about the product. Read it, correct anything that
has moved on, and add screen-level documents where you want it to be exact.
