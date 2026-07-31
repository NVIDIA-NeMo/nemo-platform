# Experimentalist control plane. Harbor and Docker remain host-side.
target "nmp-experimentalist-docker" {
  target     = "runtime"
  context    = "."
  dockerfile = "plugins/nemo-experimentalist/Dockerfile"
  contexts = {
    nmp-python-base = "target:nmp-python-base"
    nmp-workspace   = "target:nmp-workspace"
  }
  cache-to   = maybe_registry_cache_to("nmp-experimentalist")
  cache-from = maybe_registry_cache_from("nmp-experimentalist")
  tags       = sha_and_maybe_latest_tags("nmp-experimentalist")
  output     = image_output()
  platforms  = get_platforms()
}
