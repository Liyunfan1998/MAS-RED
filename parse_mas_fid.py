import csv
import json
import re
import sys
from collections import OrderedDict


def _split_name_role(text: str):
    """Split a string like 'Oleg Leonov-CEO-designate' into name and role."""
    if "-" in text:
        name, role = text.split("-", 1)
    elif "," in text:
        name, role = text.split(",", 1)
    else:
        name, role = text, None
    return name.strip(), role.strip() if role else None


def parse_person_field(value: str):
    """Extract a person's name, role and phone number from the phone field."""
    if not value:
        return None
    value = value.strip()

    # Case: "Name (Role) -phone"
    m = re.match(r"(?P<name>[A-Za-z][^()]*?)\s*\((?P<role>[^)]+)\)\s*-?\s*(?P<phone>.*)", value)
    if m:
        name = m.group("name").strip()
        role = m.group("role").strip()
        phone = m.group("phone").strip() or None
        return name, role, phone

    # Case: "phone (Name-role)" or "phone (Name, role)" or "phone (Name)"
    m = re.match(r"(?P<phone>[+\d][^()]*?)\s*\((?P<inside>[^)]+)\)", value)
    if m:
        phone = m.group("phone").strip() or None
        inside = m.group("inside").strip()
        if any(ch.isalpha() for ch in inside):
            name, role = _split_name_role(inside)
            return name, role, phone

    return None


def extract_year(filename: str) -> int:
    """Extract the four-digit year from the filename."""
    m = re.search(r"(\d{4})", filename)
    return int(m.group(1)) if m else None


def parse_mas_fid(file_path: str):
    """Parse the MAS FID TSV file and return entities and relationships."""

    companies: OrderedDict[str, dict] = OrderedDict()
    persons: OrderedDict[str, dict] = OrderedDict()
    relationships = []
    relation_keys = set()

    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            company_name = row.get("Organisation Name", "").strip()
            if not company_name:
                continue

            if company_name not in companies:
                comp_entity = {
                    "entityId": f"COMPANY_{len(companies) + 1}",
                    "type": "Company",
                    "canonicalName": company_name,
                    "mentions": [company_name],
                    "attributes": {},
                }
                companies[company_name] = comp_entity

            comp = companies[company_name]

            for key, value in row.items():
                if key == "Organisation Name":
                    continue
                value = value.strip()
                if not value:
                    continue
                attr = comp.setdefault("attributes", {}).setdefault(key, set())
                attr.add(value)

            # Look for person information in the phone field
            person_info = parse_person_field(row.get("Phone Number", ""))
            if person_info:
                name, role, phone = person_info
                if name not in persons:
                    persons[name] = {
                        "entityId": f"PERSON_{len(persons) + 1}",
                        "type": "Person",
                        "canonicalName": name,
                        "mentions": [name],
                        "attributes": {},
                    }
                person = persons[name]
                if phone:
                    person.setdefault("attributes", {}).setdefault("Phone Number", set()).add(phone)

                key = (person["entityId"], comp["entityId"], role or "")
                if key not in relation_keys:
                    relation_keys.add(key)
                    relationships.append(
                        {
                            "sourceEntityId": person["entityId"],
                            "targetEntityId": comp["entityId"],
                            "role": role.lower() if role else None,
                            "effectiveDate": None,
                        }
                    )

    def finalize(entity):
        attrs = entity.get("attributes", {})
        for k, v in attrs.items():
            if isinstance(v, set):
                if len(v) == 1:
                    attrs[k] = next(iter(v))
                else:
                    attrs[k] = sorted(v)
        return entity

    entities = [finalize(e) for e in companies.values()] + [finalize(e) for e in persons.values()]
    return entities, relationships


def build_output(file_path: str):
    report_year = extract_year(file_path)
    entities, relationships = parse_mas_fid(file_path)
    return {
        "reportYear": report_year,
        "entities": entities,
        "relationships": relationships,
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "MAS_FID_2025-06-19.xls"
    data = build_output(path)
    print(json.dumps(data, indent=2))

