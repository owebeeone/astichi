settings = {**astichi_hole(settings_entries), "timeout": 30}

labels = {
    "service": "api",
    **astichi_hole(label_entries),
    **astichi_hole(extra_label_entries),
}

lookup = {
    astichi_hole(primary_key): "primary",
    **astichi_hole(lookup_entries),
}

scoped = {
    **astichi_hole(scoped_entries),
}
