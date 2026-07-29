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
- Never end with a plan-only response. Execute tool calls directly. If any step fails, retry with corrected params and continue.
- Before final answer, verify final state with:
  - `nemo_api(resource="files.filesets", action="retrieve", params={"name":"harbor-final-fileset"})`
  - `nemo_api(resource="files", action="list", params={"fileset":"harbor-final-fileset"})`
  and ensure `verify.txt` appears.

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
