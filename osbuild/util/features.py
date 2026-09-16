"""OS Features

Shared utility for generating the OS features table (features.json),
which is read by coreos-installer.
"""

import json
import os
import yaml


def write_os_features(tree, *destinations):
    features = json.dumps(get_os_features(tree), indent=2, sort_keys=True) + '\n'
    for dest in destinations:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, 'w', encoding='utf8') as fh:
            fh.write(features)


def get_os_features(tree):
    features = {
        # coreos-installer >= 0.12.0
        'installer-config': True,
        # coreos/fedora-coreos-config@3edd2f28
        'live-initrd-network': True,
        # coreos-installer > 0.26.0
        'initrd-copy-network': True,
    }
    file = os.path.join(tree, 'usr/share/coreos-installer/example-config.yaml')
    with open(file, encoding='utf8') as f:
        example_config_yaml = yaml.safe_load(f)
    features['installer-config-directives'] = {
        k: True for k in example_config_yaml
    }
    return features
