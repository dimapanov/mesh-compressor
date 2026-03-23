#!/usr/bin/env python3
"""
Generate realistic Meshtastic mesh network messages in 8 languages.
No external APIs — template + random parameter approach only.
"""

import os
import random
import string
from pathlib import Path

random.seed(42)

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "multilingual"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TRAIN_COUNT = 45000
TEST_COUNT = 500


# ─── Spanish (es) ────────────────────────────────────────────────────────────
ES_TEMPLATES = [
    # Greetings / Status
    ("¡Buenos días!",),
    ("¡Buenas tardes!",),
    ("¡Buenas noches!",),
    ("¿Qué tal? ¿Me reciben?",),
    ("Todo bien por aquí 👍",),
    ("Aquí andamos, ¿y ustedes?",),
    ("¡Hola a todos!",),
    ("Buen día para hoy",),
    ("¡Saludos desde {city}!",),
    ("¿Cómo andan todos?",),
    ("Todo OK por mi parte",),
    ("¡Aquí sigo! Signal {sig}/5",),
    ("¡Buena onda! Todo en orden",),
    ("A ver si alguien me lee…",),
    ("Confirmo que recibo fuerte",),
    ("Buenas, aquí {name} {sig}/{maxsig}",),
    ("¡Hey! ¿Hay alguien activo?",),
    ("Recibido alto y claro",),
    ("Nodo {name} en línea",),
    ("Todos bien por {location}",),
    ("Día bonito para mesh 🏔️",),
    # Location / GPS
    ("GPS: {lat:.4f}, {lon:.4f}",),
    ("Estoy en {lat:.4f} N, {lon:.4f} W",),
    ("Coordenadas: {lat:.4f}, {lon:.4f}",),
    ("Cerca del {landmark}",),
    ("A 5 km al norte del puente",),
    ("Senderos del {area}, heading norte",),
    ("Por la zona de {city}",),
    ("En la cima del {mountain} 📍",),
    ("{lat:.3f}, {lon:.3f} — punto de encuentro",),
    ("Me muevo hacia el {direction}",),
    ("Aquí {lat:.4f} N",),
    ("Ubicación: {lat:.3f}°N, {lon:.3f}°W",),
    ("En la costa, {distance} km al sur",),
    ("Zona urbana {city}",),
    ("Refugio de montaña, GPS ok",),
    # Weather
    ("Temperatura {temp}°C, viento {wind} km/h del SW",),
    ("Hace {temp}°C, sensación {feels}°C",),
    ("Clima: {desc}, {temp}°C 💨",),
    ("{temp}°C, humedad {hum}%",),
    ("Nublado, {temp}°C, lluvia al 40%",),
    ("Día soleado, {temp}°C ☀️",),
    ("Lluvia moderada, {temp}°C 🌧️",),
    ("Viento del norte a {wind} km/h",),
    ("Mañana fresca, {temp}°C",),
    ("Temperatura actual: {temp}°C",),
    ("{temp}°C en {city}",),
    ("Presión: {pres} hPa, humedad {hum}%",),
    ("Tormenta aproximándose ⛈️",),
    ("Noche clara, {temp}°C",),
    ("¡Calor! {temp}°C y subiendo 🔥",),
    # Battery / Signal
    ("Batería al {bat}%",),
    ("Nivel de batería: {bat}% 🔋",),
    ("Señal fuerte, 3 saltos",),
    ("Batería baja: {bat}% ⚠️",),
    ("Signal {sig}/5, batería {bat}%",),
    ("5 saltos hasta la base",),
    ("Signal débil aquí, solo 1 barra 📶",),
    ("Batería OK ({bat}%), signal {sig}",),
    ("{sig}/5 signal, todo estable",),
    ("Bat: {bat}%, sig: {sig}/5 ✅",),
    ("Conectado directo, signal {sig}",),
    ("Batería cargando: {bat}%",),
    ("Signal media, {hops} saltos",),
    # Emergency / Help
    ("¡Emergencia! Necesito ayuda en punto {marker} 🚨",),
    ("Beacon de emergencia activado 🚨",),
    ("¿Alguien me recibe? ¡Emergencia!",),
    ("Ayuda requerida en coordenadas {lat:.4f},{lon:.4f}",),
    ("Mensaje de emergencia — marcar {marker}",),
    ("¡Favor de reportar! Situación crítica",),
    ("Emergencia en {location}",),
    ("Alerta: necesito asistencia médica",),
    ("Se perdió grupo — requerimos ayuda",),
    ("¡Urgente! Equipo en problemas",),
    ("Beacon activado por {name}",),
    ("¿Hay alguien en {city}? ¡Emergencia!",),
    # Casual chat
    ("¡Bonito día hoy! 🌞",),
    ("Buen finde para todos",),
    ("¡Nos vemos en el meetup! 🏕️",),
    ("¿Alguien va al punto de reunión?",),
    ("Buena red hoy, saludos",),
    ("¡Gracias por la red! ⭐",),
    ("Día tranquilo en la zona",),
    ("¿Qué tal el finde?",),
    ("Yo por aquí, todo tranquilo",),
    ("¡Buena malla hoy!",),
    ("Aburrido… a esperar que llueva 😴",),
    ("Alguien para un café virtual? ☕",),
    ("¡Salud desde {city}!",),
    # Coordination
    ("Equipo 2, muévanse al punto {cp}",),
    ("Todos den su reporte por favor",),
    ("Check-in general — ¿quién recibe?",),
    ("Grupo {num} en posición {num2}",),
    ("Reunión en 15 minutos en {location}",),
    ("Coordinación: todas las unidades confirmar",),
    ("Equipo 1 avance al norte",),
    ("¿Listos? A las 3pm en punto",),
    ("Rumbo al punto {cp}, confirmen",),
    ("Punto {num} establecido, cubriendo zona",),
    ("Reforzar posición en {landmark}",),
    ("Rally en {city} a las {time}",),
    ("Todos a cobertura, nos movemos",),
    # Technical
    ("Nodos activos: {nodes}",),
    ("Actualizado a firmware v{fw}",),
    ("Cambié al canal {ch}",),
    ("Canal {ch} — primary ahora",),
    ("Nodo count: {nodes}",),
    ("{nodes} nodos en la red",),
    ("Canales: {ch}, {ch2} activos",),
    ("Firmware v{fw} — todo ok ✅",),
    ("{nodes} nodos, {direct} directos",),
    ("Actualizando a v{fw} ahora",),
    ("Test de alcance, ¿me leen?",),
    ("Rangetest: {dist} km resultados",),
    ("Mesh estable, {nodes} nodos 🌐",),
    ("TX power ajustado a {tx} dBm",),
    ("Canal cambiado, probando cobertura",),
]


def es_generate():
    city = random.choice(
        [
            "Madrid",
            "Barcelona",
            "Sevilla",
            "Valencia",
            "Bilbao",
            "Málaga",
            "Granada",
            "Zaragoza",
            "Toledo",
            "Córdoba",
        ]
    )
    landmark = random.choice(
        [
            "puente mayor",
            "lago",
            "bosque",
            "río",
            "campus",
            "parque central",
            "refugio",
            "antena",
        ]
    )
    area = random.choice(["pinos", "montaña", "valle", "costa", "campo"])
    mountain = random.choice(
        ["Cerro Verde", "Pico Norte", "Montaña Real", "Cerro Azul", "Peña Mayor"]
    )
    direction = random.choice(["norte", "sur", "este", "oeste"])
    name = random.choice(
        ["Nodo-01", "Mesh-ES", "Node-Alpha", "Base-Mad", "Node-7B", "Repeater-1"]
    )
    location = random.choice(["zona rural", "ciudad", "playa", "monte", "campo"])
    desc = random.choice(["despejado", "nublado", "lluvioso", "ventoso", "neblina"])
    marker = random.randint(1, 99)
    cp = random.randint(1, 20)
    num = random.randint(1, 9)
    num2 = random.randint(1, 9)
    time = random.choice(["3pm", "2pm", "4pm", "18:00", "19:30"])
    fw = random.choice(["2.5.14", "2.6.1", "2.7.3", "2.8.0"])
    nodes = random.randint(5, 120)
    direct = random.randint(1, 15)
    ch = random.randint(1, 20)
    ch2 = random.randint(1, 20)
    dist = round(random.uniform(0.5, 25.0), 1)
    tx = random.choice([6, 12, 17, 20, 22, 27])
    lat = round(random.uniform(36.0, 43.5), 4)
    lon = round(random.uniform(1.5, 10.0), 4)
    temp = round(random.uniform(-5, 40), 1)
    feels = round(temp + random.uniform(-3, 3), 1)
    wind = random.randint(0, 60)
    hum = random.randint(20, 100)
    pres = random.randint(990, 1030)
    bat = random.randint(5, 100)
    sig = random.randint(1, 5)
    maxsig = 5
    distance = random.randint(1, 50)
    hops = random.randint(1, 7)
    template = random.choice(ES_TEMPLATES)
    return template[0].format(**locals())


