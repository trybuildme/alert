MODULE_REGISTRY = {}

def get_module_info(name):
    return MODULE_REGISTRY.get(name)

def list_modules():
    return list(MODULE_REGISTRY.values())
