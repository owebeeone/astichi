# astichi-snippet: {"bind": {"module_path": "pkg.mod"}}

astichi_bind_external(module_path)
astichi_pyimport(module=astichi_ref(external=module_path), names=(thing,))
value = thing()
