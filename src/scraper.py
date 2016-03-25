import requests
import io
from bs4 import BeautifulSoup
import sys
import re
import geocoder
import pprint
import json


INSPECTION_DOMAIN = 'http://info.kingcounty.gov'
INSPECTION_PATH = '/health/ehs/foodsafety/inspections/Results.aspx'
INSPECTION_PARAMS = {
    'Output': 'W',
    'Business_Name': '',
    'Business_Address': '',
    'Longitude': '',
    'Latitude': '',
    'City': '',
    'Zip_Code': '',
    'Inspection_Type': 'All',
    'Inspection_Start': '',
    'Inspection_End': '',
    'Inspection_Closed_Business': 'A',
    'Violation_Points': '',
    'Violation_Red_Points': '',
    'Violation_Descr': '',
    'Fuzzy_Search': 'N',
    'Sort': 'H'
}


def get_inspection_page(**kwargs):
    url = INSPECTION_DOMAIN + INSPECTION_PATH
    params = INSPECTION_PARAMS.copy()
    for key, val in kwargs.items():
        if key in INSPECTION_PARAMS:
            params[key] = val
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.content, resp.encoding


def load_inspection_page(page):
    page = io.open(page, encoding='utf-8', mode='r')
    text = page.read()
    page.close()
    return text, 'utf-8'


def parse_source(html, encoding='utf-8'):
    parsed = BeautifulSoup(html, 'html5lib')
    return parsed


def extract_data_listings(html):
    id_finder = re.compile(r'PR[\d]+~')
    return html.find_all('div', id=id_finder)


def has_two_tds(elem):
    is_tr = elem.name == 'tr'
    td_children = elem.find_all('td', recursive=False)
    has_two = len(td_children) == 2
    return is_tr and has_two


def clean_data(td):
    data = td.string
    try:
        return data.strip(" \n:-")
    except AttributeError:
        return u""


def extract_restaurant_metadata(elem):
    metadata_rows = elem.find('tbody').find_all(
        has_two_tds, recursive=False
    )
    rdata = {}
    current_label = ''
    for row in metadata_rows:
        key_cell, val_cell = row.find_all('td', recursive=False)
        new_label = clean_data(key_cell)
        current_label = new_label if new_label else current_label
        rdata.setdefault(current_label, []).append(clean_data(val_cell))
    return rdata


def is_inspection_row(elem):
    is_tr = elem.name == 'tr'
    if not is_tr:
        return False
    td_children = elem.find_all('td', recursive=False)
    has_four = len(td_children) == 4
    this_text = clean_data(td_children[0]).lower()
    contains_word = 'inspection' in this_text
    does_not_start = not this_text.startswith('inspection')
    return is_tr and has_four and contains_word and does_not_start


def extract_score_data(elem):
    inspection_rows = elem.find_all(is_inspection_row)
    samples = len(inspection_rows)
    total = high_score = average = 0
    for row in inspection_rows:
        strval = clean_data(row.find_all('td')[2])
        try:
            intval = int(strval)
        except (ValueError, TypeError):
            samples -= 1
        else:
            total += intval
            high_score = intval if intval > high_score else high_score
    if samples:
        average = total/float(samples)
    data = {
        u'Average Score': float("{0:.2f}".format(average)),
        u'High Score': high_score,
        u'Total Inspections': samples
    }
    return data


def generate_results(test=False, limit=4):
    kwargs = {
        'Inspection_Start': '2/1/2013',
        'Inspection_End': '2/1/2015',
        'Zip_Code': '98109',
    }
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        html, encoding = load_inspection_page('inspection_page.html')
    else:
        html, encoding = get_inspection_page(**kwargs)
    doc = parse_source(html, encoding)
    listings = extract_data_listings(doc)
    for listing in listings[:limit]:
        metadata = extract_restaurant_metadata(listing)
        score_data = extract_score_data(listing)
        for key in score_data:
            metadata[key] = score_data[key]
        yield metadata


def get_geojson(result):
    address = " ".join(result.get('Address', ''))
    if not address:
        return None
    geo = geocoder.google(address).geojson
    data = {}
    keepers = ['Business Name', 'Average Score', 'Total Inspections',
               'High Score', 'Address']
    for key, val in result.items():
        if key not in keepers:
            continue
        if isinstance(key, list):
            val = ' '.join(val)
        data[key] = val
    new_address = geo['properties'].get('address')
    if new_address:
        data['Address'] = new_address
    geo['properties'] = data
    return geo

if __name__ == '__main__':
    test = len(sys.argv) > 1 and sys.argv[1] == 'test'
    complete_result = {'type': 'FeatureCollection', 'features': []}
    for result in generate_results(test):
        final_result = get_geojson(result)
        pprint.pprint(final_result)
        complete_result['features'].append(final_result)
    with open('my_map.json', 'w') as fh:
        json.dump(complete_result, fh)