# ─── German (de) ─────────────────────────────────────────────────────────────
DE_TEMPLATES = [
    ("Guten Morgen!",),
    ("Guten Abend!",),
    ("Moin aus {city}!",),
    ("Alles klar hier 👍",),
    ("Jemand da? Hallo?",),
    ("Empfang gut hier, und bei euch?",),
    ("Grüße vom {landmark}!",),
    ("Tag auch!",),
    ("Moin moin!",),
    ("Tag, {name} ist on",),
    ("Hier läuft alles normal",),
    ("Na? Wie geht's?",),
    ("Bist du noch da?",),
    ("Ich höre dich gut",),
    ("Alles im grünen Bereich",),
    ("{city} meldet sich 📡",),
    ("Hier {name}, Signal {sig}/5",),
    ("Mensch, schöner Tag heute 🌤️",),
    # GPS
    ("GPS: {lat:.4f}, {lon:.4f}",),
    ("Standort: {lat:.4f} N, {lon:.4f} O",),
    ("Koordinaten {lat:.3f}°N, {lon:.3f}°O",),
    ("Nahe dem {landmark}",),
    ("{distance} km nördlich der Brücke",),
    ("Im Waldgebiet {area}",),
    ("Auf dem {mountain} 🌲📍",),
    ("Position: {lat:.4f},{lon:.4f}",),
    ("Richtung {direction} unterwegs",),
    ("Stadtgebiet {city}",),
    ("Am {landmark} angekommen",),
    ("{lat:.3f} N, {lon:.3f} O",),
    ("Küste, {distance} km südlich",),
    # Weather
    ("{temp}°C, Wind {wind} km/h aus SW",),
    ("Aktuell {temp}°C, gefühlt {feels}°C",),
    ("Wetter: {desc}, {temp}°C 🌥️",),
    ("{temp}°C, Luftfeuchtigkeit {hum}%",),
    ("Bewölkt, {temp}°C, Regen 40%",),
    ("Sonnig, {temp}°C ☀️",),
    ("Leichter Regen, {temp}°C 🌧️",),
    ("Nordwind, {wind} km/h",),
    ("Kühle {temp}°C am Morgen",),
    ("Temperatur: {temp}°C",),
    ("{temp}°C in {city}",),
    ("Druck: {pres} hPa, feucht {hum}%",),
    ("Gewitter im Anmarsch ⛈️",),
    ("Klar, {temp}°C nachts",),
    ("Heiß! {temp}°C und steigend 🔥",),
    # Battery
    ("Akku bei {bat}%",),
    ("Akku: {bat}% 🔋",),
    ("Signal stark, 3 Sprünge",),
    ("Akku schwach: {bat}% ⚠️",),
    ("Signal {sig}/5, Akku {bat}%",),
    ("5 Sprünge zur Basis",),
    ("Signal mittel, 2 Balken 📶",),
    ("Akku OK ({bat}%), Signal {sig}",),
    ("{sig}/5, alles stabil",),
    ("Akku laden: {bat}%",),
    ("Direktverbindung, Signal {sig}",),
    ("{sig}/5 Empfang, alles gut",),
    # Emergency
    ("NOTFALL! Brauche Hilfe bei {marker} 🚨",),
    ("Notfall-Bake aktiviert 🚨",),
    ("Hört mich jemand? NOTFALL!",),
    ("Hilfe nötig bei {lat:.4f},{lon:.4f}",),
    ("Notsignal — Punkt {marker}",),
    ("Dringend: brauche Unterstützung!",),
    ("Notfall in {location}",),
    ("Brauche medizinische Hilfe",),
    ("Gruppe verirrt — brauchen Hilfe",),
    ("Dringend! Team in Schwierigkeiten",),
    ("Bake von {name} aktiviert",),
    ("Jemand in {city}? NOTFALL!",),
    # Casual
    ("Schöner Tag heute! 🌞",),
    ("Gutes Wochenende allerseits",),
    ("Bis zum Treffen! 🏕️",),
    ("Jemand zum Treffpunkt?",),
    ("Netz läuft gut heute 👍",),
    ("Danke fürs Netz! ⭐",),
    ("Ruhiger Tag hier",),
    ("Wie war euer Wochenende?",),
    ("Alles ruhig hier",),
    ("Tolles Mesh heute!",),
    ("Etwas langweilig 😴",),
    ("Kaffee? ☕",),
    ("Grüße aus {city}!",),
    # Coordination
    ("Team 2, geht zu Punkt {cp}",),
    ("Alle bitte melden!",),
    ("Allgemeiner Check-in — wer hört?",),
    ("Gruppe {num} an Position {num2}",),
    ("Treffen in 15 Min bei {location}",),
    ("Alle Einheiten: Status melden",),
    ("Team 1 nach {direction}",),
    ("Bereit? Um {time} genau",),
    ("Kurs auf Punkt {cp}, bestätigen",),
    ("Punkt {num} besetzt, Zone {area}",),
    ("Position verstärken am {landmark}",),
    ("Treff in {city} um {time}",),
    ("Alle in Deckung, wir bewegen uns",),
    # Technical
    ("Aktive Knoten: {nodes}",),
    ("Firmware auf v{fw} aktualisiert",),
    ("Kanal gewechselt auf {ch}",),
    ("Kanal {ch} — primär",),
    ("Knotenanzahl: {nodes}",),
    ("{nodes} Knoten im Netz",),
    ("Kanäle: {ch}, {ch2} aktiv",),
    ("Firmware v{fw} — alles OK ✅",),
    ("{nodes} Knoten, {direct} direkt",),
    ("Update auf v{fw} läuft",),
    ("Reichweitentest, hört mich jemand?",),
    ("Test: {dist} km Ergebnis",),
    ("Mesh stabil, {nodes} Knoten 🌐",),
    ("TX-Leistung auf {tx} dBm",),
]


def de_generate():
    city = random.choice(
        [
            "Berlin",
            "München",
            "Hamburg",
            "Frankfurt",
            "Köln",
            "Stuttgart",
            "Dresden",
            "Heidelberg",
            "Freiburg",
            "Nürnberg",
        ]
    )
    landmark = random.choice(
        [
            "Brücke",
            "See",
            "Wald",
            "Turm",
            "Berg",
            "Schloss",
            "Marktplatz",
            "Bahnhof",
            "Feld",
            "Kirche",
        ]
    )
    area = random.choice(
        ["Schwarzwald", "Bayern", "Alpenvorland", "Odenwald", "Spessart", "Erzgebirge"]
    )
    mountain = random.choice(
        ["Feldberg", "Watzmann", "Brocken", "Zugspitze", "Schwarzwald"]
    )
    direction = random.choice(["Norden", "Süden", "Osten", "Westen"])
    name = random.choice(
        ["Node-DE-01", "Mesh-DE", "Knoten-7B", "Base-BER", "DL-Node", "Repeater-1"]
    )
    location = random.choice(["ländlicher Raum", "Stadt", "Wald", "Gebirge", "Feld"])
    desc = random.choice(["klar", "bewölkt", "regnerisch", "windig", "nebelig"])
    marker = random.randint(1, 99)
    cp = random.randint(1, 20)
    num = random.randint(1, 9)
    num2 = random.randint(1, 9)
    time = random.choice(["15:00", "14:00", "16:00", "18:00", "19:30"])
    fw = random.choice(["2.5.14", "2.6.1", "2.7.3", "2.8.0"])
    nodes = random.randint(5, 120)
    direct = random.randint(1, 15)
    ch = random.randint(1, 20)
    ch2 = random.randint(1, 20)
    dist = round(random.uniform(0.5, 25.0), 1)
    tx = random.choice([6, 12, 17, 20, 22, 27])
    lat = round(random.uniform(47.0, 55.0), 4)
    lon = round(random.uniform(6.0, 15.0), 4)
    temp = round(random.uniform(-10, 35), 1)
    feels = round(temp + random.uniform(-3, 3), 1)
    wind = random.randint(0, 60)
    hum = random.randint(20, 100)
    pres = random.randint(990, 1030)
    bat = random.randint(5, 100)
    sig = random.randint(1, 5)
    distance = random.randint(1, 50)
    hops = random.randint(1, 7)
    template = random.choice(DE_TEMPLATES)
    return template[0].format(**locals())


