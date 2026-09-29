"""
price_watch.py
================
يقرأ صفحات مواقع تجميع المنشورات، يستخرج أسعار فئات منتجات معيّنة
(زيت، بيض، صلصة طماطم، طماطم/خضار، فواكه)، ويبني جدول مقارنة.

بُني على فحص فعلي لبنية الصفحات الحقيقية (مو تخمين):
- Eurospin/Lidl/Pam/Penny على confrontavolantini.com: صفحة نصية منظمة
  بشكل "- اسم المنتج (كمية): X,XX € — pag. N" تحت عناوين فئات "### ...".
  هذي ثقة عالية.
- Il Gigante/TIGROS على anteprimavolantino.it: لا توجد صفحة منظمة، فقط
  صفحة تصنيف ثابتة نجيب منها رابط آخر مقال، والمقال نثر عادي يذكر أسعار
  متفرقة داخل الجمل. ثقة أقل، ونعلّمها بوضوح بالتقرير.
- D-più: كل المصادر المفحوصة (confrontavolantini, anteprimavolantino,
  kimbino, doveconviene) تعرضه كصور تُقلّب فقط، بدون نص. غير مغطى آليًا.
"""

import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

HEADERS = {"User-Agent": "Mozilla/5.0 (Se3ra price-watch bot; personal project)"}

# ---------------------------------------------------------------------------
# مصادر ثقة عالية: نص منظم بشكل ثابت
HIGH_CONFIDENCE_STORES = {
    "Eurospin": "https://confrontavolantini.com/anteprima/anteprima-nuovo-volantino-eurospin",
    "Lidl":     "https://confrontavolantini.com/anteprima/anteprima-nuovo-volantino-lidl",
    "Pam":      "https://confrontavolantini.com/anteprima/anteprima-nuovo-volantino-pam",
    "Penny":    "https://confrontavolantini.com/anteprima/anteprima-nuovo-volantino-penny",
    "Ipercoop": "https://confrontavolantini.com/anteprima/anteprima-nuovo-volantino-ipercoop",
}

# مصادر ثقة أقل: صفحة تصنيف ثابتة تودّي لمقال متجدد أسبوعيًا، نص نثري
LOW_CONFIDENCE_STORES = {
    "Il Gigante": "https://www.anteprimavolantino.it/il-gigante/",
    "TIGROS":     "https://www.anteprimavolantino.it/tigros/",
}

# غير مغطى آليًا (صور فقط بكل المصادر المفحوصة) — يُذكر بالتقرير فقط
UNSUPPORTED_STORES = ["D-più"]

# فئات المنتجات، بترتيب أولوية: أول فئة تطابق اسم المنتج تفوز، وما نكرر
# المنتج بفئة ثانية (يحل مشكلة "Passata di pomodoro" اللي كانت تتكرر).
CATEGORY_PRIORITY = [
    ("صلصة طماطم", ["passata", "polpa di pomodoro", "sugo"]),
    ("زيت",        ["olio"]),
    ("بيض",        ["uova", "uovo"]),
    ("فواكه",      ["mele", "uva", "arance", "pesche", "banane", "kiwi", "mirtilli",
                     "susine", "ananas", "limoni", "avocado", "frutta"]),
    ("طماطم/خضار", ["pomodor", "zucchine", "insalata", "verdura", "cipolle",
                     "patate", "melanzane", "spinaci", "cetrioli", "funghi"]),
]

# نمط السطر المنظم بصفحات confrontavolantini.com:
# "- اسم المنتج (كمية): 1,99 € — pag. 3"  (الكمية اختيارية)
STRUCTURED_LINE = re.compile(
    r"^-\s*(?P<name>.+?)(?:\s*\((?P<qty>[^)]+)\))?\s*:\s*(?P<price>[\d]+,[\d]{2})\s*€",
    re.UNICODE
)

# نمط فضفاض للنثر بصفحات anteprimavolantino.it: "... اسم قبل السعر ... a 4,29 euro"
PROSE_PRICE = re.compile(
    r"([A-ZÀ-Ý][A-Za-zÀ-ÿ'\s]{3,50}?)\s+(?:è\s+|sono\s+|costa\s+|costano\s+)?a\s+([\d]+[,.][\d]{2})\s*(?:€|euro)",
    re.UNICODE
)


