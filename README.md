# Kart Racer

Retro-Kartrennen im Browser für bis zu 4 Spieler. Freie Plätze fahren Bots.

- `index.html` – das Spiel (läuft auch allein per Doppelklick, dann ohne Mehrspieler)
- `server.py` – Mehrspieler-Server, nur Python 3.10+ nötig, keine Zusatzpakete
- `render.yaml` – Einstellungen für das kostenlose Hosting bei Render

## Lokal starten

```
python server.py
```

Dann im Browser `http://localhost:8000` öffnen. Mit `?raum=name` am Ende des Links
spielt eine Gruppe in einem eigenen Raum, z. B. `http://localhost:8000/?raum=klasse10b`.

## Im selben Netzwerk spielen (z. B. Schul-WLAN)

1. `python server.py` starten.
2. Eigene IP-Adresse herausfinden: `ipconfig` → „IPv4-Adresse“, z. B. `192.168.1.23`.
3. Mitspieler öffnen `http://192.168.1.23:8000`.

Fragt die Windows-Firewall nach, „Zugriff zulassen“ wählen. In vielen Schulnetzen sind
Verbindungen zwischen Geräten gesperrt; dann bleibt nur das Hosting im Internet.

## Kostenlos im Internet hosten (Render)

1. Konto bei https://github.com anlegen und ein neues Repository erstellen.
2. Diesen Ordner hochladen (auf GitHub „Add file → Upload files“ oder per `git push`).
3. Konto bei https://render.com anlegen (Anmeldung mit GitHub geht).
4. „New → Blueprint“ wählen, das Repository auswählen und bestätigen.
   Render liest `render.yaml` und startet den Server.
5. Nach ein paar Minuten gibt es einen Link wie `https://kart-racer-xyz.onrender.com`.
   Den teilst du mit deinen Mitschülern.

Hinweis: Im Gratis-Tarif schläft der Server nach 15 Minuten ohne Besucher ein.
Der erste Aufruf danach dauert etwa eine Minute, dann läuft alles normal.

## So funktioniert der Mehrspieler

Jeder Browser simuliert sein eigenes Kart und schickt dessen Zustand etwa 20-mal pro
Sekunde an den Server, der ihn an alle anderen im Raum weiterreicht. Der Spieler mit der
kleinsten Kennung ist Host: Er startet die Rennen und steuert die Bots.
