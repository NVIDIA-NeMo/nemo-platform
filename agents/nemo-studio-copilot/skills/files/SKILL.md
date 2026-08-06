---
name: files
description: platform fileset and file CRUD playbook with the exact `nemo_api(resource='files'|'files.filesets', ...)` sequence used by harbor benchmarks. Use when the task involves filesets, file uploads/downloads, `verify.txt`, `harbor-test-fileset`, or `harbor-final-fileset`.
---
File tasks

- Use `nemo_api` for small file content uploads:
  - resource: `files`
  - action: `upload_content`
  - params: `{"content": "text", "remote_path": "verify.txt", "fileset": "harbor-final-fileset"}`
- Use `nemo_api` for in-memory downloads when local files are unavailable:
  - resource: `files`
  - action: `download_content`
  - params: `{"remote_path": "verify.txt", "fileset": "harbor-final-fileset"}`
- Use resource `files.filesets` for fileset create/list/retrieve/delete operations.
- Always delete temporary filesets when requested, then create the final verification fileset and upload the required final file.
- Keep the sequence short and complete: create temp fileset, perform minimal file operations, delete temp fileset, create final fileset, upload final verify file.
- Never end with a plan-only response. Execute tool calls directly.
- For `create`, `upload_content`, and `delete`, treat a `nemo_api` error as an
  unknown commit state unless it explicitly confirms a pre-commit validation
  failure. Correct a confirmed pre-commit validation failure and retry once.
- Before retrying any other mutation error, read back the operation's stable
  identity (fileset name for create/delete; fileset plus remote path for
  upload/delete) to determine whether the intended state already exists, or use
  a supported idempotency key on the original request. Retry once only when the
  read-back confirms the mutation did not commit or the idempotency key makes
  replay safe. If commit state remains unknown, do not retry; stop and report it.
- If a safe retry also fails, stop the sequence and return the error or request
  one focused clarification; do not continue to later steps after an
  unrecoverable failure.
- Before final answer, verify final state with:
  - `nemo_api(resource="files.filesets", action="retrieve", params={"name":"harbor-final-fileset"})`
  - `nemo_api(resource="files", action="list", params={"fileset":"harbor-final-fileset"})`
  - `nemo_api(resource="files", action="download_content", params={"remote_path":"verify.txt","fileset":"harbor-final-fileset"})`
  Ensure `verify.txt` appears, then confirm its downloaded content equals the
  required content (`harbor-verification-content` in the benchmark flow). If
  the service instead provides a trusted checksum or version, compare it with
  the expected checksum or version.

Fileset CRUD benchmark playbook (prefer this exact flow):

1) `nemo_api(resource="files.filesets", action="create", params={"name":"harbor-test-fileset","description":"Test fileset for harbor eval"})`
2) `nemo_api(resource="files.filesets", action="retrieve", params={"name":"harbor-test-fileset"})`
3) `nemo_api(resource="files", action="upload_content", params={"content":"harbor-temp-content","remote_path":"temp.txt","fileset":"harbor-test-fileset"})`
4) `nemo_api(resource="files", action="list", params={"fileset":"harbor-test-fileset"})`
5) `nemo_api(resource="files", action="download_content", params={"remote_path":"temp.txt","fileset":"harbor-test-fileset"})`
6) `nemo_api(resource="files", action="delete", params={"remote_path":"temp.txt","fileset":"harbor-test-fileset"})`
7) `nemo_api(resource="files.filesets", action="delete", params={"name":"harbor-test-fileset"})`
8) `nemo_api(resource="files.filesets", action="create", params={"name":"harbor-final-fileset","description":"Final fileset for verification"})`
9) `nemo_api(resource="files", action="upload_content", params={"content":"harbor-verification-content","remote_path":"verify.txt","fileset":"harbor-final-fileset"})`
