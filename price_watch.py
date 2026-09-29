"""
price_watch.py
================
يقرأ صفحات مواقع تجميع المنشورات (confrontavolantini.com و
anteprimavolantino.it) لمحلات محددة، يستخرج أسعار فئات منتجات معيّنة
(زيت، بيض، صلصة طماطم، طماطم/خضار، فواكه)، ويبني جدول مقارنة: أفضل
سعر، الكمية، والمحل.

⚠️ هذا سكربت "أفضل محاولة" (best-effort): بُني على نمط النص الملاحظ
بنتائج البحث (مثال: "Olio extra vergine di oliva Desantis (3 L): 13,99 €
— pag. 1")، لكنه ما تحقق منه على اتصال إنترنت حي بعد. أول تشغيل له
لازم يُراجع يدويًا قبل ما يُعتمد عليه — بالضبط زي ما اتفقنا.
"""

import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# المحلات المستهدفة وروابط صفحاتها على مواقع تجميع المنشورات
STORES = {
    "Eurospin": "https://confrontavolantini.com/eurospin",
    "Lidl": "https://confrontavolantini.com/anteprima/anteprima-nuovo-volantino-lidl",
    "Pam": "https://confrontavolantini.com/anteprima/anteprima-nuovo-volantino-pam",
    "Penny": "https://confrontavolantini.com/anteprima/anteprima-nuovo-volantino-penny",
    "Il Gigante": "https://www.anteprimavolantino.it/?s=il+gigante",
    "TIGROS": "https://www.anteprimavolantino.it/?s=tigros",
    "D-più": "https://www.anteprimavolantino.it/?s=d-piu",
}

# فئات المنتجات المستهدفة، وكلمات البحث الإيطالية اللي تدل عليها
CATEGORIES = {
    "زيت":        ["olio"],
    "بيض":        ["uova", "uovo"],
    "صلصة طماطم": ["passata", "polpa di pomodoro", "pomodoro a pezzetti"],
    "طماطم/خضار": ["pomodori", "pomodoro", "zucchine", "insalata", "verdura"],
    "فواكه":      ["mele", "uva", "arance", "pesche", "banane", "frutta"],
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Se3ra price-watch bot; contact: personal project)"}

# نمط استخراج: "اسم المنتج (كمية): سعر € — pag. رقم"
# مبني على الشكل الملاحظ بمصادر confrontavolantini.com
PRICE_PATTERN = re.compile(
    r"([A-Za-zÀ-ÿ0-9\s'\.\-]{4,80}?)"      # اسم المنتج
    r"\s*\(?([\d.,]+\s?(?:g|kg|ml|l|L|pz))?\)?"  # الكمية (اختيارية)
    r"\s*:?\s*([\d]+,[\d]{2})\s*€",         # السعر
    re.UNICODE
)


def fetch_page_text(url: str) -> str:
    """يجيب نص الصفحة الخام. يرجع نص فاضي عند أي فشل، بدل ما يوقف السكربت كامل."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # نشيل السكربتات والستايلات عشان ما تلخبط النص
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)
    except requests.exceptions.RequestException as e:
        print(f"   ⚠️ فشل تحميل {url}: {e}")
        return ""


def extract_matching_products(text: str, keywords: list[str]) -> list[dict]:
    """يدوّر داخل النص على أي جملة تحتوي كلمة مفتاحية، ويحاول يستخرج منها
    اسم المنتج والكمية والسعر حسب النمط."""
    results = []
    lowered_text = text.lower()
    for kw in keywords:
        idx = 0
        while True:
            pos = lowered_text.find(kw, idx)
            if pos == -1:
                break
            # ناخذ مقطع نص حوالين الكلمة المفتاحية عشان نلقى فيه السعر
            snippet = text[max(0, pos - 60): pos + 100]
            match = PRICE_PATTERN.search(snippet)
            if match:
                name, qty, price = match.groups()
                results.append({
                    "name": name.strip(" -–:"),
                    "qty": (qty or "غير محدد").strip(),
                    "price": float(price.replace(",", ".")),
                })
            idx = pos + len(kw)
    return results


def run_price_watch() -> list[dict]:
    all_rows = []
    for store_name, url in STORES.items():
        print(f"🔍 {store_name}: {url}")
        text = fetch_page_text(url)
        if not text:
            continue
        for category, keywords in CATEGORIES.items():
            products = extract_matching_products(text, keywords)
            for p in products:
                all_rows.append({
                    "category": category,
                    "store": store_name,
                    "name": p["name"],
                    "qty": p["qty"],
                    "price": p["price"],
                    "source": url,
                })
    return all_rows


def build_best_price_report(rows: list[dict]) -> str:
    """يبني تقرير نصي: أفضل سعر لكل فئة، مع الكمية والمحل، مرتب حسب الفئة."""
    if not rows:
        return "❌ ما انسحب أي منتج. راجع الروابط والنمط قبل الاعتماد على السكربت."

    report_lines = [f"📋 تقرير أسعار — {datetime.now().strftime('%Y-%m-%d')}\n" + "=" * 40]
    categories_seen = sorted(set(r["category"] for r in rows))

    for cat in categories_seen:
        cat_rows = sorted([r for r in rows if r["category"] == cat], key=lambda r: r["price"])
        report_lines.append(f"\n🏷️ {cat}:")
        for r in cat_rows[:5]:  # أفضل 5 نتائج بكل فئة
            report_lines.append(
                f"   {r['price']:.2f}€ — {r['name']} ({r['qty']}) — {r['store']}"
            )

    report_lines.append("\n" + "=" * 40)
    report_lines.append("⚠️ راجع هذي الأسعار يدويًا قبل التسوق — السكربت قد يخطئ بالاستخراج.")
    return "\n".join(report_lines)


if __name__ == "__main__":
    rows = run_price_watch()
    print("\n" + build_best_price_report(rows))

