# Discovery Engine Data Provenance Report

**Date of Audit:** November 8, 2026  
**Audited Datasets:**
1. **Primary Active Database:** `data/discovery_engine.db` (19 raw items, 19 tagged items)
2. **Historical / Full Corpus Database:** `data/discovery_engine_2153_backup.db` (2,153 raw items, 1,739 tagged items)
3. **Repository Source Files:** `data/raw_items.csv`, `data/golden_19_backup/raw_items.csv`, `data/tagged_items.csv`

---

## 1. Executive Summary & Stop-Gate Decision

Under **Step 1, Criterion 4** of the task instructions:
> *"If fewer than 20 retention-relevant, non-synthetic records have a SPECIFIC URL, STOP after this report and tell me honestly what the data is and where it came from. Do not continue and do not fill gaps. If at least 20 qualify, continue."*

### Stop-Gate Status: **TRIGGERED (STOP)**
- In the active production database (`data/discovery_engine.db`), exactly **0** non-synthetic records have a `SPECIFIC` URL.
- Every single record (19 out of 19, 100%) points to a `GENERIC` root URL (subreddit homepages, app store product pages, YouTube search query results, or forum category indices).
- Number of retention-relevant records with a `SPECIFIC` URL = **0** ($0 < 20$).
- Therefore, processing halts immediately after this report. No labelling pack or synthetic gaps are generated.

---

## 2. Primary Active Database: `data/discovery_engine.db`

### 2.1 Per-Platform Source URL Classification

| Platform (`source`) | Total Items | SPECIFIC Count | GENERIC Count | Retention Relevant (`=1`) & SPECIFIC | `collected_at` Date Range |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **reddit** | 6 | 0 | 6 | 0 | `2024-06-01T00:00:00Z` to `2024-06-01T00:00:00Z` |
| **play_store** | 3 | 0 | 3 | 0 | `2024-06-01T00:00:00Z` to `2024-06-01T00:00:00Z` |
| **youtube** | 3 | 0 | 3 | 0 | `2024-06-01T00:00:00Z` to `2024-06-01T00:00:00Z` |
| **help_forum** | 3 | 0 | 3 | 0 | `2024-06-01T00:00:00Z` to `2024-06-01T00:00:00Z` |
| **app_store** | 2 | 0 | 2 | 0 | `2024-06-01T00:00:00Z` to `2024-06-01T00:00:00Z` |
| **web** | 2 | 0 | 2 | 0 | `2024-06-01T00:00:00Z` to `2024-06-01T00:00:00Z` |
| **Total** | **19** | **0** | **19** | **0** | **`2024-06-01T00:00:00Z`** |

### 2.2 Sample URLs (Primary Database)

#### Reddit
- **SPECIFIC:** None (0 items)
- **GENERIC (all 6 items):**
  1. `https://www.reddit.com/r/IndiaInvestments/`
  2. `https://www.reddit.com/r/IndianStreetBets/`
  3. `https://www.reddit.com/r/IndiaInvestments/`
  4. `https://www.reddit.com/r/IndianStreetBets/`
  5. `https://www.reddit.com/r/IndiaInvestments/`

#### Play Store
- **SPECIFIC:** None (0 items)
- **GENERIC (all 3 items):**
  1. `https://play.google.com/store/apps/details?id=com.nextbillion.groww`
  2. `https://play.google.com/store/apps/details?id=com.nextbillion.groww`
  3. `https://play.google.com/store/apps/details?id=com.nextbillion.groww`

#### YouTube
- **SPECIFIC:** None (0 items)
- **GENERIC (all 3 items):**
  1. `https://www.youtube.com/results?search_query=groww+sip+mutual+funds`
  2. `https://www.youtube.com/results?search_query=groww+smallcap+sip`
  3. `https://www.youtube.com/results?search_query=groww+sip+hidden+charges`

#### Help Forum
- **SPECIFIC:** None (0 items)
- **GENERIC (all 3 items):**
  1. `https://tradingqna.com/c/mutual-funds/`
  2. `https://tradingqna.com/c/mutual-funds/`
  3. `https://tradingqna.com/c/mutual-funds/`

#### App Store
- **SPECIFIC:** None (0 items)
- **GENERIC (all 2 items):**
  1. `https://apps.apple.com/in/app/groww-stocks-mutual-fund-upi/id1404871703`
  2. `https://apps.apple.com/in/app/groww-stocks-mutual-fund-upi/id1404871703`

#### Web
- **SPECIFIC:** None (0 items)
- **GENERIC (all 2 items):**
  1. `https://www.google.com/search?q=why+first+time+investors+stop+sip+india`
  2. `https://www.google.com/search?q=is+groww+safe+for+sip+mutual+funds`

