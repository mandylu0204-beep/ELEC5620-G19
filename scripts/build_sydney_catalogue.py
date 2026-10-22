"""Build the independent Sydney catalogue from the preserved 2.1 input.

The catalogue combines official static facts with explicit reference allowances
and simulated dynamic conditions. It never rewrites an existing sealed package,
queries a booking service, or claims that a forecast/road check was observed.
"""
import argparse
from copy import deepcopy
import csv
from datetime import date, datetime, time, timedelta
import hashlib
import io
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/synthetic_demo_v2_1'
TARGET = ROOT / 'data/sydney_surrounds_v2_2'
CHECKED = '2026-10-23'
VERSION = '2.2.0'
REGION = 'Sydney & Surrounds'
NPWS = 'https://www.nationalparks.nsw.gov.au/camping-and-accommodation/campgrounds/'
ISLAND = 'https://www.cockatooisland.gov.au/en/stay/waterfront-campground/'
PROVENANCE = {'source_type': 'SYNTHETIC', 'source_name': 'CampMate Synthetic Demo Dataset v2',
              'source_date': '2026-10-07', 'demo_only': True}
ID_MAP = dict(zip(
    ('demo-pine-camp', 'demo-river-flat', 'demo-ridge-lookout', 'demo-fern-walk',
     'demo-lake-meadow', 'demo-sandstone-grove', 'demo-cloud-gully',
     'demo-wattle-rest', 'demo-granite-ledge', 'demo-moonlit-field'),
    ('the-basin', 'bonnie-vale', 'bents-basin', 'cattai', 'euroka', 'lane-cove',
     'putty-beach', 'little-beach', 'tallow-beach', 'cockatoo-island')))

