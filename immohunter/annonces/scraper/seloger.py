"""SeLoger Scraper — barre de recherche, fonctionne pour toute ville."""
import re
import time
import random
from playwright.sync_api import sync_playwright
from immohunter.annonces.scraper.parser import parse_price, parse_surface, parse_rooms, parse_bedrooms, parse_location, parse_type
import config


def scrape():
    city = config.city
    postal = getattr(config, "postal_code", None)

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(user_agent=config.USER_AGENT, viewport={"width": 1920, "height": 1080}, locale="fr-FR")
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false });")
    page = ctx.new_page()

    # 1. Aller sur SeLoger
    print("[SeLoger] Ouverture seloger.com...")
    try:
        page.goto("https://www.seloger.com/", timeout=15000)
        time.sleep(4)
    except Exception as e:
        print("[SeLoger] Erreur: {}".format(e))
        browser.close(); pw.stop()
        return []

    # 2. Supprimer cookies banner
    page.evaluate("""() => {
        document.querySelectorAll('#usercentrics-root, [class*=cookie], [class*=consent], [id*=didomi]').forEach(el => el.remove());
    }""")
    time.sleep(1)
    for btn in ["Continuer sans accepter", "Tout refuser", "Deny"]:
        try:
            page.click("button:has-text('{}')".format(btn), timeout=2000)
            time.sleep(1)
            break
        except Exception:
            continue
    page.evaluate("document.querySelectorAll('#usercentrics-root').forEach(el => el.remove())")
    time.sleep(1)

    # 3. Rechercher la ville
    search_input = None
    for inp in page.query_selector_all("input"):
        ph = inp.get_attribute("placeholder") or ""
        if any(kw in ph.lower() for kw in ["ville", "lieu", "code postal", "adresse", "recherch", "saisir"]):
            search_input = inp
            break

    if not search_input:
        print("[SeLoger] Champ recherche non trouve")
        browser.close(); pw.stop()
        return []

    search_input.click()
    time.sleep(1)
    search_input.fill(city)
    time.sleep(3)

    # 4. Cliquer suggestion
    cp_str = str(postal) if postal else ""
    clicked = page.evaluate("""(args) => {
        const [term, cp] = args;
        const items = document.querySelectorAll('[role=option], [class*=suggest] li, [class*=Suggest] li, [class*=autocomplete] li');
        for (const item of items) {
            const txt = item.innerText.toLowerCase();
            if (txt.includes(term.toLowerCase())) {
                if (!cp || txt.includes(cp)) { item.click(); return item.innerText; }
            }
        }
        if (items.length > 0) { items[0].click(); return items[0].innerText; }
        return null;
    }""", [city, cp_str])

    if clicked:
        print("[SeLoger] Suggestion: {}".format(str(clicked).strip()[:50]))
    else:
        print("[SeLoger] Aucune suggestion pour '{}'".format(city))
        browser.close(); pw.stop()
        return []

    time.sleep(2)

    # 5. Cliquer Rechercher
    page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
            if (btn.innerText.toLowerCase().includes('rechercher')) { btn.click(); return; }
        }
    }""")
    time.sleep(6)
    print("[SeLoger] {}".format(page.url[:120]))

    # 6. Scraper les pages
    results = []

    for pn in range(1, config.max_pages + 1):
        if pn > 1:
            cur = page.url
            if "page=" in cur:
                new_url = re.sub(r"page=\d+", "page={}".format(pn), cur)
            else:
                new_url = "{}&page={}".format(cur, pn) if "?" in cur else "{}?page={}".format(cur, pn)
            try:
                page.goto(new_url, timeout=15000, wait_until="domcontentloaded")
                time.sleep(5)
            except Exception:
                break

        for _ in range(5):
            page.evaluate("window.scrollBy(0, window.innerHeight)")
            time.sleep(0.8)

        # Extraire texte + URL ensemble depuis chaque carte
        cards_data = page.evaluate("""() => {
            const results = [];
            const seen = new Set();
            const cards = document.querySelectorAll('[data-testid*=card]');
            for (const card of cards) {
                const text = card.innerText || '';
                if (text.length < 50 || !text.includes('\u20ac')) continue;
                const key = text.substring(0, 80);
                if (seen.has(key)) continue;
                seen.add(key);
                let href = null;
                let link = card.querySelector('a[href*=annonces]');
                if (!link) link = card.closest('a[href*=annonces]');
                if (!link) {
                    let parent = card.parentElement;
                    for (let i = 0; i < 5 && parent; i++) {
                        const a = parent.querySelector('a[href*=annonces]');
                        if (a) { link = a; break; }
                        parent = parent.parentElement;
                    }
                }
                if (link) href = link.href.split('?')[0];
                results.push({text: text.substring(0, 500), url: href});
            }
            return results;
        }""")

        count = 0
        for cd in cards_data:
            text = cd["text"]
            r = {
                "plateforme": "SeLoger",
                "prix": parse_price(text),
                "surface_m2": parse_surface(text),
                "nb_pieces": parse_rooms(text),
                "nb_chambres": parse_bedrooms(text),
                "type_bien": parse_type(text),
                "description": "",
                "url": cd["url"],
            }
            loc, cp = parse_location(text)
            r["localisation"] = loc or city
            r["code_postal"] = cp or (str(postal) if postal else None)

            if r["prix"] and r["prix"] > 10000:
                r["titre"] = "{} {} m2 - {:,} EUR".format(
                    r.get("type_bien") or "Bien", r.get("surface_m2") or "?", r["prix"])
                results.append(r)
                count += 1

        print("[SeLoger] Page {}: {} annonces".format(pn, count))
        if count == 0:
            break
        time.sleep(random.uniform(2, 4))

    # 7. Sauvegarder les annonces AVANT les descriptions
    #    Comme ca si Ctrl+C pendant les descriptions, les donnees sont preservees
    import csv as _csv
    import os as _os
    from immohunter.annonces.scraper.geo import city_to_slug
    slug = city_to_slug(city)
    csv_path = "{}/annonces_{}.csv".format(config.OUTPUT_DIR, slug)
    _os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    keys = ["plateforme", "titre", "prix", "surface_m2", "nb_pieces", "nb_chambres",
            "localisation", "code_postal", "type_bien", "url", "description"]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = _csv.DictWriter(f, fieldnames=keys, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(results)
    print("[SeLoger] {} annonces sauvegardees dans {}".format(len(results), csv_path))

    # 8. Descriptions (avec progression + sauvegarde toutes les 50)
    to_fetch = [r for r in results if r.get("url")]
    if to_fetch:
        total = len(to_fetch)
        print("[SeLoger] Descriptions: 0/{} ...".format(total))
        ok = 0
        for i, r in enumerate(to_fetch):
            try:
                page.goto(r["url"], timeout=12000, wait_until="domcontentloaded")
                time.sleep(2)
                desc = page.evaluate("""() => {
                    for (const sel of ['[data-testid*=description]', '[class*=Description]', '[class*=description]']) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.length > 50) return el.innerText.substring(0, 3000);
                    }
                    let best = '';
                    document.querySelectorAll('p').forEach(p => {
                        if (p.innerText.length > best.length && p.innerText.length > 80) best = p.innerText;
                    });
                    return best.substring(0, 3000);
                }""")
                if desc and len(desc) > 30:
                    r["description"] = desc
                    ok += 1
            except Exception:
                pass

            # Progression
            if (i + 1) % 10 == 0:
                pct = int((i + 1) / total * 100)
                print("[SeLoger] Descriptions: {}/{} ({}%) — {} OK".format(i + 1, total, pct, ok))

            # Sauvegarde toutes les 50
            if (i + 1) % 50 == 0:
                with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                    w = _csv.DictWriter(f, fieldnames=keys, delimiter=";", extrasaction="ignore")
                    w.writeheader()
                    w.writerows(results)

            time.sleep(random.uniform(1, 2))

        # Sauvegarde finale
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = _csv.DictWriter(f, fieldnames=keys, delimiter=";", extrasaction="ignore")
            w.writeheader()
            w.writerows(results)
        print("[SeLoger] {}/{} descriptions OK — sauvegarde finale".format(ok, total))

    browser.close()
    pw.stop()
    print("[SeLoger] {} annonces total".format(len(results)))
    return results
