"""Shared UI helpers."""


def get_font_family(config_store):
    return config_store.get_str('font_family', 'Quicksand')
