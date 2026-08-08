# AstroMatch Web — pubblicazione

Questa cartella è pronta per essere pubblicata come Web Service.

## Metodo consigliato: Render + GitHub

1. Crea un repository GitHub chiamato `astromatch`.
2. Carica il contenuto di questa cartella nel repository.
3. In Render: New → Web Service.
4. Collega il repository GitHub.
5. Seleziona Docker come runtime (è già presente Dockerfile).
6. Crea il servizio.
7. Render fornirà un indirizzo `https://...onrender.com`.

Il file `render.yaml` imposta già:
- servizio web Docker
- health check `/api/health`
- deploy automatico

## Nota
Il piano gratuito è adatto a test e dimostrazione; Render segnala che i servizi
free vanno in sleep dopo inattività. Per un servizio pubblico stabile valutare
un piano a pagamento.

## Dominio personale
Dopo il primo deploy puoi aggiungere un dominio personalizzato dalle impostazioni
del servizio Render.