# ─── French (fr) ─────────────────────────────────────────────────────────────
FR_TEMPLATES = [
    ("Bonjour à tous!",),
    ("Bonsoir!",),
    ("Salut de {city}!",),
    ("Ça va? Vous me recevez?",),
    ("Tout va bien ici 👍",),
    ("On est là, et vous?",),
    ("Salutations du {landmark}!",),
    ("Bonjour!",),
    ("Coucou!",),
    ("Hey, quelqu'un?",),
    ("Signal OK, {sig}/5",),
    ("Tout semble fonctionner",),
    ("{name} en ligne depuis {city}",),
    ("Beau temps aujourd'hui 🌞",),
    ("Bonne mesh ce matin",),
    ("Salutations de {name}!",),
    # GPS
    ("GPS: {lat:.4f}, {lon:.4f}",),
    ("Position: {lat:.4f} N, {lon:.4f} E",),
    ("Coordonnées: {lat:.3f}°N, {lon:.3f}°E",),
    ("Près du {landmark}",),
    ("À {distance} km au nord du pont",),
    ("Zone {area}, en direction {direction}",),
    ("Sommet du {mountain} 📍",),
    ("{lat:.4f} N, {lon:.4f} E",),
    ("En route vers {direction}",),
    ("Quartier {city}",),
    ("{lat:.3f}, {lon:.3f} — rdv ici",),
    ("Côte, {distance} km au sud",),
    ("Forêt {area}",),
    # Weather
    ("Température {temp}°C, vent {wind} km/h du SW",),
    ("Il fait {temp}°C, ressenti {feels}°C",),
    ("Météo: {desc}, {temp}°C 🌥️",),
    ("{temp}°C, humidité {hum}%",),
    ("Nuageux, {temp}°C, pluie 40%",),
    ("Ensoleillé, {temp}°C ☀️",),
    ("Pluie légère, {temp}°C 🌧️",),
    ("Vent du nord, {wind} km/h",),
    ("Matin fraîche, {temp}°C",),
    ("Température actuelle: {temp}°C",),
    ("{temp}°C à {city}",),
    ("Pression: {pres} hPa, hum. {hum}%",),
    ("Orage qui approche ⛈️",),
    ("Nuit claire, {temp}°C",),
    ("Chaud! {temp}°C et ça monte 🔥",),
    # Battery
    ("Batterie à {bat}%",),
    ("Batterie: {bat}% 🔋",),
    ("Signal fort, 3 sauts",),
    ("Batterie faible: {bat}% ⚠️",),
    ("Signal {sig}/5, batterie {bat}%",),
    ("5 sauts jusqu'à la base",),
    ("Signal moyen, 2 barres 📶",),
    ("Batterie OK ({bat}%), signal {sig}",),
    ("{sig}/5 signal, tout stable",),
    ("Batterie en charge: {bat}%",),
    ("Connexion directe, signal {sig}",),
    # Emergency
    ("URGENCE! Besoin d'aide au point {marker} 🚨",),
    ("Balise d'urgence activée 🚨",),
    ("Quelqu'un m'entend? URGENCE!",),
    ("Aide requise à {lat:.4f},{lon:.4f}",),
    ("Signal d'urgence — point {marker}",),
    ("Urgent: besoin de soutien!",),
    ("Urgence à {location}",),
    ("Besoin d'aide médicale",),
    ("Groupe perdu — besoin d'aide",),
    ("Urgent! Équipe en difficulté",),
    ("Balise {name} activée",),
    ("Quelqu'un à {city}? URGENCE!",),
    # Casual
    ("Belle journée! 🌞",),
    ("Bon week-end à tous",),
    ("On se voit au rendez-vous! 🏕️",),
    ("Quelqu'un au point de rencontre?",),
    ("Réseau stable aujourd'hui 👍",),
    ("Merci pour le réseau! ⭐",),
    ("Journée tranquille",),
    ("Comment va le week-end?",),
    ("Tout va bien ici",),
    ("Super mesh aujourd'hui!",),
    ("Un peu ennuyeux 😴",),
    ("Un café? ☕",),
    ("Salutations de {city}!",),
    # Coordination
    ("Équipe 2, déplacez-vous au point {cp}",),
    ("Tout le monde se manifeste!",),
    ("Check-in général — qui reçoit?",),
    ("Groupe {num} en position {num2}",),
    ("Rendez-vous dans 15 min à {location}",),
    ("Coordination: toutes les unités confirmer",),
    ("Équipe 1 avancer vers {direction}",),
    ("Prêts? À {time} précises",),
    ("Cap sur le point {cp}, confirmez",),
    ("Point {num} établi, couvrant zone {area}",),
    ("Renforcer position au {landmark}",),
    ("Rassemblement à {city} à {time}",),
    ("Tous à couvert, on bouge",),
    # Technical
    ("Nœuds actifs: {nodes}",),
    ("Firmware mis à jour vers v{fw}",),
    ("Canal changé vers {ch}",),
    ("Canal {ch} — primaire",),
    ("Nombre de nœuds: {nodes}",),
    ("{nodes} nœuds dans le réseau",),
    ("Canaux: {ch}, {ch2} actifs",),
    ("Firmware v{fw} — tout OK ✅",),
    ("{nodes} nœuds, {direct} directs",),
    ("Mise à jour vers v{fw} en cours",),
    ("Test de portée, vous m'entendez?",),
    ("Test: {dist} km résultats",),
    ("Mesh stable, {nodes} nœuds 🌐",),
    ("Puissance TX réglée à {tx} dBm",),
]


def fr_generate():
    city = random.choice(
        [
            "Paris",
            "Lyon",
            "Marseille",
            "Nice",
            "Bordeaux",
            "Toulouse",
            "Strasbourg",
            "Brest",
            "Nantes",
            "Rennes",
        ]
    )
    landmark = random.choice(
        [
            "pont",
            "lac",
            "forêt",
            "colline",
            "tour",
            "cathédrale",
            "place",
            "gare",
            "champs",
            "village",
        ]
    )
    area = random.choice(["forêt", "montagne", "côte", "champ", "province"])
    mountain = random.choice(["Mont Blanc", "Puy de Dôme", "Alpes", "Jura", "Pyrénées"])
    direction = random.choice(["nord", "sud", "est", "ouest"])
    name = random.choice(
        ["Node-FR-01", "Mesh-FR", "Node-7B", "Base-PAR", "FR-Node", "Relay-1"]
    )
    location = random.choice(["zone rurale", "ville", "forêt", "montagne", "plaine"])
    desc = random.choice(["dégagé", "nuageux", "pluvieux", "venté", "brumeux"])
    marker = random.randint(1, 99)
    cp = random.randint(1, 20)
    num = random.randint(1, 9)
    num2 = random.randint(1, 9)
    time = random.choice(["15h", "14h", "16h", "18h", "19h30"])
    fw = random.choice(["2.5.14", "2.6.1", "2.7.3", "2.8.0"])
    nodes = random.randint(5, 120)
    direct = random.randint(1, 15)
    ch = random.randint(1, 20)
    ch2 = random.randint(1, 20)
    dist = round(random.uniform(0.5, 25.0), 1)
    tx = random.choice([6, 12, 17, 20, 22, 27])
    lat = round(random.uniform(41.0, 51.0), 4)
    lon = round(random.uniform(-5.0, 8.0), 4)
    temp = round(random.uniform(-5, 38), 1)
    feels = round(temp + random.uniform(-3, 3), 1)
    wind = random.randint(0, 70)
    hum = random.randint(20, 100)
    pres = random.randint(990, 1030)
    bat = random.randint(5, 100)
    sig = random.randint(1, 5)
    distance = random.randint(1, 50)
    hops = random.randint(1, 7)
    template = random.choice(FR_TEMPLATES)
    return template[0].format(**locals())


