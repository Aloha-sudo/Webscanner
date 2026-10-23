# Demo: three sources, one project

**[Download demo-project.zip](demo-project.zip)** · [Evidence matrix JSON](demo-visibility.json) · [SVG export](../docs/images/network-map-demo.svg)

The demo is entirely synthetic. It uses documentation addresses `192.0.2.0/24` and `.example` hostnames. No network was scanned, and there are no real screenshots, credentials or organization data in the archive.

## Open it in WebScanner

1. Download `demo-project.zip` (on GitHub, use the file's download button).
2. Choose **Project management → Import project** and select the ZIP.
3. Inspect the preview: one network segment and three reports. Create the project; choose another name if it already exists.
4. Open **Network map**, select **Demo - service reachability** and **Documentation lab**.
5. Choose **Project management → Project description → Open saved map**. Alternatively, select all three reports and click **Build map**.

No scan task is launched. All imported records receive new local IDs. Original JSON files, authors, dates, report sources, the description and saved report selection are included.

## What to explore

| Source | Observations |
| --- | --- |
| `192.0.2.10` · Analyst | Analyst host record, SSH on `.20`, HTTPS on `.40` |
| `192.0.2.20` · Jump host | SSH on `.30`, HTTPS on `.40`, SMB on `.50` |
| `192.0.2.30` · App gateway | PostgreSQL on `.60`, HTTP monitoring on `.70` |

- Start from `192.0.2.10` and expand the branches toward the database.
- Open the portal `.40` and select `443/TCP` to inspect its two observing sources.
- Open `.30` and explore its incoming and outgoing neighborhood.
- Find a directed observation path from `.10` to `.60`.
- Switch to the evidence table: missing observations remain **No data**, because scan scope is not confirmed.
- Export the current map or full map as SVG.

Observation timestamps are `09:30`, `09:40` and `09:50` UTC on 23 October 2026. The interface displays them in your browser's time zone, always using the 24-hour clock.

## About the README image

The image was produced from `demo-visibility.json` using the application's `fullMapSvg` exporter, then rendered as PNG. It is an actual example of an exported graph. It is not a browser screenshot and does not demonstrate UI controls or unreleased features.

## По-русски

Скачайте ZIP и выберите **Управление проектом → Импорт проекта**. После импорта откройте **Карту сети**, выберите демопроект и **Documentation lab**, затем откройте сохранённую карту через описание проекта или постройте её по трём отчётам.

Все данные вымышленные. Никакие сканы при импорте не запускаются. Проверьте портал `.40:443` из двух источников, окружение `.30` и цепочку наблюдений от `.10` до `.60`. Отсутствующие записи означают «Нет данных», а связи не подтверждают физический маршрут или возможность перехода.
