import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF, RDFS, XSD

EX = Namespace("http://example.org/mkr/")


def iri(kind, name):
    return EX[f"{kind}/{name.strip().replace(' ', '_')}"]


def parse_date(text):
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def read_flights(path):
    flights = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            flight_id = row["flight_id"].strip().upper()
            if flight_id in flights:
                continue

            delay, source = None, None
            match = re.search(r"delay=(\d+);by=(\w+)", row["note"])
            if match:
                delay, source = int(match.group(1)), match.group(2)

            price = row["price_eur"].strip()
            flights[flight_id] = {
                "id": flight_id,
                "airline": row["airline"].strip(),
                "from_city": row["from_city"].strip().title(),
                "from_country": row["from_country"].strip(),
                "to_city": row["to_city"].strip().title(),
                "to_country": row["to_country"].strip(),
                "date": parse_date(row["dep_date"]),
                "duration": int(row["duration_min"]),
                "price": Decimal(price) if price else None,
                "delay": delay,
                "source": source,
            }
    return flights


def add_schema(graph):
    for cls in (EX.Flight, EX.Airline, EX.City, EX.Country, EX.Source):
        graph.add((cls, RDF.type, RDFS.Class))

    for cls in (EX.BudgetFlight, EX.LongFlight):
        graph.add((cls, RDF.type, RDFS.Class))
        graph.add((cls, RDFS.subClassOf, EX.Flight))

    properties = [
        (EX.operatedBy, EX.Flight, EX.Airline),
        (EX.departsFrom, EX.Flight, EX.City),
        (EX.arrivesAt, EX.Flight, EX.City),
        (EX.locatedIn, EX.City, EX.Country),
        (EX.departureDate, EX.Flight, XSD.date),
        (EX.durationMin, EX.Flight, XSD.integer),
        (EX.priceEur, EX.Flight, XSD.decimal),
        (EX.hasDelayMinutes, EX.Flight, XSD.integer),
        (EX.reportedBy, RDF.Statement, EX.Source),
        (EX.fromBusyCountry, EX.Flight, XSD.boolean),
    ]
    for prop, domain, value_range in properties:
        graph.add((prop, RDF.type, RDF.Property))
        graph.add((prop, RDFS.domain, domain))
        graph.add((prop, RDFS.range, value_range))


def build_graph(flights, params):
    graph = Graph()
    graph.bind("ex", EX)
    add_schema(graph)

    departures = defaultdict(set)
    for flight in flights.values():
        departures[flight["from_country"]].add(flight["id"])
    busy_countries = {country for country, ids in departures.items() if len(ids) >= 2}

    for flight in flights.values():
        for city, country in ((flight["from_city"], flight["from_country"]),
                              (flight["to_city"], flight["to_country"])):
            city_node = iri("city", city)
            country_node = iri("country", country)
            graph.add((city_node, RDF.type, EX.City))
            graph.add((city_node, RDFS.label, Literal(city, lang="en")))
            graph.add((city_node, EX.locatedIn, country_node))
            graph.add((country_node, RDF.type, EX.Country))
            graph.add((country_node, RDFS.label, Literal(country, lang="en")))

        airline_node = iri("airline", flight["airline"])
        graph.add((airline_node, RDF.type, EX.Airline))
        graph.add((airline_node, RDFS.label, Literal(flight["airline"], lang="en")))

        node = iri("flight", flight["id"])
        is_budget = flight["price"] is not None and flight["price"] <= params["budget_threshold_eur"]
        is_long = flight["duration"] >= params["long_flight_min"]

        if is_budget:
            graph.add((node, RDF.type, EX.BudgetFlight))
        if is_long:
            graph.add((node, RDF.type, EX.LongFlight))
        if not is_budget and not is_long:
            graph.add((node, RDF.type, EX.Flight))

        graph.add((node, EX.operatedBy, airline_node))
        graph.add((node, EX.departsFrom, iri("city", flight["from_city"])))
        graph.add((node, EX.arrivesAt, iri("city", flight["to_city"])))
        graph.add((node, EX.departureDate, Literal(flight["date"], datatype=XSD.date)))
        graph.add((node, EX.durationMin, Literal(flight["duration"], datatype=XSD.integer)))

        if flight["price"] is not None:
            graph.add((node, EX.priceEur, Literal(str(flight["price"]), datatype=XSD.decimal)))
        if flight["from_country"] in busy_countries:
            graph.add((node, EX.fromBusyCountry, Literal(True, datatype=XSD.boolean)))

        if flight["delay"] is not None:
            statement = iri("stmt", f"{flight['id']}-delay")
            source_node = iri("source", flight["source"])
            graph.add((statement, RDF.type, RDF.Statement))
            graph.add((statement, RDF.subject, node))
            graph.add((statement, RDF.predicate, EX.hasDelayMinutes))
            graph.add((statement, RDF.object, Literal(flight["delay"], datatype=XSD.integer)))
            graph.add((statement, EX.reportedBy, source_node))
            graph.add((source_node, RDF.type, EX.Source))
            graph.add((source_node, RDFS.label, Literal(flight["source"], lang="en")))

    return graph


if __name__ == "__main__":
    flights_path, params_path, output_path = sys.argv[1:4]

    flights = read_flights(flights_path)
    with open(params_path, encoding="utf-8") as f:
        params = json.load(f)

    graph = build_graph(flights, params)
    graph.serialize(output_path, format="turtle")

    print(f"рейсів: {len(flights)}")
    print(f"трійок: {len(graph)}")
    print(f"збережено: {output_path}")
