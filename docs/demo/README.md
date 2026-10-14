# Demo data

`Connections.csv` is a **fully synthetic** LinkedIn-style export: 105 fictional people at 11
invented companies across Libya, the Gulf and beyond, including a few names written in
Arabic. Any resemblance to real people or companies is coincidental.

Use it to try PNCA without touching your own network:

1. Start the app (`docker compose up -d --build`) and open <http://127.0.0.1:8199>.
2. Under **Add contacts → LinkedIn export**, upload `docs/demo/Connections.csv`.

LinkedIn exports carry no location, so the network map at first only shows clusters by
company. To see bridge contacts, set a city on a few people (contact page → **Edit
details**). Contacts in the same city get linked across companies.

The screenshots in `docs/assets/` were made from this file, with a few locations, pipeline
stages, follow-ups and tasks added through the app.
