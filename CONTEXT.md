# Faida

Profit visibility for GCC cafeterias and multi-branch chains, fed through WhatsApp: supplier invoices in, costed menus and branch figures out.
This glossary holds the words the product uses and the words it refuses, so a screen, a message and a conversation say the same thing.

## Language

### Invoices

**Filing**:
The one step that turns a normalized invoice and a supplier's catalog into what the database stores and the reply reads: the checks with snapped folded in, the price alerts, the derived confidence and the line rows. Runs the same for a photo, a correction and a typed invoice.
_Avoid_: Processing, post-processing, enrichment, validation (that is the arithmetic alone)

### Figures

**Quality word**:
The one of four words every derived figure carries, in PRD §24's vocabulary: reliable with limitations, estimated, incomplete, unavailable.
A figure is never greener than its worst input (C9), so the word of a derived figure is the worst of its inputs' words, in that precedence, worst first; a total over rows reads unavailable only when every row is and incomplete when any row is a hole among others.
Owned once, in `quality.py`: the words, their order and their English; which of the four a layer may produce is that layer's rule.
_Avoid_: Verified (nothing corroborates a pack size or cross-checks a till), complete (coverage is *costed*), confidence (that is the extraction's own derived number, not this word), label or badge as the noun

**Price in force**:
A material's one price at a moment: the newest delivery we could cost, among the packs mapped to it, by printed invoice date.
When a newer delivery could not be costed the older price still shows, reads estimated and names that delivery and why it has no cost.
Worked out once, in `price_in_force.py`, with the sentence saying why a price is estimated and the words for its unit ("per kg", "each"); a screen prints those and composes none of its own.
_Avoid_: Current price (a period figure takes the price in force on its last day, not today's), average or cheapest price (it is neither), cost (that is one invoice line's figure)

**Period read**:
Everything a period screen starts from, read once for one tenant and one period: the period the rule resolved, the branches, each branch's clipped window, the papers no branch claimed, the chain total, the menu costed at the prices in force on the period's last day, and the period's item sales.
Every figure on the dashboard, the sales screen and the usage printout is derived from one of these and never from a second reading of the same tables, so two screens over one period cannot disagree on a window or a plate.
_Avoid_: Context, bundle, snapshot (nothing is stored), preamble