### 2.3 Data Integrity & Anomaly Checks (`data/discovery_engine.db`)
- **Identical `collected_at` Timestamps:** 19 out of 19 items (100.0%) share the exact timestamp `2024-06-01T00:00:00Z`.
- **Blank `app_name`:** 19 out of 19 items (100.0%) have an empty/blank `app_name` field.
- **Text Duplication:** 0 duplicate texts (19 unique texts across 19 rows).

---

## 3. Historical / Full Corpus Database: `data/discovery_engine_2153_backup.db`

To provide complete transparency across the entire repository, we also audited the full historical dataset containing 2,153 raw records.

### 3.1 Per-Platform Source URL Classification

| Platform (`source`) | Total Items | SPECIFIC Count | GENERIC Count | Retention Relevant (`=1`) & SPECIFIC | `collected_at` Date Range |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **play_store** | 1,128 | 17 | 1,111 | 3 | `2024-06-01T00:00:00Z` to `2026-10-24T09:50:37Z` |
| **app_store** | 373 | 2 | 371 | 2 | `2024-06-01T00:00:00Z` to `2026-10-22T17:03:00Z` |
| **help_forum** | 317 | 317 | 0 | 122 | `2024-06-01T00:00:00Z` to `2026-10-22T17:12:32Z` |
| **youtube** | 299 | 299 | 0 | 42 | `2024-06-01T00:00:00Z` to `2026-10-22T17:13:18Z` |
| **reddit** | 34 | 34 | 0 | 29 | `2024-06-01T00:00:00Z` to `2026-10-22T17:04:44Z` |
| **web** | 2 | 0 | 2 | 0 | `2024-06-01T00:00:00Z` to `2024-06-01T00:00:00Z` |
| **Total** | **2,153** | **669** | **1,484** | **198** | `2024-06-01T00:00:00Z` to `2026-10-24T09:50:37Z` |

### 3.2 Sample URLs (Backup Database)

#### Reddit
- **SPECIFIC (34 items - Note: these are slug-only synthetic permalinks):**
  1. `https://reddit.com/r/IndiaInvestments/comments/first_sip_negative_returns`
  2. `https://reddit.com/r/IndianStreetBets/comments/election_crash_stopped_sip`
  3. `https://reddit.com/r/IndiaInvestments/comments/sip_feels_like_a_bill`
  4. `https://reddit.com/r/IndianStreetBets/comments/sip_vs_ipo_fomo`
  5. `https://reddit.com/r/IndiaInvestments/comments/layoffs_restarting_sip_friction`
- **GENERIC:** None

#### Play Store
- **SPECIFIC (17 items):**
  1. `https://play.google.com/store/apps/details?id=com.nextbillion.groww&review=101` (mock parameter)
  2. `https://play.google.com/store/apps/details?id=com.nextbillion.groww&review=205` (mock parameter)
  3. `https://play.google.com/store/apps/details?id=com.nextbillion.groww&review=301` (mock parameter)
  4. `https://play.google.com/store/apps/details?id=com.nextbillion.groww&reviewId=ae074fad-fed3-4e4f-9068-716ec1645729` (Apify ID, not scored)
  5. `https://play.google.com/store/apps/details?id=com.nextbillion.groww&reviewId=aa890bdf-8732-4a02-81e8-529693ac3c75` (Apify ID, not scored)
- **GENERIC (1,111 items):**
  1. `https://play.google.com/store/apps/details?id=com.nextbillion.groww`
  2. `https://play.google.com/store/apps/details?id=com.nextbillion.groww`
  3. `https://play.google.com/store/apps/details?id=com.nextbillion.groww`
  4. `https://play.google.com/store/apps/details?id=com.nextbillion.groww`
  5. `https://play.google.com/store/apps/details?id=com.nextbillion.groww`

#### YouTube
- **SPECIFIC (299 items):**
  1. `https://youtube.com/watch?v=groww_sip_review#c1` (mock video id)
  2. `https://youtube.com/watch?v=smallcap_sip_truth#c12` (mock video id)
  3. `https://youtube.com/watch?v=hidden_charges_sip_groww#c4` (mock video id)
  4. `https://www.youtube.com/watch?v=WpijDxpIM8s` (repeated video URL, no comment ID)
  5. `https://www.youtube.com/watch?v=WpijDxpIM8s` (repeated video URL, no comment ID)
- **GENERIC:** None