# ─── Portuguese (pt) ─────────────────────────────────────────────────────────
PT_TEMPLATES = [
    ("Bom dia!",),
    ("Boa tarde!",),
    ("Boa noite!",),
    ("Oi, tudo bem? Me ouvem?",),
    ("Tudo certo por aqui 👍",),
    ("Estou aqui, e vocês?",),
    ("Saudações de {city}!",),
    ("Alguém me ouve?",),
    ("{name} online",),
    ("Tudo funcionando bem",),
    ("Confirmo que recebo bem",),
    ("Sinal {sig}/5, tudo ok",),
    ("Bom dia de {weather}!",),
    ("Olá do {landmark}!",),
    ("{city} na rede 📡",),
    # GPS
    ("GPS: {lat:.4f}, {lon:.4f}",),
    ("Coordenadas: {lat:.4f} S, {lon:.4f} W",),
    ("Local: {lat:.3f}°S, {lon:.3f}°W",),
    ("Perto do {landmark}",),
    ("A {distance} km ao norte da ponte",),
    ("Área de {area}, indo para {direction}",),
    ("No topo do {mountain} 📍",),
    ("{lat:.4f} S, {lon:.4f} W",),
    ("Seguindo para {direction}",),
    ("Zona urbana {city}",),
    ("{lat:.3f}, {lon:.3f} — ponto de encontro",),
    ("Costa, {distance} km ao sul",),
    # Weather
    ("Temperatura {temp}°C, vento {wind} km/h do SW",),
    ("Faz {temp}°C, sensação {feels}°C",),
    ("Clima: {desc}, {temp}°C 🌥️",),
    ("{temp}°C, umidade {hum}%",),
    ("Nublado, {temp}°C, chuva 40%",),
    ("Ensolarado, {temp}°C ☀️",),
    ("Chuva leve, {temp}°C 🌧️",),
    ("Vento do norte, {wind} km/h",),
    ("Manhã fresca, {temp}°C",),
    ("Temperatura atual: {temp}°C",),
    ("{temp}°C em {city}",),
    ("Pressão: {pres} hPa, umid. {hum}%",),
    ("Tempestade se aproximando ⛈️",),
    ("Noite clara, {temp}°C",),
    ("Calor! {temp}°C e subindo 🔥",),
    # Battery
    ("Bateria em {bat}%",),
    ("Nível: {bat}% 🔋",),
    ("Sinal forte, 3 saltos",),
    ("Bateria baixa: {bat}% ⚠️",),
    ("Sinal {sig}/5, bateria {bat}%",),
    ("5 saltos até a base",),
    ("Sinal médio, 2 barras 📶",),
    ("Bateria OK ({bat}%), sinal {sig}",),
    ("{sig}/5 sinal, tudo estável",),
    ("Bateria carregando: {bat}%",),
    ("Conexão direta, sinal {sig}",),
    # Emergency
    ("URGÊNCIA! Preciso de ajuda no ponto {marker} 🚨",),
    ("Beacon de emergência ativado 🚨",),
    ("Alguém me ouve? URGÊNCIA!",),
    ("Ajuda necessária em {lat:.4f},{lon:.4f}",),
    ("Sinal de emergência — marcador {marker}",),
    ("Urgente: preciso de suporte!",),
    ("Emergência em {location}",),
    ("Preciso de ajuda médica",),
    ("Grupo perdido — precisamos de ajuda",),
    ("Urgente! Equipe em dificuldade",),
    ("Beacon {name} ativado",),
    ("Alguém em {city}? URGÊNCIA!",),
    # Casual
    ("Dia lindo hoje! 🌞",),
    ("Bom fim de semana a todos",),
    ("Nos vemos no encontro! 🏕️",),
    ("Alguém no ponto de encontro?",),
    ("Rede estável hoje 👍",),
    ("Obrigado pela rede! ⭐",),
    ("Dia tranquilo aqui",),
    ("Como foi o fim de semana?",),
    ("Tudo quieto por aqui",),
    ("Boa mesh hoje!",),
    ("Um pouco entediado 😴",),
    ("Um café? ☕",),
    ("Saudações de {city}!",),
    # Coordination
    ("Equipe 2, movam para o ponto {cp}",),
    ("Todos se reportem por favor",),
    ("Check-in geral — quem recebe?",),
    ("Grupo {num} em posição {num2}",),
    ("Reunião em 15 min em {location}",),
    ("Coordenação: todas unidades confirmar",),
    ("Equipe 1 avançar para {direction}",),
    ("Prontos? Às {time} em ponto",),
    ("Rumando ao ponto {cp}, confirmem",),
    ("Ponto {num} estabelecido, cobrindo {area}",),
    ("Reforçar posição no {landmark}",),
    ("Encontro em {city} às {time}",),
    ("Todos para cobertura, nos movemos",),
    # Technical
    ("Nós ativos: {nodes}",),
    ("Firmware atualizado para v{fw}",),
    ("Canal alterado para {ch}",),
    ("Canal {ch} — primário",),
    ("Contagem de nós: {nodes}",),
    ("{nodes} nós na rede",),
    ("Canais: {ch}, {ch2} ativos",),
    ("Firmware v{fw} — tudo OK ✅",),
    ("{nodes} nós, {direct} diretos",),
    ("Atualizando para v{fw} agora",),
    ("Teste de alcance, me ouvem?",),
    ("Teste: {dist} km resultados",),
    ("Mesh estável, {nodes} nós 🌐",),
    ("TX ajustado para {tx} dBm",),
]


def pt_generate():
    city = random.choice(
        [
            "São Paulo",
            "Rio de Janeiro",
            "Lisboa",
            "Porto",
            "Belo Horizonte",
            "Brasília",
            "Recife",
            "Fortaleza",
            "Salvador",
            "Curitiba",
        ]
    )
    landmark = random.choice(
        [
            "ponte",
            "lago",
            "floresta",
            "morro",
            "cristo",
            "prédio",
            "praça",
            "estação",
            "campo",
            "vilarejo",
        ]
    )
    area = random.choice(["floresta", "montanha", "costa", "interior", "serra"])
    mountain = random.choice(
        [
            "Pico da Bandeira",
            "Serra da Mantiqueira",
            "Serra do Mar",
            "Pico 3",
            "Monte Roraima",
        ]
    )
    direction = random.choice(["norte", "sul", "leste", "oeste"])
    name = random.choice(
        ["Node-BR-01", "Mesh-PT", "Node-7B", "Base-SP", "BR-Node", "Relay-1"]
    )
    location = random.choice(["zona rural", "cidade", "floresta", "montanha", "campo"])
    desc = random.choice(["limpo", "nublado", "chuvoso", "ventoso", "nebuloso"])
    marker = random.randint(1, 99)
    cp = random.randint(1, 20)
    num = random.randint(1, 9)
    num2 = random.randint(1, 9)
    time = random.choice(["15h", "14h", "16h", "18h", "19h30"])
    fw = random.choice(["2.5.14", "2.6.1", "2.7.3", "2.8.0"])
    nodes = random.randint(5, 120)
    direct = random.randint(1, 15)
    ch = random.randint(1, 20)
    ch2 = random.randint(1, 20)
    dist = round(random.uniform(0.5, 25.0), 1)
    tx = random.choice([6, 12, 17, 20, 22, 27])
    lat = round(random.uniform(-33.0, 5.0), 4)
    lon = round(random.uniform(-73.0, -34.0), 4)
    temp = round(random.uniform(5, 40), 1)
    feels = round(temp + random.uniform(-3, 3), 1)
    wind = random.randint(0, 60)
    hum = random.randint(20, 100)
    pres = random.randint(990, 1030)
    bat = random.randint(5, 100)
    sig = random.randint(1, 5)
    distance = random.randint(1, 50)
    weather = random.choice(["sol", "chuva", "nublado"])
    hops = random.randint(1, 7)
    template = random.choice(PT_TEMPLATES)
    return template[0].format(**locals())


