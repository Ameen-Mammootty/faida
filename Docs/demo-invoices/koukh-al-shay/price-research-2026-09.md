# What these ingredients actually cost in the UAE, September 2026

The five demo papers were written to make the arithmetic work, not to be true.
Boneless chicken printed at AED 3.45 a kilo, which is roughly a fifth of what any Dubai cafeteria pays, and the closing margin screen showed chicken curries earning 89%.
The founder's call on 2026-09-01: the last image of the demo has to be margins an owner recognises, or the whole chain above it reads as a toy.

This is the evidence behind the repriced papers.
One row per line on the four preparation papers, each with the pack we now print, the ex-VAT price, what that works out to per kilo or litre, what it replaced, and the source we actually read.
**No number here is in the papers without a source and a date.**

## How the prices were found, and what that is worth

Five researchers worked in parallel, one per product family, against UAE foodservice and wholesale sources: Tradeling, Chef Middle East and MH Enterprises first, then Horeca Market, Falcon Pack, Barakat, NRTC, Sidco, Fresh Focus, Femco, Al Aweer Central Market's daily bulletin, and retail (Lulu, Carrefour, Noon, Amazon.ae) only as a ceiling.
Every row was then re-checked once, and the rows that could move a plate by more than a few fils were re-checked twice.

Three rules were applied throughout, and they are the reason to trust the table:

- **Only prices actually seen on a page actually loaded.** No reconstruction from memory, no "typical market knowledge". Where nothing was found, the row says NOT FOUND or names a proxy, and that is a real answer rather than a gap papered over.
- **VAT basis is stated per row, never assumed.** UAE VAT is 5%. Retail listings are inclusive and are divided by 1.05 where used; the arithmetic is shown in the underlying research files. The papers print ex-VAT prices, per C4.
- **No invented wholesale discount.** Where only retail existed, the row is marked an estimate and keeps the retail figure. Quietly shaving 30% off a Carrefour price to make it "look wholesale" would be exactly the invention this product exists to eliminate.

**Two sources did most of the heavy lifting.**
`horecamarket.ae` (Mirbat Foodstuff Trading LLC) states every price as "AED X.XX Plus 5% VAT" per kilogram with a minimum order weight - explicit ex-VAT wholesale, the best evidence class available, and it settled the chicken question.
Tradeling's B2B catalogue covered the dry goods almost entirely; its listings state "Incl. VAT" and were de-VATed.

### The honest limits

- **Nobody quoted us a price.** These are published list prices, not the number a cafeteria negotiates with a supplier it has bought from for four years. Real invoice prices will run below several of these, particularly on the frozen proteins and the disposables. That direction is worth stating out loud on stage if anyone asks.
- **Produce is a spot market.** Al Aweer prices move weekly. Six produce lines were originally priced off a single day's bulletin, and one of them - capsicum - turned out to sit 46% below its own 56-day average. Every Al Aweer row that has a multi-day history now uses the **average**, not the spot price, because a demo wants a representative cost rather than one arbitrary Tuesday. Tomato and lemon could not be re-based: their slugs collide with the site's category rollup, so they keep a single-day figure and say so.
- **Two rows are proxies, not the item.** The disposable 1 L and 2 L karak flasks do not have a findable bulk price anywhere in the UAE. They are priced off a Falcon Pack PET bottle-and-cap at the same volumes, labelled as a proxy, with the 2 L extrapolated. This is the weakest row in the set and it is flagged in place.
- **Brand tier is a choice, not a fact.** Evaporated milk ranges from AED 7.12/L for a generic carton to AED 13.72/L for Rainbow; cooking cream from AED 5.60 to AED 19.08/L. We chose the tier a mid-market cafeteria actually buys and said so per row. A different tier is a defensible different answer, not a correction.

## What moved, and by how much

The old sheet was not uniformly cheap. It was uniformly arbitrary - some lines a fifth of reality, others double it - which is what you would expect of numbers chosen to make a total come out round.

**Badly understated:**

