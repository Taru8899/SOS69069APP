"""Backward-compatible wrappers → local_store (TRUTH bucket). """
import local_store as ls

CACHE_NAME = ls.FILE_TRUTH

def load_events(user_data_dir):
    return ls.truth_load(user_data_dir)

def save_events(user_data_dir, events, source="network"):
    return ls.truth_save(user_data_dir, events, source)

def merge_events(existing, incoming, max_events=None):
    return ls.merge_events(existing, incoming, max_events or ls.CAP_TRUTH)

def cache_age_seconds(user_data_dir):
    return ls.cache_age_seconds(user_data_dir, ls.FILE_TRUTH)
