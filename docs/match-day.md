# Wedstrijddag: checklist voor de streamer

Voor de vrijwilliger die bij Almere Pioneers de stream verzorgt. Technische
achtergrond staat in de Engelse docs; hier alleen wat je op de dag doet.

Wat je nodig hebt: de MacBook met OBS en dit project, de USB-kabel naar de
Anatec AK30, de iPhone met LensLink, en een werkende `.env` (inloggegevens
FOYS en het OBS-wachtwoord staan erin; vraag ze aan de beheerder, zet ze
nooit in een appje).

---

## Een uur voor de wedstrijd

1. MacBook aan, op de wifi van de hal. iPhone op dezelfde wifi.
2. AK30 aanzetten en met de USB-kabel aan de MacBook.
3. OBS starten.
4. Terminal openen, dan:

       cd ~/Documents/anatec-ak30-obs-overlay
       source .venv/bin/activate
       python3 scoreboard/server.py --anatec auto

   Laat dit venster open staan tot na de wedstrijd.
5. In de browser: http://localhost:5001. Kies de wedstrijd van vandaag.
6. In OBS het statusvenster (dock) bekijken:
   - Anatec: groen zodra de server de console gevonden heeft
   - FOYS: groen na het kiezen van de wedstrijd
   - OBS: groen; staat er een scène als "ontbreekt", dan klopt de naam in
     OBS niet met `.env`
7. iPhone: LensLink starten, adres invullen in OBS, beeld controleren.
8. Scène "Scène 2: WIDE Overlay" kiezen. Druk op een knop van de AK30 en
   kijk of de balk meebeweegt.
9. Stream starten in OBS. Controleer op een telefoon of het beeld op
   YouTube aankomt (reken op zo'n 20 seconden vertraging).

---

## Tijdens de wedstrijd

- Niets invoeren. Score, klok en fouten komen vanzelf van de AK30 en van
  de DWF-tablet van de tafel.
- Let op de meldingen in het dock. Bij de rust zet de server zelf de
  statistieken in beeld en zegt wanneer hij terugschakelt. Schakel je zelf,
  dan laat de server dat zo.
- Komt er geen foutpopup meer, of loopt de score achter: kijk eerst in het
  dock welke bron rood staat, daarna in het Terminal-venster.
- Fluit voor de laatste periode: de server wacht tot de tafel de wedstrijd
  in de DWF afsluit en zet dan de eindstand in beeld.

---

## Na de wedstrijd

Volgt er nog een wedstrijd, dan blijven server, OBS en iPhone gewoon
aan:

1. Wachten tot de eindstand in beeld staat (of zelf de eindscène kiezen).
2. Stream stoppen in OBS.
3. In de browser op http://localhost:5001 de volgende wedstrijd kiezen.
   Het dock springt terug naar de beginstand; de AK30 wordt door de tafel
   zelf op nul gezet.
4. Scène "Scène 2: WIDE Overlay" kiezen en een nieuwe stream starten in
   OBS. Even op een telefoon controleren of de nieuwe uitzending loopt.

Na de laatste wedstrijd:

1. Wachten tot de eindstand in beeld staat.
2. Stream stoppen in OBS.
3. In Terminal: Ctrl+C.
4. USB-kabel los, iPhone van de klem.

---

## Als het misgaat

| Wat je ziet | Wat je doet |
|---|---|
| Anatec blijft rood | Kabel opnieuw insteken; `auto` zoekt de poort zelf terug. Staat `capture.py` nog open? Sluiten, de poort kan maar door één programma gebruikt worden. |
| FOYS rood na het kiezen | Inloggegevens in `.env` controleren. De wedstrijd gaat door; score en klok komen van de AK30, alleen namen en fouten ontbreken. |
| OBS rood | Staat OBS aan? Tools > WebSocket Server Settings: server aan, poort 4455, wachtwoord gelijk aan `.env`. |
| Browser Source blijft leeg | Draait het Terminal-venster nog? Eerst de server, dan OBS. |
| iPhone geen beeld | Zelfde wifi? Nieuw IP-adres gekregen? Op de iPhone bij deze wifi "Privé-wifi-adres" uitzetten helpt. |
| Waarschuwing over LibreSSL bij het starten | Negeren. |

Niet zelf aan `.env` of aan de scènenamen in OBS sleutelen tijdens een
wedstrijd; dat doen we erna, aan het bureau.