# ─── Chinese (zh) ────────────────────────────────────────────────────────────
ZH_TEMPLATES = [
    ("早上好！",),
    ("晚上好！",),
    ("大家好！",),
    ("你好，能收到吗？",),
    ("这边一切正常 👍",),
    ("我在呢，你们呢？",),
    ("从{city}发来问候！",),
    ("有人吗？",),
    ("{name} 在线",),
    ("信号{sig}/5，一切正常",),
    ("确认信号良好",),
    ("天气真不错 🌞",),
    ("测试一下网络",),
    ("收到了，信号很稳",),
    ("{city}节点在线 📡",),
    # GPS
    ("GPS: {lat:.4f}, {lon:.4f}",),
    ("坐标: {lat:.4f}°N, {lon:.4f}°E",),
    ("位置: {lat:.3f}°N, {lon:.3f}°E",),
    ("在{landmark}附近",),
    ("桥北{distance}公里",),
    ("{area}区域，向北走",),
    ("{mountain}山顶 📍",),
    ("{lat:.4f}°N, {lon:.4f}°E",),
    ("往{direction}方向行进",),
    ("{city}市区",),
    ("坐标 {lat:.3f},{lon:.3f}，集合点",),
    ("海边，往南{distance}公里",),
    # Weather
    ("温度{temp}°C，风速{wind}公里/小时",),
    ("当前{temp}°C，体感{feels}°C",),
    ("天气:{desc}，{temp}°C 🌥️",),
    ("{temp}°C，湿度{hum}%",),
    ("阴天，{temp}°C，降雨概率40%",),
    ("晴天，{temp}°C ☀️",),
    ("小雨，{temp}°C 🌧️",),
    ("北风，{wind}公里/小时",),
    ("早晨凉爽，{temp}°C",),
    ("当前温度: {temp}°C",),
    ("{city}气温{temp}°C",),
    ("气压{pres}hPa，湿度{hum}%",),
    ("雷暴即将来临 ⛈️",),
    ("夜间晴朗，{temp}°C",),
    ("好热！{temp}°C，还在上升 🔥",),
    # Battery
    ("电量{bat}%",),
    ("电池: {bat}% 🔋",),
    ("信号强，3跳",),
    ("电量低: {bat}% ⚠️",),
    ("信号{sig}/5，电量{bat}%",),
    ("到基站5跳",),
    ("信号中等，2格 📶",),
    ("电量正常({bat}%)，信号{sig}",),
    ("{sig}/5，状态稳定",),
    ("充电中: {bat}%",),
    ("直连接收，信号{sig}",),
    # Emergency
    ("紧急！需要在标记点{marker}获得帮助 🚨",),
    ("紧急信标已激活 🚨",),
    ("有人能收到吗？紧急！",),
    ("需要在{lat:.4f},{lon:.4f}获得帮助",),
    ("紧急信号 — 标记{marker}",),
    ("紧急：需要支援！",),
    ("{location}发生紧急情况",),
    ("需要医疗援助",),
    ("队伍迷路 — 需要帮助",),
    ("紧急！队伍遇到困难",),
    ("{name}的信标已激活",),
    ("{city}有人吗？紧急！",),
    # Casual
    ("今天天气真好！🌞",),
    ("大家周末愉快",),
    ("集合点见！🏕️",),
    ("有人在集合点吗？",),
    ("今天网络很稳定 👍",),
    ("感谢网络！⭐",),
    ("今天很安静",),
    ("周末过得怎么样？",),
    ("这里一切平静",),
    ("今天网络真棒！",),
    ("有点无聊 😴",),
    ("来杯咖啡？ ☕",),
    ("从{city}发来问候！",),
    # Coordination
    ("第二队，移动到检查点{cp}",),
    ("所有人请报告",),
    ("全体签到 — 谁能收到？",),
    ("第{num}组在位置{num2}",),
    ("15分钟后在{location}集合",),
    ("协调：所有单位确认",),
    ("第一队向北推进",),
    ("准备好了吗？{time}准时",),
    ("目标检查点{cp}，确认",),
    ("{num}号点已建立，覆盖{area}区域",),
    ("加强{landmark}位置",),
    ("{time}在{city}集合",),
    ("所有人隐蔽，我们移动",),
    # Technical
    ("活跃节点: {nodes}",),
    ("固件已更新到v{fw}",),
    ("频道已切换到{ch}",),
    ("频道{ch} — 主频道",),
    ("节点数量: {nodes}",),
    ("网络中有{nodes}个节点",),
    ("频道: {ch}, {ch2} 活跃",),
    ("固件v{fw} — 一切正常 ✅",),
    ("{nodes}节点，{direct}直连",),
    ("正在更新到v{fw}",),
    ("范围测试，能收到吗？",),
    ("测试: {dist}公里结果",),
    ("网络稳定，{nodes}节点 🌐",),
    ("发射功率调到{tx}dBm",),
]


def zh_generate():
    city = random.choice(
        [
            "北京",
            "上海",
            "广州",
            "深圳",
            "成都",
            "杭州",
            "武汉",
            "西安",
            "南京",
            "重庆",
            "天津",
            "苏州",
            "长沙",
            "郑州",
            "昆明",
        ]
    )
    landmark = random.choice(
        [
            "长城",
            "故宫",
            "西湖",
            "长江",
            "黄河",
            "黄山",
            "泰山",
            "嵩山",
            "赵山",
            "寺庙",
            "古镇",
            "岛屿",
            "草原",
            "沙漠",
        ]
    )
    area = random.choice(["森林", "山区", "海岸", "平原", "草原", "沙漠"])
    mountain = random.choice(
        ["华山", "泰山", "黄山", "峨眉山", "长白山", "珠穆朗玛", "祁连山"]
    )
    direction = random.choice(["北", "南", "东", "西"])
    name = random.choice(
        ["节点01", "Mesh-CN", "节点7B", "北京站", "上海节点", "中继器1"]
    )
    location = random.choice(["农村", "城市", "森林", "山区", "平原"])
    desc = random.choice(["晴朗", "多云", "阴天", "小雨", "大风", "雾"])
    marker = random.randint(1, 99)
    cp = random.randint(1, 20)
    num = random.randint(1, 9)
    num2 = random.randint(1, 9)
    time = random.choice(["15:00", "14:00", "16:00", "18:00", "19:30"])
    fw = random.choice(["2.5.14", "2.6.1", "2.7.3", "2.8.0"])
    nodes = random.randint(5, 120)
    direct = random.randint(1, 15)
    ch = random.randint(1, 20)
    ch2 = random.randint(1, 20)
    dist = round(random.uniform(0.5, 25.0), 1)
    tx = random.choice([6, 12, 17, 20, 22, 27])
    lat = round(random.uniform(18.0, 53.0), 4)
    lon = round(random.uniform(73.0, 135.0), 4)
    temp = round(random.uniform(-15, 40), 1)
    feels = round(temp + random.uniform(-3, 3), 1)
    wind = random.randint(0, 60)
    hum = random.randint(20, 100)
    pres = random.randint(990, 1030)
    bat = random.randint(5, 100)
    sig = random.randint(1, 5)
    distance = random.randint(1, 50)
    hops = random.randint(1, 7)
    template = random.choice(ZH_TEMPLATES)
    return template[0].format(**locals())


