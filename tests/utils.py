import os
from tempfile import NamedTemporaryFile
import yaml


def generate_test_npat_file(name, min_node_count):
    """
    Create npat manifest for testing.
    """
    template_path = os.path.join(os.path.dirname(__file__), 'npat_template.yaml')
    tmpl = open(template_path, 'rt').read()
    text = tmpl.format(name=name, minimumNodeCount=min_node_count)
    data = yaml.safe_load(text)
    with NamedTemporaryFile(prefix='npat', suffix='.yaml', delete=False) as tf:
        npat_file = tf.name
    with open(npat_file, 'w') as f:
        yaml.dump(data, f)
    return npat_file
