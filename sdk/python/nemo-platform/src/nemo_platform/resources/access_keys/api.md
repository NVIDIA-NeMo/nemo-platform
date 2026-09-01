<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# AccessKeys

Types:

```python
from nemo_platform.types.access_keys import (
    AccessKeyCreateRequest,
    AccessKeyCreateResponse,
    AccessKeyErrorResponse,
    AccessKeyListResponse,
    AccessKeyMetadataResponse,
    AccessKeyNotImplementedErrorResponse,
    AccessKeyRevokeResponse,
    AccessKeyRotateResponse,
    AccessKeyStatusChangeResponse,
)
```

Methods:

- <code title="post /apis/auth/v2/access-keys">client.access_keys.<a href="./src/nemo_platform/resources/access_keys/access_keys.py">create</a>(\*\*<a href="src/nemo_platform/types/access_keys/access_key_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/access_keys/access_key_create_response.py">AccessKeyCreateResponse</a></code>
- <code title="get /apis/auth/v2/access-keys">client.access_keys.<a href="./src/nemo_platform/resources/access_keys/access_keys.py">list</a>(\*\*<a href="src/nemo_platform/types/access_keys/access_key_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/access_keys/access_key_list_response.py">AccessKeyListResponse</a></code>
- <code title="delete /apis/auth/v2/access-keys/{jti}">client.access_keys.<a href="./src/nemo_platform/resources/access_keys/access_keys.py">delete</a>(jti) -> <a href="./src/nemo_platform/types/access_keys/access_key_revoke_response.py">AccessKeyRevokeResponse</a></code>
- <code title="post /apis/auth/v2/access-keys/{jti}/rotate">client.access_keys.<a href="./src/nemo_platform/resources/access_keys/access_keys.py">rotate</a>(jti) -> <a href="./src/nemo_platform/types/access_keys/access_key_rotate_response.py">AccessKeyRotateResponse</a></code>
- <code title="post /apis/auth/v2/access-keys/{jti}/suspend">client.access_keys.<a href="./src/nemo_platform/resources/access_keys/access_keys.py">suspend</a>(jti) -> <a href="./src/nemo_platform/types/access_keys/access_key_status_change_response.py">AccessKeyStatusChangeResponse</a></code>
- <code title="post /apis/auth/v2/access-keys/{jti}/unsuspend">client.access_keys.<a href="./src/nemo_platform/resources/access_keys/access_keys.py">unsuspend</a>(jti) -> <a href="./src/nemo_platform/types/access_keys/access_key_status_change_response.py">AccessKeyStatusChangeResponse</a></code>