# ─── Arabic (ar) ─────────────────────────────────────────────────────────────
AR_TEMPLATES = [
    ("صباح الخير!",),
    ("مساء الخير!",),
    ("مساء النور!",),
    ("كيف حالكم؟ هل تسمعونني؟",),
    ("كل شيء بخير هنا 👍",),
    ("أنا هنا، وأنتم؟",),
    ("تحياتي من {city}! 📡",),
    ("هل هناك أحد؟",),
    ("{name} متصل الآن",),
    ("الإشارة {sig}/5، كل شيء طبيعي",),
    ("أؤكد أنني أستقبل بشكل جيد",),
    ("يوم جميل اليوم 🌞",),
    ("اختبار الشبكة",),
    ("تم الاستقبال، إشارة مستقرة",),
    ("{city} على الشبكة 📡",),
    # GPS
    ("GPS: {lat:.4f}, {lon:.4f}",),
    ("الإحداثيات: {lat:.4f}°ش, {lon:.4f}°ق",),
    ("الموقع: {lat:.3f}°ش, {lon:.3f}°ق",),
    (" بالقرب من {landmark}",),
    ("{distance} كم شمال الجسر",),
    ("منطقة {area}، متجه شمالاً",),
    ("قمة {mountain} 📍",),
    ("{lat:.4f}°ش, {lon:.4f}°ق",),
    ("في طريقنا نحو {direction}",),
    ("منطقة {city} الحضرية",),
    ("الإحداثيات {lat:.3f},{lon:.3f} — نقطة التجمع",),
    ("الساحل، {distance} كم جنوباً",),
    # Weather
    ("درجة الحرارة {temp}°م، الرياح {wind} كم/س من الجنوب الغربي",),
    ("الآن {temp}°م، الإحساس {feels}°م",),
    ("الطقس: {desc}، {temp}°م 🌥️",),
    ("{temp}°م، الرطوبة {hum}%",),
    ("غائم، {temp}°م، احتمال المطر 40%",),
    ("مشمس، {temp}°م ☀️",),
    ("مطر خفيف، {temp}°م 🌧️",),
    ("رياح شمالية، {wind} كم/س",),
    ("صباح بارد، {temp}°م",),
    ("الحرارة الحالية: {temp}°م",),
    ("{temp}°م في {city}",),
    ("الضغط: {pres} هكتوباسكال، الرطوبة {hum}%",),
    ("عاصفة رعدية قادمة ⛈️",),
    ("ليلة صافية، {temp}°م",),
    ("حار! {temp}°م وما زالت ترتفع 🔥",),
    # Battery
    ("البطارية {bat}%",),
    ("مستوى البطارية: {bat}% 🔋",),
    ("إشارة قوية، 3 قفزات",),
    ("بطارية منخفضة: {bat}% ⚠️",),
    ("الإشارة {sig}/5، البطارية {bat}%",),
    ("5 قفزات إلى القاعدة",),
    ("إشارة متوسطة، 2 شريط 📶",),
    ("البطارية طبيعية ({bat}%)، الإشارة {sig}",),
    ("{sig}/5 إشارة، كل شيء مستقر",),
    ("جاري الشحن: {bat}%",),
    ("اتصال مباشر، الإشارة {sig}",),
    # Emergency
    ("طوارئ! أحتاج مساعدة عند النقطة {marker} 🚨",),
    ("منارة الطوارئ مفعلة 🚨",),
    ("هل يسمعني أحد؟ طوارئ!",),
    ("أحتاج مساعدة عند {lat:.4f},{lon:.4f}",),
    ("إشارة طوارئ — علامة {marker}",),
    ("عاجل: أحتاج دعماً!",),
    ("طوارئ في {location}",),
    ("أحتاج مساعدة طبية",),
    ("فريقنا ضائع — نحتاج مساعدة",),
    ("عاجل! الفريق في ورطة",),
    ("منارة {name} مفعلة",),
    ("هل هناك أحد في {city}؟ طوارئ!",),
    # Casual
    ("يوم جميل اليوم! 🌞",),
    ("أجازة نهاية الأسبوع للجميع",),
    ("نلتقي عند نقطة التجمع! 🏕️",),
    ("هل أحد عند نقطة التجمع؟",),
    ("الشبكة مستقرة اليوم 👍",),
    ("شكراً على الشبكة! ⭐",),
    ("يوم هادئ هنا",),
    ("كيف كانت إجازة نهاية الأسبوع؟",),
    ("كل شيء هادئ هنا",),
    ("شبكة ممتازة اليوم!",),
    ("ممل قليلاً 😴",),
    ("قهوة؟ ☕",),
    ("تحياتي من {city}!",),
    # Coordination
    ("الفريق 2، انتقل إلى نقطة التحقق {cp}",),
    ("الرجاء的报告 من الجميع",),
    ("تسجيل عام — من يستقبل؟",),
    ("الفريق {num} في الموقع {num2}",),
    ("اجتماع بعد 15 دقيقة في {location}",),
    ("تنسيق: تأكيد جميع الوحدات",),
    ("الفريق 1 يتقدم شمالاً",),
    ("جاهزون؟ الساعة {time} بالضبط",),
    ("متجه نحو نقطة {cp}، تأكدوا",),
    ("النقطة {num} جاهزة، تغطي منطقة {area}",),
    ("تعزيز الموقع عند {landmark}",),
    ("تجمع في {city} الساعة {time}",),
    ("الجميع للاحتماء، نحن نتنقل",),
    # Technical
    ("العقد النشطة: {nodes}",),
    ("تم تحديث البرنامج إلى v{fw}",),
    ("تم تغيير القناة إلى {ch}",),
    ("القناة {ch} — القناة الرئيسية",),
    ("عدد العقد: {nodes}",),
    ("{nodes} عقدة في الشبكة",),
    ("القنوات: {ch}، {ch2} نشطة",),
    ("البرنامج v{fw} — كل شيء طبيعي ✅",),
    ("{nodes} عقدة، {direct} مباشرة",),
    ("جاري التحديث إلى v{fw}",),
    ("اختبار المدى، هل تسمعونني؟",),
    ("اختبار: نتائج {dist} كم",),
    ("الشبكة مستقرة، {nodes} عقدة 🌐",),
    ("قوة الإرسال مضبوطة على {tx} ديسيبل",),
]


def ar_generate():
    city = random.choice(
        [
            "الرياض",
            "جدة",
            "مكة",
            "الدمام",
            "أبها",
            "المدينة",
            "تبوك",
            "القصيم",
            "حائل",
            "نجران",
        ]
    )
    landmark = random.choice(
        [
            "الجسر",
            "البحيرة",
            "الغابة",
            "الجبل",
            "الوادي",
            "السوق",
            "المسجد",
            "القلعة",
            "الصحراء",
            "النهر",
        ]
    )
    area = random.choice(["غابة", "جبل", "ساحل", "صحراء", "وادي", "سهول"])
    mountain = random.choice(
        ["جبل السودة", "جبل القارة", " Jabal Al-Lawz", "جبل طويق", "الهفوف"]
    )
    direction = random.choice(["شمال", "جنوب", "شرق", "غرب"])
    name = random.choice(
        ["عقدة-01", "Mesh-AR", "عقدة-7B", "محطة-الرياض", "AR-Node", "مكرر-1"]
    )
    location = random.choice(["منطقة ريفية", "مدينة", "غابة", "جبل", "صحراء"])
    desc = random.choice(["صافٍ", "غائم", "ماطر", "عاصف", "ضبابي"])
    marker = random.randint(1, 99)
    cp = random.randint(1, 20)
    num = random.randint(1, 9)
    num2 = random.randint(1, 9)
    time = random.choice(["15:00", "14:00", "16:00", "18:00", "19:30"])
    fw = random.choice(["2.5.14", "2.6.1", "2.7.3", "2.8.0"])
    nodes = random.randint(5, 120)
    direct = random.randint(1, 15)
    ch = random.randint(1, 20)
    ch2 = random.randint(1, 20)
    dist = round(random.uniform(0.5, 25.0), 1)
    tx = random.choice([6, 12, 17, 20, 22, 27])
    lat = round(random.uniform(16.0, 32.0), 4)
    lon = round(random.uniform(35.0, 55.0), 4)
    temp = round(random.uniform(5, 50), 1)
    feels = round(temp + random.uniform(-3, 3), 1)
    wind = random.randint(0, 60)
    hum = random.randint(10, 95)
    pres = random.randint(990, 1030)
    bat = random.randint(5, 100)
    sig = random.randint(1, 5)
    distance = random.randint(1, 50)
    hops = random.randint(1, 7)
    template = random.choice(AR_TEMPLATES)
    return template[0].format(**locals())


