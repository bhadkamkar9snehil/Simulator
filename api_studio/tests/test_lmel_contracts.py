"""Exercise the existing Studio HTTP runtime with the workbook project package."""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PACKAGE = Path(__file__).resolve().parents[1] / 'projects/lmel_sap.json'


def call(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(base.rstrip('/') + path, data=data, headers={'Content-Type': 'application/json'}, method=method)
    try:
        response = urlopen(req, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        return response.code, json.loads(response.read())


def run(base, install):
    package = json.loads(PACKAGE.read_text(encoding='utf-8'))
    if install:
        status, result = call(base, 'POST', '/api/studio/import/project', package)
        assert status == 200 and result['success'], result
        project_id = result['new_project_id']
        status, result = call(base, 'POST', f'/api/studio/projects/{project_id}/activate', {})
        assert status == 200 and result['success'], result
    status, health = call(base, 'GET', '/api/studio/health')
    assert status == 200 and health['success'], health
    project_id = health['active_project_id']
    status, actual = call(base, 'GET', f'/api/studio/endpoints?project_id={project_id}')
    assert status == 200 and len(actual['data']) == len(package['endpoints']) == 21
    for endpoint in package['endpoints']:
        status, body = call(base, endpoint['method'], endpoint['path'], endpoint['request_example'])
        assert status == endpoint['status_code'], (endpoint['name'], status, body)
        assert body == endpoint['response_template'], endpoint['name']
        wrong = 'POST' if endpoint['method'] == 'GET' else 'GET'
        status, _ = call(base, wrong, endpoint['path'], endpoint['request_example'])
        assert status == 404, (endpoint['name'], 'wrong method accepted')
    # Exercise the existing configured failure path, then restore exact endpoint settings.
    sales = next(e for e in actual['data'] if e['name'] == 'Sales Order')
    try:
        failed = dict(sales, failure_rate=1)
        status, result = call(base, 'POST', '/api/studio/endpoints', failed)
        assert status == 200 and result['success']
        status, body = call(base, 'GET', sales['path'], {})
        assert status == 500 and body['error']['message']['value'] == 'Configured simulator failure'
    finally:
        status, result = call(base, 'POST', '/api/studio/endpoints', sales)
        assert status == 200 and result['success'], 'Failure fixture restoration failed'
    print(f'PASS: 21 native Studio HTTP routes, 21 wrong-method refusals, configured failure/restoration; active project {project_id}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:5050')
    parser.add_argument('--install', action='store_true', help='Import and activate the package; existing project data is retained')
    args = parser.parse_args()
    run(args.base_url, args.install)
