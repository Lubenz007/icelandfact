# saganidag.is – Sagan í Dag

Daglegur „dálkur Sagnfræðingsins“: staðfestir atburðir úr íslenskri og heimssögu, afmælisbörn, orð dagsins, spurningakeppni, verðlagið þá, útvarpspistill – og **afmælisdagurinn þinn**: sláðu inn fæðingardag og sjáðu hvað gerðist þá, hve marga daga þú hefur lifað og hvað Morgunblaðið kostaði þegar þú fæddist.

Hýst á GitHub Pages (`saganidag.is` / `icelandfact.alit.is`). Engin bakendaþjónusta, engir lyklar í vafranum: allt efni er kyrrstætt JSON sem GitHub Actions býr til.

---

## Hvernig þetta virkar

```
Wikipedia (en + is) ──┐
Wikipedia pageviews ──┤   .github/scripts/generate_fact.py
Hagstofa (VNV)      ──┼──►  + Azure OpenAI GPT-5.6 (eða Gemini)  ──►  fact.json        (í dag)
mbl_prices.json     ──┘                                                days/MM-DD.json  (allir 366 dagar)
                                                                       data/verdlag.json
```

* **Grundun.** Atburðir og afmæli koma EINGÖNGU úr Wikipedia-listum; módelið velur og endursegir. Skriftan hendir sjálfkrafa öllu sem ekki finnst í heimildinni (`sanitize()`).
* **Afmælisbörn** eru raðað eftir raunverulegum flettingum á Wikipedia síðustu 30 daga, svo Serena Williams vinnur af óþekktum barón. Íslensk afmælisbörn koma úr „Fædd“-kafla íslensku Wikipediu.
* **Mynd dagsins** er raunveruleg Wikipedia-mynd við einn valinn atburð.
* **Landshluti** er merktur á hvern íslenskan atburð (Suðurland, Norðurland …).
* **Spurningakeppni** (3 krossaspurningar) er smíðuð eingöngu úr atburðunum sem voru valdir – svarið er alltaf í gögnunum.
* **Útvarpspistill** – 60–90 orð tilbúin til upplesturs, með „Afrita“-hnappi. Frjálst til notkunar í útvarpi ef saganidag.is er nefnt.
* **Verðlag** er reiknað úr vísitölu neysluverðs Hagstofunnar og staðfestum Morgunblaðsverðum – aldrei giskað.

Vafrinn sækir `fact.json` fyrir daginn í dag og `days/MM-DD.json` fyrir afmælisdaga. `?d=03-14&y=1992` opnar afmælissýn beint (deilanlegur hlekkur).

---

## Uppsetning

### 1. Leyndarmál (Settings → Secrets and variables → Actions)

| Secret | Hlutverk |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | t.d. `https://<nafn>.openai.azure.com/openai/v1` (aðalveitandi) |
| `AZURE_OPENAI_KEY` | Azure API-lykill |
| `AZURE_OPENAI_DEPLOYMENT` | nafn deployment-sins, t.d. `gpt-5.6` (sjálfgefið ef sleppt) |
| `GEMINI_API_KEY` | valfrjálst – varaleið ef Azure bregst, eða eina leiðin ef Azure vantar |

Ef bæði eru til staðar er Azure reynt fyrst og Gemini ef það mistekst.

### 2. Bakfylla alla 366 daga (einu sinni)

Actions → **Backfill all days** → Run workflow. Tekur u.þ.b. 1–2 klst., committar á 20 daga fresti svo ekkert tapast. Hægt að keyra aftur hvenær sem er; sleppir dögum sem eru til nema `force` sé hakað. `only` = `03-14 12-24` fyrir staka daga.

### 3. Daglega keyrslan

**Daily Fact** keyrir kl. 01:00 UTC, skrifar `fact.json`, uppfærir `days/` fyrir daginn og `data/verdlag.json`. Hægt að ræsa handvirkt.

### 4. Keyra heima

```bash
export AZURE_OPENAI_ENDPOINT=... AZURE_OPENAI_KEY=... AZURE_OPENAI_DEPLOYMENT=gpt-5.6
python .github/scripts/generate_fact.py            # dagurinn í dag
python .github/scripts/backfill_days.py --only 03-14
python -m http.server 8000                         # opna http://localhost:8000
```

---

## Skrár

| Skrá | Hlutverk |
|---|---|
| `index.html` | Síðan öll (dagblaðaútlit, flipar „Í dag“ / „Afmælisdagurinn þinn“, spurningakeppni, deiling) |
| `fact.json` | Efni dagsins í dag |
| `days/MM-DD.json` | Efni fyrir hvern almanaksdag (ártalsóháð) |
| `data/verdlag.json` | VNV-röð Hagstofunnar + Morgunblaðsverð, notað í vafranum |
| `.github/scripts/generate_fact.py` | Öll gagnasöfnun, prompt, LLM-köll, grundunarsía |
| `.github/scripts/backfill_days.py` | Býr til alla daga |
| `.github/scripts/collect_mbl_prices.py` + `mbl_prices.json` | Staðfest Morgunblaðsverð af timarit.is |
| `qr.html` | QR-kóði á síðuna |

---

## Kostnaður

Azure GPT-5.6: ein keyrsla á dag ≈ 6–8 þúsund tókar inn, 2–3 þúsund út – nokkrir aurar. Bakfyllingin öll ≈ 366 slík köll, nokkrir dollarar einu sinni. Gemini 2.5 Flash er ókeypis innan dagskvóta og dugar líka.
