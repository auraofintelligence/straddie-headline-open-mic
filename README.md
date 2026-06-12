# Straddie Headline Open Mic

A small multi-page static site that refreshes a daily board of funny English-language news headlines and uses them as a gentle prompt for a possible Straddie comedy open mic night.

The site stores only the headline, source, link, date, and a short note about why the wording made the board. It does not copy article bodies.

## Pages

- `index.html` - today's bill and the open mic question
- `headlines.html` - searchable headline list
- `open-mic.html` - possible local comedy night shape
- `sources.html` - feeds and selection rules
- `archive.html` - dated headline snapshots
- `site-map.html` - public route map

## Daily automation

GitHub Actions runs `tools/refresh_site.py` every day at 7:35am Brisbane time. The script:

1. Reads `data/sources.json`.
2. Fetches public RSS and Atom feeds.
3. Filters out heavy harm stories and scarebait-style prediction/conspiracy headlines.
4. Scores headlines with transparent humour rules.
5. Gives NT News the strongest source boost, with smaller boosts for tabloid/offbeat print-news sources.
6. Writes `assets/data/headlines.json`, `assets/data/headline-images/*.svg`, and `data/archive/YYYY-MM-DD.json`.
7. Regenerates the static HTML pages with a visible record-update timestamp.

Run it locally:

```powershell
python tools\refresh_site.py
```

Then open `index.html` in a browser, or serve the folder locally:

```powershell
python -m http.server 4173
```

## Generated images

The page hero images were generated as project assets, converted to WebP, and saved in `assets/img/`. The daily workflow refreshes headline content and generates small SVG newspaper-style headline images, so it does not need an API key.

NT News is deliberately prime front and centre. The direct NT News RSS endpoint currently returns a cookie wall or empty response to Python, so the automation uses a Google News RSS search for `site:ntnews.com.au` and labels it transparently as NT News in the source list.

## Editing the source list

Add or remove feeds in `data/sources.json`. Keep each source as:

```json
{
  "name": "Example Paper",
  "country": "Australia",
  "type": "newspaper",
  "feed_url": "https://example.com/rss"
}
```

## Design note

The site is deliberately plain-speaking: linked headlines, a friendly room, and no bossy campaign language. The open mic idea is a question for the community, not a demand.