| Line | Was | Now | Factor |
|---|---|---|---|
| Chicken boneless | 3.45/kg | 18.00/kg | **5.2x** |
| Chicken wings | 2.90/kg | 13.50/kg | **4.7x** |
| Salt | 0.84/kg | 2.56/kg | 3.0x |
| Evaporated milk | 4.69/L | 11.51/L | 2.5x |
| Condensed milk | 7.65/kg | 19.86/kg | 2.6x |
| Kasuri methi | 52.00/kg | 135.00/kg | 2.6x |
| Takeaway container | 0.33/pc | 0.585/pc | 1.8x |
| Beef boneless | 13.60/kg | 22.00/kg | 1.6x |

**Overstated - the sheet was not biased in one direction:**

| Line | Was | Now |
|---|---|---|
| Ginger | 6.80/kg | 2.95/kg |
| Cumin seed | 32.00/kg | 16.50/kg |
| Corn starch | 12.00/kg | 6.45/kg |
| Green cardamom | 296.00/kg | 190.00/kg |
| Dry ginger | 72.00/kg | 50.80/kg |
| White pepper | 92.00/kg | 55.80/kg |
| Garlic peeled | 9.20/kg | 9.00/kg (pack corrected 5 kg box to 1 kg tub) |

**Close enough to leave nearly alone:** onion, tomato, lemon, capsicum, ghee, yoghurt, paneer, sunflower oil, tomato ketchup, CTC black tea, Boost, Horlicks.
Capsicum is the neat case - the single-day quote suggested a 2.5x miss, and the 56-day average landed within 6% of what the paper already said.

## Three findings that are not prices

**The chicken number was the symptom, not the disease.** Chicken wings were wrong by the same factor, condensed milk by 2.6x, the takeaway container by 1.8x. The understatement was systematic across imported and processed goods - anything where a plausible-sounding number could not be checked against a supermarket shelf.

**"Habbat Al Hamra" was misdescribed.** The paper prints it as a tea blend. Every UAE source that sells it shows a **seed** product - red seeds of the garden-cress family, sometimes sold as aliv or asario, brewed into a milky drink. A wrong ingredient identity survives every price correction, so this one was fixed in the description as well as the number.

**Pack sizes have to be ones that exist.** Three packs on the old papers were shapes no UAE supplier sells: a 500 g bag of curry leaves (sold in 50-100 g packs), a 5 kg box of peeled garlic (sold in 1 kg tubs), and a 25 kg sack of toor dal (sold in 15 kg). Those are corrected. A pack nobody sells is the same class of error as a price nobody charges.

## One constraint that is ours, not the market's

Real Gulf evaporated milk is labelled in **grams** - a Rainbow carton is 48x410g.
The papers print **48x400ml**, in millilitres, and that is deliberate: the recipes measure evaporated milk in millilitres, so a mass pack would fail the unit conversion in `plates.to_base_qty` and every karak on the menu would read *incomplete* rather than costed.
Millilitre-labelled evaporated milk does exist, so the paper is not lying; but the choice was driven by the recipe's unit and it should not be mistaken for a rounding decision.
The price per litre is taken from the real gram-labelled cartons.

## The table

Every line on the four preparation papers (KAS-1 to KAS-4).
KAS-5 repeats four of KAS-3's packs a week later and is covered in the money-moment section of the README.
Prices are what the paper prints: **ex-VAT**, per pack.

