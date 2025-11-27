import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studiozens.settings')
django.setup()

from django.urls import resolve
from django.urls.exceptions import Resolver404

try:
    match = resolve('/api/v1/analytics/kpis/export/')
    print('Resolved:', match)
    print('View:', match.func)
except Resolver404 as e:
    print('404:', e)

# List all analytics URLs
from django.urls import get_resolver
resolver = get_resolver()
print('\nAll analytics URLs:')
for pattern in resolver.url_patterns:
    if 'analytics' in str(pattern.pattern):
        print(f'  {pattern.pattern}')
        if hasattr(pattern, 'url_patterns'):
            for sub in pattern.url_patterns:
                print(f'    {sub.pattern}')