# ─── Japanese (ja) ───────────────────────────────────────────────────────────
JA_TEMPLATES = [
    ("おはようございます！",),
    ("こんばんは！",),
    ("皆さんこんにちは！",),
    ("聞こえますか？",),
    ("こちらは問題ありません 👍",),
    ("ここにいるよ！",),
    ("{city}からです！ 📡",),
    ("誰かいますか？",),
    ("{name}オンライン",),
    (" 信号{sig}/5，正常です",),
    ("良好に受信できました",),
    ("今日は天気が良いな 🌞",),
    ("ネットワークテスト",),
    ("届いてます、信号安定",),
    ("{city}ノードオンライン 📡",),
    # GPS
    ("GPS: {lat:.4f}, {lon:.4f}",),
    ("座標: {lat:.4f}°N, {lon:.4f}°E",),
    ("位置: {lat:.3f}°N, {lon:.3f}°E",),
    ("{landmark}の近くです",),
    ("橋から{distance}km北",),
    ("{area}方面、北へ",),
    ("{mountain}山顶 📍",),
    ("{lat:.4f}°N, {lon:.4f}°E",),
    ("{direction}へ向かっています",),
    ("{city}市内",),
    ("座標 {lat:.3f},{lon:.3f}、集合地点",),
    ("海岸、南へ{distance}km",),
    # Weather
    ("気温{temp}°C、風速{wind}km/h",),
    ("今は{temp}°C、体感{feels}°C",),
    ("天気:{desc}、{temp}°C 🌥️",),
    ("{temp}°C、湿度{hum}%",),
    ("曇り、{temp}°C、雨の確率40%",),
    ("晴れ、{temp}°C ☀️",),
    ("小雨、{temp}°C 🌧️",),
    ("北風、{wind}km/h",),
    ("朝は涼しい、{temp}°C",),
    ("現在の気温: {temp}°C",),
    ("{city}の気温{temp}°C",),
    ("気圧{pres}hPa、湿度{hum}%",),
    ("雷雨接近中 ⛈️",),
    ("夜は晴れ、{temp}°C",),
    ("暑いや！{temp}°C、まだ上がる 🔥",),
    # Battery
    ("バッテリー{bat}%",),
    ("バッテリー: {bat}% 🔋",),
    ("信号強い、3ホップ",),
    ("バッテリー少: {bat}% ⚠️",),
    ("信号{sig}/5、バッテリー{bat}%",),
    ("基地まで5ホップ",),
    ("信号中、2本 📶",),
    ("バッテリーOK({bat}%)、信号{sig}",),
    ("{sig}/5、状態安定",),
    ("充電中: {bat}%",),
    ("直接接続、信号{sig}",),
    # Emergency
    ("緊急！ポイント{marker}で助けが必要です 🚨",),
    ("緊急ビーコン作動 🚨",),
    ("誰か聞こえますか？緊急！",),
    ("{lat:.4f},{lon:.4f}で助けが必要です",),
    ("緊急信号 — マーカー{marker}",),
    ("至急！支援が必要です",),
    ("{location}で緊急発生",),
    ("医療支援が必要です",),
    ("グループが道に迷いました — 助けて",),
    ("至急！チームが困難に",),
    ("{name}のビーコン作動",),
    ("{city}の誰か？緊急！",),
    # Casual
    ("今日はいい天気！🌞",),
    ("みな良い週末を",),
    ("集合点で会おう！🏕️",),
    ("集合点に誰かいますか？",),
    ("今日はネットワーク安定 👍",),
    ("ネットワークありがとう！⭐",),
    ("今日は静かな日",),
    ("週末はどうでしたか？",),
    ("ここは何も問題ありません",),
    ("今日のメッシュ優秀！",),
    ("ちょっと退屈 😴",),
    ("コーヒーでも？ ☕",),
    ("{city}からです！",),
    # Coordination
    ("チーム2、チェックポイント{cp}へ移動",),
    ("みんな報告してください",),
    ("全体チェックイン — 受信できる？",),
    ("チーム{num}、位置{num2}",),
    ("15分後に{location}で集合",),
    ("調整：全ユニット確認",),
    ("チーム1、北へ前進",),
    ("準備いい？{time}に正確に",),
    ("チェックポイント{cp}へ向かう、返信して",),
    ("ポイント{num}確保、{area}エリアカバー中",),
    ("{landmark}の守りを強化",),
    ("{time}に{city}で集合",),
    ("みんな退避、移動します",),
    # Technical
    ("アクティブノード: {nodes}",),
    ("ファームウェアv{fw}に更新",),
    ("チャンネルを{ch}に変更",),
    ("チャンネル{ch} — プライマリ",),
    ("ノード数: {nodes}",),
    ("ネットワーク内に{nodes}ノード",),
    ("チャンネル: {ch}、{ch2}アクティブ",),
    ("ファームウェアv{fw} — 正常 ✅",),
    ("{nodes}ノード、{direct}直接",),
    ("v{fw}へ更新中",),
    ("距離テスト、届いてますか？",),
    ("テスト: {dist}km結果",),
    ("メッシュ安定、{nodes}ノード 🌐",),
    ("TXパワーを{tx}dBmに調整",),
]


def ja_generate():
    city = random.choice(
        [
            "東京",
            "大阪",
            "京都",
            "名古屋",
            "横浜",
            "札幌",
            "仙台",
            "広島",
            "福岡",
            "神戸",
            "千葉",
            "埼玉",
            "川崎",
            "福岡",
            "新潟",
        ]
    )
    landmark = random.choice(
        [
            "富士山",
            "鎌倉",
            "奈良",
            "天桥立",
            "厳島神社",
            "日光",
            "嵐山",
            "富士山",
            "白金台",
            "明治神宮",
            "金阁寺",
            "清水寺",
            " пров",
        ]
    )
    area = random.choice(["森林", "山地", "海岸", "平野", "高原", "岛"])
    mountain = random.choice(["富士山", "槍ヶ岳", "穂高岳", "剣岳", "白馬岳", "御嶽山"])
    direction = random.choice(["北", "南", "東", "西"])
    name = random.choice(
        ["ノード01", "Mesh-JP", "ノード7B", "東京駅", "JP-Node", "リレー1"]
    )
    location = random.choice(["地方", "都市", "森林", "山地", "平野"])
    desc = random.choice(["晴れ", "曇り", "雨", "強風", "霧"])
    marker = random.randint(1, 99)
    cp = random.randint(1, 20)
    num = random.randint(1, 9)
    num2 = random.randint(1, 9)
    time = random.choice(["15:00", "14:00", "16:00", "18:00", "19:30"])
    fw = random.choice(["2.5.14", "2.6.1", "2.7.3", "2.8.0"])
    nodes = random.randint(5, 120)
    direct = random.randint(1, 15)
    ch = random.randint(1, 20)
    ch2 = random.randint(1, 20)
    dist = round(random.uniform(0.5, 25.0), 1)
    tx = random.choice([6, 12, 17, 20, 22, 27])
    lat = round(random.uniform(24.0, 45.0), 4)
    lon = round(random.uniform(125.0, 146.0), 4)
    temp = round(random.uniform(-10, 38), 1)
    feels = round(temp + random.uniform(-3, 3), 1)
    wind = random.randint(0, 60)
    hum = random.randint(20, 100)
    pres = random.randint(990, 1030)
    bat = random.randint(5, 100)
    sig = random.randint(1, 5)
    distance = random.randint(1, 50)
    hops = random.randint(1, 7)
    template = random.choice(JA_TEMPLATES)
    return template[0].format(**locals())


# ─── Korean (ko) ─────────────────────────────────────────────────────────────
KO_TEMPLATES = [
    ("좋은 아침!",),
    ("좋은 저녁!",),
    ("안녕하세요!",),
    ("들리세요?",),
    ("여기 다 괜찮아요 👍",),
    ("나 여기 있어요!",),
    ("{city}에서 인사합니다! 📡",),
    ("누구 없어요?",),
    ("{name} 온라인",),
    ("신호 {sig}/5, 정상运作",),
    ("잘 받았습니다",),
    ("오늘 날씨가 좋네요 🌞",),
    ("네트워크 테스트",),
    ("도착, 신호 안정적",),
    ("{city} 노드 온라인 📡",),
    # GPS
    ("GPS: {lat:.4f}, {lon:.4f}",),
    ("좌표: {lat:.4f}°N, {lon:.4f}°E",),
    ("위치: {lat:.3f}°N, {lon:.3f}°E",),
    ("{landmark} 근처예요",),
    ("다리에서 북쪽으로 {distance}km",),
    ("{area} 지역, 북쪽으로",),
    ("{mountain} 정상 📍",),
    ("{lat:.4f}°N, {lon:.4f}°E",),
    ("{direction} 방향으로 이동 중",),
    ("{city} 시내",),
    ("좌표 {lat:.3f},{lon:.3f} — 집합地点",),
    ("해안, 남쪽으로 {distance}km",),
    # Weather
    ("온도 {temp}°C, 바람 {wind}km/h",),
    ("지금 {temp}°C, 체감 {feels}°C",),
    ("날씨: {desc}, {temp}°C 🌥️",),
    ("{temp}°C, 습도 {hum}%",),
    ("흐림, {temp}°C, 비 올 확률 40%",),
    ("맑음, {temp}°C ☀️",),
    ("가벼운 비, {temp}°C 🌧️",),
    ("북풍, {wind}km/h",),
    ("아침은 선선해요, {temp}°C",),
    ("현재 온도: {temp}°C",),
    ("{city} 온도 {temp}°C",),
    ("기압 {pres}hPa, 습도 {hum}%",),
    ("천둥번개 다가오는 중 ⛈️",),
    ("밤하늘 맑음, {temp}°C",),
    ("더워! {temp}°C, 계속 오르고 있어 🔥",),
    # Battery
    ("배터리 {bat}%",),
    ("배터리: {bat}% 🔋",),
    ("신호 강함, 3홉",),
    ("배터리 부족: {bat}% ⚠️",),
    ("신호 {sig}/5, 배터리 {bat}%",),
    ("기지까지 5홉",),
    ("신호 보통, 2칸 📶",),
    ("배터리 OK({bat}%), 신호 {sig}",),
    ("{sig}/5, 상태 안정",),
    ("충전 중: {bat}%",),
    ("직접 연결, 신호 {sig}",),
    # Emergency
    ("긴급! 마커 {marker}에서 도움 필요 🚨",),
    ("긴급 비콘 활성화 🚨",),
    ("누구나 들리세요? 긴급!",),
    ("{lat:.4f},{lon:.4f}에서 도움 필요",),
    ("긴급 신호 — 마커 {marker}",),
    ("至急! 지원이 필요합니다",),
    ("{location}에서 긴급 상황",),
    ("의료 지원이 필요합니다",),
    ("그룹이 길을 잃었습니다 — 도와주세요",),
    ("긴급! 팀이 어려움에 처했습니다",),
    ("{name}의 비콘 활성화됨",),
    ("{city}에 누가 있어요? 긴급!",),
    # Casual
    ("오늘 날씨가 좋네요! 🌞",),
    ("모두 좋은 주말 보내세요",),
    ("집결지에서 봐요! 🏕️",),
    ("집결지에 누가 있어요?",),
    ("오늘 네트워크 안정적이에요 👍",),
    ("네트워크 감사합니다! ⭐",),
    ("오늘은 조용한 날이에요",),
    ("주말은 어땠어요?",),
    ("여기 아무 문제 없어요",),
    ("오늘 메시 훌륭해요!",),
    ("좀 심심해 😴",),
    ("커피 한잔? ☕",),
    ("{city}에서 인사합니다!",),
    # Coordination
    ("팀 2, 체크포인트 {cp}로 이동하세요",),
    ("모두 보고해 주세요",),
    ("전체 체크인 — 수신되세요?",),
    ("팀 {num}, 위치 {num2}",),
    ("15분 후 {location}에서 집합",),
    ("조정: 모든 유닛 확인하세요",),
    ("팀 1 북쪽으로 전진",),
    ("준비됐나요? {time}에 정확히",),
    ("체크포인트 {cp} 향해 가요, 확인하세요",),
    ("포인트 {num} 확보, {area} 지역 커버 중",),
    ("{landmark} 위치 방어 강화",),
    ("{time}에 {city}에서 집합",),
    ("모두 엄폐, 이동합니다",),
    # Technical
    ("활성 노드: {nodes}",),
    ("펌웨어 v{fw}로 업데이트됨",),
    ("채널 {ch}로 변경됨",),
    ("채널 {ch} — 기본",),
    ("노드 수: {nodes}",),
    ("네트워크에 {nodes}개 노드",),
    ("채널: {ch}, {ch2} 활성화",),
    ("펌웨어 v{fw} — 정상 ✅",),
    ("{nodes}개 노드, {direct}개 직접 연결",),
    ("v{fw} 업데이트 진행 중",),
    ("거리 테스트, 들리세요?",),
    ("테스트: {dist}km 결과",),
    ("메쉬 안정, {nodes}개 노드 🌐",),
    ("TX 파워 {tx}dBm로 조정",),
]


