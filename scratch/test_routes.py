import sys
import os

sys.path.insert(0, os.path.abspath('.'))

from admin.app import (
    citizen_portal,
    chatbot_portal,
    api_get_schemes,
    api_get_scheme_detail,
    api_get_departments,
    api_get_stats
)
from scraper.database import get_db

print("1. Testing citizen_portal():")
res_index = citizen_portal()
print(f"   Status: {res_index.status_code if hasattr(res_index, 'status_code') else 'FileResponse'}, Path: {getattr(res_index, 'path', 'N/A')}")
assert os.path.exists(getattr(res_index, 'path', 'index.html'))

print("\n2. Testing chatbot_portal():")
res_chat = chatbot_portal()
print(f"   Status: {res_chat.status_code if hasattr(res_chat, 'status_code') else 'FileResponse'}, Path: {getattr(res_chat, 'path', 'N/A')}")
assert os.path.exists(getattr(res_chat, 'path', 'chatbot.html'))

print("\n3. Testing api_get_schemes():")
schemes_resp = api_get_schemes()
schemes_list = schemes_resp.get('schemes') or []
print(f"   Status: {schemes_resp.get('status')}, Total Schemes: {schemes_resp.get('total')}, Count: {len(schemes_list)}")
assert schemes_resp.get('status') == 'SUCCESS'
assert schemes_resp.get('total') > 0
assert len(schemes_list) > 0

print("\n4. Testing api_get_scheme_detail(2):")
detail_resp = api_get_scheme_detail(2)
scheme_2 = detail_resp.get('scheme', {})
print(f"   Scheme 2: {scheme_2.get('scheme_name')} ({scheme_2.get('department')})")
assert "Gruha Lakshmi" in scheme_2.get('scheme_name')

print("\n5. Testing api_get_departments():")
dept_resp = api_get_departments()
dept_list = dept_resp.get('departments') if isinstance(dept_resp, dict) else dept_resp
print(f"   Returned {len(dept_list)} departments: {dept_list[:3]}")
assert len(dept_list) > 0

print("\n6. Testing api_get_stats(db):")
db_session = next(get_db())
stats = api_get_stats(db_session)
print(f"   Stats: {stats}")

print("\n==========================================")
print("ALL ROUTE & API CHECKS PASSED PERFECTLY!")
print("==========================================")
