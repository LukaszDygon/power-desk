# Energy data sources

A tagged reference list of energy data publishers. It covers European power, gas, carbon and weather in
detail, plus forecasting and machine-learning services and the main sources outside Europe. Every table
uses the same columns and the tag vocabulary below.

Each row was checked against the publisher's own pages: Europe on **2026-11-01**, and the forecasting
services and global sections on **2026-11-02**. Terms change often, so re-check the Docs link before you
build a source. **(unv.)** marks a point that could not be confirmed on a primary page, because the page
rendered only with JavaScript, returned 403, or did not state it. The sources power-desk ingests are those in
`elt/src/power_desk_elt/ingest/registry.py`.

**Contents**
1. [Tags](#tags)
2. [What matters most](#what-matters-most)
3. [Transparency platforms and system operators (Europe)](#transparency-platforms-and-system-operators-europe)
4. [Exchanges (Europe)](#exchanges-europe)
5. [Auctions (Europe)](#auctions-europe)
6. [Weather](#weather)
7. [Forecasting services and machine-learning models](#forecasting-services-and-machine-learning-models)
8. [Aggregators, statistics and reference data](#aggregators-statistics-and-reference-data)
9. [Commercial vendors](#commercial-vendors)
10. [Outside Europe](#outside-europe)
11. [Gaps](#gaps)

## Tags

**Columns**

| Column | Content |
|---|---|
| Source | Publisher or product, and its operator |
| Area | Region tag, then countries, bidding zones or hubs |
| Type | What kind of publisher it is (one or more tags) |
| Data types | What it publishes, from the data-type list below |
| Delivery | How the data reaches you, with formats in brackets |
| Access | What you need to get the data; split by channel where they differ, e.g. `Free` (web) · `Paid` (API) |
| Licence & notes | Licence, rate limits and changes from 2024–2026 |
| Docs | Link to the documentation or the page checked |

**Area tags**

| Tag | Countries and zones |
|---|---|
| `Global` | Worldwide coverage |
| `Europe` | Several European regions, or all ENTSO-E/EU zones |
| `GB & Ireland` | GB, IE, NI; SEM is the all-island market |
| `Western Europe` | DE, LU, FR, BE, NL, AT, CH |
| `Southern Europe` | ES, PT, IT |
| `Nordics` | DK1–2, NO1–5, SE1–4, FI |
| `CEE` | PL, CZ, SK, HU, SI, HR, RO, BG |
| `North America` | US, CA, MX |
| `Asia-Pacific` | AU, JP, IN, CN, KR, SG |
| `Latin America` | BR, CL |
| `Africa` | ZA |

**Type tags**

| Tag | Meaning |
|---|---|
| `Transparency` | Regulatory transparency or inside-information platform |
| `System operator` | TSO, ISO, market operator or imbalance settlement body |
| `Exchange` | Power, gas or carbon exchange |
| `Auction` | Transmission, capacity, balancing, carbon or certificate auctions |
| `Gas` | Gas market or infrastructure |
| `Weather` | Weather service, model or reanalysis |
| `Forecast` | Service selling or publishing forecasts |
| `ML model` | Machine-learning weather model with published output or weights |
| `Aggregator` | Republishes and normalises other publishers' data |
| `Statistics` | Official or annual statistics |
| `Reference` | Registers, plant databases, scenarios |
| `Commercial` | Commercial data vendor |

**Data types**

| Group | Data types |
|---|---|
| Prices | DA prices, ID prices, imbalance prices, futures, price forecast, retail prices |
| System | load, load forecast, generation, RES forecast, capacity, outages, flows, transfer capacity, frequency |
| Balancing | balancing, ancillary services, redispatch |
| Auctions | auction results |
| Gas | gas flows, gas storage, LNG |
| Carbon | emissions, carbon intensity |
| Weather | NWP, ensembles, observations, reanalysis, irradiance, capacity factors |
| Reference | plant register, energy balances, scenarios, news |

**Delivery tags**
- **API**: REST, SOAP or OData pull.
- **Push**: AMQP, SFTP or email push, notification service, satellite broadcast.
- **RSS**: RSS or Atom feeds.
- **Web**: dashboards and online publication.
- **Download**: bulk files over HTTP, (S)FTP or cloud buckets.

**Access tags**
- **`Free`**: no account needed.
- **`Account`**: free, but needs a registration, API key or token.
- **`Paid`**: a subscription, licence or quote.

## What matters most

- **Exchange data is the main licensing constraint.** EPEX SPOT, Nord Pool, EEX and ICE Endex show some
  prices on the web free of charge, but only for internal or personal use. Their files, APIs and any
  redistribution are paid. For day-ahead prices of coupled zones, the licence-light routes are ENTSO-E
  Transparency, SMARD and the TSO portals: Energinet, OMIE's files, and GME after registration.
- **15-minute MTU.** SDAC moved to 15-minute products on 1 Oct 2025, and European intraday auctions
  started on 13 Jun 2024. Expect 96 day-ahead periods per day and some renamed datasets; for example,
  Energinet's `Elspotprices` became `DayAheadPrices`.
- **Weather is now mostly open.** ECMWF's whole real-time catalogue has been CC BY 4.0 with no data
  charge since 1 Oct 2025; delivery services are still charged. Météo-France has been open since
  Jan 2024. DWD, KNMI, DMI, FMI and MET Norway are CC BY 4.0.
- **Non-commercial traps.** These are free to use only for non-commercial purposes:
  - Open-Meteo and Electricity Maps free tiers.
  - IEA WEO free data (CC BY-NC-SA).
  - OpenElectricity (CC BY-NC).
  - Renewables.ninja (unv.).
  - Energy-Charts prices outside the 16 SMARD zones.
  - EUMETSAT data under 1 h latency.
  - Pangu-Weather and GraphCast weights.

  Met Office data on AWS is share-alike (CC BY-SA).
- **Machine-learning forecasts.** Commercial forecast services are paid and mostly priced on quote. To
  build your own models, ECMWF AIFS is the cleanest open machine-learning weather model: data and weights
  are CC BY 4.0, and commercial use is allowed.
- **Stale:** Open Power System Data has not been updated since 2020, and JRC-PPDB-OPEN since 2019.

## Transparency platforms and system operators (Europe)

### Pan-European

| Source | Area | Type | Data types | Delivery | Access | Licence & notes | Docs |
|---|---|---|---|---|---|---|---|
| **ENTSO-E Transparency Platform** (ENTSO-E) | `Europe` all ENTSO-E bidding zones | `Transparency` | load, load forecast, generation, capacity, outages, flows, transfer capacity, DA prices, balancing, imbalance prices | API (XML) · Push (subscriptions) · Download (File Library) · Web | `Account` (email transparency@entsoe.eu, then token) | Reuse terms (unv.). File Library replaces SFTP (SFTP shutdown planned Sep 2025, unv.). The quoted 400 req/min limit has no official source | [Platform](https://www.entsoe.eu/data/transparency-platform/) · [Support and API docs](https://transparencyplatform.zendesk.com) |
| **ENTSOG Transparency Platform** (ENTSOG) | `Europe` gas interconnection points, balancing zones | `Transparency` `Gas` | gas flows, capacity, outages | API (XML/CSV/XLSX/JSON) · Web | `Free` | No key in the API manual v3.0 (Oct 2025); filters are mandatory | [Platform](https://transparency.entsog.eu) |
| **ACER / REMIT** (ACER) | `Europe` EU | `Transparency` | outages, news | Web · Download (AEGIS/CHEST, CSV) | `Free` | No transaction data is public. The Inside Information Access Point and the REMIT Data Reference Centre opened May 2025 and are in beta | [REMIT](https://www.acer.europa.eu/remit) |
| **EEX Transparency** (EEX) | `Europe` power 19 countries, gas 12 | `Transparency` | outages, generation, capacity | Web · API (real-time) | `Free` (web) · `Paid` (API) | ACER-approved inside-information platform | [Platform](https://www.eex-transparency.com) |
| **EU balancing platforms**: PICASSO, MARI, TERRE, IGCC (ENTSO-E) | `Europe` member TSOs | `Transparency` | balancing, imbalance prices | Web (PDF) · API (through ENTSO-E TP, unv.) | `Free` | KPI reports and accession roadmaps. Terna reconnected to PICASSO Dec 2025; ELES and MAVIR joined 2026 | [PICASSO](https://www.entsoe.eu/network_codes/eb/picasso/) |

### GB and Ireland

| Source | Area | Type | Data types | Delivery | Access | Licence & notes | Docs |
|---|---|---|---|---|---|---|---|
| **Elexon Insights (BMRS)** (Elexon) | `GB & Ireland` GB | `Transparency` | balancing, imbalance prices, generation, load, load forecast, outages, flows | API (JSON) · Push (IRIS, AMQP) · Web | `Free` (API, no key) · `Account` (IRIS) | BMRS licence allows commercial use with attribution. Old BMRS API off since 31 May 2024 | [Developer portal](https://developer.data.elexon.co.uk) |
| **NESO Data Portal** (NESO) | `GB & Ireland` GB | `System operator` | load, load forecast, RES forecast, balancing, ancillary services, flows, frequency | API (CKAN, Datastore SQL) · Download (CSV) | `Free` | NESO Open Licence (based on OGL v3), set per dataset. Limits: 1 req/s, 2 req/min for SQL | [API guidance](https://www.neso.energy/data-portal/api-guidance) |
| **EirGrid / SONI** | `GB & Ireland` IE, NI | `System operator` | load, generation, carbon intensity | Download (XLSX) · Web (Smart Grid Dashboard) | `Free` | Licence (unv.). The dashboard's JSON is undocumented | [EirGrid](https://www.eirgrid.ie) |
| **SEMO** (EirGrid, SONI) | `GB & Ireland` SEM | `System operator` | balancing, imbalance prices | API (static reports, JSON) · Download | `Free` (unv.) | The API document dates from 2019 | [SEMO](https://www.sem-o.com) |

### Western Europe

| Source | Area | Type | Data types | Delivery | Access | Licence & notes | Docs |
|---|---|---|---|---|---|---|---|
| **SMARD** (Bundesnetzagentur) | `Western Europe` DE-LU and neighbours | `Transparency` | generation, load, load forecast, DA prices, flows | Web · Download (CSV/XLSX, up to 2 years per file) | `Free` | CC BY 4.0, credit "Bundesnetzagentur \| SMARD.de". No official API; the JSON is community-documented | [Data use](https://www.smard.de/en/datennutzung) |
| **Netztransparenz.de** (50Hertz, Amprion, TenneT DE, TransnetBW) | `Western Europe` DE control areas | `System operator` | imbalance prices, balancing, RES forecast, redispatch | API (OAuth2) · Download (CSV) | `Account` | Covers reBAP, NRV balance and EEG market values | [Web API](https://www.netztransparenz.de/en/Web-API) |
| **German TSO sites** (50Hertz, Amprion, TenneT DE, TransnetBW) | `Western Europe` DE | `System operator` | load, generation | Web · Download (unv.) | `Free` (unv.) | Not checked individually; the data is also on Netztransparenz and ENTSO-E | — |
| **RTE Data portal** (RTE) | `Western Europe` FR | `System operator` | generation, load, flows, balancing, outages | API (OAuth2) | `Account` | You subscribe to each API separately. Quotas (unv.) | [Catalogue](https://data.rte-france.com/catalog) |
| **ODRÉ / éCO2mix** (RTE and partners) | `Western Europe` FR and regions | `System operator` | generation, load, carbon intensity, gas flows | API (Opendatasoft v2.1) · Download (CSV/JSON/XLSX) | `Free` | Licence Ouverte 2.0. 50,000 calls per month | [Portal](https://odre.opendatasoft.com) |
| **Elia Open Data** (Elia) | `Western Europe` BE | `System operator` | load, RES forecast, imbalance prices, balancing, redispatch | API (Opendatasoft v2.1) · Download | `Free` | Elia Open Data Licence. About 110 datasets | [Portal](https://opendata.elia.be) |
| **TenneT NL** (TenneT) | `Western Europe` NL | `System operator` | imbalance prices, balancing, transfer capacity | API · Web | `Account` (API key) | Fair-use policy. 12-second balance delta feed; the 1-minute feed was retired May 2026 | [Developer portal](https://developer.tennet.eu) |
| **APG** (Austrian Power Grid) | `Western Europe` AT | `System operator` | load, load forecast, generation, outages, balancing, imbalance prices, DA prices | API (Swagger) · Web · Download (data before 2023) | `Free` or `Account` (request access, 2024) | © APG, no open licence | [Transparency](https://markt.apg.at/en/transparency) |
| **Swissgrid** | `Western Europe` CH | `System operator` | load, generation, energy balances | Download (XLSX/CSV) | `Free` | Licence (unv.). No API | [Swissgrid](https://www.swissgrid.ch) |

### Southern Europe

| Source | Area | Type | Data types | Delivery | Access | Licence & notes | Docs |
|---|---|---|---|---|---|---|---|
| **REE REData** (Red Eléctrica) | `Southern Europe` ES | `System operator` | generation, load, flows, DA prices | API (JSON) | `Free` | Licence (unv.) | [REData API](https://www.ree.es/en/datos/apidata) |
| **REE ESIOS** (Red Eléctrica) | `Southern Europe` ES | `System operator` | balancing, DA prices, imbalance prices, load forecast, RES forecast | API · Download (archives) | `Account` (personal token) | — | [API](https://api.esios.ree.es) |
| **REN Data Hub** (REN) | `Southern Europe` PT | `System operator` `Gas` | generation, load forecast, RES forecast, flows, gas flows, gas storage, LNG | Web · Download · API (unv.) | `Free` | Licence (unv.) | [Data Hub](https://datahub.ren.pt/en) |
| **Terna** | `Southern Europe` IT zones | `System operator` | load, generation, capacity, energy balances | API · Download (unv.) | `Account` (key and secret) | Settlement and metering APIs are private | [Developer portal](https://developer.terna.it) |

### Nordics and CEE

| Source | Area | Type | Data types | Delivery | Access | Licence & notes | Docs |
|---|---|---|---|---|---|---|---|
| **Energi Data Service** (Energinet) | `Nordics` DK1, DK2 | `System operator` | DA prices, generation, load, emissions, balancing, imbalance prices, flows, gas flows | API (JSON/CSV/XLSX) | `Free` | CC BY 4.0. HTTP 429 when over the limit. `Elspotprices` replaced by `DayAheadPrices` (15 minutes) from 30 Sep 2025 | [Portal](https://www.energidataservice.dk) |
| **Fingrid Open Data** (Fingrid) | `Nordics` FI | `System operator` | generation, load, load forecast, RES forecast, balancing, ancillary services, imbalance prices, flows | API | `Account` (API key) | 10,000 requests a day, one per 2 s. CC BY 4.0 (unv.) | [Instructions](https://data.fingrid.fi/en/instructions) |
| **Statnett** | `Nordics` NO and Nordic | `System operator` | generation, load, flows, frequency | Download · API (undocumented) | `Free` | Terms (unv.) | statnett.no (not checked) |
| **Svenska kraftnät** | `Nordics` SE1–SE4 | `System operator` | ancillary services, balancing, load forecast | API and Download (CKAN, CSV) | `Free` | CC BY 4.0. data.svk.se is replacing Mimer | [Data service](https://data.svk.se/en_GB) |
| **eSett Open Data** (eSett) | `Nordics` FI, SE, NO, DK | `System operator` | imbalance prices, generation, load | API · Web | `Free` | Imbalance settlement body; 15-minute data since May 2023 | [Portal](https://opendata.esett.com) |
| **PSE** | `CEE` PL | `System operator` | DA prices, load, generation, balancing, transfer capacity | API (OData-style) | `Free` (unv.) | API v2 since 15 Jun 2025 | api.raporty.pse.pl (did not render) |

Not checked: Elering (EE), ČEPS (CZ), MAVIR (HU), and the national inside-information platforms on ACER's
list.

## Exchanges (Europe)

### Power spot markets

| Source | Area | Type | Data types | Delivery | Access | Licence & notes | Docs |
|---|---|---|---|---|---|---|---|
| **EPEX SPOT** (EEX Group) | `Europe` AT, BE, CH, DE, DK, FI, FR, GB, NL, NO, PL, SE | `Exchange` | DA prices, ID prices | Web · Download (FTP/webshare, CSV) · API (real-time) | `Free` (web, internal use) · `Paid` (files, API) | Display and redistribution need a separate licence. General Conditions Market Data dated 1 Nov 2025 | [Webshop](https://webshop.eex-group.com/offerdescription_epex_spot_MD_ISVs) |
| **Nord Pool** (Euronext), incl. N2EX | `Europe` Nordics, Baltics, CWE, GB | `Exchange` | DA prices, ID prices | Web (Data Portal) · API (Market Data API v2, Intraday read-only) | `Free` (recent DA on web) · `Paid` (portal €1,200–9,000/yr, API) | Redistribution costs extra. History paid since 2022. Legacy APIs shut 31 Dec 2025 | [Data services](https://www.nordpoolgroup.com/en/services/power-market-data-services/dataportalregistration/) |
| **OMIE** | `Southern Europe` ES, PT | `Exchange` | DA prices, ID prices, transfer capacity | Download (file repository, 6 rolling years) | `Free` | "All rights reserved"; terms (unv.). Local intraday sessions replaced by European IDAs from 13 Jun 2024 | [File access](https://www.omie.es/en/file-access-list) |
| **GME** | `Southern Europe` IT zones | `Exchange` | DA prices, ID prices, gas flows | API (from 15 Oct 2025) · Download (FTPS, being retired) · Web | `Account` (formal sign-up by certified email, no fee) | Plain FTP closed 30 Sep 2025. PUN Index GME | [API service](https://www.mercatoelettrico.org/en-us/Home/APIService) |
| **SEMOpx** (EirGrid, SONI) | `GB & Ireland` SEM | `Exchange` | DA prices, ID prices | API (XML/CSV, no auth) · Web | `Free` | Some documents are for members only | [Market data](https://www.semopx.com/market-data/) |
| **OTE** | `CEE` CZ | `Exchange` | DA prices, ID prices, gas flows | Download (daily XLSX) · API (SOAP) · RSS | `Free` | Terms of use not checked | [Day-ahead market](https://www.ote-cr.cz/en/short-term-markets/electricity/day-ahead-market) |
| **TGE** (Polish Power Exchange) | `CEE` PL | `Exchange` | DA prices, ID prices, futures | Web · Download (AIR platform, CSV) · Push (real-time feed from the Warsaw Stock Exchange) | `Free` (web, personal use) · `Paid` (commercial use) | Commercial use needs a licence from the Warsaw Stock Exchange; Market Data Policy 2025 | [Services](https://tge.pl/TGE_Services) |
| **HUPX** (ADEX) | `CEE` HU | `Exchange` | DA prices, ID prices, futures | Web (HUPX Labs) · Download (reports, SFTP) | `Free` (daily reports) · `Paid` (live and history) | Public history was shortened when data moved to HUPX Labs | [HUPX Labs](https://labs.hupx.hu) |
| **BSP SouthPool** (ADEX) | `CEE` SI | `Exchange` | DA prices, ID prices | Web (on HUPX Labs) · Download | `Free` (views) · `Paid` (data service, unv.) | Runs the ADEX intraday continuous market (Oct 2026) | [BSP](https://www.bsp-southpool.com) |
| **CROPEX** | `CEE` HR | `Exchange` | DA prices, ID prices, futures | Web · Download | `Free` (unv.) | — | [CROPEX](https://www.cropex.hr/en/) |
| **OPCOM** | `CEE` RO | `Exchange` | DA prices, ID prices, imbalance prices, gas flows | Web · RSS · Download (PDF) | `Free` | No API found | [OPCOM](https://www.opcom.ro) |
| **IBEX** | `CEE` BG | `Exchange` | DA prices, ID prices | Web | `Free` (unv.) | The site did not render | ibex.bg |

### Futures, gas and carbon

| Source | Area | Type | Data types | Delivery | Access | Licence & notes | Docs |
|---|---|---|---|---|---|---|---|
| **EEX** (EEX Group) | `Europe` DE, FR, IT, NL power; THE, TTF, PEG gas | `Exchange` `Gas` | futures, DA prices, emissions | Web (short history) · Download (sFTP, File Cloud) · API | `Free` (short web window) · `Paid` (feeds, per market) | Using an index in a product needs a licence | [EEX](https://www.eex.com) |
| **ICE Endex** (ICE) | `Western Europe` TTF, NBP, ZTP | `Exchange` `Gas` | futures, DA prices | Download (Report Center, CSV) | `Paid` | Free or delayed access (unv.) | [Report Center](https://www.ice.com/report-center) |
| **MIBGAS** | `Southern Europe` ES, PT | `Exchange` `Gas` | DA prices, futures | Web · Download | `Free` (web) | File terms (unv.) | [MIBGAS](https://www.mibgas.es/en) |
| **Trading Hub Europe** | `Western Europe` THE (DE) | `System operator` `Gas` | imbalance prices, balancing | Web · Download | `Free` | API (unv.) | [THE](https://www.tradinghub.eu) |
| **GIE AGSI+ / ALSI** (GIE) | `Europe` EU per country, company and site | `Transparency` `Gas` | gas storage, LNG, outages | API (key in URL) · Web | `Account` | Attribution required, or the key can be revoked | [AGSI+](https://agsi.gie.eu) |
| **PRISMA** | `Europe` interconnection points | `Auction` `Gas` | auction results, transfer capacity | Web (CSV export) · API | `Account` or `Paid` | Public aggregates are on ACER AEGIS | [PRISMA](https://www.prisma-capacity.eu) |

## Auctions (Europe)

| Source | Area | Type | Data types | Delivery | Access | Licence & notes | Docs |
|---|---|---|---|---|---|---|---|
| **JAO** (Joint Allocation Office) | `Europe` Core, Nordic, Italy North, CH, GB links | `Auction` | auction results, transfer capacity | API (auction data, JSON, 31 days per call) · Web and API (Publication Tool) · eCAT | `Account` (free token after accepting T&Cs) · `Free` (Publication Tool web) | Flow-based parameters for Core, Nordic and Italy North | [Market data API](https://www.jao.eu/page-api/market-data) |
| **EEX: EU ETS auctions** (EEX) | `Europe` EU | `Auction` | auction results, emissions | Web (last 45 days) · Download (history 2012–2025) | `Free` | Fees change 1 Sep 2026. ETS2 auctions start 2027 | [EU ETS auctions](https://www.eex.com/en/markets/environmentals/eu-ets1-eu-ets2-auctions/eu-ets1-auctions) |
| **EEX: Guarantees of Origin** (EEX) | `Western Europe` FR | `Auction` | auction results | Download (XLSX/ZIP) | `Free` (auction results) · `Paid` (GO exchange data, unv.) | Power GO auctions monthly, biogas GO quarterly | [French GO auctions](https://www.eex.com/en/markets/energy-certificates/french-auctions-power) |
| **regelleistung.net** (German TSOs) | `Western Europe` DE and FCR cooperation | `Auction` | auction results, ancillary services | Web (Datencenter) · Download | `Free` | Formats and API (unv.) | [regelleistung.net](https://www.regelleistung.net) |
| **NESO balancing auctions** (NESO) | `GB & Ireland` GB | `Auction` | auction results, ancillary services | API (CKAN) · Download (CSV) | `Free` | NESO Open Licence. Response and reserve products moved to Enduring Auction Capability (EAC) | [EAC results](https://www.neso.energy/data-portal/eac-auction-results) |
| **EMR Delivery Body: Capacity Market** (NESO) | `GB & Ireland` GB | `Auction` | auction results, capacity | API and Download (NESO portal) · Web | `Free` | Register updated weekly. Latest auction T-4 for 2029/30 (Jun 2026) | [Register](https://www.neso.energy/data-portal/capacity-market-register) |
| **LCCC / EMR Settlement** | `GB & Ireland` GB | `Auction` | generation, DA prices, auction results | Download (JSON/CSV) · API (unv.) | `Free` | Licence per dataset; some are OGL | [Data portal](https://dp.lowcarboncontracts.uk) |

## Weather

| Source | Area | Type | Data types | Delivery | Access | Licence & notes | Docs |
|---|---|---|---|---|---|---|---|
| **ECMWF Open Data** (ECMWF) | `Global` | `Weather` `ML model` | NWP, ensembles | Download (HTTPS, AWS/Azure/GCP mirrors) · Push (WIS2 notifications) | `Free` | CC BY 4.0. Includes IFS, AIFS and ENS; 0.25°, plus 0.1° IFS from 20 Oct 2026. Only about the last 12 runs are kept | [Open data](https://www.ecmwf.int/en/forecasts/datasets/open-data) |
| **ECMWF real-time catalogue** (ECMWF) | `Global` | `Weather` | NWP, ensembles | Push (ECPDS) · API (MARS archive) | `Paid` (service and delivery) | Data CC BY 4.0 with no data charge since 1 Oct 2025 | [Announcement](https://www.ecmwf.int/node/29328) |
| **Copernicus CDS** (C3S, ECMWF) | `Global` | `Weather` | reanalysis | API (`cdsapi`) · Web | `Account` | CC BY. ERA5 is hourly at 0.25° from 1940, with about 5 days' latency. Access notices posted Oct 2026; check them before bulk pulls | [ERA5](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels) |
| **C3S energy / PECD** (C3S, ENTSO-E) | `Europe` · `Global` | `Weather` `Reference` | capacity factors, load, scenarios | API (`cdsapi`) | `Account` | CC BY. PECD v4.2 covers 1950–2024 plus projections | [Energy dataset](https://cds.climate.copernicus.eu/datasets/sis-energy-derived-reanalysis) |
| **CAMS solar radiation** (Copernicus ADS) | `Europe` · `Africa` | `Weather` | irradiance | API (`cdsapi`) · Web | `Account` | CC BY. GHI, DNI and DHI from 2004, 1-minute to monthly. ADS terms change announced Oct 2026 | [Dataset](https://ads.atmosphere.copernicus.eu/datasets/cams-solar-radiation-timeseries) |
| **DWD Open Data** (Deutscher Wetterdienst) | `Global` · `Europe` · `Western Europe` DE | `Weather` | NWP, ensembles, observations | Download (HTTPS, GRIB2) · API (WMS/WFS) · RSS | `Free` | CC BY 4.0. Models: ICON, ICON-EU, ICON-D2, MOSMIX | [NWP](https://opendata.dwd.de/weather/nwp/) |
| **Met Office Weather DataHub** | `Global` · `GB & Ireland` UK | `Weather` | NWP, ensembles, observations | API · Download (file orders) | `Account` (free quota) · `Paid` (above it) | Free quota: 1 GB a month or 360 calls a day. DataPoint retired 1 Dec 2025 | [Pricing](https://datahub.metoffice.gov.uk/pricing/atmospheric) |
| **Met Office on AWS** | `Global` · `GB & Ireland` UK | `Weather` | NWP | Download (S3, NetCDF) | `Free` | **CC BY-SA** (share-alike). Two-year rolling archive | [Registry](https://registry.opendata.aws/met-office-global-deterministic/) |
| **Météo-France** | `Western Europe` FR · `Europe` · `Global` | `Weather` | NWP, ensembles (unv.), observations | API (portal) · Download (GRIB) | `Free` (files) · `Account` (API) | Etalab 2.0. All public data free since Jan 2024. Models: AROME 1.3 km, ARPEGE | [Models](https://www.data.gouv.fr/datasets/modele-numerique-de-previsions-meteorologiques) |
| **KNMI Data Platform** | `Western Europe` NL · `Europe` | `Weather` | NWP, observations | API (files, EDR, WMS) · Push (notification service) | `Account` (anonymous key valid to Aug 2027) | CC BY 4.0. Model: HARMONIE-AROME | [Open Data API](https://developer.dataplatform.knmi.nl/open-data-api) |
| **DMI Open Data** | `Nordics` DK, North Sea | `Weather` | NWP, observations | API (STAC, EDR) · Download | `Free` | No key on the current endpoints. CC BY 4.0 (unv.) | [Docs](https://opendatadocs.dmi.govcloud.dk) |
| **MET Norway** | `Nordics` · `Global` points | `Weather` | NWP, observations | API (needs a User-Agent; at most 20 req/s) · Download (THREDDS) | `Free` (api.met.no) · `Account` (Frost) | CC BY 4.0. Caching is mandatory | [Terms](https://api.met.no/doc/TermsOfService) |
| **FMI Open Data** | `Nordics` FI | `Weather` | observations, irradiance, NWP | API (WFS/WMS) | `Free` | CC BY 4.0 | [Licence](https://en.ilmatieteenlaitos.fi/open-data-licence) |
| **SMHI Open Data** | `Nordics` SE | `Weather` | observations, NWP | API | `Free` | Creative Commons (version unv.). The snow1g API replaced pmp3g in 2026 | [Open data](https://opendata.smhi.se) |
| **AEMET OpenData** | `Southern Europe` ES | `Weather` | observations, NWP | API · RSS | `Account` (free key) | Reuse with credit | [OpenData](https://opendata.aemet.es/centrodedescargas/inicio) |
| **MeteoSwiss OGD** | `Western Europe` CH, Alps | `Weather` | NWP, ensembles, observations | API (STAC, GRIB2) | `Free` | Credit "Source: MeteoSwiss". Files are kept only 24 h. Models: ICON-CH1, ICON-CH2 | [Docs](https://opendatadocs.meteoswiss.ch) |
| **GeoSphere Austria Data Hub** | `Western Europe` AT | `Weather` | observations, NWP (unv.) | API | `Free` (unv.) | — | [Data Hub](https://data.hub.geosphere.at) |
| **EUMETSAT and CM SAF** | `Europe` · `Africa` | `Weather` | irradiance, observations | API (Data Store) · Push (EUMETCast broadcast) | `Account` · `Paid` (commercial use under 1 h latency) | Data policy amended Nov 2025 (details unv.). SARAH-3 irradiance | [EUMETSAT](https://www.eumetsat.int) |
| **NOAA GFS / GEFS** (NCEP) | `Global` | `Weather` | NWP, ensembles | Download (NOMADS, AWS S3) · Push (SNS) | `Free` | US public domain. 0.25°, out to 384 h | [Registry](https://registry.opendata.aws/noaa-gfs-bdp-pds/) |
| **NASA POWER** | `Global` | `Weather` | irradiance, reanalysis | API · Download (AWS) | `Free` | Covers 1981 onwards | [POWER](https://power.larc.nasa.gov) |
| **PV_Live** (Sheffield Solar) | `GB & Ireland` GB | `Weather` | generation | API (no key) | `Free` | CC BY 4.0. National, GSP and PES-region PV outturn estimates. A PV_Live_EU service also exists | [PV_Live](https://www.solar.sheffield.ac.uk/pvlive/) |
| **PVGIS** (EC JRC) | `Global` (Europe, Africa, Asia, Americas) | `Weather` | irradiance, capacity factors | API (v5.3, 30 calls/s) | `Free` | Licence not stated | [API](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis_en) |
| **Renewables.ninja** | `Global` | `Weather` | capacity factors | API (token) · Download | `Account` | Non-commercial (unv.) | [API docs](https://www.renewables.ninja/documentation/api) |
| **Open-Meteo** | `Global` | `Weather` `Aggregator` | NWP, ensembles, reanalysis | API · Download (S3) | `Free` (non-commercial, under 10k calls/day) · `Paid` | Data CC BY 4.0. Aggregates IFS/AIFS, ICON, GFS, AROME, UKMO, HARMONIE | [Terms](https://open-meteo.com/en/terms) |
| **Solcast** (DNV) | `Global` | `Weather` `Forecast` | irradiance, RES forecast | API | `Account` (a few free calls) · `Paid` | Live, forecast and historical data | [Pricing](https://solcast.com/pricing) |
| **Meteomatics** | `Global` · `Europe` (1 km) | `Weather` `Forecast` | NWP, RES forecast | API | `Paid` | Own EURO1k model | [Weather API](https://www.meteomatics.com/en/weather-api/) |
| **Tomorrow.io** | `Global` | `Weather` `Forecast` | NWP, irradiance, RES forecast | API | `Account` (free plan, limits unv.) · `Paid` (energy products) | Wind power per farm, node and system, 0–48 h | [Weather API](https://www.tomorrow.io/weather-api/) |
| **DTN** (incl. ex-MeteoGroup) | `Global` · `Europe` | `Weather` `Forecast` | NWP, RES forecast | API (unv.) | `Paid` | Product details (unv.) | [EU forecast system (PDF)](https://www.dtn.com/wp-content/uploads/2025/03/dtn-forecast-system-eu.pdf) |
| **Spire Weather** | `Global` | `Weather` `Forecast` | NWP, ensembles, RES forecast | API | `Paid` | Own satellite data; 200-member sub-seasonal ensemble | [Spire](https://spire.com/weather-climate/) |
| **StormGeo Energy Analytics** | `Europe` | `Weather` `Forecast` | price forecast, RES forecast | Web · API (unv.) | `Paid` | Owner (unv.) | [Product page](https://www.stormgeo.com/products/european-power-market-analysis) |

## Forecasting services and machine-learning models

### Forecast providers

| Source | Area | Type | Data types | Delivery | Access | Licence & notes | Docs |
|---|---|---|---|---|---|---|---|
| **Meteologica** (ES) | `Global` 80+ countries, by country, TSO/ISO zone or node | `Forecast` | RES forecast, load forecast, price forecast, NWP | Web (xTraders platform, downloads) · API or FTP (not stated, unv.) | `Paid` | Demand ensemble to 14 days; short, medium and long range | [Services](https://main1.meteologica.com/services.html) |
| **emsys renewables** (ex-energy & meteo systems) | `Europe` wind 30+ countries, solar 15+ | `Forecast` | RES forecast, load forecast, flows | Push (custom formats) · Web (portal) | `Paid` | Previento (wind) and Suncast (solar); 20 TSOs as clients | [emsys](https://www.emsys-renewables.com/) |
| **enercast** | `Europe` 20+ countries | `Forecast` | RES forecast, NWP | API · Push (email, FTP) · Web | `Paid` | Site and area forecasts, 15 minutes to 31 days | [Products](https://www.enercast.de/products/) |
| **Dexter Energy** | `Europe` (zones unv.) | `Forecast` | RES forecast, price forecast, imbalance prices | API | `Paid` | Battery support added Jul 2025; Series C 2025 | [Dexter](https://dexterenergy.ai) |
| **AleaSoft** | `Europe` MIBEL, FR, DE/AT, IT, SEM, GB and others | `Forecast` | price forecast, load forecast, RES forecast | Push (email, FTP) · API (AleaApp database) | `Paid` · `Free` (weekly commentary) | Hourly to 10 days, mid term to 3 years, long term 10–40 years | [Price forecasting](https://aleasoft.com/energy-price-forecasting/) |
| **ENFOR** | `Europe` (unv.) | `Forecast` | RES forecast, load forecast, price forecast | (unv.) | `Paid` | District-energy business sold to Danfoss (unv.) | [ENFOR](https://enfor.dk) |
| **Optimeering** | `Nordics` | `Forecast` | imbalance prices, ancillary services | Web · API (unv.) | `Paid` | Forecasts for imbalance prices and aFRR/mFRR | [Optimeering](https://www.optimeering.com) |
| **Jua** | `Global` · `Europe` (5 km) | `Forecast` `ML model` | NWP, ensembles, RES forecast | API · Python SDK | `Paid` | Own EPT-2 model: 0–240 h, ensembles to 60 days, up to 24 runs a day | [Jua](https://www.jua.ai) |
| **Whiffle** | `Europe` | `Forecast` | NWP, RES forecast | API · Push (email, SFTP, unv.) | `Paid` | Large-eddy simulation at under 100 m | [Whiffle](https://whiffle.nl) |
| **Reuniwatt / Steadysun** | `Global` | `Forecast` | irradiance, RES forecast | Subscription (unv.) | `Paid` | Solar nowcasting from sky imagers and satellite, up to 2 weeks ahead | [Steadysun](https://steadysun.com) |
| **Rebase Energy** | `Global` | `Forecast` | RES forecast, load forecast | API (Python) · Push (SFTP, ActiveMQ) · BigQuery | `Paid` (self sign-up) | Platform for building your own models; open-source tooling | [Rebase](https://www.rebase.energy) |
| **KISTERS** | (unv.) | `Forecast` | (unv.) | SaaS or on-premises | `Paid` | Sells AI-based forecasting and optimisation | [Product](https://www.kisters.eu/product/forecasting-and-optimisation/) |
| **Open Climate Fix** | `GB & Ireland` GB · `Western Europe` NL · `Asia-Pacific` IN | `Forecast` `ML model` | RES forecast | API (on request) · open Python library and models | `Free` (open source; MIT, per-repo unv.) · `Paid` (commercial API) | Quartz Solar GB national PV forecast is used by NESO | [OCF](https://www.openclimatefix.org) |
| **Amperon** | `North America` · `Europe` (since 2024) · `Asia-Pacific` AU | `Forecast` | load forecast, RES forecast, price forecast | API · Web · Snowflake | `Paid` | Probabilistic wind and solar since Apr 2026 | [Amperon](https://www.amperon.co) |
| **Enertel AI** | `North America` ISOs | `Forecast` | price forecast | Web · Download | `Paid` | Probabilistic nodal prices. Owned by S&P Global since Mar 2026 | [Enertel](https://www.enertel.ai) |
| **Tyba** | `North America` CAISO, ERCOT, MISO | `Forecast` | price forecast | Web | `Paid` | Battery bidding and revenue modelling | [Tyba](https://www.tyba.ai) |

### Machine-learning weather models

| Source | Area | Type | Data types | Delivery | Access | Licence & notes | Docs |
|---|---|---|---|---|---|---|---|
| **ECMWF AIFS** | `Global` | `ML model` `Weather` | NWP, ensembles | Download (ECMWF open data) · weights on Hugging Face | `Free` | Data and weights CC BY 4.0, code Apache 2.0. Commercial use allowed | [Open data](https://www.ecmwf.int/en/forecasts/datasets/open-data) · [Weights](https://huggingface.co/ecmwf/aifs-ens-1.0) |
| **Google DeepMind WeatherNext** | `Global` | `ML model` `Weather` | NWP, ensembles | Earth Engine · BigQuery · Vertex AI (allow-list) | `Account` · `Paid` (Google Cloud) | GraphCast weights CC BY-NC-SA; newer weights CC BY (unv.). WeatherNext 2 released Nov 2025 | [WeatherNext](https://developers.google.com/weathernext) |
| **NVIDIA Earth-2** | `Global` | `ML model` `Weather` | NWP, ensembles | Weights on Hugging Face and GitHub · NIM | `Free` | NVIDIA Open Model License (unv.). Atlas, StormScope, CorrDiff, FourCastNet 3; open family released Jan 2026 | [Earth-2](https://www.nvidia.com/en-us/high-performance-computing/earth-2/) |
| **Microsoft Aurora** | `Global` | `ML model` `Weather` | NWP | Weights on GitHub and Hugging Face · Azure AI Foundry | `Free` (weights) · `Paid` (Foundry) | Code and weights MIT. Commercial use of the Foundry version needs permission | [Aurora](https://ai.azure.com/catalog/models/Aurora) |
| **Huawei Pangu-Weather** | `Global` | `ML model` `Weather` | NWP | Weights (ONNX) | `Free` | **Non-commercial only** (CC BY-NC-SA 4.0) | [GitHub](https://github.com/198808xc/Pangu-Weather) |

## Aggregators, statistics and reference data

| Source | Area | Type | Data types | Delivery | Access | Licence & notes | Docs |
|---|---|---|---|---|---|---|---|
| **Energy-Charts** (Fraunhofer ISE) | `Europe` (most detail for DE) | `Aggregator` | generation, capacity, DA prices, flows, RES forecast, frequency | Web · API (v2, JSON) | `Free` | CC BY 4.0. Prices outside the 16 SMARD zones are for private use only. 2 req/min per endpoint | [API](https://api.energy-charts.info) |
| **Ember** | `Global` 200+ geographies | `Aggregator` `Statistics` | generation, capacity, load, emissions, carbon intensity | Web · API · Download | `Account` (API key) | CC BY 4.0 | [API](https://ember-energy.org/data/api) |
| **Carbon Intensity API** (NESO and partners) | `GB & Ireland` GB, 14 regions | `Aggregator` | carbon intensity, generation | API · Download (CSV) | `Free` | CC BY 4.0. Forecasts 96 h or more ahead | [API](https://carbonintensity.org.uk) |
| **Electricity Maps** | `Global` 130+ zones | `Aggregator` | carbon intensity, generation, flows, DA prices, load | API · Web | `Free` (non-commercial tier) · `Paid` (about €4.5–6k per signal per zone per year) | Datasets are now for academic use only. Parser code is open | [Pricing](https://www.electricitymaps.com/pricing) |
| **Agorameter** (Agora Energiewende) | `Western Europe` DE | `Aggregator` | generation, load, DA prices | Web | `Free` | Licence not stated. Locational prices added 2026 | [Agorameter](https://www.agora-energiewende.org/data-tools/agorameter) |
| **GridStatus.io** | `North America` | `Aggregator` | DA prices, load, generation | API · open-source `gridstatus` library | `Account` (free tier) · `Paid` | Library BSD-3. Not found to cover the EU | [GridStatus](https://www.gridstatus.io) |
| **Eurostat** | `Europe` EU27, EEA | `Statistics` | energy balances, retail prices, capacity | API (JSON-stat, SDMX) · Download | `Free` | Commission reuse policy | [API](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-introduction) |
| **IEA** | `Global` | `Statistics` | energy balances, generation | Web · Download (SDMX) | `Account` (monthly electricity, CC BY 4.0) · `Paid` (detailed balances) | WEO free data is CC BY-NC-SA. Legacy CSV dropped | [Monthly electricity](https://www.iea.org/data-and-statistics/data-product/monthly-electricity-statistics) |
| **EIA International** | `Global` ~220 countries | `Statistics` | energy balances, capacity | API (v2) · Download · Web | `Account` (key) | US public domain | [International](https://www.eia.gov/international) |
| **IRENA (IRENASTAT)** | `Global` ~200 countries | `Statistics` | capacity, generation | Web (PxWeb) · Download | `Free` | With attribution. Capacity released Mar–Apr, generation in Jul | [IRENASTAT](https://pxweb.irena.org) |
| **EI Statistical Review of World Energy** | `Global` | `Statistics` | energy balances, emissions | Download (XLSX/CSV) · Web (PDF) | `Free` | Cite EI. Co-produced with Ember from 2026 | [Statistical Review](https://www.energyinst.org/statistical-review) |
| **UN Energy Statistics** (UNSD) | `Global` ~240 countries | `Statistics` | energy balances | Web (UNdata) · Download | `Free` | UNdata terms | [UNSD](https://unstats.un.org/unsd/energystats) |
| **World Bank** | `Global` | `Statistics` | energy balances | API · Download | `Free` | CC BY 4.0 | [Data](https://data.worldbank.org) |
| **UK DESNZ**: DUKES, Energy Trends, REPD | `GB & Ireland` UK | `Statistics` `Reference` | energy balances, plant register | Download | `Free` | OGL v3 | [DUKES](https://www.gov.uk/government/collections/digest-of-uk-energy-statistics-dukes) |
| **Ofgem data portal** | `GB & Ireland` GB | `Statistics` | DA prices, retail prices | Web · Download (CSV) | `Free` | Licence not stated | [Portal](https://www.ofgem.gov.uk/energy-data-and-research/data-portal) |
| **EU ETS Union Registry** (DG CLIMA) | `Europe` EU ETS installations | `Reference` | emissions | Download (XLSX) · Web | `Free` | 2025 verified emissions published Apr 2026 | [Union Registry](https://climate.ec.europa.eu/eu-action/eu-emissions-trading-system-eu-ets/union-registry_en) |
| **ENTSO-E TYNDP / ERAA / PEMMDB** | `Europe` ENTSO-E area | `Reference` | scenarios, capacity, load | Download (ZIP/XLSX) · Web | `Free` | Licence (unv.) | [ERAA](https://www.entsoe.eu/outlooks/eraa/) |
| **Marktstammdatenregister** (BNetzA) | `Western Europe` DE | `Reference` | plant register | Download (daily XML) · API (web services) | `Free` (download) · `Account` (web services) | DL-DE-BY 2.0 | [Download](https://www.marktstammdatenregister.de/MaStR/Datendownload) |
| **Global Energy Monitor** | `Global` | `Reference` | plant register | Download (XLSX via form) | `Free` | CC BY 4.0 | [Power tracker](https://globalenergymonitor.org/projects/global-integrated-power-tracker/) |
| **Open Infrastructure Map** | `Global` | `Reference` | plant register | Web · Download (Overpass) | `Free` | ODbL; lines, substations and plants from OpenStreetMap | [About](https://openinframap.org/about) |
| **JRC-IDEES / JRC-PPDB-OPEN** (EC JRC) | `Europe` EU | `Reference` | energy balances, plant register | Download | `Free` | IDEES runs to 2021. PPDB has not been updated since 2019 | [JRC](https://jeodpp.jrc.ec.europa.eu) · [PPDB](https://zenodo.org/records/3574566) |
| **Open Power System Data** | `Europe` | `Aggregator` `Reference` | load, generation, DA prices, plant register | Download (CSV/XLSX/SQLite) | `Free` | Licence per original owner. **Not updated since 2020** | [OPSD](https://open-power-system-data.org) |

## Commercial vendors

| Source | Area | Type | Data types | Delivery | Access | Licence & notes | Docs |
|---|---|---|---|---|---|---|---|
| **Montel** (Markets, EnAppSys, Energy Quantified, News) | `Europe` power, gas, carbon | `Commercial` `Forecast` | DA prices, ID prices, futures, RES forecast, outages, news | Web · API (pull and push) · Python · Excel | `Paid` (Energy Quantified 14-day trial) | Bought EnAppSys (2023), Energy Quantified (2023), Energy Brainpool (2024) | [Montel](https://www.montel.energy) |
| **Volue Insight** (ex-Wattsight) | `Europe` | `Commercial` `Forecast` | RES forecast, price forecast, NWP, ensembles | Web · API · Python · Excel | `Paid` | Owned by Advent and Generation IM since Oct 2024 | [Weather-driven fundamentals](https://www.volue.com/products-and-services/weather-driven-fundamentals) |
| **Kpler** (incl. ex-COR-e) | `Europe` 48 countries | `Commercial` `Forecast` | outages, RES forecast, load forecast, price forecast, gas storage | Terminal · API · cloud database | `Paid` | — | [Power](https://www.kpler.com/solutions/fundamental-intelligence/power) |
| **LSEG** (ex-Refinitiv) | `Global` | `Commercial` | DA prices, futures, RES forecast, news | Workspace · Excel · API · feeds | `Paid` | Resells Argus and ICIS | [LSEG](https://www.lseg.com) |
| **Bloomberg** | `Global` | `Commercial` | futures, DA prices, news | Terminal · B-PIPE · Data License · Snowflake | `Paid` | Includes BNEF research | [Bloomberg](https://professional.bloomberg.com) |
| **ICIS** (RELX) | `Europe` | `Commercial` | DA prices, futures, price forecast | ICIS Clarity · API · Excel | `Paid` | Energy Foresight fundamentals | [Delivery partners](https://www.icis.com/explore/about/data-delivery-partners) |
| **Argus Media** | `Global` | `Commercial` | DA prices, futures, news | Argus Direct · Excel · API · Snowflake | `Paid` | Available on Snowflake since Jan 2026 | [Argus](https://www.argusmedia.com) |
| **S&P Global Commodity Insights** (Platts) | `Global` | `Commercial` | DA prices, futures, LNG, price forecast | Platts Connect · Excel · API (streaming and bulk) | `Paid` | Also owns Enertel (2026) and the JKM benchmark | [Commodity Insights](https://www.spglobal.com/commodityinsights) |
| **Aurora Energy Research** | `Europe` · `Global` | `Commercial` `Forecast` | price forecast, capacity, scenarios | EOS platform · software | `Paid` | API not confirmed | [Aurora](https://auroraer.com) |
| **Rystad Energy** | `Global` | `Commercial` | capacity, generation | Cube Browser · API (Spektra, 2026) | `Paid` | — | [Rystad](https://www.rystadenergy.com) |
| **Modo Energy** | `GB & Ireland` · `Europe` · `North America` · `Asia-Pacific` AU | `Commercial` | ancillary services, price forecast | Terminal · API | `Paid` | Battery storage revenue indices | [Modo](https://modoenergy.com) |
| **Pexapark** | `Europe` (and US) | `Commercial` | price forecast | Web · API | `Paid` | PPA and battery reference prices | [Pexapark](https://pexapark.com) |

## Outside Europe

Summary level only: one row per main publisher, not checked dataset by dataset. Global statistics
(EIA International, IRENA, EI, UN, World Bank) and NASA POWER are listed above.

| Source | Area | Type | Data types | Delivery | Access | Licence & notes | Docs |
|---|---|---|---|---|---|---|---|
| **EIA API v2 and Grid Monitor** (EIA-930) | `North America` US | `Statistics` `Transparency` | load, load forecast, generation, flows, energy balances | API · Download | `Account` (key) | US public domain. EIA lost staff in 2025, and some reports were cancelled; the API still updates | [Open data](https://www.eia.gov/opendata) |
| **FERC EQR** | `North America` US | `Transparency` | auction results | Download | `Free` | Moving to XBRL-CSV (Order 917, 2026) | [FERC](https://www.ferc.gov) |
| **CAISO OASIS** | `North America` CAISO, WEIM, EDAM | `System operator` | DA prices, ID prices, ancillary services, load, generation | API (zipped CSV/XML) · Web | `Free` | EDAM went live in May 2026 | [OASIS](http://oasis.caiso.com) |
| **ERCOT Public API** | `North America` ERCOT | `System operator` | DA prices, ID prices, load, generation, ancillary services | API | `Account` (key) | Real-time co-optimisation (RTC+B) went live in Dec 2025 | [Developer portal](https://developer.ercot.com) |
| **PJM Data Miner 2** | `North America` PJM | `System operator` | DA prices, ID prices, load, generation, capacity, ancillary services | API · Web | `Account` | Non-members: 6 connections per minute, 50k rows per fetch | [Data Miner](https://dataminer2.pjm.com) |
| **MISO** | `North America` MISO | `System operator` | DA prices, ID prices, load, generation | API · Download | `Free` (real-time) · `Account` (Data Exchange) | — | [MISO](https://www.misoenergy.org) |
| **SPP** | `North America` SPP | `System operator` | DA prices, ID prices, load, generation | Download (CSV) | `Free` | RTO expanded west in Apr 2026 | [Portal](https://portal.spp.org) |
| **NYISO** | `North America` NYISO | `System operator` | DA prices, ID prices, load, generation, flows | Download (CSV) | `Free` | — | [MIS](http://mis.nyiso.com) |
| **ISO-NE** | `North America` New England | `System operator` | DA prices, ID prices, load, load forecast, generation | Download (ISO Express) · API (web services) | `Free` (downloads) · `Account` (API) | — | [ISO Express](https://www.iso-ne.com/isoexpress) |
| **IESO** | `North America` Ontario | `System operator` | DA prices, ID prices, load, generation | Download (XML/CSV) | `Free` | Nodal day-ahead market since May 2025; the HOEP price series ended | [Reports](https://reports-public.ieso.ca) |
| **AESO** | `North America` Alberta | `System operator` | DA prices, load, flows | API · Download | `Account` (key) | — | [API portal](https://developer-apim.aeso.ca) |
| **CENACE** | `North America` MX | `System operator` | DA prices, ID prices, load, generation | Web · Download (CSV) · API (unv.) | `Free` | API docs page returned an error | [CENACE](https://www.cenace.gob.mx) |
| **CME / ICE** (US) | `North America` · `Asia-Pacific` | `Exchange` | futures | Download (DataMine) · feeds · Web (delayed) | `Free` (delayed settlements on web) · `Paid` | Henry Hub, PJM, ERCOT and JKM futures | [CME](https://www.cmegroup.com) |
| **NOAA HRRR** | `North America` CONUS, Alaska | `Weather` | NWP | Download (NOMADS, AWS/GCP/Azure) | `Free` | US public domain. 3 km resolution, updated hourly | [NOMADS](https://nomads.ncep.noaa.gov) |
| **AEMO NEMWeb / MMS** | `Asia-Pacific` NEM (QLD, NSW, VIC, SA, TAS) | `System operator` | DA prices, load, generation, outages | Download (CSV/zip, MMS archive) | `Free` | © AEMO, reuse permitted. 5-minute dispatch. MMS Data Model v5.6 (Nov 2025) | [NEMWeb](https://nemweb.com.au) |
| **AEMO WEM** | `Asia-Pacific` Western Australia | `System operator` | DA prices, load, generation, outages | Download · Web | `Free` | — | [WEM](https://wa.aemo.com.au) |
| **OpenElectricity** (ex-OpenNEM) | `Asia-Pacific` NEM, WEM | `Aggregator` | generation, DA prices, emissions | API · SDKs | `Account` (key) | **CC BY-NC 4.0**; commercial use needs a licence | [OpenElectricity](https://openelectricity.org.au) |
| **JEPX** | `Asia-Pacific` JP | `Exchange` | DA prices, ID prices | Web · Download | `Free` | 30-minute system and area prices | [JEPX](https://www.jepx.jp) |
| **OCCTO and area TSOs** | `Asia-Pacific` JP, 10 areas | `System operator` | load, generation, flows, outages | Web · Download (CSV per TSO) | `Free` | — | [OCCTO](https://www.occto.or.jp) |
| **Grid-India** | `Asia-Pacific` IN | `System operator` | load, generation, frequency | Web · Download (PDF/XLS) | `Free` | No documented API | [Grid-India](https://grid-india.in) |
| **IEX** | `Asia-Pacific` IN | `Exchange` | DA prices, ID prices | Web · Download | `Free` (web) · `Paid` (history and feeds, unv.) | — | [IEX](https://www.iexindia.com) |
| **China NEA / CEC / NBS** | `Asia-Pacific` CN | `Statistics` | load, generation | Web | `Free` (headline figures) · `Paid` (detail) | No market API | [NEA](https://www.nea.gov.cn) |
| **KPX EPSIS** | `Asia-Pacific` KR | `System operator` | DA prices, load, generation, capacity | Web · Download · API (data.go.kr) | `Account` (key) | Legacy SMP API marked for deletion | [EPSIS](https://epsis.kpx.or.kr) |
| **Singapore EMC / EMA** | `Asia-Pacific` SG | `System operator` `Statistics` | DA prices, load | Web · Download | `Free` | EMA terms allow commercial reuse with credit | [EMC](https://www.emcsg.com) |
| **JMA** | `Asia-Pacific` JP | `Weather` | NWP, observations | Web (JSON) · NWP through JMBSC | `Free` (web) · `Paid` (real-time NWP) | No official API | [JMA](https://www.jma.go.jp) |
| **Platts JKM** (S&P Global) | `Asia-Pacific` North-East Asia | `Commercial` `Gas` | LNG, DA prices | API · feeds | `Paid` | — | [Commodity Insights](https://www.spglobal.com/commodityinsights) |
| **ONS** | `Latin America` BR (SIN) | `System operator` | load, generation, flows, DA prices | API (CKAN) · Download (S3: CSV/Parquet/XLSX) | `Free` | New S3 bucket; some datasets discontinued after Sep 2024 | [Open data](https://dados.ons.org.br) |
| **CCEE** | `Latin America` BR | `System operator` | DA prices | Download · API (unv.) | `Free` | Publishes the PLD price | [Open data](https://dadosabertos.ccee.org.br) |
| **Coordinador Eléctrico Nacional** | `Latin America` CL | `System operator` | DA prices, generation, load | Web · API (unv.) | `Account` (unv.) | The API endpoint could not be opened | [Coordinador](https://www.coordinador.cl) |
| **Eskom Data Portal** | `Africa` ZA | `System operator` | load, generation, outages | Web · Download (CSV) | `Free` | Bulk data on request by email | [Data portal](https://www.eskom.co.za/dataportal) |

## Gaps

- **Not confirmed on a primary page:**
  - Free history depth on Nord Pool.
  - Download formats on regelleistung.net and IBEX.
  - Any free access to ICE Endex.
  - APIs for THE and MIBGAS.
- **Not checked:** the German TSOs' own sites and the Elering, ČEPS and MAVIR portals.
- **Licences not confirmed:** REE, Terna, REN, Swissgrid, EirGrid, Statnett, PSE, ENTSO-E reuse terms and
  Renewables.ninja.
- **ENTSO-E SFTP shutdown:** planned for Sep 2025; whether it has happened is unconfirmed.
- **ENTSO-E rate limit:** the often-quoted 400 requests/min has no official source.
- **EUMETSAT:** licence by latency after the Nov 2025 policy change is unconfirmed.
- **Undocumented endpoints:** Statnett, EirGrid dashboard and SMARD JSON can change without notice.
- **Forecast services:** Meteologica's API and FTP delivery and ENFOR's coverage are not stated on their
  sites; ask the vendors. The licences for the WeatherNext and NVIDIA Earth-2 weights were seen only in
  secondary sources.
- **Outside Europe:** Chile's and Mexico's APIs could not be opened, and IEX's paid data terms were not
  checked.
