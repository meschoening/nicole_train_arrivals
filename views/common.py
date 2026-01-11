"""Shared UI helpers."""


def get_font_family(config_store):
    config = config_store.load()
    return config.get('font_family', 'Quicksand')
