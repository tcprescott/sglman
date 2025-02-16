# this centralizes the configuration of the application

import yaml

app_config: dict = yaml.load(open('config.yaml'), Loader=yaml.SafeLoader)

DEBUG = app_config.get('debug', False)
DATABASE = app_config['database']