#### Help Forum
- **SPECIFIC (317 items):**
  1. `https://tradingqna.com/t/first-time-investor-sip-churn-in-corrections/8841`
  2. `https://tradingqna.com/t/groww-mutual-fund-nav-confusion-first-sip/9912`
  3. `https://tradingqna.com/t/underperforming-sip-comparison-switch/10420`
  4. `https://tradingqna.com/t/topic/117119`
  5. `https://tradingqna.com/t/topic/198362`
- **GENERIC:** None

#### App Store
- **SPECIFIC (2 items):**
  1. `https://apps.apple.com/in/app/groww-stocks-mutual-fund/id1404871703?review=502`
  2. `https://apps.apple.com/in/app/groww-stocks-mutual-fund/id1404871703?review=410`
- **GENERIC (371 items):**
  1. `https://apps.apple.com/in/app/id1404871703`
  2. `https://apps.apple.com/in/app/id1404871703`
  3. `https://apps.apple.com/in/app/id1404871703`
  4. `https://apps.apple.com/in/app/id1404871703`
  5. `https://apps.apple.com/in/app/id1404871703`

#### Web
- **SPECIFIC:** None (0 items)
- **GENERIC (2 items):**
  1. `https://duckduckgo.com/?q=why+first+time+investors+stop+sip+india`
  2. `https://duckduckgo.com/?q=is+groww+safe+for+sip+mutual+funds`

### 3.3 Data Integrity & Anomaly Checks (`data/discovery_engine_2153_backup.db`)
- **Identical `collected_at` Timestamps:**
  - 444 items share `2026-10-22T19:04:14.287402+00:00`
  - 414 items share `2026-10-24T09:50:37.385714+00:00`
  - 371 items share `2026-10-22T17:03:00.371993+00:00`
  - 310 items share `2026-10-22T17:03:12.806647+00:00`
  - 261 items share `2026-10-22T17:02:45.771472+00:00`
  - 19 items share `2024-06-01T00:00:00Z`
  - Over 84% of records originate from 5 automated batch scrape runs.
- **Blank `app_name`:** 19 out of 2,153 items (0.9%) have an empty `app_name`.
- **Text Duplication:** 0 duplicate texts (2,153 unique texts across 2,153 rows).

---

## 4. Honest Explanation of Data Provenance

### Where Did This Data Originate?

1. **The Active Database (`data/discovery_engine.db` - 19 Golden Records):**
   - This database holds the **"Golden 19 Baseline"**, which was curated as a benchmark demonstration suite covering 10 distinct SIP drop-off problem areas (e.g., *Unrealistic Return Expectations*, *Early Portfolio Shock*, *Rigid Mandate Controls*).
   - In earlier iterations (see `data/golden_19_backup/raw_items.csv`), these 19 items were assigned mock slug URLs (e.g. `reddit.com/.../comments/first_sip_negative_returns` and `...&review=101`).
   - Because those synthetic slugs returned 404 HTTP errors if clicked, a later data sanitization step replaced all URLs with clean generic platform landing pages (`reddit.com/r/IndiaInvestments/`, `play.google.com/store/apps/details?id=com.nextbillion.groww`, etc.).
   - Consequently, in the active database, **zero items point to a specific post, comment, or individual review permalink**.

2. **The App Store & Play Store Scraping Architecture:**
   - Over 98% of the mobile app reviews in the backup database (1,482 out of 1,501 items) were collected by scraping Play Store and App Store listings.
   - The scrapers (`collectors/play_store.py` and `collectors/app_store.py`) saved the application package URL (`details?id=com.nextbillion.groww` and `app/id1404871703`) as the item URL, because public App Store web frontends do not provide permanent deep-links to individual user reviews.

3. **The Reddit Permalinks in the Backup DB:**
   - The 34 Reddit records in `data/discovery_engine_2153_backup.db` do not contain standard Reddit post identifiers (e.g., `reddit.com/r/.../comments/{id}/{title}/`).
   - Instead, they follow a synthetic slug format (`/comments/{slug}` without the base-36 post ID). If requested over HTTP, Reddit redirects or returns a 404 error because the post ID is missing.

4. **The YouTube Links in the Backup DB:**
   - 296 of the 299 YouTube entries point to a single static video URL (`https://www.youtube.com/watch?v=WpijDxpIM8s`), representing a video under which user comments were collected, but lacking individual comment permalink anchors (`#lc=...`).

---

## 5. Conclusion & Mandatory Stop

In compliance with **Step 1, Criterion 4**:
- In `data/discovery_engine.db`, **0** retention-relevant records have a genuine `SPECIFIC` URL.
- We have stopped execution and refrained from fabricating records, synthesizing fake IDs, or guessing permalinks.
- Awaiting user instruction before proceeding to Step 2.