def categorize(name: str) -> str | None:
    lowered = name.lower()
    for category, keywords in CATEGORY_PRIORITY:
        if any(kw in lowered for kw in keywords):
            return category
    return None


def fetch_text(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    except requests.exceptions.RequestException as e:
        print(f"   ⚠️ فشل تحميل {url}: {e}")
        return ""


def parse_high_confidence(text: str, store: str) -> list[dict]:
    """يقرأ الأسطر المنظمة '- اسم (كمية): سعر € — pag. N'."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        m = STRUCTURED_LINE.match(line)
        if not m:
            continue
        name = m.group("name").strip()
        category = categorize(name)
        if category is None:
            continue
        rows.append({
            "category": category,
            "store": store,
            "name": name,
            "qty": (m.group("qty") or "غير محدد").strip(),
            "price": float(m.group("price").replace(",", ".")),
            "confidence": "عالية",
        })
    return rows


def find_latest_article_url(category_page_html: str, base_url: str) -> str | None:
    """يدوّر على أول رابط مقال 'volantino-<slug>' داخل صفحة التصنيف."""
    m = re.search(r'href="(https://www\.anteprimavolantino\.it/\d+/volantino-[^"]+)"', category_page_html)
    return m.group(1) if m else None


def parse_low_confidence(text: str, store: str) -> list[dict]:
    """يستخرج أسعار من نص نثري بنمط فضفاض — أقل دقة، لازم مراجعة يدوية."""
    rows = []
    for m in PROSE_PRICE.finditer(text):
        name = m.group(1).strip()
        category = categorize(name)
        if category is None:
            continue
        rows.append({
            "category": category,
            "store": store,
            "name": name,
            "qty": "غير محدد",
            "price": float(m.group(2).replace(",", ".")),
            "confidence": "⚠️ منخفضة (نص نثري)",
        })
    return rows


def run_price_watch() -> list[dict]:
    all_rows = []

    for store, url in HIGH_CONFIDENCE_STORES.items():
        print(f"🔍 [ثقة عالية] {store}: {url}")
        text = fetch_text(url)
        if text:
            rows = parse_high_confidence(text, store)
            print(f"   ✅ لُقي {len(rows)} منتج مطابق")
            all_rows.extend(rows)

    for store, category_page in LOW_CONFIDENCE_STORES.items():
        print(f"🔍 [ثقة منخفضة] {store}: {category_page}")
        try:
            r = requests.get(category_page, headers=HEADERS, timeout=20)
            r.raise_for_status()
            article_url = find_latest_article_url(r.text, category_page)
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️ فشل تحميل صفحة التصنيف: {e}")
            continue
        if not article_url:
            print("   ⚠️ ما لقيت رابط أحدث مقال")
            continue
        print(f"   → أحدث مقال: {article_url}")
        text = fetch_text(article_url)
        if text:
            rows = parse_low_confidence(text, store)
            print(f"   ⚠️ لُقي {len(rows)} منتج مطابق (يحتاج مراجعة)")
            all_rows.extend(rows)

    return all_rows


def build_report(rows: list[dict]) -> str:
    lines = [f"📋 تقرير أسعار سعرة — {datetime.now().strftime('%Y-%m-%d')}", "=" * 40]

    if not rows:
        lines.append("❌ ما انسحب أي منتج هالمرة. راجع الروابط قبل الاعتماد على التقرير.")
    else:
        categories = sorted(set(r["category"] for r in rows))
        for cat in categories:
            cat_rows = sorted([r for r in rows if r["category"] == cat], key=lambda r: r["price"])
            lines.append(f"\n🏷️ {cat}:")
            for r in cat_rows[:5]:
                lines.append(f"   {r['price']:.2f}€ — {r['name']} ({r['qty']}) — {r['store']} [{r['confidence']}]")

    lines.append("\n" + "=" * 40)
    lines.append(f"❌ غير مغطى آليًا (يحتاج متابعة يدوية): {', '.join(UNSUPPORTED_STORES)}")
    lines.append("⚠️ راجع كل الأسعار يدويًا قبل التسوق، خصوصًا المعلّمة بثقة منخفضة.")
    return "\n".join(lines)


if __name__ == "__main__":
    rows = run_price_watch()
    print("\n" + build_report(rows))