# Values omitted here are deliberately unknown. These are not copied from the
# fictional locations to which the old identifiers happened to refer.
SITES = [
    dict(id='the-basin', name='The Basin campground', slug='the-basin-campground',
         subregion='Pittwater, Ku-ring-gai Chase National Park', fee=60,
         vehicle=False, public=True, water=True, showers=True, fire=True,
         wheelchair=None, step_free=None, walk_in=True,
         facilities=['toilets', 'cold showers', 'drinking water', 'gas/electric barbecues', 'picnic tables'],
         restrictions=['Arrival by ferry, boat or on foot; no vehicle access to the campground',
                       'From West Head Road parking, carry equipment down a steep 2.8 km track',
                       'Fires only in designated wood barbecues or bookable fire pits, subject to current restrictions',
                       'Noise restrictions after 10pm; heat beads prohibited'],
         access='Arrive by Palm Beach ferry, boat or a steep 2.8 km walking track. Wheelchair access is by ferry with assistance potentially required.',
         risk=['steep_terrain', 'limited_mobile_reception'], seasons='all'),
    dict(id='bonnie-vale', name='Bonnie Vale campground', slug='bonnie-vale-campground',
         subregion='Bundeena, Royal National Park', fee=85,
         vehicle=True, public=True, water=True, showers=True, fire=False,
         wheelchair=True, step_free=True, walk_in=False,
         facilities=['toilets', 'hot showers', 'drinking water', 'gas/electric barbecues', 'picnic tables', 'accessible path'],
         restrictions=['Campfires and solid fuel burners prohibited; gas/electric barbecues provided',
                       'One parking space per site', 'Keep noise down after 10pm'],
         access='Vehicle camping, or Cronulla to Bundeena ferry followed by a 15 minute walk. Concrete paths reach accessible amenities; campsites are on flat grass.',
         risk=['limited_mobile_reception'], seasons='all'),
    dict(id='bents-basin', name='Bents Basin campground', slug='bents-basin-campground',
         subregion='Greendale, Bents Basin State Conservation Area', fee=60,
         vehicle=True, public=None, water=False, showers=True, fire=True,
         wheelchair=True, step_free=True, walk_in=False,
         facilities=['toilets', 'hot showers', 'barbecue facilities', 'picnic tables', 'accessible path'],
         restrictions=['Bring all drinking water', 'Enter via Wolstenholme Avenue, not Bents Basin Road',
                       'Use designated fire rings or raised cooking equipment, subject to current restrictions',
                       'Keep noise down after 10pm'],
         access='2WD access via Wolstenholme Avenue. Most campsites permit parking beside the tent; some require a short walk. Accessible amenities may require an MLAK key.',
         risk=['limited_water', 'limited_mobile_reception'], seasons='all'),
    dict(id='cattai', name='Cattai campground', slug='cattai-campground',
         subregion='Hawkesbury, Cattai National Park', fee=55,
         vehicle=True, public=None, water=False, showers=True, fire=True,
         wheelchair=None, step_free=None, walk_in=False,
         facilities=['toilets', 'hot showers', 'barbecue facilities', 'camp kitchen', 'accessible toilet'],
         restrictions=['Bring drinking and cooking water; available water needs treatment',
                       'Fires only in designated or portable off-the-ground barbecues, subject to current restrictions',
                       'Observe gate hours; retain the booking gate code', 'Keep noise down after 10pm'],
         access='Drive into the campground. Grass and gravel terrain may require wheelchair assistance; an accessible toilet is available.',
         risk=['limited_water'], seasons='all'),
    dict(id='euroka', name='Euroka campground', slug='euroka-campground',
         subregion='Glenbrook, Blue Mountains National Park', fee=45,
         vehicle=False, public=None, water=False, showers=False, fire=False,
         wheelchair=None, step_free=None, walk_in=True,
         facilities=['toilets', 'wood barbecues', 'picnic tables'],
         restrictions=['Tent-only sites; walk 5 to 15 metres from campground parking',
                       'Bring all drinking and cooking water',
                       'Campfires prohibited; cooking is permitted in provided wood barbecues and fire rings, subject to current restrictions',
                       'Observe Glenbrook gate hours', 'Keep noise down after 10pm'],
         access='Drive to the campground carparks, then carry equipment 5 to 15 metres. Tent sites do not permit camping beside a vehicle. Uneven ground; toilets are wheelchair accessible.',
         risk=['limited_water', 'limited_mobile_reception'], seasons='all'),
    dict(id='lane-cove', name='Lane Cove caravan park', slug='lane-cove-caravan-park',
         subregion='Macquarie Park, Lane Cove National Park', fee=95,
         vehicle=True, public=True, water=True, showers=True, fire=False,
         wheelchair=None, step_free=None, walk_in=False,
         coordinates=('-33.78952666', '151.14316666'),
         facilities=['toilets', 'hot showers', 'drinking water', 'gas/electric barbecues', 'camp kitchen', 'picnic tables', 'swimming pool'],
         restrictions=['Enter via Plassey Road, not Riverside Drive', 'One vehicle per site',
                       'Campfires and solid fuel burners prohibited; gas/electric barbecues provided',
                       'Amplified music prohibited'],
         access='2WD access via Plassey Road, or walk about 900 metres from North Ryde station. Accessible shower and toilet at amenities block 3; assistance may be required.',
         risk=[], seasons='all'),
    dict(id='putty-beach', name='Putty Beach campground', slug='putty-beach-campground',
         subregion='Killcare, Bouddi National Park', fee=65,
         vehicle=False, public=None, water=True, showers=True, fire=False,
         wheelchair=False, step_free=None, walk_in=True,
         facilities=['toilets', 'outdoor shower', 'drinking water', 'gas/electric barbecues', 'picnic tables'],
         restrictions=['Tent-only sites with a short walk from parking; no overnight stays in vehicles',
                       'Wood campfires prohibited at campground and beach', 'Keep noise down after 10pm'],
         access='Park near the campground and carry equipment to the tent site. Kerbs and grass separate parking from sites; NPWS lists no wheelchair access despite an accessible toilet.',
         risk=['limited_mobile_reception'], seasons='all'),
    dict(id='little-beach', name='Little Beach campground', slug='little-beach-campground',
         subregion='Bouddi, Central Coast', fee=35, capacity=6,
         vehicle=False, public=None, water=False, showers=False, fire=False,
         wheelchair=False, step_free=False, walk_in=True,
         facilities=['toilets', 'gas/electric barbecues', 'picnic tables'],
         restrictions=['Carry all equipment and water along a 750 metre gravel trail from Grahame Drive',
                       'Maximum 6 people per campsite', 'Wood campfires prohibited at campground and beach',
                       'No overnight stays in vehicles', 'Keep noise down after 10pm'],
         access='Walk 750 metres from the carpark along a gravel trail with uphill sections. No wheelchair access.',
         risk=['limited_water', 'limited_mobile_reception'], seasons='all'),
    dict(id='tallow-beach', name='Tallow Beach campground', slug='tallow-beach-campground',
         subregion='Killcare, Bouddi National Park', fee=35,
         vehicle=False, public=None, water=False, showers=False, fire=False,
         wheelchair=False, step_free=False, walk_in=True,
         facilities=['toilets'],
         restrictions=['Carry all equipment and drinking water down a steep 1.2 km gravel trail',
                       'Wood campfires prohibited at campground and beach', 'Bring a cooking stove',
                       'No overnight stays in vehicles', 'Keep noise down after 10pm'],
         access='Steep 1.2 km walk from Hawke Head Drive parking. Not recommended for elderly or very young campers. Access roads may require 4WD in wet weather.',
         risk=['steep_terrain', 'limited_water', 'limited_mobile_reception'], seasons='all'),
    dict(id='cockatoo-island', name='Cockatoo Island waterfront campground',
         subregion='Cockatoo Island, Sydney Harbour', fee=65, capacity=4,
         vehicle=False, public=True, water=None, showers=True, fire=None,
         wheelchair=True, step_free=None, walk_in=True, pets=None,
         facilities=['toilets', 'hot showers', 'communal kitchen', 'boiling water', 'accessible toilet', 'accessible shower'],
         restrictions=['BYO tent on a 4m by 4m unpowered site; standard occupancy is 4 guests',
                       'Advance booking required; same-day bookings not accepted',
                       'Arrive by ferry or other water transport and carry equipment from the wharf'],
         access='Public ferries serve the island. BYO tent sites have accessible shower and toilet facilities. The wider heritage island has separate accessibility constraints.',
         risk=[], seasons='all'),
]


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def csv_bytes(rows, fieldnames):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def csv_read(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        return reader.fieldnames, list(reader)


def boolean(value):
    return 'unknown' if value is None else str(value).lower()


def url(site):
    return NPWS + site['slug'] if 'slug' in site else ISLAND


def visitor_url(site):
    return url(site) + '/visitor-info' if 'slug' in site else ISLAND + 'byo-tent-option/'


def replacement(value):
    if isinstance(value, list):
        return [replacement(item) for item in value]
    if isinstance(value, dict):
        return {key: replacement(item) for key, item in value.items()}
    if isinstance(value, str):
        for old, new in ID_MAP.items():
            value = value.replace(old, new)
        value = value.replace('CampMate Demo Region', REGION)
        if value.startswith('Demo Camper '):
            value = {'Demo Camper A': 'Alex', 'Demo Camper B': 'Jamie',
                     'Demo Camper C': 'Taylor', 'Demo Camper D': 'Morgan'}.get(value, 'Camper')
    return value


def source_entry(value, status, source=None, note=None):
    result = {'value': value, 'status': status}
    if source:
        result['source_url'] = source
    if note:
        result['note'] = note
    return result


def build():
    manifest = json.loads((SOURCE / 'manifest.json').read_bytes())
    content = {}
    fields, old_camps = csv_read(SOURCE / 'data/synthetic_campsites.csv')
    original_by_id = {row['campsite_id']: row for row in old_camps}
    reverse_ids = {value: key for key, value in ID_MAP.items()}
    camps, catalogue = [], {}
    for site in SITES:
        site = deepcopy(site)
        if site['id'] in {'the-basin', 'euroka', 'putty-beach', 'little-beach', 'tallow-beach'}:
            site['facilities'].append('carpark with signed walking access to campsites')
        row = deepcopy(original_by_id[reverse_ids[site['id']]])
        row.update(campsite_id=site['id'], name=site['name'], region=REGION,
                   subregion=site['subregion'], latitude='unknown', longitude='unknown',
                   nightly_fee_aud=str(site['fee']), max_group_size=str(site.get('capacity', 4)),
                   booking_required='true', vehicle_access=boolean(site['vehicle']),
                   public_transport_access=boolean(site['public']), toilets='true',
                   potable_water=boolean(site['water']), showers=boolean(site['showers']),
                   fire_allowed=boolean(site['fire']), pets_allowed=boolean(site.get('pets', False)),
                   wheelchair_accessible=boolean(site['wheelchair']), supported_seasons=site['seasons'],
                   facilities=';'.join(site['facilities']), mandatory_restrictions=';'.join(site['restrictions']),
                   risk_tags=';'.join(site['risk']), revision_date=CHECKED,
                   walk_in_only=boolean(site['walk_in']), quiet_environment='unknown',
                   step_free_path=boolean(site['step_free']),
                   notes=site['access'],
                   demo_attribute_provenance='Static facts checked against the sealed source catalogue; unknown is not false. Reference allowances and product limits are explicitly separated from official facts.')
        if site.get('coordinates'):
            row['latitude'], row['longitude'] = site['coordinates']
        camps.append(row)
        official = url(site)
        visitor = visitor_url(site)
        facts = {
            'name': source_entry(site['name'], 'OFFICIAL', official),
            'subregion': source_entry(site['subregion'], 'OFFICIAL', official),
            'region': source_entry(REGION, 'PRODUCT_LABEL', note='Grouping for Sydney, Blue Mountains and Central Coast; not a local government boundary.'),
            'booking_required': source_entry(True, 'OFFICIAL', official),
            'toilets': source_entry(True, 'OFFICIAL', official),
            'potable_water': source_entry(site['water'], 'OFFICIAL' if site['water'] is not None else 'UNKNOWN', official,
                'Boiling water is listed for Cockatoo Island, but unrestricted potable tap supply is not established in the checked page.' if site['id']=='cockatoo-island' else None),
            'showers': source_entry(site['showers'], 'OFFICIAL', official, 'Outdoor shower only.' if site['id']=='putty-beach' else None),
            'vehicle_access': source_entry(site['vehicle'], 'OFFICIAL', visitor,
                'Direct vehicle camping is the current planning attribute. Nearby carparks plus carrying gear do not count as camping beside a vehicle.'),
            'public_transport_access': source_entry(site['public'], 'OFFICIAL' if site['public'] is not None else 'UNKNOWN', visitor if site['public'] is not None else None),
            'wheelchair_accessible': source_entry(site['wheelchair'], 'OFFICIAL' if site['wheelchair'] is not None else 'UNKNOWN', visitor,
                'Conditional or assisted access is kept unknown rather than represented as independent access.'),
            'step_free_path': source_entry(site['step_free'], 'OFFICIAL' if site['step_free'] is not None else 'UNKNOWN', visitor),
            'fire_allowed': source_entry(site['fire'], 'OFFICIAL' if site['fire'] is not None else 'UNKNOWN', visitor,
                'Permission is conditional on designated facilities and current restrictions. Wood/solid-fuel prohibitions are not a comprehensive ban on gas cooking.'),
            'pets_allowed': source_entry(site.get('pets', False), 'OFFICIAL' if 'slug' in site else 'UNKNOWN', visitor if 'slug' in site else None,
                'Certified assistance animals are an exception to national park pet restrictions.' if 'slug' in site else None),
            'quiet_environment': source_entry(None, 'UNKNOWN', note='Noise rules do not guarantee quiet surroundings.'),
            'max_group_size': source_entry(site.get('capacity', 4),
                'OFFICIAL' if site['id'] in {'little-beach','cockatoo-island'} else 'PRODUCT_LIMIT',
                visitor if site['id'] in {'little-beach','cockatoo-island'} else None,
                'Supported single-site planning group cap, not the maximum occupancy of the real campground. Larger multi-site/group bookings are not priced by this catalogue.'),
            'nightly_fee_aud': source_entry(str(site['fee']), 'REFERENCE_ESTIMATE',
                visitor if site['id']=='cockatoo-island' else None,
                'Whole-group per-night planning allowance, including a reference park-entry/parking allowance where applicable. Not an official tariff, availability result or booking quote.'),
            'supported_seasons': source_entry(['all'], 'PRODUCT_ASSUMPTION', note='Year-round planning catalogue coverage, subject to real booking availability and current alerts; does not certify that dates are bookable.'),
            'facilities': source_entry(site['facilities'], 'OFFICIAL', official),
            'mandatory_restrictions': source_entry(site['restrictions'], 'OFFICIAL', visitor),
            'risk_tags': source_entry(site['risk'], 'PRODUCT_TAGS', visitor,
                'Qualitative planning tags derived from access, water and reception notes; not a measured risk or current emergency alert.'),
            'latitude': source_entry(row['latitude'] if row['latitude']!='unknown' else None,
                'OFFICIAL' if site.get('coordinates') else 'UNKNOWN', visitor if site.get('coordinates') else None),
            'longitude': source_entry(row['longitude'] if row['longitude']!='unknown' else None,
                'OFFICIAL' if site.get('coordinates') else 'UNKNOWN', visitor if site.get('coordinates') else None),
        }
        catalogue[site['id']] = dict(official_name=site['name'], source_urls=[official, visitor], checked_on=CHECKED,
            fields=facts, access_notes=site['access'], static_restrictions=site['restrictions'],
            pricing_notes=('Operator BYO rate checked: Monday-Thursday AUD55/night, Friday-Sunday AUD65/night for up to4; one extra guest costs AUD15/night. Product uses65 as a reference, caps group at4 and does not implement special-event pricing.'
                           if site['id']=='cockatoo-island' else
                           'Official page requires a date-specific availability/booking query for actual camping prices. Catalogue amount is an independently chosen planning estimate; no live booking query was made.'))
    content['data/synthetic_campsites.csv'] = csv_bytes(camps, fields)
    for filename in ('synthetic_profiles.json', 'synthetic_requests.json', 'runtime_requests.json'):
        updated = replacement(json.loads((SOURCE/'data'/filename).read_bytes()))
        text = json.dumps(updated, ensure_ascii=False)
        for original in old_camps:
            replacement_name = next(site['name'] for site in SITES if ID_MAP[original['campsite_id']]==site['id'])
            text = text.replace(original['name'], replacement_name)
        content['data/' + filename] = encode(json.loads(text))
    fields, gear = csv_read(SOURCE / 'data/synthetic_gear_rules.csv')
    for row in gear:
        row['notes'] = 'Planning reference rule. Unknown quantities remain unknown and must be confirmed; thresholds are product assumptions, not official campsite requirements.'
        row['revision_date'] = CHECKED
    content['data/synthetic_gear_rules.csv'] = csv_bytes(gear, fields)
    fields, costs = csv_read(SOURCE / 'data/synthetic_cost_reference.csv')
    for row in costs:
        row['notes'] = 'Planning cost reference; not a current market quote.'
        row['assumption'] = row['assumption'].replace('Synthetic demonstration assumption; not a real-time market price.', 'Reference planning estimate; not a real-time market price.').replace('whole demo trip', 'whole trip')
        row['revision_date'] = CHECKED
        if row['cost_id']=='cost-01':
            row.update(low_aud='35', typical_aud='65', high_aud='95', item_name='Campsite nightly planning allowance',
                assumption='Selected campsite reference allowance for the whole supported group per night. Includes a reference park-entry/parking allowance where applicable. Actual rates and bookings require operator confirmation.')
        if row['cost_id']=='cost-15':
            row.update(low_aud='0', typical_aud='0', high_aud='0',
                assumption='No separate parking charge is added in this reference calculation: the campsite nightly allowance already includes a reference park-entry/parking allowance. Zero here is not a claim that real parking or entry is free.')
    content['data/synthetic_cost_reference.csv'] = csv_bytes(costs, fields)
    old_safety = replacement(json.loads((SOURCE / 'data/runtime_safety_evidence.json').read_bytes()))
    # Weather remains simulated. Remove every old invented closure/fire event;
    # one neutral simulated FIRE/ROAD/RESTRICTION record per period is rebuilt.
    rows = [row for row in old_safety if row['active_kinds']==['WEATHER']]
    periods = json.loads((SOURCE / 'coverage.json').read_bytes())['periods']
    for site in SITES:
        for first, last in periods:
            observed = datetime.combine(date.fromisoformat(first)-timedelta(days=1), time(0), ZoneInfo('Australia/Sydney')).isoformat()
            for kind in ('FIRE', 'ROAD', 'RESTRICTION'):
                empty = dict(summary=None, source_date='unknown', status='MISSING', data_status='MISSING', observed_at=None, valid_from=None, valid_until=None)
                row = dict(safety_case_id=f"trip-{site['id']}-{kind.lower()}-{first}-{last}", campsite_id=site['id'],
                    scenario_date=first, valid_from=first, valid_until=last, weather=deepcopy(empty), fire=deepcopy(empty),
                    road_access={**empty, 'status':'UNKNOWN'}, campsite_restrictions=[], risk_tags=[], mandatory_blockers=[],
                    evidence_facts={}, active_kinds=[kind], published_at=observed,
                    restriction_observed_at=observed if kind=='RESTRICTION' else None, max_age_days=45, origin_case_ids=[], **PROVENANCE)
                if kind=='RESTRICTION':
                    row['campsite_restrictions'] = site['restrictions']
                else:
                    field = 'fire' if kind=='FIRE' else 'road_access'
                    row[field] = dict(summary='No synthetic fire restriction.' if kind=='FIRE' else 'open in synthetic scenario',
                        source_date=PROVENANCE['source_date'], status='AVAILABLE' if kind=='FIRE' else 'OPEN', data_status='AVAILABLE',
                        observed_at=observed, valid_from=first, valid_until=last)
                rows.append(row)
    rows.sort(key=lambda row:row['safety_case_id'])
    content['data/runtime_safety_evidence.json'] = encode(rows)
    content['data/synthetic_safety_scenarios.json'] = encode(rows)
    content['data/source_catalogue.json'] = encode(dict(dataset_version=VERSION, checked_on=CHECKED, region=REGION,
        description='Official static campsite facts with separately identified planning limits, reference costs and simulated dynamic conditions.',
        provenance_policy='Frozen legacy source DTO is retained as SYNTHETIC because the combined input includes generated weather, road and fire scenarios. Official field-level evidence is tracked here and sealed in manifest; this is not a live official data feed.',
        assumptions=dict(dynamic_conditions='Weather, road state and current fire state are simulated inputs, not verified live conditions. Old fictional closures were removed. Check official alerts independently for real travel.',
            prices='Whole-group reference allowances are not operator prices. No booking, ferry fare, availability, traffic or live weather API was queried.',
            capacity='Unless an explicit per-site source is recorded, max_group_size is a conservative product planning cap of4, not a campground occupancy claim.',
            coordinates='Only Lane Cove has explicit decimal GPS in the checked official visitor page. Other legacy fictional coordinates were removed.',
            unknowns='Unknown public transport, accessibility, fire permission or potable supply are not converted into false/true. No guaranteed quietness is inferred from quiet hours.',
            seasons='Catalogue supports year-round trip input, subject to date guards and simulated coverage; this is not a booking availability promise.'),
        campsites=catalogue))
    content['coverage.json'] = encode(dict(dataset_version=VERSION, periods=periods, weather_horizon_days=7, weather_max_age_days=7,
        nonweather_max_age_days=45, selection_policy='trip-evidence-selection-1', campsites=sorted(catalogue), record_count=len(rows),
        kinds=['WEATHER','FIRE','ROAD','RESTRICTION'], retained_restrictions=[],
        coverage_limit='Single-record full-trip coverage; partial intervals are reported, not spliced. Simulated weather must already be published at the registered check date.',
        provenance_note='Independent2.2.0 static Sydney catalogue plus simulated dynamic evidence. Original2.0 and2.1 seals are unchanged.'))
    content['README.md'] = b'''# Sydney & Surrounds catalogue 2.2.0

Official static names, locations, facilities and access notes were checked on
2026-10-23. See data/source_catalogue.json for field-level URLs, unknowns,
product planning caps and reference costs. This mixed catalogue retains frozen
synthetic provenance internally: weather, road and current fire state are
simulation inputs, not live forecasts or official safety checks. Real booking
availability was not queried. Do not use this snapshot as real travel clearance.

The original 2.0.0 and 2.1.0 directories are preserved. IDs intentionally differ
from fictional locations, so historical saved runs retain their original source.
The normal input contains no inherited fictional road closure or total-fire-ban
event. Static wood-fire rules do not establish a comprehensive gas-cooking ban.
Prices are whole-group nightly planning allowances, not per-person official rates.
The separate parking reference is zero to avoid charging the allowance twice;
this does not assert that actual park entry or parking is free.

Use automatic trip evidence selection with no manually forced scenario IDs.
The source catalogue must remain sealed and be retained in daily snapshots.
Reproduce or compare this package with scripts/build_sydney_catalogue.py.
'''
    content['manifest.json'] = encode(dict(dataset_version=VERSION, revision_date=CHECKED, provenance=PROVENANCE,
        evidence_selection_policy='trip-evidence-selection-1', derived_from='synthetic_demo_v2_1/2.1.0',
        catalogue_policy='sydney-static-with-simulated-dynamics-1', catalogue_file='data/source_catalogue.json',
        original_manifest_sha256=hashlib.sha256((SOURCE/'manifest.json').read_bytes()).hexdigest(),
        files_sha256={name:hashlib.sha256(payload).hexdigest() for name,payload in sorted(content.items())}))
    return content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=TARGET)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    content = build()
    target = args.output.resolve()
    if args.check:
        assert all((target/name).read_bytes()==payload for name,payload in content.items()), 'Generated bytes differ'
        print(f'Deterministic package comparison passed; {len(content)} files; no writes.')
        return
    if target.exists():
        parser.error('Output exists; use --check or a new output directory.')
    target.mkdir(parents=True)
    for name, payload in content.items():
        path = target/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(f'Created independent {VERSION} package with10 campsites; {len(content)} files.')


if __name__=='__main__':
    main()
