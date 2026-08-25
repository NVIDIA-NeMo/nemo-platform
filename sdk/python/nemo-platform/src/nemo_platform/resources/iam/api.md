# Iam

## RoleBindings

Types:

```python
from nemo_platform.types.iam import (
    DateRangeFilter,
    RoleBinding,
    RoleBindingFilter,
    RoleBindingParam,
    RoleBindingsPage,
)
```

Methods:

- <code title="post /apis/auth/v2/iam/role-bindings">client.iam.role_bindings.<a href="./src/nemo_platform/resources/iam/role_bindings.py">create</a>(\*\*<a href="src/nemo_platform/types/iam/role_binding_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/iam/role_binding.py">RoleBinding</a></code>
- <code title="get /apis/auth/v2/iam/role-bindings/{name}">client.iam.role_bindings.<a href="./src/nemo_platform/resources/iam/role_bindings.py">retrieve</a>(name) -> <a href="./src/nemo_platform/types/iam/role_binding.py">RoleBinding</a></code>
- <code title="get /apis/auth/v2/iam/role-bindings">client.iam.role_bindings.<a href="./src/nemo_platform/resources/iam/role_bindings.py">list</a>(\*\*<a href="src/nemo_platform/types/iam/role_binding_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/iam/role_binding.py">SyncDefaultPagination[RoleBinding]</a></code>
- <code title="delete /apis/auth/v2/iam/role-bindings/{name}">client.iam.role_bindings.<a href="./src/nemo_platform/resources/iam/role_bindings.py">delete</a>(name, \*\*<a href="src/nemo_platform/types/iam/role_binding_delete_params.py">params</a>) -> <a href="./src/nemo_platform/types/shared/delete_response.py">DeleteResponse</a></code>