| Material | Paper | Pack | AED ex-VAT | Per base unit | Was | Source (seen 2026-09-01) | Confidence |
|---|---|---|---|---|---|---|---|
| Onion | KAS-1 | 10 kg bag | 17.90 | **1.79 /kg** | 22.00 | [Al Aweer Central Market, 57-day average](https://alaweerprices.com/price/onion) - unstated (open-market wholesale) | solid |
| Tomato | KAS-1 | 6 kg box | 16.50 | **2.75 /kg** | 15.00 | [Al Aweer Central Market, single day 30/08](https://alaweerprices.com/) - unstated (open-market wholesale) | thin - single day, no clean per-variety history |
| Capsicum | KAS-1 | 5 kg box | 19.75 | **3.95 /kg** | 21.00 | [Al Aweer Central Market, 56-day average](https://alaweerprices.com/price/capsicum-green) - unstated (open-market wholesale) | solid |
| Ginger | KAS-1 | 5 kg box | 14.75 | **2.95 /kg** | 34.00 | [Al Aweer Central Market, 56-day average](https://alaweerprices.com/price/ginger) - unstated (open-market wholesale) | solid |
| Garlic | KAS-1 | 1 kg tub | 9.00 | **9.00 /kg** | 46.00/5 kg | [Sidco Foods, frozen peeled garlic 1 kg](https://sidcofoods.ae/product/frozen-peeled-garlic-1-kg/) - incl. VAT | thin - two named suppliers ~2x apart |
| Green chilli | KAS-1 | 1 kg bag | 7.60 | **7.60 /kg** | 9.50 | [Al Aweer Central Market, 56-day average](https://alaweerprices.com/price/green-chilli) - unstated (open-market wholesale) | solid |
| Coriander, fresh | KAS-1 | 1 kg bag | 8.50 | **8.50 /kg** | 12.00 | [Fresh Focus Food Stuff, coriander by the kg (HORECA)](https://freshfocusfoodstuff.com/products/coriander-leaves/) - unstated | solid direction, thin on VAT basis |
| Curry leaves | KAS-1 | 100 g pkt | 2.50 | **25.00 /kg** | 11.00/500 g | [Chefmart + Barakat Fresh, both AED 2.60/100 g](https://chefmart.ae/product/curry-leaves/) - incl. VAT (Barakat) | solid - two-source agreement |
| Spring onion | KAS-1 | 2 kg bag | 30.00 | **15.00 /kg** | 16.00 | [Fresh Focus Food Stuff, spring onion](https://freshfocusfoodstuff.com/products/herbs-spring-onion/) - unstated | solid |
| Lemon | KAS-1 | 5 kg box | 18.50 | **3.70 /kg** | 19.50 | [Al Aweer Central Market, single day 30/08](https://alaweerprices.com/) - unstated (open-market wholesale) | thin - single day, no clean per-variety history |
| Mushroom | KAS-1 | 2 kg box | 42.00 | **21.00 /kg** | 27.00 | [NRTC Fresh + Fresh Mart, same 2 kg pack](https://freshmartuae.com/product/mushroom-button-box/) - unstated | thin - no case/carton wholesale quote published |
| Spinach | KAS-1 | 2 kg box | 16.00 | **8.00 /kg** | 13.00 | [Barakat Fresh](https://barakatfresh.ae/spinach-250g.html) - incl. VAT | solid |
| Cauliflower | KAS-1 | 6 kg box | 24.65 | **4.11 /kg** | 18.00 | [Al Aweer Central Market, 56-day average](https://alaweerprices.com/price/cauliflower) - unstated (open-market wholesale) | solid |
| Green peas | KAS-1 | 1 kg bag | 7.00 | **7.00 /kg** | 8.75 | [Horeca Market, frozen green peas](https://horecamarket.ae/product/frozen-green-peas/) - ex-VAT (explicit) | solid |
| Coconut, grated | KAS-1 | 1 kg bag | 22.40 | **22.40 /kg** | 14.00 | [Sidco Foods, grated coconut 1 kg](https://sidcofoods.ae/product/coconut-grated-1kg/) - incl. VAT (explicit) | thin - single source |
| Ginger-garlic paste | KAS-1 | 1 kg tub | 20.00 | **20.00 /kg** | 18.00 | [Tradeling, Ahmed Foods ginger garlic paste](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| White sugar | KAS-2 | 50 kg sack | 125.50 | **2.51 /kg** | 115.00 | [Tradeling, Khaleej Sugar 50 kg](https://www.tradeling.com/ae-en/product-details/khaleej-sugar-50-kg-69f61e641b90afb3e691aa1a) - incl. VAT | solid |
| Salt | KAS-2 | 25 kg sack | 64.00 | **2.56 /kg** | 21.00 | [Tradeling, Gulf Salt + Coral Salt 25 kg bags (scraped)](https://www.tradeling.com/ae-en/product-details/gulf-salt-25kg-bag-6a3e5d5b38f2e564a8e83aec) - incl. VAT | solid - two scraped pages |
| Red chilli powder | KAS-2 | 1 kg pkt | 30.50 | **30.50 /kg** | 17.50 | [Tradeling, Eastern chilli powder 1 kg](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | thin - brand tier judgment |
| Turmeric | KAS-2 | 1 kg pkt | 24.50 | **24.50 /kg** | 14.00 | [Tradeling, Dahab turmeric powder 1 kg](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Coriander powder | KAS-2 | 1 kg pkt | 27.00 | **27.00 /kg** | 13.50 | [Tradeling, Eastern coriander powder 1 kg](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | thin - brand tier judgment |
| Coriander seed, crushed | KAS-2 | 500 g pkt | 10.40 | **20.80 /kg** | 9.00 | [Tradeling, coriander whole/crushed](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Garam masala | KAS-2 | 500 g pkt | 14.00 | **28.00 /kg** | 22.00 | [Tradeling, Omega garam masala](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | thin - brand tier judgment |
| Cumin seed | KAS-2 | 500 g pkt | 8.25 | **16.50 /kg** | 16.00 | [Tradeling, Volga cumin seeds 1 kg](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Kashmiri chilli powder | KAS-2 | 500 g pkt | 21.30 | **42.60 /kg** | 24.00 | [Tradeling, Bayara Kashmiri chilli powder 1 kg](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Kasuri methi | KAS-2 | 250 g pkt | 33.75 | **135.00 /kg** | 13.00 | [Tradeling, Shan kasuri methi](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Black pepper, crushed | KAS-2 | 500 g pkt | 29.60 | **59.20 /kg** | 42.00 | [Tradeling, Bayara black pepper crushed 1 kg (scraped)](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| White pepper | KAS-2 | 500 g pkt | 27.90 | **55.80 /kg** | 46.00 | [Tradeling, white pepper catering packs (2nd pass)](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid - now brackets black pepper |
| Dried red chilli | KAS-2 | 1 kg pkt | 22.00 | **22.00 /kg** | 26.00 | [Tradeling, Teja red chilli whole 1 kg](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Cinnamon stick | KAS-2 | 500 g pkt | 41.75 | **83.50 /kg** | 31.00 | [Tradeling, Bayara whole cinnamon 500 g](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Green cardamom | KAS-2 | 500 g pkt | 95.00 | **190.00 /kg** | 148.00 | [Tradeling, Emperor Akbar green cardamom 1 kg](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Dry ginger | KAS-2 | 250 g pkt | 12.70 | **50.80 /kg** | 18.00 | [Tradeling, Bayara + Natural ginger powder (2nd pass)](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid - wide brand spread |
| Baking soda | KAS-2 | 1 kg pkt | 10.70 | **10.70 /kg** | 9.00 | [Tradeling, Natural baking soda 1 kg (scraped)](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Corn flour | KAS-2 | 1 kg pkt | 8.35 | **8.35 /kg** | 11.50 | [Tradeling, corn flour catering](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Corn starch | KAS-2 | 1 kg pkt | 6.45 | **6.45 /kg** | 12.00 | [Tradeling, corn starch catering](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Toor dal | KAS-2 | 15 kg sack | 91.00 | **6.07 /kg** | 148.00/25 kg | [Tradeling, Volga toor dal 15 kg](https://www.tradeling.com/ae-en/product-details/volga-toor-dal-15-kg-63735cc2da9cc4a458133c36) - incl. VAT | solid - pack shrunk to the one that exists |
| Cashew nuts | KAS-2 | 1 kg pkt | 89.70 | **89.70 /kg** | 64.00 | [Tradeling, ATF cashew W320 1 kg](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid - exact grade match |
| Pistachio, slivered | KAS-2 | 500 g pkt | 112.10 | **224.20 /kg** | 92.00 | [Tradeling, Nicense + Natural slivered pistachio (2nd pass)](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid - slivered, not whole |
| Desiccated coconut | KAS-2 | 1 kg pkt | 25.00 | **25.00 /kg** | 21.00 | [Tradeling, Omega desiccated coconut 1 kg](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Saffron | KAS-2 | 50 g tin | 465.00 | **9300.00 /kg** | 340.00 | [Tradeling, saffron 50 g (scraped)](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Evaporated milk | KAS-3 | 48x400ml ctn | 221.00 | **11.51 /litre** | 90.00 | [Rainbow evap, 7 listings; Amazon.ae + Ebsouq state VAT](https://www.amazon.ae/Rainbow-Evaporated-Milk-Grams-Pieces/dp/B07V6DCKH8) - incl. VAT (explicit) | solid - AED 11.18-12.58/L cluster |
| Condensed milk | KAS-3 | 48x395g ctn | 376.50 | **19.86 /kg** | 145.00 | [Tradeling, Rainbow condensed 397 g x48](https://www.tradeling.com/ae-en/catalog/) - incl. VAT (explicit) | solid |
| Fresh milk | KAS-3 | 12x1l ctn | 56.50 | **4.71 /litre** | 42.00 | [Tradeling, Al Ain long life full cream 1 L x12](https://www.tradeling.com/ae-en/catalog/) - incl. VAT (explicit) | solid |
| Milk powder | KAS-3 | 25 kg sack | 333.50 | **13.34 /kg** | 395.00 | [Tradeling, VOLGA instant full cream 25 kg (2nd pass)](https://www.tradeling.com/ae-en/catalog/) - incl. VAT (explicit) | solid |
| Butter | KAS-3 | 10 kg ctn | 265.00 | **26.50 /kg** | 235.00 | [Femco, Milkrich unsalted butter 25 kg](https://www.femco.ae/fem/product/milkrich-unsalted-butter/) - incl. VAT (explicit) | solid |
| Ghee | KAS-3 | 5 kg tin | 146.50 | **29.30 /kg** | 148.00 | [Tradeling, Assel vegetable ghee 4.6 kg](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Cream, cooking | KAS-3 | 12x1l ctn | 160.00 | **13.33 /litre** | 96.00 | [Tradeling + Goodness UAE, Pristine 26% 12x1L (2nd pass)](https://goodnessuae.com/) - incl. VAT | solid - mid-market tier |
| Yoghurt | KAS-3 | 5 kg tub | 31.50 | **6.30 /kg** | 34.00 | [Baladi Foodstuff + UAE Ministry of Economy dashboard](https://www.baladifoodstuff.com/products/chtoora-yoghurt) - unstated | solid - two independent sources |
| Egg | KAS-3 | 1.8 kg tray | 15.80 | **8.78 /kg** | 13.50 | [Al Wholesale + Freshfocus, 12-tray carton ~AED 190 (2nd pass)](https://freshfocusfoodstuff.com/) - unstated | thin - VAT basis unstated |
| Paneer | KAS-3 | 1 kg pkt | 25.00 | **25.00 /kg** | 26.00 | [Horeca Market, frozen paneer cubes 1 kg](https://horecamarket.ae/product/frozen-paneer-cubes/) - ex-VAT (explicit) | solid |
| Chicken, boneless | KAS-3 | 10 kg ctn | 180.00 | **18.00 /kg** | 34.50 | [Horeca Market, frozen chicken breast, + 3 more](https://horecamarket.ae/product/frozen-chicken-breast/) - ex-VAT (explicit) | solid - AED 16-20/kg band |
| Chicken wings | KAS-3 | 10 kg ctn | 135.00 | **13.50 /kg** | 29.00 | [Horeca Market, frozen chicken wings](https://horecamarket.ae/) - ex-VAT (explicit) | solid - AED 11.50-18.40 band |
| Beef, boneless | KAS-3 | 5 kg ctn | 110.00 | **22.00 /kg** | 68.00 | [Horeca Market, boneless beef listings](https://horecamarket.ae/product-tag/boneless/) - ex-VAT (explicit) | estimate - interpolated between named cuts |
| Prawns, peeled | KAS-3 | 1 kg bag | 24.00 | **24.00 /kg** | 38.00 | [Horeca Market PUD 40/60 + 3 grade-matched (2nd pass)](https://horecamarket.ae/product/frozen-shrimps-pud-40-60-1-kg-pkt/) - ex-VAT (explicit) | thin - AED 18-32/kg grade spread |
| CTC black tea | KAS-4 | 5 kg bag | 85.00 | **17.00 /kg** | 92.00 | [Tradeling, Alokozay CTC loose black tea catering 5 kg](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Instant coffee | KAS-4 | 200 g jar | 17.62 | **88.10 /kg** | 78.00 | [Nescafe Classic 200 g jar - no catering tin listed anywhere](https://www.tradeling.com/ae-en/catalog/) - incl. VAT (retail) | estimate-from-retail - jar-derived, cheap end |
| Kashmiri green tea leaves | KAS-4 | 1 kg pkt | 87.00 | **87.00 /kg** | 54.00 | [Alokozay Green Gun Powder loose tea - PROXY](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | PROXY - Kashmiri tea NOT FOUND under its own name |
| Habbat Al Hamra blend | KAS-4 | 1 kg pkt | 26.50 | **26.50 /kg** | 68.00 | [Union Coop, Asario / cress seed, several SKUs](https://www.unioncoop.ae/) - incl. VAT (explicit) | solid - identity corrected to a seed |
| Boost powder | KAS-4 | 450 g tin | 21.45 | **47.67 /kg** | 22.50 | [Tradeling, Boost instant 500 g](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Horlicks powder | KAS-4 | 500 g tin | 21.00 | **42.00 /kg** | 24.00 | [Tradeling, Horlicks classic malt 500 g](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Drinking chocolate powder | KAS-4 | 1 kg tin | 71.50 | **71.50 /kg** | 34.00 | [Tradeling, Arkadia drinking chocolate 40% 1 kg](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Cocoa powder | KAS-4 | 1 kg tin | 73.20 | **73.20 /kg** | 42.00 | [Tradeling, cocoa powder catalog](https://www.tradeling.com/ae-en/catalog/cacao-chocolate-powder) - incl. VAT | solid |
| Sahlab powder | KAS-4 | 500 g pkt | 19.95 | **39.90 /kg** | 28.00 | [Union Coop, sahlab 500 g](https://www.unioncoop.ae/) - incl. VAT (retail) | solid |
| Rose water | KAS-4 | 500 ml btl | 3.35 | **6.70 /litre** | 6.50 | [Tradeling, Virginia Green Garden rose water 450 ml](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Oil | KAS-4 | 5 l tin | 37.50 | **7.50 /litre** | 39.00 | [Tradeling, Top Chef pure sunflower oil 5 L](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Vinegar | KAS-4 | 5 l can | 20.90 | **4.18 /litre** | 14.00 | [Tradeling, Real Value white vinegar 1 gal x4](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | thin - pack shape differs |
| Light soy sauce | KAS-4 | 4 l can | 17.50 | **4.38 /litre** | 32.00/5 l | [fnb.addtocart.ae, Daily Fresh soy sauce 4x4 L](https://fnb.addtocart.ae/) - unstated | thin |
| Red chilli sauce | KAS-4 | 5 l can | 64.00 | **12.80 /litre** | 29.00 | [Tradeling small-bottle cartons as a floor](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | estimate - no bulk-can SKU exists |
| Tomato ketchup | KAS-4 | 5 l can | 27.25 | **5.45 /litre** | 26.00 | [Tradeling, Vital Foods ketchup 5 kg jerry can x4](https://www.tradeling.com/ae-en/catalog/) - incl. VAT | solid |
| Honey cake, whole (10 slices) | KAS-4 | 1 pc | 57.00 | **57.00 /each** | 34.00 | [Carrefour UAE bakery whole cakes](https://www.carrefouruae.com/mafuae/en/) - incl. VAT (retail) | estimate-from-retail |
| Zafran cake, whole (10 slices) | KAS-4 | 1 pc | 35.00 | **35.00 /each** | 36.00 | [Brownie Point Dubai, saffron milk cake](https://browniepointuae.com/product_inquiry/saffron-milk-cake) - incl. VAT (retail) | estimate-from-retail |
| Lotus cake, whole (10 slices) | KAS-4 | 1 pc | 51.50 | **51.50 /each** | 42.00 | [Carrefour UAE bakery whole cakes](https://www.carrefouruae.com/mafuae/en/) - incl. VAT (retail) | estimate-from-retail |
| Cake box + fork | KAS-4 | 100 pcs ctn | 42.00 | **0.42 /each** | 38.00 | [Alibaba FOB ballpark only](https://www.alibaba.com/) - unstated | weak - no UAE-stocked combo SKU |
| Delivery cup S + lid | KAS-4 | 100 pcs ctn | 23.00 | **0.23 /each** | 21.00 | [Falcon Pack Online, paper cup + lid (lid size proxy)](https://falconpackonline.com/en/product/100940-6291055074441-paper-cup) - unstated | thin - lid is a size proxy |
| Delivery cup M + lid | KAS-4 | 100 pcs ctn | 27.20 | **0.27 /each** | 24.00 | [Falcon Pack Online, cup 19.11 + lid 8.09](https://falconpackonline.com/en/product/203602-62910552344870-paper-cup) - unstated | solid arithmetic, thin VAT basis |
| Delivery cup L + lid | KAS-4 | 100 pcs ctn | 33.20 | **0.33 /each** | 28.00 | [Falcon Pack Online, cup 25.10 + lid 8.09](https://falconpackonline.com/en/) - unstated | solid arithmetic, thin VAT basis |
| Disposable flask 1 L | KAS-4 | 50 pcs ctn | 67.00 | **1.34 /each** | 62.00 | [Falcon Pack 1000 ml PET bottle + cap - PROXY](https://falconpackonline.com/en/) - unstated | PROXY - not the insulated flask |
| Disposable flask 2 L | KAS-4 | 50 pcs ctn | 101.50 | **2.03 /each** | 88.00 | [Falcon Pack 1000/1500 ml, extrapolated to 2 L - PROXY](https://falconpackonline.com/en/) - unstated | PROXY + extrapolation - weakest row |
| Paper cup small + lid | KAS-4 | 100 pcs ctn | 12.00 | **0.12 /each** | 17.50 | [Falcon Pack Online, cup 5.46 + lid 6.52 (proxy lid)](https://falconpackonline.com/en/) - unstated | thin |
| Paper cup large + lid | KAS-4 | 100 pcs ctn | 20.30 | **0.20 /each** | 21.00 | [Falcon Pack Online, cup 12.18 + lid 8.09](https://falconpackonline.com/en/) - unstated | solid arithmetic, thin VAT basis |
| Takeaway container + lid | KAS-4 | 100 pcs ctn | 58.50 | **0.58 /each** | 33.00 | [Falcon Pack Online, 750 ml tub + lid kit](https://falconpackonline.com/en/) - unstated | solid - two SKUs agree within 3.5% |

## Where each number came from, in full

The per-row evidence - every listing seen, its pack, its price, its VAT basis and the arithmetic - is in `price-research/`, one file per product family:

| File | Covers |
|---|---|
| `A-produce.md` | KAS-1, the 16 fresh produce lines |
| `B-dry-spices.md` | KAS-2, sugar, salt, spices, dals, nuts |
| `C-dairy-protein.md` | KAS-3, dairy, eggs, paneer, frozen proteins |
| `D1-beverage-bakery.md` | KAS-4, tea, beverage powders, bought-in cakes |
| `D2-oils-sauces-packaging.md` | KAS-4, oils, sauces, every disposable |

They record the prices that were *rejected* as well as the ones chosen, which is what makes a brand-tier decision auditable rather than arbitrary, and each carries a "second pass" section showing which rows were re-checked and why.
