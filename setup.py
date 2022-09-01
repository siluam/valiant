# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['titan']

package_data = \
{'': ['*']}

install_requires = \
['addict', 'click']

setup_kwargs = {
    'name': 'titan',
    'version': '1.0.0.0',
    'description': "Fine. I'll do it myself.",
    'long_description': None,
    'author': 'sylvorg',
    'author_email': 'jeet.ray@syvl.org',
    'maintainer': None,
    'maintainer_email': None,
    'url': None,
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'python_requires': '>=3.10,<4.0',
}


setup(**setup_kwargs)

