"""Every line of every paper, extracted and compared against the source table."""
import asyncio, pathlib, sys
from decimal import Decimal
sys.path.insert(0, "apps/api/src")
sys.path.insert(0, "Docs/demo-invoices/koukh-al-shay")
from build_prompts import SUPPLIERS
from faida_api.extraction.pipeline import build_provider
from faida_api.extraction.normalize import normalize_extracted

async def main():
    key = [l.split("=",1)[1].strip() for l in pathlib.Path("apps/api/.env").read_text().splitlines()
           if l.startswith("GEMINI_API_KEY=")][0]
    provider = build_provider("gemini", gemini_api_key=key)
    bad = 0
    for paper in SUPPLIERS:
        rows = SUPPLIERS[paper][6]
        png = pathlib.Path(f"Docs/demo-invoices/koukh-al-shay/{paper}.png")
        res, _ = await provider.extract(png.read_bytes(), "image/png")
        inv = normalize_extracted(res.invoice)
        if len(inv.lines) != len(rows):
            print(f"{paper}: LINE COUNT {len(inv.lines)} != {len(rows)}"); bad += 1; continue
        for (code, desc, qty, unit, pack, price), got in zip(rows, inv.lines):
            checks = {
                "name":  (desc, (got.raw_name or "").strip()),
                "qty":   (Decimal(str(qty)), got.qty),
                "unit":  (unit, (got.unit or "").strip()),
                "pack":  (pack.replace(" ", "").lower(), (got.pack_size or "").replace(" ", "").lower()),
                "price": (Decimal(str(price)), got.unit_price),
            }
            for what, (want, have) in checks.items():
                if want != have:
                    print(f"{paper} {desc!r} {what}: printed {want!r}, read {have!r}"); bad += 1
        print(f"{paper}: {len(rows)} lines verified")
    print()
    print("MISMATCHES:", bad)

asyncio.run(main())
