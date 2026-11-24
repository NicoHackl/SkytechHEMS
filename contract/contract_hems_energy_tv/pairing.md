# SkytechHEMS ↔ Skytech Energy TV

Version 1 für die Kopplung im selben lokalen IPv4-Netz. Die Beteiligten sind die TV-App,
die Companion App auf dem iPhone, das HEMS-Panel und die ausgewählte Home-Assistant-Instanz.

1. Apple TV öffnet für fünf Minuten einen HTTP-Listener auf einer privaten IPv4-Adresse
   und einem freien Port. Der QR-Code öffnet die Einstiegsseite `/?pair=<UUID>`. Der
   Zufallswert gilt für diese Sitzung.
2. Die Einstiegsseite öffnet `homeassistant://navigate/app/<addon-slug>/energy-tv/<ipv4>/<port>/<UUID>`.
   Der Supervisor-Slug entspricht dem HEMS-Repository aus der Installationsanleitung oder
   einer lokalen Installation. Die Companion App wählt die Home-Assistant-Instanz.
3. Das HEMS-Panel liest den Kopplungspfad aus der gleichursprünglichen HA-Seite und zeigt
   „Mit Apple TV verbinden“. Nach Bestätigung navigiert das iPhone zu
   `http://<ipv4>:<port>/authorize?pair=<UUID>&instance=<HA-Ursprung>`.
4. Die TV-App bindet diese Instanz an einen eigenen OAuth-`state` und startet auf ihr
   `/auth/authorize` mit S256-PKCE. `client_id` ist der lokale Listener-Ursprung mit
   abschließendem Schrägstrich. Die `redirect_uri` ist `/callback` auf demselben Ursprung.
5. Die TV-App prüft `state`, nimmt den Einmalcode entgegen und tauscht ihn selbst bei der
   gebundenen Home-Assistant-Instanz ein. Bei Erfolg speichert sie deren Adresse,
   Client-ID und Refresh-Token im Geräteschlüsselbund und schließt den Listener.
   Der PKCE-Verifier bleibt auf Apple TV. HEMS vermittelt nur URL und Sitzung und verarbeitet
   keine Home-Assistant-Zugangsdaten.

Die manuelle Einrichtung mit Adresse und Token ist weiterhin verfügbar.
Der Ablauf verwendet die vorhandenen HEMS-Berechtigungen des ausgewählten HA-Benutzers.