def ko_generate():
    city = random.choice(
        [
            "서울",
            "부산",
            "제주",
            "인천",
            "대전",
            "광주",
            "대구",
            "울산",
            "수원",
            "창원",
            "청주",
            "전주",
            "춘천",
            "강릉",
            "경주",
        ]
    )
    landmark = random.choice(
        [
            "한강",
            "남산",
            "해운대",
            "제주도",
            "설악산",
            "정동진",
            "강화도",
            "가야산",
            "황룡사",
            "합천",
            "오대산",
            "월악산",
        ]
    )
    area = random.choice(["산림", "산악", "해안", "평야", "고원", "섬"])
    mountain = random.choice(
        ["백두산", "지리산", "한라산", "설악산", "태백산", "소백산", "팔봉"]
    )
    direction = random.choice(["북", "남", "동", "서"])
    name = random.choice(
        ["노드01", "Mesh-KR", "노드7B", "서울역", "KR-Node", "릴레이1"]
    )
    location = random.choice(["농촌", "도시", "산림", "산악", "평야"])
    desc = random.choice(["맑음", "흐림", "비", "바람", "안개"])
    marker = random.randint(1, 99)
    cp = random.randint(1, 20)
    num = random.randint(1, 9)
    num2 = random.randint(1, 9)
    time = random.choice(["15:00", "14:00", "16:00", "18:00", "19:30"])
    fw = random.choice(["2.5.14", "2.6.1", "2.7.3", "2.8.0"])
    nodes = random.randint(5, 120)
    direct = random.randint(1, 15)
    ch = random.randint(1, 20)
    ch2 = random.randint(1, 20)
    dist = round(random.uniform(0.5, 25.0), 1)
    tx = random.choice([6, 12, 17, 20, 22, 27])
    lat = round(random.uniform(33.0, 43.0), 4)
    lon = round(random.uniform(125.0, 132.0), 4)
    temp = round(random.uniform(-15, 38), 1)
    feels = round(temp + random.uniform(-3, 3), 1)
    wind = random.randint(0, 60)
    hum = random.randint(20, 100)
    pres = random.randint(990, 1030)
    bat = random.randint(5, 100)
    sig = random.randint(1, 5)
    distance = random.randint(1, 50)
    hops = random.randint(1, 7)
    template = random.choice(KO_TEMPLATES)
    return template[0].format(**locals())


# ─── Language config ─────────────────────────────────────────────────────────
LANG_CONFIG = {
    "es": ("Spanish", es_generate),
    "de": ("German", de_generate),
    "fr": ("French", fr_generate),
    "pt": ("Portuguese", pt_generate),
    "zh": ("Chinese", zh_generate),
    "ar": ("Arabic", ar_generate),
    "ja": ("Japanese", ja_generate),
    "ko": ("Korean", ko_generate),
}


def generate_messages(generator_fn, count: int) -> list[str]:
    """Generate `count` messages using the given generator function."""
    messages = []
    for _ in range(count):
        msg = generator_fn()
        # Occasionally add extra short message variants
        if random.random() < 0.05:
            msg = msg.upper()
        if random.random() < 0.03:
            msg = (
                msg
                + " "
                + random.choice(
                    ["😀", "👍", "📡", "🌐", "✅", "⚠️", "🚨", "☕", "🌞", "🔋"]
                )
            )
        messages.append(msg)
    return messages


def save_messages(messages: list[str], filepath: Path):
    with open(filepath, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(msg + "\n")


def main():
    print("=" * 60)
    print("Meshtastic Multilingual Message Generator")
    print("=" * 60)

    all_train = {}
    all_test = {}

    for lang, (name, gen_fn) in LANG_CONFIG.items():
        print(f"\n[{lang.upper()}] {name}")
        print(f"  Generating {TRAIN_COUNT} train messages...")
        train_msgs = generate_messages(gen_fn, TRAIN_COUNT)
        print(f"  Generating {TEST_COUNT} test messages...")
        test_msgs = generate_messages(gen_fn, TEST_COUNT)

        train_path = OUTPUT_DIR / f"train_{lang}.txt"
        test_path = OUTPUT_DIR / f"test_{lang}.txt"

        save_messages(train_msgs, train_path)
        save_messages(test_msgs, test_path)

        all_train[lang] = train_msgs
        all_test[lang] = test_msgs

        # Stats
        avg_len = sum(len(m) for m in train_msgs) / len(train_msgs)
        print(
            f"  → {train_path} ({len(train_msgs)} messages, avg len {avg_len:.1f} chars)"
        )
        print(f"  → {test_path}  ({len(test_msgs)} messages)")

    # Combined files
    combined_train = []
    combined_test = []
    for lang in LANG_CONFIG:
        combined_train.extend(all_train[lang])
        combined_test.extend(all_test[lang])

    random.shuffle(combined_train)
    random.shuffle(combined_test)

    save_messages(combined_train, OUTPUT_DIR / "train_all.txt")
    save_messages(combined_test, OUTPUT_DIR / "test_all.txt")

    print(f"\n{'=' * 60}")
    print("DONE — Summary")
    print(f"{'=' * 60}")
    print(f"\nOutput directory: {OUTPUT_DIR}")
    print(f"\nPer-language files:")
    for lang in LANG_CONFIG:
        name = LANG_CONFIG[lang][0]
        print(f"  train_{lang}.txt  ({TRAIN_COUNT} {name} messages)")
        print(f"  test_{lang}.txt   ({TEST_COUNT}  {name} messages)")
    print(f"\nCombined files:")
    print(f"  train_all.txt  ({len(combined_train)} messages total)")
    print(f"  test_all.txt   ({len(combined_test)} messages total)")

    # Character distribution
    print(f"\nCharacter distribution (train_all):")
    total_chars = sum(len(m) for m in combined_train)
    print(f"  Total characters: {total_chars:,}")
    print(f"  Avg message length: {total_chars / len(combined_train):.1f} chars")
    short = sum(1 for m in combined_train if len(m) <= 20)
    medium = sum(1 for m in combined_train if 20 < len(m) <= 100)
    long_ = sum(1 for m in combined_train if len(m) > 100)
    print(f"  Short (<=20):  {short:,} ({100 * short / len(combined_train):.1f}%)")
    print(f"  Medium (20-100): {medium:,} ({100 * medium / len(combined_train):.1f}%)")
    print(f"  Long (>100):   {long_:,} ({100 * long_ / len(combined_train):.1f}%)")


if __name__ == "__main__":
    main()
