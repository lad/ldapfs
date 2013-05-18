
"""Config File Support."""

import os
import ConfigParser
from .exceptions import ConfigError


# pylint: disable-msg=R0903
class ConfigFile(object):
    """ConfigParser wrapper - independent of ldapfs"""
    def __init__(self, config_path):
        self.config_path = config_path
        self.parser = ConfigParser.SafeConfigParser()
        if not self.parser.read(config_path):
            raise ConfigError('Error accessing config file: {}'.format(config_path))

    def get_sections(self):
        return self.parser.sections()

    def get(self, section, required_config=None, parse_config=None):
        """Parse a config file section and return a dict of its contents."""
        try:
            config = dict([(key, value.strip("'\" ")) for key, value in self.parser.items(section)])

            for key in required_config or []:
                if not config.get(key):
                    raise ConfigError('Error in config file "{}". Missing key "{}"'.format(self.config_path, key))

            for key, parse_fn in parse_config or []:
                if parse_fn:
                    config[key] = parse_fn(config[key])
        except ConfigError as ex:
            raise ConfigError('Error in config key "{}". {}'.format(key, ex))
        except ConfigParser.Error as ex:
            raise ConfigError('Error in config file: {}'.format(ex))

        return config

    @staticmethod
    def parse_int(intstr):
        """Return a valid int for the given string.

        Raises ConfigError if not a valid int."""
        try:
            return int(intstr)
        except ValueError:
            raise ConfigError('Failed to convert "{}" to an integer value'.format(intstr))

    @staticmethod
    def parse_bool(boolstr):
        """Return a valid boolean for the given string.

        ConfigError is raised on error."""
        bool_lower = boolstr.lower()
        if bool_lower in ['true', '1']:
            return True
        elif bool_lower in ['false', '0']:
            return False
        else:
            raise ConfigError('Failed to convert "{}" to a boolean value'.format(boolstr))

    @staticmethod
    def parse_dir(dirname):
        if os.path.isdir(dirname):
            return dirname
        else:
            raise ConfigError('Directory "{}" not found'.format(dirname))

    @staticmethod
    def parse_log_levels(log_str):
        """Split up the log level string."""
        dct = {}
        try:
            for module_level in log_str.strip().split(','):
                module, level = module_level.strip().split(':')
                dct[module.strip()] = level.strip().upper()
        except ValueError:
            raise ConfigError('Invalid log levels: "{}"'.format(log_str))

        if 'root' not in dct:
            raise ConfigError('No entry for root logger in: "{}"'.format(log_str))

        return dct
